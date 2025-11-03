#!/usr/bin/env python3
"""
Complete System Cleanup Script
================================
Clears ALL data from monitoring schema and closes ALL positions/orders on exchanges

WARNING: This is DESTRUCTIVE! Use only for fresh start.

Usage:
    python scripts/complete_cleanup.py
    python scripts/complete_cleanup.py --dry-run  # Preview only
"""

import asyncio
import asyncpg
import ccxt.async_support as ccxt
import os
import sys
from datetime import datetime
from dotenv import load_dotenv
from typing import List, Dict, Tuple

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from utils.pgpass import get_db_password

# Colors for output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_header(text: str):
    print(f"\n{Colors.BOLD}{Colors.HEADER}{'='*80}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.HEADER}{text.center(80)}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.HEADER}{'='*80}{Colors.END}\n")

def print_step(step: int, text: str):
    print(f"{Colors.BOLD}{Colors.CYAN}[{step}] {text}{Colors.END}")

def print_success(text: str):
    print(f"{Colors.GREEN}✅ {text}{Colors.END}")

def print_warning(text: str):
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.END}")

def print_error(text: str):
    print(f"{Colors.RED}❌ {text}{Colors.END}")

def print_info(text: str):
    print(f"{Colors.BLUE}ℹ️  {text}{Colors.END}")


class CompleteCleanup:
    """Complete system cleanup"""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.db_conn = None
        self.exchanges = {}
        self.stats = {
            'db_tables_cleared': 0,
            'db_rows_deleted': 0,
            'positions_closed': 0,
            'orders_cancelled': 0,
            'log_files_deleted': 0,
            'cache_files_deleted': 0,
            'errors': []
        }
        # Get project root directory
        self.project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    async def run(self):
        """Execute complete cleanup"""
        print_header("COMPLETE SYSTEM CLEANUP")

        if self.dry_run:
            print_warning("DRY RUN MODE - No changes will be made")
        else:
            print_warning("DESTRUCTIVE MODE - All data will be deleted!")
            print("\nThis will:")
            print("  • Delete ALL data from monitoring schema")
            print("  • Close ALL positions on Binance")
            print("  • Close ALL positions on Bybit")
            print("  • Cancel ALL orders on both exchanges")
            print("  • Delete ALL log files")
            print("  • Clear Python cache (__pycache__, .pyc files)")
            print("\nPress Ctrl+C now to cancel...")
            await asyncio.sleep(3)

        try:
            # Step 1: Connect to database
            print_step(1, "Connecting to database...")
            await self.connect_database()
            print_success("Connected to database")

            # Step 2: Connect to exchanges
            print_step(2, "Connecting to exchanges...")
            await self.connect_exchanges()
            print_success(f"Connected to {len(self.exchanges)} exchanges")

            # Step 3: Close all positions on exchanges
            print_step(3, "Closing all positions on exchanges...")
            await self.close_all_positions()

            # Step 4: Cancel all orders on exchanges
            print_step(4, "Cancelling all orders on exchanges...")
            await self.cancel_all_orders()

            # Step 5: Clear database tables
            print_step(5, "Clearing database tables...")
            await self.clear_database_tables()

            # Step 6: Delete log files
            print_step(6, "Deleting log files...")
            self.delete_log_files()

            # Step 7: Clear Python cache
            print_step(7, "Clearing Python cache...")
            self.clear_python_cache()

            # Step 8: Verify cleanup
            print_step(8, "Verifying cleanup...")
            await self.verify_cleanup()

            # Step 9: Show summary
            self.print_summary()

        except KeyboardInterrupt:
            print_warning("\n\nCleanup cancelled by user!")
            return False
        except Exception as e:
            print_error(f"Fatal error: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            await self.cleanup()

        return True

    async def connect_database(self):
        """Connect to PostgreSQL database"""
        db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', 5432)),
            'database': os.getenv('DB_NAME', 'tradingbot_db'),
            'user': os.getenv('DB_USER', 'tradingbot'),
            'password': get_db_password()
        }

        self.db_conn = await asyncpg.connect(**db_config)

        # Set search path
        await self.db_conn.execute("SET search_path TO monitoring, public")

    async def connect_exchanges(self):
        """Connect to exchanges"""
        # Binance
        try:
            binance_testnet = os.getenv('BINANCE_TESTNET', '').lower() == 'true'
            exchange = ccxt.binance({
                'apiKey': os.getenv('BINANCE_API_KEY'),
                'secret': os.getenv('BINANCE_API_SECRET'),
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future',
                }
            })
            if binance_testnet:
                exchange.set_sandbox_mode(True)

            await exchange.load_markets()
            self.exchanges['binance'] = exchange
            print_info(f"  Binance: {'TESTNET' if binance_testnet else 'PRODUCTION'}")
        except Exception as e:
            print_error(f"  Failed to connect to Binance: {e}")
            self.stats['errors'].append(f"Binance connection: {e}")

        # Bybit
        try:
            bybit_testnet = os.getenv('BYBIT_TESTNET', '').lower() == 'true'
            exchange = ccxt.bybit({
                'apiKey': os.getenv('BYBIT_API_KEY'),
                'secret': os.getenv('BYBIT_API_SECRET'),
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'linear',
                }
            })
            if bybit_testnet:
                exchange.urls['api'] = {
                    'public': 'https://api-testnet.bybit.com',
                    'private': 'https://api-testnet.bybit.com'
                }
                exchange.hostname = 'api-testnet.bybit.com'

            await exchange.load_markets()
            self.exchanges['bybit'] = exchange
            print_info(f"  Bybit: {'TESTNET' if bybit_testnet else 'PRODUCTION'}")
        except Exception as e:
            print_error(f"  Failed to connect to Bybit: {e}")
            self.stats['errors'].append(f"Bybit connection: {e}")

    async def close_all_positions(self):
        """Close all positions on all exchanges"""
        total_closed = 0

        for exchange_name, exchange in self.exchanges.items():
            print_info(f"  Processing {exchange_name}...")

            try:
                # Fetch all positions
                positions = await exchange.fetch_positions()
                active_positions = [p for p in positions if p.get('contracts', 0) > 0]

                print_info(f"    Found {len(active_positions)} active positions")

                for position in active_positions:
                    symbol = position['symbol']
                    contracts = position['contracts']
                    side = position['side']

                    try:
                        if not self.dry_run:
                            # Close position by creating opposite order
                            close_side = 'sell' if side == 'long' else 'buy'

                            # Market order to close
                            order = await exchange.create_order(
                                symbol=symbol,
                                type='market',
                                side=close_side,
                                amount=abs(contracts),
                                params={'reduceOnly': True}
                            )
                            print_success(f"    Closed {symbol}: {side} {contracts} contracts")
                            total_closed += 1
                        else:
                            print_info(f"    [DRY RUN] Would close {symbol}: {side} {contracts} contracts")
                            total_closed += 1

                        # Small delay to avoid rate limits
                        await asyncio.sleep(0.1)

                    except Exception as e:
                        print_error(f"    Failed to close {symbol}: {e}")
                        self.stats['errors'].append(f"Close {exchange_name} {symbol}: {e}")

            except Exception as e:
                print_error(f"  Failed to fetch positions from {exchange_name}: {e}")
                self.stats['errors'].append(f"Fetch positions {exchange_name}: {e}")

        self.stats['positions_closed'] = total_closed
        print_success(f"Closed/checked {total_closed} positions")

    async def cancel_all_orders(self):
        """Cancel all orders on all exchanges"""
        total_cancelled = 0

        for exchange_name, exchange in self.exchanges.items():
            print_info(f"  Processing {exchange_name}...")

            try:
                # Fetch all open orders
                orders = await exchange.fetch_open_orders()

                print_info(f"    Found {len(orders)} open orders")

                for order in orders:
                    symbol = order['symbol']
                    order_id = order['id']
                    order_type = order['type']

                    try:
                        if not self.dry_run:
                            await exchange.cancel_order(order_id, symbol)
                            print_success(f"    Cancelled {symbol} order {order_id} ({order_type})")
                            total_cancelled += 1
                        else:
                            print_info(f"    [DRY RUN] Would cancel {symbol} order {order_id} ({order_type})")
                            total_cancelled += 1

                        # Small delay to avoid rate limits
                        await asyncio.sleep(0.1)

                    except Exception as e:
                        print_error(f"    Failed to cancel order {order_id}: {e}")
                        self.stats['errors'].append(f"Cancel {exchange_name} order {order_id}: {e}")

            except Exception as e:
                print_error(f"  Failed to fetch orders from {exchange_name}: {e}")
                self.stats['errors'].append(f"Fetch orders {exchange_name}: {e}")

        self.stats['orders_cancelled'] = total_cancelled
        print_success(f"Cancelled/checked {total_cancelled} orders")

    async def clear_database_tables(self):
        """Clear all tables in monitoring schema"""
        # Get all tables in monitoring schema
        tables_query = """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'monitoring'
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """

        tables = await self.db_conn.fetch(tables_query)
        table_names = [row['table_name'] for row in tables]

        print_info(f"  Found {len(table_names)} tables to clear")

        total_deleted = 0

        for table_name in table_names:
            try:
                # Count rows before
                count_before = await self.db_conn.fetchval(
                    f"SELECT COUNT(*) FROM monitoring.{table_name}"
                )

                if count_before > 0:
                    if not self.dry_run:
                        # Truncate table (faster than DELETE)
                        await self.db_conn.execute(
                            f"TRUNCATE TABLE monitoring.{table_name} CASCADE"
                        )
                        print_success(f"    Cleared {table_name}: {count_before} rows deleted")
                    else:
                        print_info(f"    [DRY RUN] Would clear {table_name}: {count_before} rows")

                    total_deleted += count_before
                    self.stats['db_tables_cleared'] += 1
                else:
                    print_info(f"    {table_name}: already empty")

            except Exception as e:
                print_error(f"    Failed to clear {table_name}: {e}")
                self.stats['errors'].append(f"Clear table {table_name}: {e}")

        self.stats['db_rows_deleted'] = total_deleted
        print_success(f"Cleared {self.stats['db_tables_cleared']} tables ({total_deleted} rows)")

    def delete_log_files(self):
        """Delete all log files"""
        import glob
        import shutil

        log_dirs = [
            os.path.join(self.project_root, 'monitoring_logs'),
            os.path.join(self.project_root, 'logs'),
        ]

        log_files = [
            os.path.join(self.project_root, '*.log'),
            os.path.join(self.project_root, 'bot_output.log'),
            os.path.join(self.project_root, 'monitoring_output.log'),
        ]

        total_deleted = 0

        # Delete log directories
        for log_dir in log_dirs:
            if os.path.exists(log_dir):
                try:
                    file_count = len([f for f in os.listdir(log_dir) if os.path.isfile(os.path.join(log_dir, f))])

                    if not self.dry_run:
                        shutil.rmtree(log_dir)
                        # Recreate empty directory
                        os.makedirs(log_dir, exist_ok=True)
                        print_success(f"    Cleared {log_dir}: {file_count} files deleted")
                    else:
                        print_info(f"    [DRY RUN] Would clear {log_dir}: {file_count} files")

                    total_deleted += file_count
                except Exception as e:
                    print_error(f"    Failed to clear {log_dir}: {e}")
                    self.stats['errors'].append(f"Clear log dir {log_dir}: {e}")

        # Delete individual log files
        for pattern in log_files:
            for file_path in glob.glob(pattern):
                if os.path.isfile(file_path):
                    try:
                        if not self.dry_run:
                            os.remove(file_path)
                            print_success(f"    Deleted {os.path.basename(file_path)}")
                        else:
                            print_info(f"    [DRY RUN] Would delete {os.path.basename(file_path)}")

                        total_deleted += 1
                    except Exception as e:
                        print_error(f"    Failed to delete {file_path}: {e}")
                        self.stats['errors'].append(f"Delete log {file_path}: {e}")

        self.stats['log_files_deleted'] = total_deleted
        print_success(f"Deleted {total_deleted} log files")

    def clear_python_cache(self):
        """Clear Python cache files"""
        import glob
        import shutil

        total_deleted = 0

        # Delete __pycache__ directories
        pycache_dirs = []
        for root, dirs, files in os.walk(self.project_root):
            # Skip virtual environment
            if '.venv' in root or 'venv' in root or 'env' in root:
                continue

            if '__pycache__' in dirs:
                pycache_path = os.path.join(root, '__pycache__')
                pycache_dirs.append(pycache_path)

        for pycache_dir in pycache_dirs:
            try:
                file_count = len(os.listdir(pycache_dir))

                if not self.dry_run:
                    shutil.rmtree(pycache_dir)
                    rel_path = os.path.relpath(pycache_dir, self.project_root)
                    print_success(f"    Deleted {rel_path} ({file_count} files)")
                else:
                    rel_path = os.path.relpath(pycache_dir, self.project_root)
                    print_info(f"    [DRY RUN] Would delete {rel_path} ({file_count} files)")

                total_deleted += file_count
            except Exception as e:
                print_error(f"    Failed to delete {pycache_dir}: {e}")
                self.stats['errors'].append(f"Delete pycache {pycache_dir}: {e}")

        # Delete .pyc files
        pyc_files = []
        for root, dirs, files in os.walk(self.project_root):
            # Skip virtual environment
            if '.venv' in root or 'venv' in root or 'env' in root:
                continue

            for file in files:
                if file.endswith('.pyc'):
                    pyc_files.append(os.path.join(root, file))

        for pyc_file in pyc_files:
            try:
                if not self.dry_run:
                    os.remove(pyc_file)
                    rel_path = os.path.relpath(pyc_file, self.project_root)
                    print_success(f"    Deleted {rel_path}")
                else:
                    rel_path = os.path.relpath(pyc_file, self.project_root)
                    print_info(f"    [DRY RUN] Would delete {rel_path}")

                total_deleted += 1
            except Exception as e:
                print_error(f"    Failed to delete {pyc_file}: {e}")
                self.stats['errors'].append(f"Delete pyc {pyc_file}: {e}")

        self.stats['cache_files_deleted'] = total_deleted
        print_success(f"Deleted {total_deleted} cache files")

    async def verify_cleanup(self):
        """Verify that cleanup was successful"""
        print_info("Verifying cleanup...")

        all_clean = True

        # 1. Verify database tables are empty
        print_info("  Checking database tables...")
        tables_query = """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'monitoring'
            AND table_type = 'BASE TABLE'
        """
        tables = await self.db_conn.fetch(tables_query)

        non_empty_tables = []
        for row in tables:
            table_name = row['table_name']
            count = await self.db_conn.fetchval(
                f"SELECT COUNT(*) FROM monitoring.{table_name}"
            )
            if count > 0:
                non_empty_tables.append(f"{table_name} ({count} rows)")
                all_clean = False

        if non_empty_tables:
            print_error(f"    Found {len(non_empty_tables)} non-empty tables:")
            for table_info in non_empty_tables:
                print_error(f"      • {table_info}")
        else:
            print_success("    All database tables are empty ✓")

        # 2. Verify no positions on exchanges
        print_info("  Checking exchange positions...")
        for exchange_name, exchange in self.exchanges.items():
            try:
                positions = await exchange.fetch_positions()
                active_positions = [p for p in positions if p.get('contracts', 0) > 0]

                if active_positions:
                    print_error(f"    {exchange_name}: {len(active_positions)} positions still open:")
                    for pos in active_positions:
                        print_error(f"      • {pos['symbol']}: {pos['side']} {pos['contracts']}")
                    all_clean = False
                else:
                    print_success(f"    {exchange_name}: No positions ✓")
            except Exception as e:
                print_error(f"    Failed to verify {exchange_name} positions: {e}")
                all_clean = False

        # 3. Verify no orders on exchanges
        print_info("  Checking exchange orders...")
        for exchange_name, exchange in self.exchanges.items():
            try:
                orders = await exchange.fetch_open_orders()

                if orders:
                    print_error(f"    {exchange_name}: {len(orders)} orders still open:")
                    for order in orders:
                        print_error(f"      • {order['symbol']}: {order['type']} {order['id']}")
                    all_clean = False
                else:
                    print_success(f"    {exchange_name}: No orders ✓")
            except Exception as e:
                print_error(f"    Failed to verify {exchange_name} orders: {e}")
                all_clean = False

        print()
        if all_clean:
            print_success("✅ VERIFICATION PASSED - System is completely clean!")
        else:
            print_error("❌ VERIFICATION FAILED - Some items remain!")

        return all_clean

    def print_summary(self):
        """Print cleanup summary"""
        print_header("CLEANUP SUMMARY")

        print(f"{Colors.BOLD}Database:{Colors.END}")
        print(f"  Tables cleared:  {self.stats['db_tables_cleared']}")
        print(f"  Rows deleted:    {self.stats['db_rows_deleted']:,}")

        print(f"\n{Colors.BOLD}Exchanges:{Colors.END}")
        print(f"  Positions closed: {self.stats['positions_closed']}")
        print(f"  Orders cancelled: {self.stats['orders_cancelled']}")

        print(f"\n{Colors.BOLD}Files:{Colors.END}")
        print(f"  Log files deleted:   {self.stats['log_files_deleted']}")
        print(f"  Cache files deleted: {self.stats['cache_files_deleted']}")

        if self.stats['errors']:
            print(f"\n{Colors.BOLD}{Colors.RED}Errors ({len(self.stats['errors'])}){Colors.END}:")
            for i, error in enumerate(self.stats['errors'][:10], 1):
                print(f"  {i}. {error}")
            if len(self.stats['errors']) > 10:
                print(f"  ... and {len(self.stats['errors']) - 10} more")

        print()
        if self.dry_run:
            print_warning("This was a DRY RUN - no actual changes were made")
        else:
            print_success("Cleanup completed successfully!")

    async def cleanup(self):
        """Cleanup connections"""
        # Close exchange connections
        for exchange in self.exchanges.values():
            try:
                await exchange.close()
            except:
                pass

        # Close database connection
        if self.db_conn:
            try:
                await self.db_conn.close()
            except:
                pass


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Complete system cleanup - clears ALL data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run (preview only)
  python scripts/complete_cleanup.py --dry-run

  # Actually perform cleanup
  python scripts/complete_cleanup.py

WARNING: This is DESTRUCTIVE and will delete ALL data!
        """
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without actually making them'
    )

    args = parser.parse_args()

    # Create and run cleanup
    cleanup = CompleteCleanup(dry_run=args.dry_run)
    success = await cleanup.run()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
