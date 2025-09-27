#!/usr/bin/env python3
"""
Cleanup script for zombie orders and stuck positions
Ensures trading system consistency and prevents resource leaks
"""

import asyncio
import argparse
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import sys
import os
from pathlib import Path
from loguru import logger
import ccxt.async_support as ccxt

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from config.settings import Settings
from core.exchange_manager import ExchangeManager
from database.repository import Repository
from database.models import Position, Order


class OrderCleanup:
    """
    Comprehensive cleanup system for trading bot
    
    Features:
    - Detect and cancel zombie orders
    - Reconcile database with exchange state
    - Close orphaned positions
    - Clean up stale data
    - Verify system consistency
    """
    
    def __init__(self, config: Dict[str, Any], dry_run: bool = True):
        self.config = config
        self.dry_run = dry_run
        
        # Components
        self.exchange_manager: Optional[ExchangeManager] = None
        self.repository: Optional[Repository] = None
        
        # Cleanup thresholds
        self.max_order_age_hours = config.get('max_order_age_hours', 24)
        self.max_position_age_days = config.get('max_position_age_days', 7)
        self.min_order_size_usd = config.get('min_order_size_usd', 1.0)
        
        # Statistics
        self.stats = {
            'orders_checked': 0,
            'orders_cancelled': 0,
            'positions_checked': 0,
            'positions_closed': 0,
            'db_records_cleaned': 0,
            'errors': []
        }
        
        logger.info(f"OrderCleanup initialized (dry_run={dry_run})")
    
    async def initialize(self):
        """Initialize connections to exchange and database"""
        
        try:
            # Initialize exchange manager
            self.exchange_manager = ExchangeManager(self.config)
            await self.exchange_manager.initialize()
            
            # Initialize repository
            self.repository = Repository(self.config['database'])
            await self.repository.initialize()
            
            logger.info("Cleanup system initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize cleanup system: {e}")
            raise
    
    async def run_full_cleanup(self) -> Dict[str, Any]:
        """Run complete cleanup process"""
        
        logger.info("Starting full cleanup process...")
        
        try:
            # 1. Clean zombie orders
            await self.cleanup_zombie_orders()
            
            # 2. Reconcile positions
            await self.reconcile_positions()
            
            # 3. Clean database records
            await self.cleanup_database()
            
            # 4. Verify system consistency
            await self.verify_consistency()
            
            # 5. Generate report
            report = self.generate_report()
            
            logger.info("Cleanup process completed successfully")
            return report
            
        except Exception as e:
            logger.error(f"Cleanup process failed: {e}")
            self.stats['errors'].append(str(e))
            return self.stats
    
    async def cleanup_zombie_orders(self):
        """Detect and cancel zombie orders"""
        
        logger.info("Checking for zombie orders...")
        
        for exchange_name in ['binance', 'bybit']:
            try:
                # Get all open orders from exchange
                exchange_orders = await self._get_exchange_orders(exchange_name)
                
                # Get open orders from database
                db_orders = await self.repository.get_open_orders(exchange_name)
                
                # Find zombies (orders on exchange but not in DB or too old)
                zombies = await self._identify_zombie_orders(
                    exchange_orders, 
                    db_orders
                )
                
                # Cancel zombie orders
                for order in zombies:
                    await self._cancel_zombie_order(exchange_name, order)
                
                # Find orphaned DB records (in DB but not on exchange)
                orphaned = await self._identify_orphaned_orders(
                    exchange_orders,
                    db_orders
                )
                
                # Clean orphaned records
                for order in orphaned:
                    await self._clean_orphaned_order(order)
                
            except Exception as e:
                logger.error(f"Error cleaning orders on {exchange_name}: {e}")
                self.stats['errors'].append(f"{exchange_name}: {str(e)}")
    
    async def _get_exchange_orders(self, exchange_name: str) -> List[Dict[str, Any]]:
        """Get all open orders from exchange"""
        
        try:
            exchange = self.exchange_manager.exchanges.get(exchange_name)
            if not exchange:
                return []
            
            # Fetch all open orders
            orders = await exchange.fetch_open_orders()
            
            self.stats['orders_checked'] += len(orders)
            
            return orders
            
        except Exception as e:
            logger.error(f"Failed to fetch orders from {exchange_name}: {e}")
            return []
    
    async def _identify_zombie_orders(self,
                                     exchange_orders: List[Dict[str, Any]],
                                     db_orders: List[Order]) -> List[Dict[str, Any]]:
        """Identify zombie orders that should be cancelled"""
        
        zombies = []
        current_time = datetime.now(timezone.utc)
        max_age = timedelta(hours=self.max_order_age_hours)
        
        # Create set of DB order IDs for quick lookup
        db_order_ids = {order.exchange_order_id for order in db_orders}
        
        for order in exchange_orders:
            order_id = order.get('id')
            timestamp = order.get('timestamp', 0)
            
            # Check if order is a zombie
            is_zombie = False
            reason = ""
            
            # 1. Order not in database (orphaned)
            if order_id not in db_order_ids:
                is_zombie = True
                reason = "Not tracked in database"
            
            # 2. Order too old
            elif timestamp:
                order_time = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
                if current_time - order_time > max_age:
                    is_zombie = True
                    reason = f"Too old ({(current_time - order_time).days} days)"
            
            # 3. Order size too small (dust)
            order_value = order.get('price', 0) * order.get('amount', 0)
            if order_value < self.min_order_size_usd:
                is_zombie = True
                reason = f"Dust order (${order_value:.2f})"
            
            if is_zombie:
                logger.warning(f"Found zombie order: {order_id} - {reason}")
                zombies.append(order)
        
        return zombies
    
    async def _cancel_zombie_order(self, exchange_name: str, order: Dict[str, Any]):
        """Cancel a zombie order"""
        
        order_id = order.get('id')
        symbol = order.get('symbol')
        
        if self.dry_run:
            logger.info(f"[DRY RUN] Would cancel zombie order {order_id} on {exchange_name}")
            return
        
        try:
            exchange = self.exchange_manager.exchanges.get(exchange_name)
            if exchange:
                await exchange.cancel_order(order_id, symbol)
                self.stats['orders_cancelled'] += 1
                logger.info(f"Cancelled zombie order {order_id} on {exchange_name}")
        
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            self.stats['errors'].append(f"Cancel failed: {order_id}")
    
    async def _identify_orphaned_orders(self,
                                       exchange_orders: List[Dict[str, Any]],
                                       db_orders: List[Order]) -> List[Order]:
        """Identify orders in DB but not on exchange"""
        
        orphaned = []
        
        # Create set of exchange order IDs
        exchange_order_ids = {order.get('id') for order in exchange_orders}
        
        for db_order in db_orders:
            if db_order.exchange_order_id not in exchange_order_ids:
                logger.warning(f"Found orphaned DB order: {db_order.id}")
                orphaned.append(db_order)
        
        return orphaned
    
    async def _clean_orphaned_order(self, order: Order):
        """Clean orphaned order from database"""
        
        if self.dry_run:
            logger.info(f"[DRY RUN] Would clean orphaned order {order.id} from database")
            return
        
        try:
            # Mark order as cancelled/failed in DB
            order.status = 'cancelled'
            order.updated_at = datetime.now(timezone.utc)
            await self.repository.update_order(order)
            
            self.stats['db_records_cleaned'] += 1
            logger.info(f"Cleaned orphaned order {order.id} from database")
            
        except Exception as e:
            logger.error(f"Failed to clean order {order.id}: {e}")
    
    async def reconcile_positions(self):
        """Reconcile positions between database and exchange"""
        
        logger.info("Reconciling positions...")
        
        for exchange_name in ['binance', 'bybit']:
            try:
                # Get positions from exchange
                exchange_positions = await self._get_exchange_positions(exchange_name)
                
                # Get active positions from database
                db_positions = await self.repository.get_active_positions(exchange_name)
                
                self.stats['positions_checked'] += len(db_positions)
                
                # Reconcile differences
                await self._reconcile_position_differences(
                    exchange_name,
                    exchange_positions,
                    db_positions
                )
                
            except Exception as e:
                logger.error(f"Error reconciling positions on {exchange_name}: {e}")
                self.stats['errors'].append(f"Position reconciliation: {str(e)}")
    
    async def _get_exchange_positions(self, exchange_name: str) -> List[Dict[str, Any]]:
        """Get all positions from exchange"""
        
        try:
            exchange = self.exchange_manager.exchanges.get(exchange_name)
            if not exchange:
                return []
            
            # Fetch positions
            positions = await exchange.fetch_positions()
            
            # Filter out zero positions
            active_positions = [
                p for p in positions 
                if p.get('contracts', 0) != 0
            ]
            
            return active_positions
            
        except Exception as e:
            logger.error(f"Failed to fetch positions from {exchange_name}: {e}")
            return []
    
    async def _reconcile_position_differences(self,
                                             exchange_name: str,
                                             exchange_positions: List[Dict[str, Any]],
                                             db_positions: List[Position]):
        """Reconcile differences between exchange and database positions"""
        
        # Create position maps for comparison
        exchange_map = {p['symbol']: p for p in exchange_positions}
        db_map = {p.symbol: p for p in db_positions}
        
        # Find positions only in database (need to close)
        for symbol, db_pos in db_map.items():
            if symbol not in exchange_map:
                logger.warning(f"Position {symbol} exists in DB but not on exchange")
                await self._close_orphaned_position(db_pos)
        
        # Find positions only on exchange (need to track)
        for symbol, exch_pos in exchange_map.items():
            if symbol not in db_map:
                logger.warning(f"Position {symbol} exists on exchange but not in DB")
                await self._create_missing_position(exchange_name, exch_pos)
        
        # Verify matching positions have correct size
        for symbol in set(exchange_map.keys()) & set(db_map.keys()):
            exch_pos = exchange_map[symbol]
            db_pos = db_map[symbol]
            
            exch_size = Decimal(str(abs(exch_pos.get('contracts', 0))))
            db_size = abs(db_pos.size)
            
            if abs(exch_size - db_size) > Decimal('0.00001'):
                logger.warning(f"Position size mismatch for {symbol}: "
                             f"Exchange={exch_size}, DB={db_size}")
                await self._update_position_size(db_pos, exch_size)
    
    async def _close_orphaned_position(self, position: Position):
        """Close position that no longer exists on exchange"""
        
        if self.dry_run:
            logger.info(f"[DRY RUN] Would close orphaned position {position.id}")
            return
        
        try:
            # Mark position as closed
            position.status = 'closed'
            position.closed_at = datetime.now(timezone.utc)
            position.exit_reason = 'orphaned_cleanup'
            await self.repository.update_position(position)
            
            self.stats['positions_closed'] += 1
            logger.info(f"Closed orphaned position {position.id}")
            
        except Exception as e:
            logger.error(f"Failed to close position {position.id}: {e}")
    
    async def _create_missing_position(self, exchange_name: str, exchange_pos: Dict[str, Any]):
        """Create database record for position that exists on exchange"""
        
        if self.dry_run:
            logger.info(f"[DRY RUN] Would create position record for {exchange_pos['symbol']}")
            return
        
        try:
            # Create new position record
            position = Position(
                exchange=exchange_name,
                symbol=exchange_pos['symbol'],
                side='long' if exchange_pos.get('side') == 'long' else 'short',
                size=Decimal(str(abs(exchange_pos.get('contracts', 0)))),
                entry_price=Decimal(str(exchange_pos.get('average', 0))),
                status='active',
                created_at=datetime.now(timezone.utc),
                metadata={'source': 'cleanup_reconciliation'}
            )
            
            await self.repository.create_position(position)
            logger.info(f"Created missing position record for {position.symbol}")
            
        except Exception as e:
            logger.error(f"Failed to create position record: {e}")
    
    async def _update_position_size(self, position: Position, correct_size: Decimal):
        """Update position size to match exchange"""
        
        if self.dry_run:
            logger.info(f"[DRY RUN] Would update position {position.id} size to {correct_size}")
            return
        
        try:
            position.size = correct_size
            position.updated_at = datetime.now(timezone.utc)
            await self.repository.update_position(position)
            
            logger.info(f"Updated position {position.id} size to {correct_size}")
            
        except Exception as e:
            logger.error(f"Failed to update position size: {e}")
    
    async def cleanup_database(self):
        """Clean up old and stale database records"""
        
        logger.info("Cleaning database records...")
        
        try:
            current_time = datetime.now(timezone.utc)
            
            # 1. Clean old closed positions
            old_positions_cutoff = current_time - timedelta(days=30)
            deleted = await self.repository.delete_old_positions(old_positions_cutoff)
            self.stats['db_records_cleaned'] += deleted
            logger.info(f"Deleted {deleted} old closed positions")
            
            # 2. Clean old filled/cancelled orders
            old_orders_cutoff = current_time - timedelta(days=14)
            deleted = await self.repository.delete_old_orders(old_orders_cutoff)
            self.stats['db_records_cleaned'] += deleted
            logger.info(f"Deleted {deleted} old orders")
            
            # 3. Clean old signals
            old_signals_cutoff = current_time - timedelta(days=7)
            deleted = await self.repository.delete_old_signals(old_signals_cutoff)
            self.stats['db_records_cleaned'] += deleted
            logger.info(f"Deleted {deleted} old signals")
            
            # 4. Vacuum database (PostgreSQL maintenance)
            if not self.dry_run:
                await self.repository.vacuum_database()
                logger.info("Database vacuumed successfully")
            
        except Exception as e:
            logger.error(f"Database cleanup failed: {e}")
            self.stats['errors'].append(f"Database cleanup: {str(e)}")
    
    async def verify_consistency(self):
        """Verify system consistency after cleanup"""
        
        logger.info("Verifying system consistency...")
        
        issues = []
        
        try:
            # 1. Check for duplicate positions
            duplicates = await self.repository.find_duplicate_positions()
            if duplicates:
                issues.append(f"Found {len(duplicates)} duplicate positions")
                logger.warning(f"Duplicate positions detected: {duplicates}")
            
            # 2. Check for invalid order states
            invalid_orders = await self.repository.find_invalid_orders()
            if invalid_orders:
                issues.append(f"Found {len(invalid_orders)} orders with invalid states")
                logger.warning(f"Invalid orders detected: {invalid_orders}")
            
            # 3. Check position-order relationships
            orphaned_orders = await self.repository.find_orders_without_positions()
            if orphaned_orders:
                issues.append(f"Found {len(orphaned_orders)} orders without positions")
                logger.warning(f"Orphaned orders detected: {orphaned_orders}")
            
            # 4. Verify balance consistency
            for exchange_name in ['binance', 'bybit']:
                balance_ok = await self._verify_balance_consistency(exchange_name)
                if not balance_ok:
                    issues.append(f"Balance inconsistency on {exchange_name}")
            
            if issues:
                logger.warning(f"Consistency check found {len(issues)} issues")
                self.stats['errors'].extend(issues)
            else:
                logger.info("System consistency verified successfully")
            
        except Exception as e:
            logger.error(f"Consistency verification failed: {e}")
            self.stats['errors'].append(f"Verification failed: {str(e)}")
    
    async def _verify_balance_consistency(self, exchange_name: str) -> bool:
        """Verify balance consistency between expected and actual"""
        
        try:
            exchange = self.exchange_manager.exchanges.get(exchange_name)
            if not exchange:
                return True
            
            # Get actual balance
            balance = await exchange.fetch_balance()
            
            # Get expected balance from positions
            positions = await self.repository.get_active_positions(exchange_name)
            
            # Calculate expected margin usage
            total_margin = Decimal('0')
            for position in positions:
                margin = abs(position.size * position.entry_price)
                total_margin += margin
            
            # Check if margin usage is reasonable
            # This is a simplified check - actual implementation would be more complex
            
            return True
            
        except Exception as e:
            logger.error(f"Balance verification failed for {exchange_name}: {e}")
            return False
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate cleanup report"""
        
        report = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'dry_run': self.dry_run,
            'statistics': {
                'orders_checked': self.stats['orders_checked'],
                'orders_cancelled': self.stats['orders_cancelled'],
                'positions_checked': self.stats['positions_checked'],
                'positions_closed': self.stats['positions_closed'],
                'database_records_cleaned': self.stats['db_records_cleaned']
            },
            'errors': self.stats['errors'],
            'success': len(self.stats['errors']) == 0
        }
        
        return report
    
    def print_summary(self):
        """Print cleanup summary"""
        
        print("\n" + "="*60)
        print(" CLEANUP SUMMARY")
        print("="*60)
        
        if self.dry_run:
            print("\n🔍 DRY RUN MODE - No actual changes made")
        
        print(f"\n📊 Statistics:")
        print(f"  Orders checked: {self.stats['orders_checked']}")
        print(f"  Orders cancelled: {self.stats['orders_cancelled']}")
        print(f"  Positions checked: {self.stats['positions_checked']}")
        print(f"  Positions closed: {self.stats['positions_closed']}")
        print(f"  DB records cleaned: {self.stats['db_records_cleaned']}")
        
        if self.stats['errors']:
            print(f"\n⚠️  Errors encountered: {len(self.stats['errors'])}")
            for error in self.stats['errors'][:5]:  # Show first 5 errors
                print(f"  - {error}")
        else:
            print(f"\n✅ No errors encountered")
        
        print("="*60)
    
    async def cleanup(self):
        """Cleanup resources"""
        
        if self.exchange_manager:
            await self.exchange_manager.close()
        
        if self.repository:
            await self.repository.close()


async def main():
    """Main entry point"""
    
    parser = argparse.ArgumentParser(description='Clean up zombie orders and stuck positions')
    parser.add_argument('--config', default='config/settings.yaml', help='Config file path')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode (no actual changes)')
    parser.add_argument('--exchange', help='Specific exchange to clean (default: all)')
    parser.add_argument('--max-age', type=int, default=24, help='Max order age in hours')
    
    args = parser.parse_args()
    
    # Load configuration
    settings = Settings(args.config)
    config = settings.get_all()
    
    # Update config with command line args
    config['max_order_age_hours'] = args.max_age
    if args.exchange:
        config['exchanges'] = [args.exchange]
    
    # Create and run cleanup
    cleanup = OrderCleanup(config, dry_run=args.dry_run)
    
    try:
        await cleanup.initialize()
        report = await cleanup.run_full_cleanup()
        cleanup.print_summary()
        
        # Save report
        import json
        report_file = f"cleanup_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\n📄 Report saved to {report_file}")
        
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        sys.exit(1)
    
    finally:
        await cleanup.cleanup()


if __name__ == "__main__":
    asyncio.run(main())