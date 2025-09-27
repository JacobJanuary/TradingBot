"""
Position Manager - Core trading logic
Coordinates between exchange, database, and protection systems
"""
import asyncio
import logging
from typing import Dict, Optional, List
from decimal import Decimal
from dataclasses import dataclass
from datetime import datetime

from config.settings import TradingConfig
from database.repository import Repository as TradingRepository
from protection.trailing_stop import SmartTrailingStopManager
from websocket.event_router import EventRouter
from core.exchange_manager import ExchangeManager

logger = logging.getLogger(__name__)


@dataclass
class PositionRequest:
    """Request to open new position"""
    signal_id: int
    symbol: str
    exchange: str
    side: str  # 'BUY' or 'SELL'
    entry_price: float

    # Optional overrides
    position_size_usd: Optional[float] = None
    stop_loss_percent: Optional[float] = None
    take_profit_percent: Optional[float] = None


@dataclass
class PositionState:
    """Current position state"""
    id: int
    symbol: str
    exchange: str
    side: str  # 'long' or 'short'
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_percent: float

    has_stop_loss: bool = False
    stop_loss_price: Optional[float] = None

    has_trailing_stop: bool = False
    trailing_activated: bool = False

    opened_at: datetime = None
    age_hours: float = 0


class PositionManager:
    """
    Central position management system
    Handles opening, monitoring, and closing positions
    """

    def __init__(self,
                 config: TradingConfig,
                 exchanges: Dict[str, ExchangeManager],
                 repository: TradingRepository,
                 event_router: EventRouter):
        """Initialize position manager"""
        self.config = config
        self.exchanges = exchanges
        self.repository = repository
        self.event_router = event_router

        # Trailing stop manager for each exchange
        self.trailing_managers = {
            name: SmartTrailingStopManager(exchange)
            for name, exchange in exchanges.items()
        }

        # Active positions tracking
        self.positions: Dict[str, PositionState] = {}  # symbol -> position

        # Position locks
        self.position_locks: set = set()

        # Risk management
        self.total_exposure = Decimal('0')
        self.position_count = 0

        # Statistics
        self.stats = {
            'positions_opened': 0,
            'positions_closed': 0,
            'total_pnl': Decimal('0'),
            'win_count': 0,
            'loss_count': 0
        }

        # Register WebSocket event handlers
        self._register_event_handlers()

        logger.info("PositionManager initialized")

    def _register_event_handlers(self):
        """Register handlers for WebSocket events"""

        @self.event_router.on('position.update')
        async def handle_position_update(data: Dict):
            await self._on_position_update(data)

        @self.event_router.on('order.filled')
        async def handle_order_filled(data: Dict):
            await self._on_order_filled(data)

        @self.event_router.on('stop_loss.triggered')
        async def handle_stop_loss(data: Dict):
            await self._on_stop_loss_triggered(data)

    async def open_position(self, request: PositionRequest) -> Optional[PositionState]:
        """
        Open new position with complete workflow:
        1. Validate request
        2. Check risk limits
        3. Calculate position size
        4. Execute market order
        5. Set stop loss
        6. Initialize trailing stop
        7. Save to database
        """

        symbol = request.symbol
        exchange_name = request.exchange.lower()

        # Acquire position lock
        lock_key = f"{exchange_name}_{symbol}"
        if lock_key in self.position_locks:
            logger.warning(f"Position already being processed for {symbol}")
            return None

        self.position_locks.add(lock_key)

        try:
            # 1. Get exchange
            exchange = self.exchanges.get(exchange_name)
            if not exchange:
                logger.error(f"Exchange {exchange_name} not available")
                return None

            # 2. Check if position already exists
            if await self._position_exists(symbol, exchange_name):
                logger.warning(f"Position already exists for {symbol} on {exchange_name}")
                return None

            # 3. Validate risk limits
            if not await self._validate_risk_limits(request):
                logger.warning(f"Risk limits exceeded for {symbol}")
                return None

            # 4. Calculate position size
            position_size_usd = request.position_size_usd or self.config.position_size_usd
            quantity = await self._calculate_position_size(
                exchange, symbol, request.entry_price, position_size_usd
            )

            if not quantity:
                logger.error(f"Failed to calculate position size for {symbol}")
                return None

            # 5. Validate spread
            if not await self._validate_spread(exchange, symbol):
                logger.warning(f"Spread too wide for {symbol}")
                return None

            # 6. Execute market order
            logger.info(f"Opening position: {symbol} {request.side} {quantity:.6f}")

            # Convert side: BUY -> buy, SELL -> sell
            order_side = request.side.lower()

            order = await exchange.create_market_order(symbol, order_side, quantity)

            if not order or order.status != 'closed':
                logger.error(f"Failed to open position for {symbol}")
                return None

            # 7. Create position state
            position = PositionState(
                id=None,  # Will be set after DB insert
                symbol=symbol,
                exchange=exchange_name,
                side='long' if request.side == 'BUY' else 'short',
                quantity=order.filled,
                entry_price=order.price,
                current_price=order.price,
                unrealized_pnl=0,
                unrealized_pnl_percent=0,
                opened_at=datetime.now()
            )

            # 8. Save to database
            trade_id = await self.repository.create_trade({
                'signal_id': request.signal_id,
                'symbol': symbol,
                'exchange': exchange_name,
                'side': order_side,
                'quantity': order.amount,
                'price': order.price,
                'executed_qty': order.filled,
                'average_price': order.price,
                'order_id': order.id,
                'status': 'FILLED'
            })

            position_id = await self.repository.create_position({
                'trade_id': trade_id,
                'symbol': symbol,
                'exchange': exchange_name,
                'side': position.side,
                'quantity': position.quantity,
                'entry_price': position.entry_price
            })

            position.id = position_id

            # 9. Set stop loss
            stop_loss_percent = request.stop_loss_percent or self.config.stop_loss_percent
            stop_loss_price = await self._calculate_stop_loss(
                position.entry_price, position.side, stop_loss_percent
            )

            if await self._set_stop_loss(exchange, position, stop_loss_price):
                position.has_stop_loss = True
                position.stop_loss_price = stop_loss_price

                await self.repository.update_position_stop_loss(
                    position_id, stop_loss_price, ""
                )

            # 10. Initialize trailing stop
            trailing_manager = self.trailing_managers.get(exchange_name)
            if trailing_manager:
                await trailing_manager.create_trailing_stop(
                    symbol=symbol,
                    side=position.side,
                    entry_price=position.entry_price,
                    quantity=position.quantity,
                    initial_stop=stop_loss_price
                )
                position.has_trailing_stop = True

            # 11. Update internal tracking
            self.positions[symbol] = position
            self.position_count += 1
            self.total_exposure += Decimal(str(position.quantity * position.entry_price))
            self.stats['positions_opened'] += 1

            logger.info(
                f"✅ Position opened: {symbol} {position.side} "
                f"{position.quantity:.6f} @ ${position.entry_price:.4f}"
            )

            return position

        except Exception as e:
            logger.error(f"Error opening position for {symbol}: {e}", exc_info=True)
            return None

        finally:
            self.position_locks.discard(lock_key)

    async def _position_exists(self, symbol: str, exchange: str) -> bool:
        """Check if position already exists"""
        # Check local tracking
        if symbol in self.positions:
            return True

        # Check database
        db_position = await self.repository.get_open_position(symbol, exchange)
        if db_position:
            return True

        # Check exchange
        exchange_obj = self.exchanges.get(exchange)
        if exchange_obj:
            positions = await exchange_obj.fetch_positions([symbol])
            if positions and positions[0]['contracts'] > 0:
                return True

        return False

    async def _validate_risk_limits(self, request: PositionRequest) -> bool:
        """Validate risk management rules"""

        # Check max positions
        if self.position_count >= self.config.max_positions:
            logger.warning(f"Max positions reached: {self.position_count}/{self.config.max_positions}")
            return False

        # Check max exposure
        position_size_usd = request.position_size_usd or self.config.position_size_usd
        new_exposure = self.total_exposure + Decimal(str(position_size_usd))

        if new_exposure > self.config.max_exposure_usd:
            logger.warning(
                f"Max exposure would be exceeded: "
                f"${new_exposure:.2f} > ${self.config.max_exposure_usd:.2f}"
            )
            return False

        return True

    async def _calculate_position_size(self,
                                       exchange: ExchangeManager,
                                       symbol: str,
                                       price: float,
                                       size_usd: float) -> Optional[float]:
        """Calculate position size with exchange constraints"""

        # Basic calculation
        quantity = size_usd / price

        # Apply exchange precision
        formatted_qty = exchange.amount_to_precision(symbol, quantity)

        # Check minimum
        min_amount = exchange.get_min_amount(symbol)
        if formatted_qty < min_amount:
            logger.warning(f"Quantity {formatted_qty} below minimum {min_amount} for {symbol}")
            return None

        return formatted_qty

    async def _validate_spread(self, exchange: ExchangeManager, symbol: str) -> bool:
        """Validate bid-ask spread"""

        ticker = await exchange.fetch_ticker(symbol)
        if not ticker:
            return False

        bid = ticker.get('bid')
        ask = ticker.get('ask')

        if not bid or not ask or bid <= 0 or ask <= 0:
            return False

        spread_percent = ((ask - bid) / bid) * 100
        max_spread = float(self.config.max_spread_percent)

        if spread_percent > max_spread:
            logger.warning(f"Spread {spread_percent:.2f}% exceeds max {max_spread}%")
            return False

        return True

    async def _calculate_stop_loss(self, entry_price: float, side: str, percent: float) -> float:
        """Calculate stop loss price"""

        if side == 'long':
            return entry_price * (1 - percent / 100)
        else:
            return entry_price * (1 + percent / 100)

    async def _set_stop_loss(self,
                             exchange: ExchangeManager,
                             position: PositionState,
                             stop_price: float) -> bool:
        """Set stop loss order"""

        try:
            # Determine order side (opposite of position)
            order_side = 'sell' if position.side == 'long' else 'buy'

            order = await exchange.create_stop_loss_order(
                symbol=position.symbol,
                side=order_side,
                amount=position.quantity,
                stop_price=stop_price
            )

            if order:
                logger.info(f"Stop loss set for {position.symbol} at ${stop_price:.4f}")
                return True

        except Exception as e:
            logger.error(f"Failed to set stop loss for {position.symbol}: {e}")

        return False

    async def _on_position_update(self, data: Dict):
        """Handle position update from WebSocket"""

        symbol = data.get('symbol')
        if not symbol or symbol not in self.positions:
            return

        position = self.positions[symbol]

        # Update position state
        position.current_price = data.get('mark_price', position.current_price)
        position.unrealized_pnl = data.get('unrealized_pnl', 0)

        # Calculate PnL percent
        if position.entry_price > 0:
            if position.side == 'long':
                position.unrealized_pnl_percent = (
                        (position.current_price - position.entry_price) / position.entry_price * 100
                )
            else:
                position.unrealized_pnl_percent = (
                        (position.entry_price - position.current_price) / position.entry_price * 100
                )

        # Update trailing stop
        trailing_manager = self.trailing_managers.get(position.exchange)
        if trailing_manager and position.has_trailing_stop:
            update_result = await trailing_manager.update_price(symbol, position.current_price)

            if update_result and update_result.get('action') == 'activated':
                position.trailing_activated = True
                logger.info(f"Trailing stop activated for {symbol}")

        # Update database
        await self.repository.update_position_from_websocket({
            'symbol': symbol,
            'exchange': position.exchange,
            'current_price': position.current_price,
            'mark_price': position.current_price,
            'unrealized_pnl': position.unrealized_pnl,
            'unrealized_pnl_percent': position.unrealized_pnl_percent
        })

    async def _on_order_filled(self, data: Dict):
        """Handle order filled event"""

        order_type = data.get('type', '').lower()
        symbol = data.get('symbol')

        # Check if it's a closing order
        if order_type in ['stop_market', 'stop', 'take_profit_market']:
            if symbol in self.positions:
                await self.close_position(symbol, data.get('exit_reason', order_type))

    async def _on_stop_loss_triggered(self, data: Dict):
        """Handle stop loss triggered event"""

        symbol = data.get('symbol')
        if symbol in self.positions:
            logger.warning(f"⚠️ Stop loss triggered for {symbol}")
            await self.close_position(symbol, 'stop_loss')

    async def close_position(self, symbol: str, reason: str = 'manual'):
        """Close position and update records"""

        if symbol not in self.positions:
            logger.warning(f"No position found for {symbol}")
            return

        position = self.positions[symbol]
        exchange = self.exchanges.get(position.exchange)

        if not exchange:
            logger.error(f"Exchange {position.exchange} not available")
            return

        try:
            # Close position on exchange
            success = await exchange.close_position(symbol)

            if success:
                # Calculate realized PnL
                exit_price = position.current_price

                if position.side == 'long':
                    realized_pnl = (exit_price - position.entry_price) * position.quantity
                    realized_pnl_percent = (exit_price - position.entry_price) / position.entry_price * 100
                else:
                    realized_pnl = (position.entry_price - exit_price) * position.quantity
                    realized_pnl_percent = (position.entry_price - exit_price) / position.entry_price * 100

                # Update database
                await self.repository.close_position(position.id, {
                    'exit_price': exit_price,
                    'exit_quantity': position.quantity,
                    'realized_pnl': realized_pnl,
                    'realized_pnl_percent': realized_pnl_percent,
                    'exit_reason': reason
                })

                # Update statistics
                self.stats['positions_closed'] += 1
                self.stats['total_pnl'] += Decimal(str(realized_pnl))

                if realized_pnl > 0:
                    self.stats['win_count'] += 1
                else:
                    self.stats['loss_count'] += 1

                # Clean up tracking
                del self.positions[symbol]
                self.position_count -= 1
                self.total_exposure -= Decimal(str(position.quantity * position.entry_price))

                # Clean up trailing stop
                trailing_manager = self.trailing_managers.get(position.exchange)
                if trailing_manager:
                    await trailing_manager.on_position_closed(symbol, realized_pnl)

                logger.info(
                    f"Position closed: {symbol} {reason} "
                    f"PnL: ${realized_pnl:.2f} ({realized_pnl_percent:.2f}%)"
                )

        except Exception as e:
            logger.error(f"Error closing position {symbol}: {e}", exc_info=True)

    def get_statistics(self) -> Dict:
        """Get current statistics"""

        win_rate = 0
        if self.stats['win_count'] + self.stats['loss_count'] > 0:
            win_rate = self.stats['win_count'] / (self.stats['win_count'] + self.stats['loss_count']) * 100

        return {
            'open_positions': self.position_count,
            'total_exposure': float(self.total_exposure),
            'positions_opened': self.stats['positions_opened'],
            'positions_closed': self.stats['positions_closed'],
            'total_pnl': float(self.stats['total_pnl']),
            'win_rate': win_rate,
            'wins': self.stats['win_count'],
            'losses': self.stats['loss_count']
        }