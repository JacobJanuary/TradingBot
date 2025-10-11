#!/usr/bin/env python3
"""
Import existing positions from exchanges into database
This will synchronize the database with actual positions on exchanges
"""
import asyncio
import sqlite3
import logging
import ccxt.async_support as ccxt
from datetime import datetime
from dotenv import load_dotenv
import os
import json

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


class PositionImporter:
    """Import positions from exchanges to database"""

    def __init__(self):
        self.exchanges = {}
        self.db_conn = None

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
            logger.info(f"✅ {name} connected")
            return exchange

        except Exception as e:
            logger.error(f"❌ {name} connection failed: {e}")
            return None

    def setup_database(self):
        """Connect to SQLite database"""
        self.db_conn = sqlite3.connect('trading_bot.db')
        self.cursor = self.db_conn.cursor()
        logger.info("✅ Connected to SQLite database")

    async def fetch_positions_from_exchange(self, exchange_name: str):
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
                    try:
                        orders = await exchange.fetch_open_orders(pos['symbol'])
                        for order in orders:
                            if order.get('stopPrice'):
                                sl_price = order['stopPrice']
                                break
                    except:
                        pass

                    position_data = {
                        'symbol': pos['symbol'],
                        'exchange': exchange_name,
                        'side': pos['side'],
                        'contracts': pos['contracts'],
                        'percentage': pos.get('percentage', 0),
                        'unrealizedPnl': pos.get('unrealizedPnl', 0),
                        'markPrice': pos.get('markPrice'),
                        'entryPrice': pos.get('info', {}).get('avgPrice') or pos.get('info', {}).get('entryPrice'),
                        'stopLossPrice': sl_price
                    }
                    active_positions.append(position_data)

            logger.info(f"📊 {exchange_name}: Found {len(active_positions)} active positions")
            return active_positions

        except Exception as e:
            logger.error(f"❌ Error fetching {exchange_name} positions: {e}")
            return []

    def check_position_exists(self, symbol: str, exchange: str) -> bool:
        """Check if position already exists in database"""
        self.cursor.execute("""
            SELECT id FROM positions
            WHERE symbol = ? AND exchange = ? AND status = 'active'
        """, (symbol, exchange))
        return self.cursor.fetchone() is not None

    def import_position_to_db(self, position: dict):
        """Import single position to database"""
        try:
            # Check if already exists
            if self.check_position_exists(position['symbol'], position['exchange']):
                logger.info(f"⏭️ Position {position['symbol']} already in database, skipping")
                return False

            # Prepare data
            entry_price = position.get('entryPrice') or position.get('markPrice', 0)
            quantity = position['contracts']

            # Insert into database
            self.cursor.execute("""
                INSERT INTO positions (
                    symbol, exchange, side, quantity, entry_price,
                    current_price, stop_loss_price, unrealized_pnl,
                    status, opened_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                position['symbol'],
                position['exchange'],
                'long' if position['side'] == 'long' else 'short',
                quantity,
                entry_price,
                position.get('markPrice'),
                position.get('stopLossPrice'),
                position.get('unrealizedPnl', 0),
                'active',
                datetime.now()
            ))

            logger.info(f"✅ Imported {position['symbol']} to database")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to import {position['symbol']}: {e}")
            return False

    async def sync_all_positions(self):
        """Synchronize all positions from exchanges to database"""
        logger.info("=" * 60)
        logger.info("🔄 STARTING POSITION SYNCHRONIZATION")
        logger.info("=" * 60)

        # Setup connections
        await self.setup_exchange('binance')
        await self.setup_exchange('bybit')
        self.setup_database()

        imported_count = 0
        all_positions = []

        # Fetch positions from each exchange
        for exchange_name in ['binance', 'bybit']:
            if exchange_name in self.exchanges:
                positions = await self.fetch_positions_from_exchange(exchange_name)
                all_positions.extend(positions)

                # Import to database
                for pos in positions:
                    if self.import_position_to_db(pos):
                        imported_count += 1

        # Commit all changes
        self.db_conn.commit()

        # Display summary
        logger.info("\n" + "=" * 60)
        logger.info("📊 SYNCHRONIZATION COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Total positions found: {len(all_positions)}")
        logger.info(f"New positions imported: {imported_count}")

        # Show current database state
        self.cursor.execute("SELECT COUNT(*) FROM positions WHERE status = 'active'")
        total_in_db = self.cursor.fetchone()[0]
        logger.info(f"Total active positions in database: {total_in_db}")

        # List all positions
        self.cursor.execute("""
            SELECT symbol, exchange, side, quantity, entry_price, stop_loss_price
            FROM positions WHERE status = 'active'
        """)
        db_positions = self.cursor.fetchall()

        if db_positions:
            logger.info("\n📋 Positions in database:")
            for pos in db_positions:
                sl_text = f"SL: {pos[5]}" if pos[5] else "No SL"
                logger.info(f"  • {pos[1]}: {pos[0]} {pos[2]} qty={pos[3]} @ {pos[4]} [{sl_text}]")

        # Close connections
        for exchange_name, exchange in self.exchanges.items():
            await exchange.close()
        self.db_conn.close()

        return imported_count


async def main():
    importer = PositionImporter()
    await importer.sync_all_positions()


if __name__ == "__main__":
    asyncio.run(main())