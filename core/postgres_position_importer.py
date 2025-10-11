#!/usr/bin/env python3
"""
PostgreSQL Position Importer
Imports and synchronizes positions from exchanges to PostgreSQL database
"""
import asyncio
import asyncpg
import logging
import ccxt.async_support as ccxt
from datetime import datetime
from dotenv import load_dotenv
import os
import json
from typing import Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()


class PostgresPositionImporter:
    """Import positions from exchanges to PostgreSQL database"""

    def __init__(self):
        self.exchanges = {}
        self.conn = None
        self.db_url = os.getenv('DATABASE_URL')

    async def connect_database(self):
        """Connect to PostgreSQL database"""
        self.conn = await asyncpg.connect(self.db_url)
        logger.info("✅ Connected to PostgreSQL database")

        # Set search path
        await self.conn.execute("SET search_path TO monitoring, fas, public")

    async def setup_exchange(self, name: str):
        """Setup exchange connection"""
        try:
            if name == 'binance':
                use_testnet = os.getenv('BINANCE_TESTNET', '').lower() == 'true'
                exchange = ccxt.binance({
                    'apiKey': os.getenv('BINANCE_API_KEY'),
                    'secret': os.getenv('BINANCE_API_SECRET'),
                    'enableRateLimit': True,
                    'options': {
                        'defaultType': 'future',
                        'adjustForTimeDifference': True,
                    }
                })
                if use_testnet:
                    exchange.set_sandbox_mode(True)

            elif name == 'bybit':
                use_testnet = os.getenv('BYBIT_TESTNET', '').lower() == 'true'
                exchange = ccxt.bybit({
                    'apiKey': os.getenv('BYBIT_API_KEY'),
                    'secret': os.getenv('BYBIT_API_SECRET'),
                    'enableRateLimit': True,
                    'options': {
                        'defaultType': 'future',
                        'accountType': 'UNIFIED',
                    }
                })
                if use_testnet:
                    exchange.urls['api'] = {
                        'public': 'https://api-testnet.bybit.com',
                        'private': 'https://api-testnet.bybit.com'
                    }
                    exchange.hostname = 'api-testnet.bybit.com'
            else:
                return None

            await exchange.load_markets()
            self.exchanges[name] = exchange
            logger.info(f"✅ {name} connected {'(TESTNET)' if use_testnet else ''}")
            return exchange

        except Exception as e:
            logger.error(f"❌ {name} connection failed: {e}")
            return None

    async def fetch_positions_from_exchange(self, exchange_name: str) -> List[Dict]:
        """Fetch all open positions from exchange"""
        exchange = self.exchanges.get(exchange_name)
        if not exchange:
            return []

        try:
            positions = await exchange.fetch_positions()
            active_positions = []

            for pos in positions:
                if pos['contracts'] > 0:  # Only active positions
                    # Fetch open orders for this symbol to find stop-loss
                    sl_price = None
                    sl_order_id = None
                    try:
                        orders = await exchange.fetch_open_orders(pos['symbol'])
                        for order in orders:
                            if order.get('stopPrice'):
                                sl_price = order['stopPrice']
                                sl_order_id = order.get('id')
                                break
                    except Exception as e:
                        logger.warning(f"Could not fetch orders for {pos['symbol']}: {e}")

                    position_data = {
                        'symbol': pos['symbol'],
                        'exchange': exchange_name,
                        'side': pos['side'],
                        'contracts': pos['contracts'],
                        'percentage': pos.get('percentage', 0),
                        'unrealizedPnl': pos.get('unrealizedPnl', 0),
                        'markPrice': pos.get('markPrice'),
                        'entryPrice': self._extract_entry_price(pos),
                        'stopLossPrice': sl_price,
                        'stopLossOrderId': sl_order_id
                    }
                    active_positions.append(position_data)

            logger.info(f"📊 {exchange_name}: Found {len(active_positions)} active positions")
            return active_positions

        except Exception as e:
            logger.error(f"❌ Error fetching {exchange_name} positions: {e}")
            return []

    def _extract_entry_price(self, position: Dict) -> Optional[float]:
        """Extract entry price from various formats"""
        # Try different fields
        for field in ['entryPrice', 'avgPrice']:
            if field in position and position[field]:
                return float(position[field])

        # Try in info dict
        info = position.get('info', {})
        for field in ['avgPrice', 'entryPrice', 'avg_price']:
            if field in info and info[field]:
                try:
                    return float(info[field])
                except (ValueError, TypeError):
                    continue

        return position.get('markPrice')  # Fallback to mark price

    async def check_position_exists(self, symbol: str, exchange: str) -> Optional[int]:
        """Check if position already exists in database"""
        result = await self.conn.fetchrow("""
            SELECT id FROM monitoring.positions
            WHERE symbol = $1 AND exchange = $2 AND status = 'active'
        """, symbol, exchange)
        return result['id'] if result else None

    async def import_position_to_db(self, position: Dict) -> bool:
        """Import single position to database"""
        try:
            # Check if already exists
            existing_id = await self.check_position_exists(
                position['symbol'],
                position['exchange']
            )

            if existing_id:
                # Update existing position
                await self.conn.execute("""
                    UPDATE monitoring.positions
                    SET quantity = $1,
                        current_price = $2,
                        stop_loss_price = $3,
                        unrealized_pnl = $4,
                        sl_order_id = $5,
                        last_sync_at = NOW(),
                        sync_status = 'synced',
                        updated_at = NOW()
                    WHERE id = $6
                """,
                    position['contracts'],
                    position.get('markPrice'),
                    position.get('stopLossPrice'),
                    position.get('unrealizedPnl', 0),
                    position.get('stopLossOrderId'),
                    existing_id
                )
                logger.info(f"📝 Updated existing position: {position['symbol']}")
                return False  # Not a new import

            # Insert new position
            entry_price = position.get('entryPrice') or position.get('markPrice', 0)

            await self.conn.execute("""
                INSERT INTO monitoring.positions (
                    symbol, exchange, side, quantity, entry_price,
                    current_price, stop_loss_price, unrealized_pnl,
                    status, sl_order_id, last_sync_at, sync_status,
                    opened_at, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            """,
                position['symbol'],
                position['exchange'],
                'long' if position['side'] == 'long' else 'short',
                position['contracts'],
                entry_price,
                position.get('markPrice'),
                position.get('stopLossPrice'),
                position.get('unrealizedPnl', 0),
                'active',
                position.get('stopLossOrderId'),
                datetime.now(),
                'imported',
                datetime.now(),
                datetime.now()
            )

            logger.info(f"✅ Imported new position: {position['symbol']}")

            # Log event
            await self.log_import_event(position)

            return True

        except Exception as e:
            logger.error(f"❌ Failed to import {position['symbol']}: {e}")
            return False

    async def log_import_event(self, position: Dict):
        """Log position import event"""
        try:
            await self.conn.execute("""
                INSERT INTO monitoring.event_log (
                    event_type, event_data, symbol, exchange, severity
                ) VALUES ($1, $2, $3, $4, $5)
            """,
                'POSITION_IMPORTED',
                json.dumps({
                    'symbol': position['symbol'],
                    'side': position['side'],
                    'quantity': position['contracts'],
                    'has_stop_loss': position.get('stopLossPrice') is not None
                }),
                position['symbol'],
                position['exchange'],
                'INFO'
            )
        except Exception as e:
            logger.warning(f"Could not log import event: {e}")

    async def cleanup_closed_positions(self):
        """Mark positions as closed if not found on exchange"""
        # Get all active positions from DB
        db_positions = await self.conn.fetch("""
            SELECT id, symbol, exchange
            FROM monitoring.positions
            WHERE status = 'active'
        """)

        # Build set of active positions from exchanges
        active_on_exchange = set()
        for exchange_name, exchange in self.exchanges.items():
            positions = await self.fetch_positions_from_exchange(exchange_name)
            for pos in positions:
                active_on_exchange.add(f"{exchange_name}:{pos['symbol']}")

        # Mark missing positions as closed
        closed_count = 0
        for db_pos in db_positions:
            key = f"{db_pos['exchange']}:{db_pos['symbol']}"
            if key not in active_on_exchange:
                await self.conn.execute("""
                    UPDATE monitoring.positions
                    SET status = 'closed',
                        closed_at = NOW(),
                        exit_reason = 'SYNC: Position not found on exchange',
                        sync_status = 'closed_by_sync'
                    WHERE id = $1
                """, db_pos['id'])
                closed_count += 1
                logger.info(f"🔒 Marked {db_pos['symbol']} as closed")

        if closed_count > 0:
            logger.info(f"📊 Closed {closed_count} positions not found on exchanges")

    async def update_sync_status(self, exchange_name: str, positions_count: int):
        """Update synchronization status"""
        await self.conn.execute("""
            INSERT INTO monitoring.sync_status (
                exchange, last_sync_at, positions_synced, status
            ) VALUES ($1, $2, $3, $4)
        """,
            exchange_name,
            datetime.now(),
            positions_count,
            'completed'
        )

    async def sync_all_positions(self):
        """Synchronize all positions from exchanges to database"""
        logger.info("=" * 60)
        logger.info("🔄 STARTING POSTGRESQL POSITION SYNCHRONIZATION")
        logger.info("=" * 60)

        # Setup connections
        await self.connect_database()
        await self.setup_exchange('binance')
        await self.setup_exchange('bybit')

        imported_count = 0
        updated_count = 0
        all_positions = []

        # Start transaction
        async with self.conn.transaction():
            # Fetch and import positions from each exchange
            for exchange_name in ['binance', 'bybit']:
                if exchange_name in self.exchanges:
                    positions = await self.fetch_positions_from_exchange(exchange_name)
                    all_positions.extend(positions)

                    # Import to database
                    for pos in positions:
                        is_new = await self.import_position_to_db(pos)
                        if is_new:
                            imported_count += 1
                        else:
                            updated_count += 1

                    # Update sync status
                    await self.update_sync_status(exchange_name, len(positions))

            # Cleanup closed positions
            await self.cleanup_closed_positions()

        # Display summary
        logger.info("\n" + "=" * 60)
        logger.info("📊 SYNCHRONIZATION COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Total positions found: {len(all_positions)}")
        logger.info(f"New positions imported: {imported_count}")
        logger.info(f"Existing positions updated: {updated_count}")

        # Show current database state
        total_active = await self.conn.fetchval("""
            SELECT COUNT(*) FROM monitoring.positions WHERE status = 'active'
        """)
        logger.info(f"Total active positions in database: {total_active}")

        # List all positions
        db_positions = await self.conn.fetch("""
            SELECT symbol, exchange, side, quantity, entry_price, stop_loss_price
            FROM monitoring.positions
            WHERE status = 'active'
            ORDER BY exchange, symbol
        """)

        if db_positions:
            logger.info("\n📋 Active positions in database:")
            for pos in db_positions:
                sl_text = f"SL: {pos['stop_loss_price']:.4f}" if pos['stop_loss_price'] else "⚠️ NO SL"
                logger.info(
                    f"  • {pos['exchange']}: {pos['symbol']} "
                    f"{pos['side']} qty={pos['quantity']} "
                    f"@ {pos['entry_price']:.4f} [{sl_text}]"
                )

        # Check for positions without stop-loss
        no_sl = await self.conn.fetch("""
            SELECT symbol, exchange FROM monitoring.positions
            WHERE status = 'active' AND stop_loss_price IS NULL
        """)

        if no_sl:
            logger.warning("\n⚠️ POSITIONS WITHOUT STOP-LOSS:")
            for pos in no_sl:
                logger.warning(f"  • {pos['exchange']}: {pos['symbol']}")

        # Close connections
        for exchange_name, exchange in self.exchanges.items():
            await exchange.close()
        await self.conn.close()

        return imported_count


async def main():
    """Main execution"""
    importer = PostgresPositionImporter()
    await importer.sync_all_positions()


if __name__ == "__main__":
    asyncio.run(main())