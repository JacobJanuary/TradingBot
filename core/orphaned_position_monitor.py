"""
Orphaned Position Monitor

Periodically scans exchange positions and compares with database tracking.
Detects and alerts on orphaned positions (exist on exchange but not in DB).

Run frequency: Every 5 minutes
"""

import asyncio
import logging
from typing import Dict, List, Optional, Set
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class OrphanedPositionMonitor:
    """
    Detects positions that exist on exchange but are not tracked in database.

    Orphaned positions are dangerous because they:
    - Have no stop-loss protection
    - Are not monitored by trailing stop
    - Can accumulate unlimited losses
    - May indicate system bugs
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
        self.scan_interval = 300  # 5 minutes

    async def start(self):
        """Start periodic orphaned position scanning."""
        self.is_running = True
        logger.info("🔍 Orphaned Position Monitor started (scan every 5 minutes)")

        while self.is_running:
            try:
                await self._scan_for_orphans()
            except Exception as e:
                logger.error(f"Error in orphaned position scan: {e}")

            await asyncio.sleep(self.scan_interval)

    def stop(self):
        """Stop the monitor."""
        self.is_running = False
        logger.info("🛑 Orphaned Position Monitor stopped")

    async def _scan_for_orphans(self):
        """
        Scan all exchanges for orphaned positions.

        Process:
        1. Fetch all positions from each exchange
        2. Fetch all active positions from database
        3. Compare and identify orphans
        4. Alert and log any orphans found
        """
        logger.info("🔍 Starting orphaned position scan...")

        total_orphans = 0

        for exchange_name, exchange_instance in self.exchange_managers.items():
            try:
                orphans = await self._scan_exchange(exchange_name, exchange_instance)
                total_orphans += len(orphans)

                if orphans:
                    await self._handle_orphans(exchange_name, orphans)

            except Exception as e:
                logger.error(f"Error scanning {exchange_name}: {e}")

        if total_orphans == 0:
            logger.info("✅ Orphan scan complete: No orphaned positions found")
        else:
            logger.critical(f"🚨 Orphan scan complete: {total_orphans} ORPHANED POSITIONS FOUND!")

    async def _scan_exchange(
        self,
        exchange_name: str,
        exchange_instance
    ) -> List[Dict]:
        """
        Scan single exchange for orphaned positions.

        Returns:
            List of orphaned position dicts
        """
        logger.debug(f"Scanning {exchange_name} for orphans...")

        # Fetch all positions from exchange
        try:
            if exchange_name == 'bybit':
                positions = await exchange_instance.exchange.fetch_positions(
                    params={'category': 'linear'}
                )
            else:
                positions = await exchange_instance.exchange.fetch_positions()
        except Exception as e:
            logger.error(f"Failed to fetch positions from {exchange_name}: {e}")
            return []

        # Filter to only open positions
        from core.position_manager import normalize_symbol

        open_positions = []
        for pos in positions:
            contracts = float(pos.get('contracts', 0))
            if contracts > 0:
                open_positions.append({
                    'symbol': normalize_symbol(pos['symbol']),
                    'raw_symbol': pos['symbol'],
                    'side': pos.get('side', '').lower(),
                    'contracts': contracts,
                    'entry_price': float(pos.get('entryPrice', 0)),
                    'mark_price': float(pos.get('markPrice', 0)),
                    'unrealized_pnl': float(pos.get('unrealizedPnl', 0)),
                    'leverage': float(pos.get('leverage', 1)),
                })

        if not open_positions:
            logger.debug(f"{exchange_name}: No open positions")
            return []

        logger.debug(f"{exchange_name}: Found {len(open_positions)} open positions")

        # Fetch tracked positions from database
        db_positions = await self.repository.get_active_positions(exchange=exchange_name)
        tracked_symbols = {pos['symbol'] for pos in db_positions}

        logger.debug(f"{exchange_name}: Tracking {len(tracked_symbols)} positions in DB")

        # Identify orphans (on exchange but not in DB)
        orphans = []
        for pos in open_positions:
            if pos['symbol'] not in tracked_symbols:
                orphans.append({
                    **pos,
                    'exchange': exchange_name,
                    'detected_at': datetime.now(timezone.utc)
                })
                logger.warning(
                    f"⚠️ ORPHAN DETECTED on {exchange_name}: "
                    f"{pos['symbol']} {pos['side'].upper()} {pos['contracts']} contracts"
                )

        return orphans

    async def _handle_orphans(self, exchange_name: str, orphans: List[Dict]):
        """
        Handle detected orphaned positions.

        Actions:
        1. Log detailed alert
        2. Send notification (if callback configured)
        3. Optionally: Auto-close or add to tracking
        """
        for orphan in orphans:
            # Log critical alert
            logger.critical(
                f"🚨 ORPHANED POSITION DETECTED:\n"
                f"  Exchange: {exchange_name}\n"
                f"  Symbol: {orphan['symbol']}\n"
                f"  Side: {orphan['side'].upper()}\n"
                f"  Contracts: {orphan['contracts']}\n"
                f"  Entry Price: ${orphan['entry_price']:.8f}\n"
                f"  Mark Price: ${orphan['mark_price']:.8f}\n"
                f"  Unrealized PnL: ${orphan['unrealized_pnl']:.4f}\n"
                f"  Leverage: {orphan['leverage']}x\n"
                f"  ⚠️ NO STOP LOSS! ⚠️\n"
                f"  Detected at: {orphan['detected_at']}"
            )

            # Send alert via callback
            if self.alert_callback:
                try:
                    await self.alert_callback(
                        alert_type='orphaned_position',
                        exchange=exchange_name,
                        symbol=orphan['symbol'],
                        details=orphan
                    )
                except Exception as e:
                    logger.error(f"Failed to send orphan alert: {e}")

    async def manual_scan(self) -> Dict[str, List[Dict]]:
        """
        Manually trigger orphan scan (for testing or on-demand checks).

        Returns:
            Dict mapping exchange names to lists of orphans
        """
        logger.info("🔍 Manual orphan scan requested...")

        results = {}

        for exchange_name, exchange_instance in self.exchange_managers.items():
            try:
                orphans = await self._scan_exchange(exchange_name, exchange_instance)
                results[exchange_name] = orphans

                if orphans:
                    await self._handle_orphans(exchange_name, orphans)

            except Exception as e:
                logger.error(f"Error in manual scan of {exchange_name}: {e}")
                results[exchange_name] = []

        return results
