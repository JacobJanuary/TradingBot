#!/usr/bin/env python3
"""
Position Synchronization Service
Runs continuously to keep positions synchronized between exchanges and database
"""
import asyncio
import logging
import signal
import sys
from datetime import datetime, timedelta
from typing import Optional, Dict
import asyncpg
import os
from dotenv import load_dotenv

from core.postgres_position_importer import PostgresPositionImporter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()


class PositionSyncService:
    """
    Automated position synchronization service

    Features:
    - Periodic synchronization
    - Health checks
    - Alert on discrepancies
    - Graceful shutdown
    """

    def __init__(self, sync_interval: int = 60):
        """
        Initialize sync service

        Args:
            sync_interval: Seconds between sync runs (default 60)
        """
        self.sync_interval = sync_interval
        self.is_running = False
        self.importer = PostgresPositionImporter()
        self.db_url = os.getenv('DATABASE_URL')
        self.last_sync_time = None
        self.sync_count = 0
        self.error_count = 0
        self.consecutive_errors = 0

    async def start(self):
        """Start the synchronization service"""
        logger.info("🚀 Starting Position Sync Service")
        logger.info(f"📊 Sync interval: {self.sync_interval} seconds")

        self.is_running = True

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        # Initial sync
        await self.run_sync()

        # Start monitoring loop
        await self._sync_loop()

    async def _sync_loop(self):
        """Main synchronization loop"""
        while self.is_running:
            try:
                # Wait for next sync interval
                await asyncio.sleep(self.sync_interval)

                if not self.is_running:
                    break

                # Run synchronization
                await self.run_sync()

                # Reset error counter on success
                self.consecutive_errors = 0

            except Exception as e:
                self.error_count += 1
                self.consecutive_errors += 1
                logger.error(f"❌ Sync loop error #{self.error_count}: {e}")

                # Alert if too many consecutive errors
                if self.consecutive_errors >= 3:
                    await self.send_critical_alert(
                        f"Position sync failing repeatedly: {self.consecutive_errors} consecutive errors"
                    )

                # Exponential backoff on errors
                await asyncio.sleep(min(60 * self.consecutive_errors, 300))

    async def run_sync(self):
        """Run a single synchronization cycle"""
        start_time = datetime.now()
        logger.info(f"\n{'='*60}")
        logger.info(f"🔄 Sync #{self.sync_count + 1} starting...")

        try:
            # Perform synchronization
            imported = await self.importer.sync_all_positions()

            # Check for critical conditions
            await self.check_critical_conditions()

            # Update metrics
            self.last_sync_time = datetime.now()
            self.sync_count += 1

            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"✅ Sync completed in {duration:.2f} seconds")

            # Log to database
            await self.log_sync_result(True, duration, imported)

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"❌ Sync failed after {duration:.2f} seconds: {e}")

            # Log failure
            await self.log_sync_result(False, duration, 0, str(e))

            raise

    async def check_critical_conditions(self):
        """Check for critical conditions that need alerts"""
        conn = await asyncpg.connect(self.db_url)

        try:
            # Check for positions without stop-loss
            no_sl = await conn.fetch("""
                SELECT symbol, exchange, quantity, entry_price
                FROM monitoring.positions
                WHERE status = 'active' AND stop_loss_price IS NULL
            """)

            if no_sl:
                logger.critical(f"⚠️ FOUND {len(no_sl)} POSITIONS WITHOUT STOP-LOSS!")
                for pos in no_sl:
                    logger.critical(
                        f"  🚨 {pos['exchange']}: {pos['symbol']} "
                        f"qty={pos['quantity']} @ {pos['entry_price']}"
                    )

                await self.send_critical_alert(
                    f"CRITICAL: {len(no_sl)} positions without stop-loss protection!"
                )

            # Check for large unrealized losses
            large_losses = await conn.fetch("""
                SELECT symbol, exchange, unrealized_pnl
                FROM monitoring.positions
                WHERE status = 'active'
                AND unrealized_pnl < -100  -- Loss > $100
            """)

            if large_losses:
                total_loss = sum(pos['unrealized_pnl'] for pos in large_losses)
                logger.warning(
                    f"⚠️ Large unrealized losses: ${abs(total_loss):.2f} "
                    f"across {len(large_losses)} positions"
                )

            # Check for stale positions (not synced recently)
            stale = await conn.fetch("""
                SELECT symbol, exchange, last_sync_at
                FROM monitoring.positions
                WHERE status = 'active'
                AND (last_sync_at IS NULL OR last_sync_at < NOW() - INTERVAL '10 minutes')
            """)

            if stale:
                logger.warning(f"⚠️ {len(stale)} positions not synced in >10 minutes")

        finally:
            await conn.close()

    async def log_sync_result(
        self,
        success: bool,
        duration: float,
        positions_synced: int,
        error: Optional[str] = None
    ):
        """Log sync result to database"""
        try:
            conn = await asyncpg.connect(self.db_url)

            await conn.execute("""
                INSERT INTO monitoring.sync_status (
                    exchange, last_sync_at, positions_synced,
                    status, details
                ) VALUES ($1, $2, $3, $4, $5)
            """,
                'all',
                datetime.now(),
                positions_synced,
                'success' if success else 'failed',
                {
                    'duration': duration,
                    'sync_count': self.sync_count,
                    'error': error
                } if error else {'duration': duration, 'sync_count': self.sync_count}
            )

            await conn.close()

        except Exception as e:
            logger.error(f"Could not log sync result: {e}")

    async def send_critical_alert(self, message: str):
        """Send critical alert (implement your alert mechanism)"""
        logger.critical(f"🚨 ALERT: {message}")

        # TODO: Implement actual alerting (email, Telegram, etc.)
        # Example: await telegram_bot.send_message(message)

    async def get_health_status(self) -> Dict:
        """Get health status of the service"""
        conn = await asyncpg.connect(self.db_url)

        try:
            # Get active positions count
            active_positions = await conn.fetchval("""
                SELECT COUNT(*) FROM monitoring.positions WHERE status = 'active'
            """)

            # Get last sync info
            last_sync = await conn.fetchrow("""
                SELECT last_sync_at, status, positions_synced
                FROM monitoring.sync_status
                ORDER BY last_sync_at DESC
                LIMIT 1
            """)

            health = {
                'status': 'healthy' if self.consecutive_errors < 3 else 'unhealthy',
                'is_running': self.is_running,
                'sync_count': self.sync_count,
                'error_count': self.error_count,
                'consecutive_errors': self.consecutive_errors,
                'last_sync_time': self.last_sync_time.isoformat() if self.last_sync_time else None,
                'active_positions': active_positions,
                'last_sync_status': dict(last_sync) if last_sync else None
            }

            return health

        finally:
            await conn.close()

    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"📴 Received signal {signum}, shutting down gracefully...")
        self.is_running = False

    async def stop(self):
        """Stop the service gracefully"""
        logger.info("🛑 Stopping Position Sync Service...")
        self.is_running = False

        # Final sync before shutdown
        try:
            logger.info("Running final sync before shutdown...")
            await self.run_sync()
        except Exception as e:
            logger.error(f"Final sync failed: {e}")

        logger.info("✅ Position Sync Service stopped")


async def main():
    """Main entry point"""
    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description='Position Sync Service')
    parser.add_argument(
        '--interval',
        type=int,
        default=60,
        help='Sync interval in seconds (default: 60)'
    )
    parser.add_argument(
        '--once',
        action='store_true',
        help='Run sync once and exit'
    )
    args = parser.parse_args()

    # Create and run service
    service = PositionSyncService(sync_interval=args.interval)

    if args.once:
        # Run once and exit
        await service.run_sync()
    else:
        # Run continuous service
        await service.start()


if __name__ == "__main__":
    asyncio.run(main())