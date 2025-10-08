#!/usr/bin/env python3
"""
Full cleanup script for trading bot
1. Kills all running bot processes
2. Verifies they are killed
3. Cleans monitoring schema in database
4. Closes all positions and cancels all orders on exchanges
"""

import os
import sys
import asyncio
import signal
import time
import subprocess
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

import asyncpg
from core.exchange_manager import ExchangeManager
from config.settings import config
from utils.logger import logger


class FullCleanup:
    """Comprehensive cleanup for trading bot"""
    
    def __init__(self):
        self.config = config
        self.db_pool = None
        
    async def run(self):
        """Run full cleanup sequence"""
        print("\n" + "="*60)
        print("🧹 FULL CLEANUP SCRIPT")
        print("="*60)
        
        # Step 1: Kill all bot processes
        print("\n📍 Step 1: Killing all bot processes...")
        killed = self.kill_all_bot_processes()
        print(f"   Killed {killed} process(es)")
        
        # Step 2: Verify processes are dead
        print("\n📍 Step 2: Verifying processes are killed...")
        time.sleep(2)
        remaining = self.check_running_processes()
        if remaining > 0:
            print(f"   ⚠️  WARNING: {remaining} process(es) still running!")
            force_kill = self.force_kill_remaining()
            print(f"   Force killed {force_kill} process(es)")
            time.sleep(1)
            remaining = self.check_running_processes()
            if remaining > 0:
                print(f"   ❌ ERROR: Still {remaining} process(es) running!")
                return False
        print(f"   ✅ All processes killed")
        
        # Step 3: Clean database
        print("\n📍 Step 3: Cleaning monitoring schema...")
        await self.clean_database()
        print(f"   ✅ Database cleaned")
        
        # Step 4: Clean exchanges
        print("\n📍 Step 4: Cleaning exchanges...")
        await self.clean_exchanges()
        print(f"   ✅ Exchanges cleaned")
        
        # Step 5: Remove lock file
        print("\n📍 Step 5: Removing lock file...")
        self.remove_lock_file()
        print(f"   ✅ Lock file removed")
        
        # Step 6: Clean logs
        print("\n📍 Step 6: Cleaning logs...")
        self.clean_logs()
        print(f"   ✅ Logs cleaned")
        
        print("\n" + "="*60)
        print("✅ CLEANUP COMPLETE!")
        print("="*60 + "\n")
        return True
    
    def kill_all_bot_processes(self) -> int:
        """Kill all running bot processes"""
        killed = 0
        try:
            # Find all python processes running main.py
            result = subprocess.run(
                ['pgrep', '-f', 'python.*main.py'],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                pids = [p.strip() for p in result.stdout.strip().split('\n') if p.strip()]
                current_pid = str(os.getpid())
                pids = [p for p in pids if p != current_pid]
                
                for pid in pids:
                    try:
                        os.kill(int(pid), signal.SIGTERM)
                        killed += 1
                        print(f"      Killed PID {pid}")
                    except Exception as e:
                        print(f"      Failed to kill PID {pid}: {e}")
        except Exception as e:
            print(f"      Error finding processes: {e}")
        
        return killed
    
    def force_kill_remaining(self) -> int:
        """Force kill remaining processes"""
        killed = 0
        try:
            result = subprocess.run(
                ['pgrep', '-f', 'python.*main.py'],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                pids = [p.strip() for p in result.stdout.strip().split('\n') if p.strip()]
                current_pid = str(os.getpid())
                pids = [p for p in pids if p != current_pid]
                
                for pid in pids:
                    try:
                        os.kill(int(pid), signal.SIGKILL)
                        killed += 1
                        print(f"      Force killed PID {pid}")
                    except Exception as e:
                        print(f"      Failed to force kill PID {pid}: {e}")
        except Exception as e:
            print(f"      Error in force kill: {e}")
        
        return killed
    
    def check_running_processes(self) -> int:
        """Check how many bot processes are running"""
        try:
            result = subprocess.run(
                ['pgrep', '-f', 'python.*main.py'],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                pids = [p.strip() for p in result.stdout.strip().split('\n') if p.strip()]
                current_pid = str(os.getpid())
                pids = [p for p in pids if p != current_pid]
                return len(pids)
            return 0
        except Exception as e:
            print(f"      Error checking processes: {e}")
            return 0
    
    async def clean_database(self):
        """Clean monitoring schema"""
        try:
            # Connect to database
            self.db_pool = await asyncpg.create_pool(
                host=os.getenv('DB_HOST', 'localhost'),
                port=int(os.getenv('DB_PORT', 5432)),
                user=os.getenv('DB_USER'),
                password=os.getenv('DB_PASSWORD'),
                database=os.getenv('DB_NAME'),
                min_size=1,
                max_size=5
            )
            
            async with self.db_pool.acquire() as conn:
                # Truncate all monitoring tables
                tables = [
                    'monitoring.positions',
                    'monitoring.trades',
                    'monitoring.processed_signals',
                    'monitoring.protection_events'
                ]
                
                for table in tables:
                    try:
                        await conn.execute(f'TRUNCATE {table} CASCADE')
                        print(f"      Truncated {table}")
                    except Exception as e:
                        print(f"      Error truncating {table}: {e}")
                
                # Reset sequences
                sequences = [
                    'monitoring.positions_id_seq',
                    'monitoring.trades_id_seq',
                    'monitoring.processed_signals_id_seq'
                ]
                
                for seq in sequences:
                    try:
                        await conn.execute(f'ALTER SEQUENCE {seq} RESTART WITH 1')
                        print(f"      Reset {seq}")
                    except Exception as e:
                        print(f"      Error resetting {seq}: {e}")
            
            await self.db_pool.close()
            
        except Exception as e:
            print(f"      Database error: {e}")
            raise
    
    async def clean_exchanges(self):
        """Close all positions and cancel all orders on exchanges"""
        exchanges = []
        try:
            # Binance
            if 'binance' in self.config.exchanges and self.config.exchanges['binance'].enabled:
                print(f"      Cleaning Binance...")
                binance = ExchangeManager(
                    'binance',
                    self.config.exchanges['binance'].__dict__
                )
                exchanges.append(binance)
                await self.clean_exchange(binance, 'Binance')
            
            # Bybit
            if 'bybit' in self.config.exchanges and self.config.exchanges['bybit'].enabled:
                print(f"      Cleaning Bybit...")
                bybit = ExchangeManager(
                    'bybit',
                    self.config.exchanges['bybit'].__dict__
                )
                exchanges.append(bybit)
                await self.clean_exchange(bybit, 'Bybit')
            
        except Exception as e:
            print(f"      Exchange error: {e}")
            raise
        finally:
            # Close all exchange connections
            for exchange in exchanges:
                try:
                    await exchange.close()
                except Exception as e:
                    print(f"      Error closing exchange: {e}")
    
    async def clean_exchange(self, exchange: ExchangeManager, name: str):
        """Clean specific exchange"""
        try:
            # Suppress Binance warning for fetching all orders
            if hasattr(exchange, 'exchange'):
                if hasattr(exchange.exchange, 'options'):
                    exchange.exchange.options['warnOnFetchOpenOrdersWithoutSymbol'] = False
            
            # Cancel all orders
            orders = await exchange.fetch_open_orders()
            if orders:
                print(f"         Found {len(orders)} open orders on {name}")
                for order in orders:
                    try:
                        # Handle both dict and OrderResult object
                        order_id = order.get('id') if hasattr(order, 'get') else order.id
                        symbol = order.get('symbol') if hasattr(order, 'get') else order.symbol
                        
                        await exchange.cancel_order(order_id, symbol)
                        print(f"         Cancelled order {order_id} ({symbol})")
                    except Exception as e:
                        print(f"         Failed to cancel order: {e}")
            else:
                print(f"         No open orders on {name}")
            
            # Close all positions
            positions = await exchange.fetch_positions()
            if positions:
                # Filter only ACTIVE positions (contracts > 0)
                active_positions = [p for p in positions if p.get('contracts', 0) > 0]
                
                if active_positions:
                    print(f"         Found {len(active_positions)} active positions on {name}")
                    for pos in active_positions:
                        try:
                            symbol = pos['symbol']
                            side = pos['side']  # 'long' or 'short'
                            amount = pos['contracts']
                            
                            # Determine close side (opposite of position side)
                            close_side = 'sell' if side == 'long' else 'buy'
                            
                            # Close position with market order
                            result = await exchange.create_order(
                                symbol=symbol,
                                type='market',
                                side=close_side,
                                amount=amount,
                                params={'reduceOnly': True}
                            )
                            print(f"         Closed {symbol}: {side} {amount} contracts")
                        except Exception as e:
                            print(f"         Failed to close {symbol}: {e}")
                else:
                    print(f"         No active positions on {name}")
            else:
                print(f"         No positions on {name}")
                
        except Exception as e:
            print(f"         Error cleaning {name}: {e}")
    
    def remove_lock_file(self):
        """Remove process lock file"""
        lock_file = '/tmp/trading_bot.lock'
        try:
            if os.path.exists(lock_file):
                os.remove(lock_file)
                print(f"      Removed {lock_file}")
            else:
                print(f"      Lock file not found")
        except Exception as e:
            print(f"      Error removing lock file: {e}")
    
    def clean_logs(self):
        """Clean log files"""
        try:
            logs_dir = project_root / 'logs'
            
            if not logs_dir.exists():
                print(f"      Logs directory not found")
                return
            
            # Delete all .log files in logs directory
            log_files = list(logs_dir.glob('*.log'))
            
            if not log_files:
                print(f"      No log files found")
                return
            
            deleted = 0
            for log_file in log_files:
                try:
                    log_file.unlink()
                    deleted += 1
                    print(f"      Deleted {log_file.name}")
                except Exception as e:
                    print(f"      Failed to delete {log_file.name}: {e}")
            
            print(f"      Deleted {deleted}/{len(log_files)} log files")
            
        except Exception as e:
            print(f"      Error cleaning logs: {e}")


async def main():
    """Main entry point"""
    cleanup = FullCleanup()
    
    # Ask for confirmation
    print("\n⚠️  WARNING: This will:")
    print("   - Kill all running bot processes")
    print("   - Delete all data from monitoring schema")
    print("   - Close all positions on exchanges")
    print("   - Cancel all orders on exchanges")
    print()
    
    # Check if running with --force flag
    if '--force' in sys.argv:
        print("🔥 --force flag detected, proceeding without confirmation...")
    else:
        confirm = input("Type 'YES' to proceed: ")
        if confirm != 'YES':
            print("❌ Aborted")
            return
    
    print()
    success = await cleanup.run()
    
    if success:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n❌ Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

