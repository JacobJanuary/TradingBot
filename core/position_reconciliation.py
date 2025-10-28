"""
Position Reconciliation Monitor

Periodically compares tracked positions in database with actual positions on exchange.
Detects and corrects discrepancies.

Run frequency: Every 10 minutes
"""

import asyncio
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class PositionReconciliation:
    """
    Reconciles database position records with actual exchange positions.

    Checks for:
    - Positions marked active in DB but closed on exchange
    - Positions marked closed in DB but still open on exchange
    - Quantity mismatches
    - Side mismatches
    """

    def __init__(
        self,
        repository,
        exchange_managers: Dict,
        position_manager,
        alert_callback: Optional[callable] = None
    ):
        self.repository = repository
        self.exchange_managers = exchange_managers
        self.position_manager = position_manager
        self.alert_callback = alert_callback
        self.is_running = False
        self.scan_interval = 600  # 10 minutes

    async def start(self):
        """Start periodic reconciliation."""
        self.is_running = True
        logger.info("🔄 Position Reconciliation started (every 10 minutes)")

        while self.is_running:
            try:
                await self._reconcile_all()
            except Exception as e:
                logger.error(f"Error in reconciliation: {e}")

            await asyncio.sleep(self.scan_interval)

    def stop(self):
        """Stop reconciliation."""
        self.is_running = False
        logger.info("🛑 Position Reconciliation stopped")

    async def _reconcile_all(self):
        """Reconcile all exchanges."""
        logger.info("🔄 Starting position reconciliation...")

        total_mismatches = 0

        for exchange_name, exchange_instance in self.exchange_managers.items():
            try:
                mismatches = await self._reconcile_exchange(exchange_name, exchange_instance)
                total_mismatches += len(mismatches)

            except Exception as e:
                logger.error(f"Error reconciling {exchange_name}: {e}")

        if total_mismatches == 0:
            logger.info("✅ Reconciliation complete: All positions match")
        else:
            logger.warning(f"⚠️ Reconciliation complete: {total_mismatches} discrepancies found")

    async def _reconcile_exchange(
        self,
        exchange_name: str,
        exchange_instance
    ) -> List[Dict]:
        """
        Reconcile positions for single exchange.

        Returns:
            List of discrepancy dicts
        """
        # Fetch positions from both sources
        exchange_positions = await self._fetch_exchange_positions(
            exchange_name, exchange_instance
        )
        db_positions = await self.repository.get_active_positions(exchange=exchange_name)

        # Build lookup maps
        from core.position_manager import normalize_symbol

        exchange_map = {
            normalize_symbol(pos['symbol']): pos
            for pos in exchange_positions
        }

        db_map = {
            pos['symbol']: pos
            for pos in db_positions
        }

        mismatches = []

        # Check each DB position
        for symbol, db_pos in db_map.items():
            exchange_pos = exchange_map.get(symbol)

            if not exchange_pos:
                # DB says active but not on exchange
                mismatch = {
                    'type': 'missing_on_exchange',
                    'symbol': symbol,
                    'exchange': exchange_name,
                    'db_position': db_pos,
                    'exchange_position': None
                }
                mismatches.append(mismatch)
                await self._handle_mismatch(mismatch)

            else:
                # Compare details
                db_qty = float(db_pos['quantity'])
                ex_qty = exchange_pos['contracts']

                if abs(db_qty - ex_qty) > 0.01:  # Allow tiny floating point diff
                    mismatch = {
                        'type': 'quantity_mismatch',
                        'symbol': symbol,
                        'exchange': exchange_name,
                        'db_quantity': db_qty,
                        'exchange_quantity': ex_qty,
                        'difference': ex_qty - db_qty
                    }
                    mismatches.append(mismatch)
                    await self._handle_mismatch(mismatch)

        return mismatches

    async def _fetch_exchange_positions(
        self,
        exchange_name: str,
        exchange_instance
    ) -> List[Dict]:
        """Fetch all open positions from exchange."""
        try:
            if exchange_name == 'bybit':
                positions = await exchange_instance.exchange.fetch_positions(
                    params={'category': 'linear'}
                )
            else:
                positions = await exchange_instance.exchange.fetch_positions()

            from core.position_manager import normalize_symbol

            return [
                {
                    'symbol': normalize_symbol(pos['symbol']),
                    'contracts': float(pos.get('contracts', 0)),
                    'side': pos.get('side', '').lower(),
                    'entry_price': float(pos.get('entryPrice', 0)),
                }
                for pos in positions
                if float(pos.get('contracts', 0)) > 0
            ]

        except Exception as e:
            logger.error(f"Failed to fetch positions from {exchange_name}: {e}")
            return []

    async def _handle_mismatch(self, mismatch: Dict):
        """Handle detected mismatch."""
        if mismatch['type'] == 'missing_on_exchange':
            logger.warning(
                f"⚠️ RECONCILIATION MISMATCH: {mismatch['symbol']}\n"
                f"  Type: Position in DB but not on {mismatch['exchange']}\n"
                f"  DB Position ID: {mismatch['db_position']['id']}\n"
                f"  DB Quantity: {mismatch['db_position']['quantity']}\n"
                f"  Exchange: NOT FOUND\n"
                f"  Action: Marking position as closed in DB"
            )

            # Auto-fix: Mark as closed in DB
            try:
                await self.repository.update_position(
                    mismatch['db_position']['id'],
                    status='closed',
                    closed_at=datetime.now(timezone.utc),
                    exit_reason='reconciliation: position not found on exchange'
                )
                logger.info(f"✅ Auto-fixed: Marked {mismatch['symbol']} as closed")
            except Exception as e:
                logger.error(f"Failed to auto-fix position: {e}")

        elif mismatch['type'] == 'quantity_mismatch':
            logger.warning(
                f"⚠️ RECONCILIATION MISMATCH: {mismatch['symbol']}\n"
                f"  Type: Quantity mismatch\n"
                f"  DB: {mismatch['db_quantity']}\n"
                f"  Exchange: {mismatch['exchange_quantity']}\n"
                f"  Difference: {mismatch['difference']}\n"
                f"  Action: Logging for manual review"
            )
            # TODO: Decide if auto-fix or manual review

    async def manual_reconcile(self) -> Dict[str, List[Dict]]:
        """
        Manually trigger reconciliation (for testing or on-demand checks).

        Returns:
            Dict mapping exchange names to lists of mismatches
        """
        logger.info("🔄 Manual reconciliation requested...")

        results = {}

        for exchange_name, exchange_instance in self.exchange_managers.items():
            try:
                mismatches = await self._reconcile_exchange(exchange_name, exchange_instance)
                results[exchange_name] = mismatches

            except Exception as e:
                logger.error(f"Error in manual reconciliation of {exchange_name}: {e}")
                results[exchange_name] = []

        return results
