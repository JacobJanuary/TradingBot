"""
Aged Position Monitor V2 - MINIMAL implementation
Works through UnifiedPriceMonitor
Does NOT replace existing aged_position_manager.py until tested
"""

import logging
import asyncio
from typing import Dict, Optional, List
from datetime import datetime, timezone
from decimal import Decimal
from dataclasses import dataclass
import os

logger = logging.getLogger(__name__)


@dataclass
class AgedPositionTarget:
    """Simple target tracking for aged position"""
    symbol: str
    entry_price: Decimal
    target_price: Decimal
    phase: str  # 'grace', 'progressive', 'emergency'
    loss_tolerance: Decimal
    hours_aged: float
    position_id: str


class AgedPositionMonitorV2:
    """
    MINIMAL V2 implementation for aged positions
    Uses MARKET orders instead of LIMIT
    Integrates with UnifiedPriceMonitor
    """

    def __init__(self, exchange_managers, repository, position_manager=None, config=None):
        self.exchanges = exchange_managers
        self.repository = repository
        self.position_manager = position_manager

        # Configuration from env/config
        self.max_age_hours = int(os.getenv('MAX_POSITION_AGE_HOURS', 3))
        self.grace_period_hours = int(os.getenv('AGED_GRACE_PERIOD_HOURS', 8))
        self.loss_step_percent = Decimal(os.getenv('AGED_LOSS_STEP_PERCENT', '0.5'))
        self.max_loss_percent = Decimal(os.getenv('AGED_MAX_LOSS_PERCENT', '10.0'))
        self.commission_percent = Decimal(os.getenv('COMMISSION_PERCENT', '0.1')) / Decimal('100')

        # Tracked aged positions
        self.aged_targets: Dict[str, AgedPositionTarget] = {}

        # Simple stats
        self.stats = {
            'positions_monitored': 0,
            'market_closes_triggered': 0,
            'grace_closes': 0,
            'progressive_closes': 0
        }

        logger.info(
            f"AgedPositionMonitorV2 initialized: "
            f"max_age={self.max_age_hours}h, grace={self.grace_period_hours}h"
        )

    async def check_position_age(self, position) -> bool:
        """Check if position qualifies as aged"""

        # Skip if trailing stop is active
        if hasattr(position, 'trailing_activated') and position.trailing_activated:
            return False

        # Calculate age
        age_hours = self._calculate_age_hours(position)

        # Check if aged
        return age_hours > self.max_age_hours

    async def add_aged_position(self, position):
        """Add position to aged monitoring"""

        symbol = position.symbol

        if symbol in self.aged_targets:
            return  # Already monitoring

        age_hours = self._calculate_age_hours(position)
        hours_over_limit = age_hours - self.max_age_hours

        # Determine phase and target
        phase, target_price, loss_tolerance = self._calculate_target(
            position,
            hours_over_limit
        )

        # Create target tracking
        target = AgedPositionTarget(
            symbol=symbol,
            entry_price=Decimal(str(position.entry_price)),
            target_price=target_price,
            phase=phase,
            loss_tolerance=loss_tolerance,
            hours_aged=age_hours,
            position_id=getattr(position, 'id', symbol)
        )

        self.aged_targets[symbol] = target
        self.stats['positions_monitored'] += 1

        logger.info(
            f"📍 Aged position added: {symbol} "
            f"(age={age_hours:.1f}h, phase={phase}, target=${target_price:.4f})"
        )

    async def check_price_target(self, symbol: str, current_price: Decimal):
        """
        Check if current price reached target for aged position
        Called by UnifiedPriceMonitor through adapter
        """

        if symbol not in self.aged_targets:
            return

        target = self.aged_targets[symbol]

        # Check if target reached based on position side
        should_close = False

        # Get position to check side
        position = await self._get_position(symbol)
        if not position:
            del self.aged_targets[symbol]
            return

        # Check profitability first
        pnl_percent = self._calculate_pnl_percent(position, current_price)

        if pnl_percent > Decimal('0'):
            # Profitable - close immediately
            should_close = True
            logger.info(f"💰 {symbol} profitable at {pnl_percent:.2f}% - triggering close")

        else:
            # Check target based on side
            if position.side in ['long', 'buy']:
                # LONG: close if price >= target (accepting loss)
                should_close = current_price >= target.target_price
            else:
                # SHORT: close if price <= target
                should_close = current_price <= target.target_price

        if should_close:
            logger.info(
                f"🎯 Aged target reached for {symbol}: "
                f"current=${current_price:.4f} vs target=${target.target_price:.4f}"
            )

            # Trigger market close
            await self._trigger_market_close(position, target, current_price)

            # Remove from monitoring
            del self.aged_targets[symbol]

    async def _trigger_market_close(self, position, target, trigger_price):
        """Execute MARKET close order for aged position"""

        symbol = position.symbol
        exchange_name = position.exchange
        exchange = self.exchanges.get(exchange_name)

        if not exchange:
            logger.error(f"Exchange {exchange_name} not found")
            return

        try:
            # Determine close side (opposite of position)
            close_side = 'sell' if position.side in ['long', 'buy'] else 'buy'
            amount = abs(float(position.quantity))

            logger.info(
                f"📤 Creating MARKET close for aged {symbol}: "
                f"{close_side} {amount}"
            )

            # Create market order
            params = {'reduceOnly': True}
            if exchange.exchange.id == 'bybit':
                params['positionIdx'] = 0

            order = await exchange.exchange.create_order(
                symbol=symbol,
                type='market',
                side=close_side,
                amount=amount,
                params=params
            )

            if order:
                self.stats['market_closes_triggered'] += 1

                if target.phase == 'grace':
                    self.stats['grace_closes'] += 1
                else:
                    self.stats['progressive_closes'] += 1

                logger.info(
                    f"✅ Aged position {symbol} closed: "
                    f"order_id={order['id']}, phase={target.phase}"
                )

                # Update database
                if self.repository:
                    try:
                        await self.repository.update_position(
                            position.id,
                            status='closed',
                            exit_reason=f'aged_{target.phase}'
                        )
                    except Exception as e:
                        logger.error(f"Failed to update DB: {e}")

        except Exception as e:
            logger.error(f"Failed to close aged position {symbol}: {e}")

    def _calculate_target(self, position, hours_over_limit: float):
        """Calculate target price and phase for aged position"""

        entry_price = Decimal(str(position.entry_price))

        # Check phase
        if hours_over_limit <= self.grace_period_hours:
            # GRACE PERIOD - try breakeven
            phase = 'grace'
            loss_tolerance = Decimal('0')

            # Breakeven = entry + commission
            double_commission = Decimal('2') * self.commission_percent

            if position.side in ['long', 'buy']:
                target_price = entry_price * (Decimal('1') + double_commission)
            else:
                target_price = entry_price * (Decimal('1') - double_commission)

        else:
            # PROGRESSIVE LIQUIDATION
            phase = 'progressive'
            hours_in_progressive = hours_over_limit - self.grace_period_hours

            # Calculate loss tolerance (convert float to Decimal)
            loss_tolerance = Decimal(str(hours_in_progressive)) * self.loss_step_percent

            # Cap at max loss
            loss_tolerance = min(loss_tolerance, self.max_loss_percent)

            # Calculate target with loss
            if position.side in ['long', 'buy']:
                target_price = entry_price * (Decimal('1') - loss_tolerance / Decimal('100'))
            else:
                target_price = entry_price * (Decimal('1') + loss_tolerance / Decimal('100'))

        return phase, target_price, loss_tolerance

    def _calculate_age_hours(self, position) -> float:
        """Calculate position age in hours"""

        if not hasattr(position, 'opened_at'):
            return 0.0

        now = datetime.now(timezone.utc)
        opened_at = position.opened_at

        if not hasattr(opened_at, 'tzinfo') or opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=timezone.utc)

        age = now - opened_at
        return age.total_seconds() / 3600

    def _calculate_pnl_percent(self, position, current_price: Decimal) -> Decimal:
        """Calculate current PnL percentage"""

        entry_price = Decimal(str(position.entry_price))

        if position.side in ['long', 'buy']:
            pnl = ((current_price - entry_price) / entry_price) * Decimal('100')
        else:
            pnl = ((entry_price - current_price) / entry_price) * Decimal('100')

        return pnl

    async def _get_position(self, symbol: str):
        """Get position from position manager"""
        if self.position_manager and hasattr(self.position_manager, 'positions'):
            return self.position_manager.positions.get(symbol)
        return None

    def get_stats(self) -> Dict:
        """Get statistics"""
        return {
            'monitored': len(self.aged_targets),
            'total_processed': self.stats['positions_monitored'],
            'market_closes': self.stats['market_closes_triggered'],
            'grace_closes': self.stats['grace_closes'],
            'progressive_closes': self.stats['progressive_closes']
        }