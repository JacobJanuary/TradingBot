"""
Smart Trailing Stop Diagnostic Monitor
========================================
Comprehensive live monitoring and diagnostics for Trailing Stop module

IMPORTANT: Uses DATABASE as source of truth (not in-memory TS managers)
This ensures we check the actual system state, not create new instances.

Features:
- Database-based TS state monitoring (has_trailing_stop, trailing_activated)
- Database consistency checks
- Exchange order verification
- Performance metrics
- Issue detection and reporting
- Real-time progress reporting
"""

import asyncio
import json
import time
import sys
from datetime import datetime, timezone
from collections import defaultdict
from typing import Dict, List, Optional, Any
from decimal import Decimal
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

import logging
from config.settings import config as settings
from core.exchange_manager import ExchangeManager
from database.repository import Repository
# NOTE: No longer importing SmartTrailingStopManager - using DB as source of truth

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'logs/ts_diagnostic_{int(time.time())}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TSMonitor:
    """Trailing Stop Diagnostic Monitor"""

    def __init__(self, monitoring_duration_minutes: int = 15):
        self.duration_minutes = monitoring_duration_minutes
        self.start_time = None
        self.end_time = None

        # Core components
        self.exchanges: Dict[str, ExchangeManager] = {}
        # NOTE: No longer creating trailing_managers - using DB as source of truth
        self.repository: Optional[Repository] = None

        # Monitoring data
        self.stats = {
            'ts_instances': {},           # {symbol: {created_at, state, updates_count}}
            'price_updates': defaultdict(list),  # {symbol: [(timestamp, price)]}
            'activations': [],            # List of activation events
            'sl_updates': [],             # List of SL update events
            'db_snapshots': [],           # Periodic DB state snapshots
            'exchange_snapshots': [],     # Periodic exchange state snapshots
            'errors': [],                 # Errors detected
            'websocket_events': defaultdict(int),  # Event counts
            'performance': {
                'update_price_calls': 0,
                'update_price_duration_ms': [],
                'db_queries': 0,
                'db_query_duration_ms': [],
                'exchange_calls': 0,
                'exchange_call_duration_ms': []
            }
        }

        # Issues detected
        self.issues = []

        # Control
        self.running = False

    async def initialize(self):
        """Initialize monitoring components"""
        try:
            logger.info("="*80)
            logger.info("SMART TRAILING STOP DIAGNOSTIC MONITOR")
            logger.info("="*80)

            # Initialize database
            logger.info("Initializing database connection...")
            db_config = {
                'host': settings.database.host,
                'port': settings.database.port,
                'database': settings.database.database,
                'user': settings.database.user,
                'password': settings.database.password,
                'pool_size': 5,
                'max_overflow': 10
            }
            self.repository = Repository(db_config)
            await self.repository.initialize()
            logger.info("✅ Database connected")

            # Initialize exchanges
            logger.info("Initializing exchanges...")
            for name, config in settings.exchanges.items():
                if not config.enabled:
                    continue

                exchange = ExchangeManager(name, config.__dict__)
                await exchange.initialize()
                self.exchanges[name] = exchange
                logger.info(f"✅ {name.capitalize()} exchange ready")

            if not self.exchanges:
                raise Exception("No exchanges available")

            # NOTE: We do NOT create new TS managers here
            # Instead, we check the database directly (source of truth)
            # Creating new managers would show 0 TS instances (false negative)
            logger.info("ℹ️  Trailing Stop verification will use DATABASE as source of truth")
            logger.info("   (Not creating new TS managers to avoid false negatives)")

            logger.info("="*80)
            logger.info("✅ INITIALIZATION COMPLETE")
            logger.info("="*80)

        except Exception as e:
            logger.error(f"Initialization failed: {e}", exc_info=True)
            raise

    async def run_diagnostics(self):
        """Main diagnostic loop"""
        try:
            self.start_time = time.time()
            self.end_time = self.start_time + (self.duration_minutes * 60)
            self.running = True

            logger.info(f"\n{'='*80}")
            logger.info(f"Starting {self.duration_minutes}-minute monitoring session")
            logger.info(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"{'='*80}\n")

            # Start monitoring tasks
            tasks = [
                self._monitor_trailing_stops(),
                self._monitor_database(),
                self._monitor_exchange_orders(),
                self._check_consistency(),
                self._print_progress()
            ]

            # Run all tasks concurrently
            await asyncio.gather(*tasks)

            # Generate final report
            logger.info("\n" + "="*80)
            logger.info("Monitoring complete - Generating report...")
            logger.info("="*80 + "\n")

            await self._generate_final_report()

        except KeyboardInterrupt:
            logger.info("\n\nMonitoring interrupted by user")
            await self._generate_final_report()
        except Exception as e:
            logger.error(f"Diagnostic error: {e}", exc_info=True)
        finally:
            self.running = False

    async def _monitor_trailing_stops(self):
        """Monitor trailing stop state via DATABASE (source of truth)"""
        logger.info("🔍 Starting TS state monitoring via DATABASE...")
        logger.info("   Note: Using DB as source of truth (not in-memory TS managers)")

        while self.running and time.time() < self.end_time:
            try:
                # Get positions from database
                positions = await self.repository.get_open_positions()

                # Track TS instances from DB
                for pos in positions:
                    symbol = pos['symbol']
                    has_ts = pos.get('has_trailing_stop', False)
                    trailing_activated = pos.get('trailing_activated', False)

                    # Track instance if not yet tracked
                    if symbol not in self.stats['ts_instances'] and has_ts:
                        self.stats['ts_instances'][symbol] = {
                            'exchange': pos['exchange'],
                            'created_at': datetime.now().isoformat(),
                            'side': pos['side'],
                            'entry_price': float(pos['entry_price']) if pos['entry_price'] else 0,
                            'state_history': []
                        }
                        logger.info(f"📊 Detected TS instance from DB: {symbol} ({pos['side']})")

                    # Track activations from DB
                    if has_ts and trailing_activated:
                        # Check if we already recorded this activation
                        already_recorded = any(
                            a['symbol'] == symbol for a in self.stats['activations']
                        )
                        if not already_recorded:
                            self.stats['activations'].append({
                                'symbol': symbol,
                                'timestamp': datetime.now().isoformat(),
                                'activation_price': float(pos['current_price']) if pos['current_price'] else 0,
                                'entry_price': float(pos['entry_price']) if pos['entry_price'] else 0
                            })
                            logger.info(f"✅ {symbol}: TS ACTIVATED (detected via DB)")

                await asyncio.sleep(5)  # Check every 5 seconds

            except Exception as e:
                logger.error(f"Error monitoring TS via DB: {e}")
                self.stats['errors'].append({
                    'timestamp': datetime.now().isoformat(),
                    'source': 'ts_monitor_db',
                    'error': str(e)
                })
                await asyncio.sleep(10)

    async def _monitor_database(self):
        """Monitor database state"""
        logger.info("🗄️  Starting database monitoring...")

        while self.running and time.time() < self.end_time:
            try:
                start = time.time()

                # Fetch positions from database
                positions = await self.repository.get_open_positions()

                duration_ms = (time.time() - start) * 1000
                self.stats['performance']['db_queries'] += 1
                self.stats['performance']['db_query_duration_ms'].append(duration_ms)

                # Create snapshot
                snapshot = {
                    'timestamp': datetime.now().isoformat(),
                    'positions_count': len(positions),
                    'positions': []
                }

                for pos in positions:
                    snapshot['positions'].append({
                        'id': pos['id'],
                        'symbol': pos['symbol'],
                        'exchange': pos['exchange'],
                        'side': pos['side'],
                        'entry_price': pos['entry_price'],
                        'current_price': pos['current_price'],
                        'has_trailing_stop': pos.get('has_trailing_stop', False),
                        'trailing_activated': pos.get('trailing_activated', False),
                        'stop_loss_price': pos.get('stop_loss_price'),
                        'stop_loss_order_id': pos.get('stop_loss_order_id')
                    })

                self.stats['db_snapshots'].append(snapshot)

                # Log summary
                ts_count = sum(1 for p in positions if p.get('has_trailing_stop', False))
                activated_count = sum(1 for p in positions if p.get('trailing_activated', False))
                logger.debug(
                    f"📊 DB: {len(positions)} positions, "
                    f"{ts_count} with TS, {activated_count} activated"
                )

                await asyncio.sleep(30)  # Check every 30 seconds

            except Exception as e:
                logger.error(f"Error monitoring database: {e}")
                self.stats['errors'].append({
                    'timestamp': datetime.now().isoformat(),
                    'source': 'db_monitor',
                    'error': str(e)
                })
                await asyncio.sleep(30)

    async def _monitor_exchange_orders(self):
        """Monitor exchange SL orders"""
        logger.info("🔄 Starting exchange order monitoring...")

        while self.running and time.time() < self.end_time:
            try:
                # Get DB positions to know what to check
                positions = await self.repository.get_open_positions()

                for exchange_name, exchange in self.exchanges.items():
                    start = time.time()

                    # Get exchange positions
                    exchange_positions = await exchange.fetch_positions()

                    duration_ms = (time.time() - start) * 1000
                    self.stats['performance']['exchange_calls'] += 1
                    self.stats['performance']['exchange_call_duration_ms'].append(duration_ms)

                    # Create snapshot
                    snapshot = {
                        'timestamp': datetime.now().isoformat(),
                        'exchange': exchange_name,
                        'positions': []
                    }

                    for pos_dict in exchange_positions:
                        # Get contracts/size
                        size = pos_dict.get('contracts', pos_dict.get('contractSize', 0))
                        if size == 0:
                            continue

                        # Get open orders for this symbol
                        symbol = pos_dict.get('symbol', '')
                        try:
                            orders = await exchange.fetch_open_orders(symbol)
                            stop_orders = [o for o in orders if o.get('type', '').lower() in ['stop_market', 'stop', 'stop_loss']]

                            snapshot['positions'].append({
                                'symbol': symbol,
                                'side': pos_dict.get('side', ''),
                                'size': size,
                                'unrealizedPnl': pos_dict.get('unrealizedPnl', 0),
                                'stop_orders_count': len(stop_orders),
                                'stop_orders': [{
                                    'id': o.get('id'),
                                    'stopPrice': o.get('stopPrice'),
                                    'amount': o.get('amount'),
                                    'reduceOnly': o.get('reduceOnly', False)
                                } for o in stop_orders]
                            })

                        except Exception as e:
                            logger.warning(f"Failed to fetch orders for {symbol}: {e}")

                    self.stats['exchange_snapshots'].append(snapshot)

                    logger.debug(f"📊 Exchange {exchange_name}: {len(snapshot['positions'])} positions checked")

                await asyncio.sleep(60)  # Check every minute

            except Exception as e:
                logger.error(f"Error monitoring exchange: {e}")
                self.stats['errors'].append({
                    'timestamp': datetime.now().isoformat(),
                    'source': 'exchange_monitor',
                    'error': str(e)
                })
                await asyncio.sleep(60)

    async def _check_consistency(self):
        """Check consistency using DATABASE as source of truth"""
        logger.info("🔍 Starting consistency checks (DB-based)...")

        while self.running and time.time() < self.end_time:
            try:
                # Wait for some data to accumulate
                await asyncio.sleep(120)  # First check after 2 minutes

                # Get current states from DB
                db_positions = await self.repository.get_open_positions()

                # Check for DB positions without TS flag
                missing_ts_count = 0
                for pos in db_positions:
                    has_ts = pos.get('has_trailing_stop', False)

                    if not has_ts:
                        missing_ts_count += 1
                        issue = {
                            'severity': 'HIGH',
                            'type': 'missing_ts_flag',
                            'symbol': pos['symbol'],
                            'exchange': pos['exchange'],
                            'description': f'DB position exists but has_trailing_stop=False',
                            'timestamp': datetime.now().isoformat()
                        }
                        self.issues.append(issue)
                        logger.warning(f"⚠️ ISSUE: {issue['description']}")

                # Log summary
                total_positions = len(db_positions)
                with_ts = sum(1 for p in db_positions if p.get('has_trailing_stop', False))
                logger.info(f"📊 Consistency check: {with_ts}/{total_positions} positions have TS flag")

                if missing_ts_count > 0:
                    logger.warning(f"⚠️ Found {missing_ts_count} positions without TS flag")

                await asyncio.sleep(120)  # Check every 2 minutes

            except Exception as e:
                logger.error(f"Error in consistency check: {e}")
                self.stats['errors'].append({
                    'timestamp': datetime.now().isoformat(),
                    'source': 'consistency_check',
                    'error': str(e)
                })
                await asyncio.sleep(120)

    async def _print_progress(self):
        """Print real-time progress"""
        logger.info("📊 Starting progress reporter...")

        last_print = time.time()

        while self.running and time.time() < self.end_time:
            try:
                now = time.time()

                # Print every minute
                if now - last_print >= 60:
                    elapsed = int((now - self.start_time) / 60)
                    remaining = self.duration_minutes - elapsed

                    print(f"\n{'='*80}")
                    print(f"⏱️  Minute {elapsed} of {self.duration_minutes} (remaining: {remaining} min)")
                    print(f"{'='*80}")
                    print(f"📊 TS Instances: {len(self.stats['ts_instances'])}")
                    print(f"✅ Activations: {len(self.stats['activations'])}")
                    print(f"🔄 SL Updates: {len(self.stats['sl_updates'])}")
                    print(f"🗄️  DB Snapshots: {len(self.stats['db_snapshots'])}")
                    print(f"🔄 Exchange Snapshots: {len(self.stats['exchange_snapshots'])}")
                    print(f"⚠️  Issues Found: {len(self.issues)}")
                    print(f"❌ Errors: {len(self.stats['errors'])}")

                    if self.stats['errors']:
                        print(f"\nRecent Errors:")
                        for error in self.stats['errors'][-3:]:
                            print(f"  - [{error['source']}] {error['error']}")

                    if self.issues:
                        print(f"\nRecent Issues:")
                        for issue in self.issues[-3:]:
                            print(f"  - [{issue['severity']}] {issue['description']}")

                    print(f"{'='*80}\n")

                    last_print = now

                await asyncio.sleep(10)

            except Exception as e:
                logger.error(f"Error in progress reporter: {e}")
                await asyncio.sleep(30)

    async def _generate_final_report(self):
        """Generate comprehensive final report"""
        try:
            # Prepare report data
            report = {
                'metadata': {
                    'monitoring_duration_minutes': self.duration_minutes,
                    'start_time': datetime.fromtimestamp(self.start_time).isoformat() if self.start_time else None,
                    'end_time': datetime.fromtimestamp(self.end_time).isoformat() if self.end_time else None,
                    'actual_duration_seconds': int(time.time() - self.start_time) if self.start_time else 0,
                    'generated_at': datetime.now().isoformat()
                },
                'summary': {
                    'ts_instances_tracked': len(self.stats['ts_instances']),
                    'activations': len(self.stats['activations']),
                    'sl_updates': len(self.stats['sl_updates']),
                    'db_snapshots': len(self.stats['db_snapshots']),
                    'exchange_snapshots': len(self.stats['exchange_snapshots']),
                    'issues_found': len(self.issues),
                    'errors': len(self.stats['errors'])
                },
                'detailed_stats': self.stats,
                'issues': self.issues,
                'analysis': self._analyze_data(),
                'recommendations': self._generate_recommendations()
            }

            # Save to JSON
            filename = f'ts_diagnostic_report_{int(time.time())}.json'
            with open(filename, 'w') as f:
                json.dump(report, f, indent=2, default=str)

            logger.info(f"\n✅ Full report saved to: {filename}")

            # Print summary to console
            self._print_summary(report)

        except Exception as e:
            logger.error(f"Failed to generate report: {e}", exc_info=True)

    def _analyze_data(self) -> Dict[str, Any]:
        """Analyze collected data"""
        analysis = {
            'ts_functionality': {},
            'performance': {},
            'consistency': {}
        }

        # Analyze TS functionality
        analysis['ts_functionality'] = {
            'instances_created': len(self.stats['ts_instances']),
            'activations': len(self.stats['activations']),
            'activation_rate': (
                len(self.stats['activations']) / len(self.stats['ts_instances'])
                if self.stats['ts_instances'] else 0
            ),
            'symbols_with_ts': list(self.stats['ts_instances'].keys())
        }

        # Analyze performance
        perf = self.stats['performance']
        analysis['performance'] = {
            'total_db_queries': perf['db_queries'],
            'avg_db_query_ms': (
                sum(perf['db_query_duration_ms']) / len(perf['db_query_duration_ms'])
                if perf['db_query_duration_ms'] else 0
            ),
            'total_exchange_calls': perf['exchange_calls'],
            'avg_exchange_call_ms': (
                sum(perf['exchange_call_duration_ms']) / len(perf['exchange_call_duration_ms'])
                if perf['exchange_call_duration_ms'] else 0
            )
        }

        # Analyze consistency
        analysis['consistency'] = {
            'orphan_ts_instances': len([i for i in self.issues if i['type'] == 'orphan_ts_instance']),
            'missing_ts_instances': len([i for i in self.issues if i['type'] == 'missing_ts_instance']),
            'state_mismatches': len([i for i in self.issues if i['type'] == 'state_mismatch']),
            'sl_price_mismatches': len([i for i in self.issues if i['type'] == 'sl_price_mismatch'])
        }

        return analysis

    def _generate_recommendations(self) -> List[str]:
        """Generate recommendations based on findings"""
        recommendations = []

        # Check for critical issues
        critical_issues = [i for i in self.issues if i.get('severity') == 'CRITICAL']
        if critical_issues:
            recommendations.append(
                f"CRITICAL: Found {len(critical_issues)} critical issues - immediate action required!"
            )

        # Check for missing TS instances
        missing_ts = [i for i in self.issues if i['type'] == 'missing_ts_instance']
        if missing_ts:
            recommendations.append(
                f"Found {len(missing_ts)} positions without TS instances - verify TS initialization logic"
            )

        # Check for state mismatches
        state_mismatch = [i for i in self.issues if i['type'] == 'state_mismatch']
        if state_mismatch:
            recommendations.append(
                f"Found {len(state_mismatch)} state mismatches between TS and DB - implement state persistence"
            )

        # Check activation rate
        if self.stats['ts_instances']:
            activation_rate = len(self.stats['activations']) / len(self.stats['ts_instances'])
            if activation_rate == 0:
                recommendations.append(
                    "No TS activations detected - verify activation conditions and profit thresholds"
                )

        # Check for errors
        if len(self.stats['errors']) > 5:
            recommendations.append(
                f"High error rate detected ({len(self.stats['errors'])} errors) - investigate error causes"
            )

        if not recommendations:
            recommendations.append("✅ No critical issues detected - TS module functioning normally")

        return recommendations

    def _print_summary(self, report: Dict):
        """Print report summary to console"""
        print(f"\n{'='*80}")
        print("📊 DIAGNOSTIC REPORT SUMMARY")
        print(f"{'='*80}\n")

        summary = report['summary']
        print(f"TS Instances Tracked: {summary['ts_instances_tracked']}")
        print(f"Activations: {summary['activations']}")
        print(f"SL Updates: {summary['sl_updates']}")
        print(f"Issues Found: {summary['issues_found']}")
        print(f"Errors: {summary['errors']}")

        print(f"\n{'='*80}")
        print("🔍 ANALYSIS")
        print(f"{'='*80}\n")

        analysis = report['analysis']

        print("TS Functionality:")
        for key, value in analysis['ts_functionality'].items():
            if key != 'symbols_with_ts':
                print(f"  - {key}: {value}")

        print("\nPerformance:")
        for key, value in analysis['performance'].items():
            print(f"  - {key}: {value:.2f}" if isinstance(value, float) else f"  - {key}: {value}")

        print("\nConsistency:")
        for key, value in analysis['consistency'].items():
            print(f"  - {key}: {value}")

        print(f"\n{'='*80}")
        print("💡 RECOMMENDATIONS")
        print(f"{'='*80}\n")

        for i, rec in enumerate(report['recommendations'], 1):
            print(f"{i}. {rec}")

        print(f"\n{'='*80}\n")

    async def cleanup(self):
        """Cleanup resources"""
        logger.info("Cleaning up...")

        for exchange in self.exchanges.values():
            try:
                await exchange.close()
            except Exception as e:
                logger.error(f"Error closing exchange: {e}")

        if self.repository:
            try:
                await self.repository.close()
            except Exception as e:
                logger.error(f"Error closing repository: {e}")


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Smart Trailing Stop Diagnostic Monitor')
    parser.add_argument('--duration', type=int, default=15, help='Monitoring duration in minutes (default: 15)')
    args = parser.parse_args()

    monitor = TSMonitor(monitoring_duration_minutes=args.duration)

    try:
        await monitor.initialize()
        await monitor.run_diagnostics()
    except Exception as e:
        logger.critical(f"Monitor failed: {e}", exc_info=True)
    finally:
        await monitor.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nMonitoring interrupted by user")
    except Exception as e:
        print(f"\nFatal error: {e}")
