"""
Advanced Stop Loss Manager with multiple strategies and smart order management
"""

import asyncio
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_DOWN
from enum import Enum
from dataclasses import dataclass
import numpy as np
from loguru import logger

from core.exchange_manager import ExchangeManager
from database.models import Position, Order, StopLossConfig
from database.repository import Repository
from utils.decorators import async_retry, rate_limit


class StopLossType(Enum):
    """Stop loss order types"""
    FIXED = "fixed"                    # Fixed price stop
    PERCENTAGE = "percentage"          # Percentage from entry
    TRAILING = "trailing"              # Trailing stop
    SMART_TRAILING = "smart_trailing"  # ATR-based trailing
    BREAKEVEN = "breakeven"            # Move to breakeven
    PARTIAL = "partial"                # Partial position close
    TIME_BASED = "time_based"          # Time-based stop


@dataclass
class StopLossLevel:
    """Single stop loss level configuration"""
    price: Decimal
    quantity: Decimal
    type: StopLossType
    symbol: Optional[str] = None
    trigger_price: Optional[Decimal] = None
    trail_distance: Optional[Decimal] = None
    time_trigger: Optional[datetime] = None
    order_id: Optional[str] = None
    is_active: bool = False


class StopLossManager:
    """
    Manages stop loss orders with advanced features:
    - Multiple stop loss types
    - Partial position management
    - Smart trailing stops
    - Breakeven management
    - Emergency stops
    """
    
    def __init__(self, 
                 exchange_manager: ExchangeManager,
                 repository: Repository,
                 config: Dict[str, Any]):
        
        self.exchange_manager = exchange_manager
        self.repository = repository
        self.config = config
        
        # Stop loss parameters
        self.default_stop_percentage = Decimal(str(config.get('default_stop_percentage', 2.0)))
        self.trailing_activation = Decimal(str(config.get('trailing_activation', 1.0)))
        self.trailing_distance = Decimal(str(config.get('trailing_distance', 0.5)))
        self.breakeven_trigger = Decimal(str(config.get('breakeven_trigger', 1.5)))
        self.max_slippage = Decimal(str(config.get('max_slippage', 0.1)))
        
        # Smart trailing parameters
        self.use_atr_trailing = config.get('use_atr_trailing', True)
        self.atr_multiplier = Decimal(str(config.get('atr_multiplier', 2.0)))
        self.atr_period = config.get('atr_period', 14)
        
        # Partial close levels
        self.partial_levels = config.get('partial_levels', [
            {'profit_pct': 1.0, 'close_pct': 25},
            {'profit_pct': 2.0, 'close_pct': 25},
            {'profit_pct': 3.0, 'close_pct': 25}
        ])
        
        # Active stop losses per position
        self.active_stops: Dict[str, List[StopLossLevel]] = {}
        
        # Price tracking for trailing stops
        self.highest_prices: Dict[str, Decimal] = {}
        self.lowest_prices: Dict[str, Decimal] = {}
        
        # ATR cache for smart trailing
        self.atr_cache: Dict[str, Tuple[Decimal, datetime]] = {}
        
        logger.info("StopLossManager initialized with advanced features")
    
    async def setup_position_stops(self, 
                                  position: Position,
                                  stop_config: Optional[StopLossConfig] = None) -> List[StopLossLevel]:
        """
        Setup initial stop loss orders for a new position
        """
        try:
            symbol = position.symbol
            side = position.side
            entry_price = Decimal(str(position.entry_price))
            quantity = Decimal(str(position.quantity))
            
            # Use provided config or defaults
            if not stop_config:
                stop_config = await self._get_default_config(symbol)
            
            stops = []
            
            # 1. Initial fixed stop loss
            if stop_config.use_fixed_stop:
                fixed_stop = await self._create_fixed_stop(
                    symbol, side, entry_price, quantity, 
                    stop_config.fixed_stop_percentage
                )
                stops.append(fixed_stop)
            
            # 2. Setup partial take profits with trailing stops
            if stop_config.use_partial_closes:
                partial_stops = await self._create_partial_stops(
                    symbol, side, entry_price, quantity,
                    self.partial_levels
                )
                stops.extend(partial_stops)
            
            # 3. Time-based stop if configured
            if stop_config.use_time_stop:
                time_stop = await self._create_time_stop(
                    symbol, side, entry_price, quantity,
                    stop_config.max_position_hours
                )
                stops.append(time_stop)
            
            # Place orders on exchange
            placed_stops = await self._place_stop_orders(symbol, stops)
            
            # Store in active stops
            self.active_stops[position.id] = placed_stops
            
            # Initialize price tracking
            if side == 'long':
                self.highest_prices[position.id] = entry_price
            else:
                self.lowest_prices[position.id] = entry_price
            
            logger.info(f"Setup {len(placed_stops)} stop losses for position {position.id}")
            return placed_stops
            
        except Exception as e:
            logger.error(f"Failed to setup stop losses: {e}")
            # Create emergency stop
            return await self._create_emergency_stop(position)
    
    async def update_stops(self, 
                           position: Position,
                           current_price: Decimal) -> Dict[str, Any]:
        """
        Update stop losses based on current market conditions
        """
        try:
            position_id = position.id
            side = position.side
            entry_price = Decimal(str(position.entry_price))
            
            if position_id not in self.active_stops:
                logger.warning(f"No active stops for position {position_id}")
                return {'updated': 0, 'errors': []}
            
            updates = {
                'updated': 0,
                'moved_to_breakeven': False,
                'trailing_adjusted': False,
                'partials_triggered': 0,
                'errors': []
            }
            
            # Update price tracking
            if side == 'long':
                if current_price > self.highest_prices.get(position_id, entry_price):
                    self.highest_prices[position_id] = current_price
                high_water = self.highest_prices[position_id]
            else:
                if current_price < self.lowest_prices.get(position_id, entry_price):
                    self.lowest_prices[position_id] = current_price
                high_water = self.lowest_prices[position_id]
            
            # Calculate profit percentage
            if side == 'long':
                profit_pct = ((current_price - entry_price) / entry_price) * 100
            else:
                profit_pct = ((entry_price - current_price) / entry_price) * 100
            
            # Process each stop level
            for stop in self.active_stops[position_id]:
                if not stop.is_active:
                    continue
                
                # 1. Check breakeven condition
                if stop.type == StopLossType.FIXED and profit_pct >= float(self.breakeven_trigger):
                    if await self._move_to_breakeven(position, stop):
                        updates['moved_to_breakeven'] = True
                        updates['updated'] += 1
                
                # 2. Update trailing stops
                elif stop.type in [StopLossType.TRAILING, StopLossType.SMART_TRAILING]:
                    if await self._update_trailing_stop(position, stop, current_price, high_water):
                        updates['trailing_adjusted'] = True
                        updates['updated'] += 1
                
                # 3. Check time-based stops
                elif stop.type == StopLossType.TIME_BASED:
                    if await self._check_time_stop(position, stop):
                        updates['updated'] += 1
                
                # 4. Check partial close triggers
                elif stop.type == StopLossType.PARTIAL:
                    if await self._check_partial_trigger(position, stop, profit_pct):
                        updates['partials_triggered'] += 1
            
            return updates
            
        except Exception as e:
            logger.error(f"Failed to update stops: {e}")
            return {'updated': 0, 'errors': [str(e)]}
    
    async def _create_fixed_stop(self, 
                                 symbol: str,
                                 side: str,
                                 entry_price: Decimal,
                                 quantity: Decimal,
                                 stop_percentage: Decimal) -> StopLossLevel:
        """Create fixed percentage stop loss"""
        
        if side == 'long':
            stop_price = entry_price * (Decimal('1') - stop_percentage / Decimal('100'))
        else:
            stop_price = entry_price * (Decimal('1') + stop_percentage / Decimal('100'))
        
        # Round to exchange precision
        stop_price = await self._round_price(symbol, stop_price)
        
        return StopLossLevel(
            price=stop_price,
            quantity=quantity,
            type=StopLossType.FIXED,
            symbol=symbol,
            is_active=True
        )
    
    async def _create_partial_stops(self,
                                   symbol: str,
                                   side: str,
                                   entry_price: Decimal,
                                   quantity: Decimal,
                                   levels: List[Dict]) -> List[StopLossLevel]:
        """Create partial take profit levels with trailing stops"""
        
        stops = []
        remaining_qty = quantity
        
        for level in levels:
            profit_pct = Decimal(str(level['profit_pct']))
            close_pct = Decimal(str(level['close_pct']))
            
            # Calculate trigger price
            if side == 'long':
                trigger_price = entry_price * (Decimal('1') + profit_pct / Decimal('100'))
            else:
                trigger_price = entry_price * (Decimal('1') - profit_pct / Decimal('100'))
            
            # Calculate quantity for this level
            level_qty = quantity * (close_pct / Decimal('100'))
            level_qty = min(level_qty, remaining_qty)
            
            if level_qty > 0:
                stop = StopLossLevel(
                    price=trigger_price,  # Initial stop at entry
                    quantity=level_qty,
                    type=StopLossType.PARTIAL,
                    trigger_price=trigger_price,
                    trail_distance=self.trailing_distance,
                    symbol=symbol,
                    is_active=False  # Activated when trigger price hit
                )
                stops.append(stop)
                remaining_qty -= level_qty
        
        return stops
    
    async def _create_time_stop(self,
                               symbol: str,
                               side: str,
                               entry_price: Decimal,
                               quantity: Decimal,
                               max_hours: int) -> StopLossLevel:
        """Create time-based stop loss"""
        
        trigger_time = datetime.now(timezone.utc) + timedelta(hours=max_hours)
        
        # Use tighter stop for time-based exit
        stop_percentage = self.default_stop_percentage / 2
        
        if side == 'long':
            stop_price = entry_price * (Decimal('1') - stop_percentage / Decimal('100'))
        else:
            stop_price = entry_price * (Decimal('1') + stop_percentage / Decimal('100'))
        
        return StopLossLevel(
            price=stop_price,
            quantity=quantity,
            type=StopLossType.TIME_BASED,
            time_trigger=trigger_time,
            symbol=symbol,
            is_active=False  # Activated when time reached
        )
    
    async def _create_emergency_stop(self, position: Position) -> List[StopLossLevel]:
        """Create emergency stop loss when normal setup fails"""
        
        try:
            symbol = position.symbol
            side = position.side
            entry_price = Decimal(str(position.entry_price))
            quantity = Decimal(str(position.quantity))
            
            # Use wider stop for emergency
            stop_percentage = self.default_stop_percentage * 2
            
            emergency_stop = await self._create_fixed_stop(
                symbol, side, entry_price, quantity, stop_percentage
            )
            
            # Try to place immediately
            order = await self._place_single_stop(symbol, emergency_stop)
            if order:
                emergency_stop.order_id = order['id']
                emergency_stop.is_active = True
                
                self.active_stops[position.id] = [emergency_stop]
                logger.warning(f"Emergency stop placed for position {position.id}")
            
            return [emergency_stop]
            
        except Exception as e:
            logger.error(f"Failed to create emergency stop: {e}")
            return []
    
    async def _move_to_breakeven(self, position: Position, stop: StopLossLevel) -> bool:
        """Move stop loss to breakeven plus commission"""
        
        try:
            symbol = position.symbol
            side = position.side
            entry_price = Decimal(str(position.entry_price))
            
            # Calculate breakeven with commission buffer
            commission_buffer = entry_price * Decimal('0.001')  # 0.1% buffer
            
            if side == 'long':
                new_stop_price = entry_price + commission_buffer
                if new_stop_price <= stop.price:
                    return False  # Already at or above breakeven
            else:
                new_stop_price = entry_price - commission_buffer
                if new_stop_price >= stop.price:
                    return False  # Already at or below breakeven
            
            # Cancel old order and place new one
            if stop.order_id:
                await self.exchange_manager.cancel_order(stop.order_id, symbol)
            
            stop.price = new_stop_price
            stop.type = StopLossType.BREAKEVEN
            
            order = await self._place_single_stop(symbol, stop)
            if order:
                stop.order_id = order['id']
                logger.info(f"Moved stop to breakeven for {symbol}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to move to breakeven: {e}")
            return False
    
    async def _update_trailing_stop(self,
                                   position: Position,
                                   stop: StopLossLevel,
                                   current_price: Decimal,
                                   high_water: Decimal) -> bool:
        """Update trailing stop based on price movement"""
        
        try:
            symbol = position.symbol
            side = position.side
            
            # Calculate trail distance
            if stop.type == StopLossType.SMART_TRAILING:
                trail_distance = await self._calculate_atr_trail(symbol)
            else:
                trail_distance = stop.trail_distance or self.trailing_distance
            
            # Calculate new stop price
            if side == 'long':
                new_stop_price = high_water * (Decimal('1') - trail_distance / Decimal('100'))
                should_update = new_stop_price > stop.price
            else:
                new_stop_price = high_water * (Decimal('1') + trail_distance / Decimal('100'))
                should_update = new_stop_price < stop.price
            
            if should_update:
                # Cancel old order and place new one
                if stop.order_id:
                    await self.exchange_manager.cancel_order(stop.order_id, symbol)
                
                stop.price = await self._round_price(symbol, new_stop_price)
                
                order = await self._place_single_stop(symbol, stop)
                if order:
                    stop.order_id = order['id']
                    logger.debug(f"Trailing stop updated for {symbol}: {stop.price}")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to update trailing stop: {e}")
            return False
    
    async def _calculate_atr_trail(self, symbol: str) -> Decimal:
        """Calculate ATR-based trailing distance"""
        
        try:
            # Check cache
            if symbol in self.atr_cache:
                atr, timestamp = self.atr_cache[symbol]
                if datetime.now(timezone.utc) - timestamp < timedelta(minutes=5):
                    return atr * self.atr_multiplier
            
            # Fetch recent candles
            candles = await self.exchange_manager.fetch_ohlcv(
                symbol, timeframe='5m', limit=self.atr_period + 1
            )
            
            if len(candles) < self.atr_period:
                return self.trailing_distance  # Fallback to default
            
            # Calculate ATR
            highs = [c[2] for c in candles]
            lows = [c[3] for c in candles]
            closes = [c[4] for c in candles]
            
            tr_list = []
            for i in range(1, len(candles)):
                high_low = highs[i] - lows[i]
                high_close = abs(highs[i] - closes[i-1])
                low_close = abs(lows[i] - closes[i-1])
                tr = max(high_low, high_close, low_close)
                tr_list.append(tr)
            
            atr = sum(tr_list[-self.atr_period:]) / self.atr_period
            
            # Convert to percentage
            current_price = Decimal(str(closes[-1]))
            atr_percentage = (Decimal(str(atr)) / current_price) * 100
            
            # Cache result
            self.atr_cache[symbol] = (atr_percentage, datetime.now(timezone.utc))
            
            return atr_percentage * self.atr_multiplier
            
        except Exception as e:
            logger.error(f"Failed to calculate ATR: {e}")
            return self.trailing_distance
    
    async def _place_stop_orders(self, 
                                symbol: str,
                                stops: List[StopLossLevel]) -> List[StopLossLevel]:
        """Place stop loss orders on exchange"""
        
        placed_stops = []
        
        for stop in stops:
            if stop.is_active:
                order = await self._place_single_stop(symbol, stop)
                if order:
                    stop.order_id = order['id']
                    placed_stops.append(stop)
                else:
                    logger.error(f"Failed to place stop order at {stop.price}")
        
        return placed_stops
    
    @async_retry(max_attempts=3, delay=1)
    async def _place_single_stop(self, 
                                symbol: str,
                                stop: StopLossLevel) -> Optional[Dict[str, Any]]:
        """Place single stop loss order"""
        
        try:
            params = {
                'stopPrice': float(stop.price),
                'reduceOnly': True
            }
            
            # Determine order side (opposite of position)
            # This assumes we're closing the position
            order_side = 'sell' if stop.quantity > 0 else 'buy'
            
            order = await self.exchange_manager.create_order(
                symbol=symbol,
                type='stop_market',
                side=order_side,
                amount=abs(float(stop.quantity)),
                params=params
            )
            
            return order
            
        except Exception as e:
            logger.error(f"Failed to place stop order: {e}")
            return None
    
    async def _round_price(self, symbol: str, price: Decimal) -> Decimal:
        """Round price to exchange precision"""
        
        try:
            market = await self.exchange_manager.get_market(symbol)
            precision = market.get('precision', {}).get('price', 8)
            
            # Round down for safety
            factor = Decimal(10) ** -precision
            return price.quantize(factor, rounding=ROUND_DOWN)
            
        except Exception as e:
            logger.error(f"Failed to round price: {e}")
            return price
    
    async def _get_default_config(self, symbol: str) -> StopLossConfig:
        """Get default stop loss configuration"""
        
        return StopLossConfig(
            symbol=symbol,
            use_fixed_stop=True,
            fixed_stop_percentage=float(self.default_stop_percentage),
            use_trailing_stop=True,
            trailing_activation=float(self.trailing_activation),
            trailing_distance=float(self.trailing_distance),
            use_partial_closes=True,
            use_time_stop=False,
            max_position_hours=24
        )
    
    async def cancel_position_stops(self, position_id: str) -> int:
        """Cancel all stop orders for a position"""
        
        cancelled = 0
        
        if position_id in self.active_stops:
            for stop in self.active_stops[position_id]:
                if stop.order_id and stop.is_active:
                    try:
                        await self.exchange_manager.cancel_order(
                            stop.order_id, 
                            stop.symbol if hasattr(stop, 'symbol') else None
                        )
                        stop.is_active = False
                        cancelled += 1
                    except Exception as e:
                        logger.error(f"Failed to cancel stop {stop.order_id}: {e}")
            
            # Remove from active stops
            del self.active_stops[position_id]
        
        # Clean up price tracking
        self.highest_prices.pop(position_id, None)
        self.lowest_prices.pop(position_id, None)
        
        return cancelled
    
    async def get_position_stops(self, position_id: str) -> List[StopLossLevel]:
        """Get all active stops for a position"""
        return self.active_stops.get(position_id, [])