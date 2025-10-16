#!/usr/bin/env python3
"""
Zombie Manager Diagnostics and Monitoring Tool

КРИТИЧЕСКИ ВАЖНО:
- Этот скрипт ТОЛЬКО наблюдает и анализирует
- НЕ изменяет поведение бота
- НЕ отменяет ордера
- НЕ модифицирует данные

Использование:
    python zombie_manager_monitor.py --duration 10 --mode dry-run

Режимы:
    --mode dry-run: Только мониторинг и анализ (по умолчанию)
    --mode verify: Снять snapshots и проверить корректность
    --duration: Длительность мониторинга в минутах (по умолчанию 10)
"""

import asyncio
import ccxt.async_support as ccxt
import logging
import time
import json
import argparse
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Set, Optional, Any
from dataclasses import dataclass, asdict, field
from decimal import Decimal
import os
from dotenv import load_dotenv
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'logs/zombie_diagnostics_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()


@dataclass
class OrderSnapshot:
    """Snapshot of a single order"""
    order_id: str
    symbol: str
    exchange: str
    order_type: str
    side: str
    status: str
    amount: float
    price: float
    timestamp: int
    reduce_only: bool = False
    close_on_trigger: bool = False
    stop_order_type: Optional[str] = None
    position_idx: int = 0
    client_order_id: Optional[str] = None
    order_list_id: Optional[int] = None

    # Analysis metadata
    snapshot_time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class PositionSnapshot:
    """Snapshot of a single position"""
    symbol: str
    exchange: str
    side: str
    contracts: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    position_idx: int = 0
    leverage: float = 1.0

    # Analysis metadata
    snapshot_time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ZombieDeletionEvent:
    """Event of zombie order deletion detected from logs"""
    timestamp: str
    order_id: str
    symbol: str
    order_type: str
    side: str
    reason: str
    zombie_type: str
    exchange: str
    source: str  # 'log' or 'snapshot_diff'


@dataclass
class DiagnosticIssue:
    """Issue detected during diagnostics"""
    severity: str  # 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'
    issue_type: str
    description: str
    evidence: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ZombieManagerDiagnostics:
    """
    Comprehensive diagnostics tool for Zombie Manager

    Features:
    - Takes snapshots of orders and positions
    - Monitors logs in real-time
    - Detects deleted orders
    - Verifies correctness of deletions
    - Generates detailed reports
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize diagnostics

        Args:
            config: Configuration with exchange credentials and settings
        """
        self.config = config
        self.exchanges: Dict[str, ccxt.Exchange] = {}

        # Snapshots
        self.snapshots = {
            'before': {
                'orders': {},  # {exchange_name: [OrderSnapshot]}
                'positions': {},  # {exchange_name: [PositionSnapshot]}
                'timestamp': None
            },
            'after': {
                'orders': {},
                'positions': {},
                'timestamp': None
            }
        }

        # Events and issues
        self.deletion_events: List[ZombieDeletionEvent] = []
        self.log_events: List[Dict[str, Any]] = []
        self.issues: List[DiagnosticIssue] = []

        # Statistics
        self.stats = {
            'total_orders_before': 0,
            'total_orders_after': 0,
            'total_positions_before': 0,
            'total_positions_after': 0,
            'orders_deleted': 0,
            'orders_added': 0,
            'positions_closed': 0,
            'positions_opened': 0
        }

        logger.info("ZombieManagerDiagnostics initialized")

    async def initialize_exchanges(self):
        """Initialize exchange connections"""
        logger.info("🔗 Initializing exchange connections...")

        # Binance
        if self.config.get('binance_enabled'):
            try:
                self.exchanges['binance'] = ccxt.binanceusdm({
                    'apiKey': os.getenv('BINANCE_API_KEY'),
                    'secret': os.getenv('BINANCE_API_SECRET'),
                    'enableRateLimit': True,
                    'options': {
                        'defaultType': 'future',
                        'adjustForTimeDifference': True,
                        'warnOnFetchOpenOrdersWithoutSymbol': False,  # Suppress warning
                    }
                })

                if os.getenv('BINANCE_TESTNET', 'false').lower() == 'true':
                    self.exchanges['binance'].set_sandbox_mode(True)
                    logger.info("  ✅ Binance TESTNET connected")
                else:
                    logger.info("  ✅ Binance MAINNET connected")

            except Exception as e:
                logger.error(f"  ❌ Failed to initialize Binance: {e}")

        # Bybit
        if self.config.get('bybit_enabled'):
            try:
                self.exchanges['bybit'] = ccxt.bybit({
                    'apiKey': os.getenv('BYBIT_API_KEY'),
                    'secret': os.getenv('BYBIT_API_SECRET'),
                    'enableRateLimit': True,
                    'options': {
                        'defaultType': 'swap',
                    }
                })

                if os.getenv('BYBIT_TESTNET', 'false').lower() == 'true':
                    self.exchanges['bybit'].set_sandbox_mode(True)
                    logger.info("  ✅ Bybit TESTNET connected")
                else:
                    logger.info("  ✅ Bybit MAINNET connected")

            except Exception as e:
                logger.error(f"  ❌ Failed to initialize Bybit: {e}")

        if not self.exchanges:
            raise RuntimeError("No exchanges initialized - check credentials")

    async def take_snapshot(self, label: str):
        """
        Take comprehensive snapshot of current state

        Args:
            label: 'before' or 'after'
        """
        logger.info(f"📸 Taking snapshot: {label}")
        timestamp = datetime.now(timezone.utc).isoformat()

        self.snapshots[label]['timestamp'] = timestamp
        self.snapshots[label]['orders'] = {}
        self.snapshots[label]['positions'] = {}

        total_orders = 0
        total_positions = 0

        for exchange_name, exchange in self.exchanges.items():
            try:
                logger.info(f"  📊 Fetching data from {exchange_name}...")

                # Fetch orders
                orders_raw = await exchange.fetch_open_orders()
                orders_snapshot = []

                for order in orders_raw:
                    order_info = order.get('info', {})

                    orders_snapshot.append(OrderSnapshot(
                        order_id=order.get('id', ''),
                        symbol=order.get('symbol', ''),
                        exchange=exchange_name,
                        order_type=order.get('type', ''),
                        side=order.get('side', ''),
                        status=order.get('status', ''),
                        amount=float(order.get('amount', 0) or 0),
                        price=float(order.get('price', 0) or 0),
                        timestamp=order.get('timestamp', 0),
                        reduce_only=order.get('reduceOnly', False) or order_info.get('reduceOnly', False),
                        close_on_trigger=order_info.get('closeOnTrigger', False),
                        stop_order_type=order_info.get('stopOrderType'),
                        position_idx=int(order_info.get('positionIdx', 0)),
                        client_order_id=order.get('clientOrderId'),
                        order_list_id=order_info.get('orderListId', -1) if order_info.get('orderListId') else None
                    ))

                self.snapshots[label]['orders'][exchange_name] = orders_snapshot
                total_orders += len(orders_snapshot)
                logger.info(f"    ✅ Orders: {len(orders_snapshot)}")

                # Fetch positions
                positions_raw = await exchange.fetch_positions()
                positions_snapshot = []

                for pos in positions_raw:
                    contracts = float(pos.get('contracts', 0) or 0)
                    if contracts > 0:  # Only active positions
                        pos_info = pos.get('info', {})

                        positions_snapshot.append(PositionSnapshot(
                            symbol=pos.get('symbol', ''),
                            exchange=exchange_name,
                            side=pos.get('side', ''),
                            contracts=contracts,
                            entry_price=float(pos.get('entryPrice', 0) or 0),
                            mark_price=float(pos.get('markPrice', 0) or 0),
                            unrealized_pnl=float(pos.get('unrealizedPnl', 0) or 0),
                            position_idx=int(pos_info.get('positionIdx', 0)),
                            leverage=float(pos.get('leverage', 1) or 1)
                        ))

                self.snapshots[label]['positions'][exchange_name] = positions_snapshot
                total_positions += len(positions_snapshot)
                logger.info(f"    ✅ Positions: {len(positions_snapshot)}")

                # Rate limiting
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"  ❌ Error fetching data from {exchange_name}: {e}")
                self.snapshots[label]['orders'][exchange_name] = []
                self.snapshots[label]['positions'][exchange_name] = []

        # Update stats
        if label == 'before':
            self.stats['total_orders_before'] = total_orders
            self.stats['total_positions_before'] = total_positions
        else:
            self.stats['total_orders_after'] = total_orders
            self.stats['total_positions_after'] = total_positions

        logger.info(f"✅ Snapshot '{label}' complete: {total_orders} orders, {total_positions} positions")

    async def monitor_logs(self, duration_minutes: int = 10):
        """
        Monitor bot logs in real-time

        Args:
            duration_minutes: How long to monitor
        """
        log_file = self.config.get('bot_log_path', 'logs/trading_bot.log')
        duration_seconds = duration_minutes * 60
        start_time = time.time()

        logger.info(f"🔍 Starting log monitoring: {log_file}")
        logger.info(f"⏱️  Duration: {duration_minutes} minutes")

        # Patterns to search for in logs
        patterns = {
            'zombie_check_start': ['Starting enhanced zombie', 'Running advanced.*zombie'],
            'zombie_found': ['Found.*zombie', 'ZOMBIE:', 'zombies_found'],
            'zombie_deleted': ['Cancelled.*zombie', 'DELETING ORDER:', 'zombies_cancelled'],
            'error': ['ERROR', 'CRITICAL', 'Failed to cancel'],
            'sl_check': ['check_positions_protection', 'Setting stop losses'],
            'sl_deleted': ['DELETING ORDER.*STOP', 'IF THIS IS A STOP-LOSS']
        }

        try:
            with open(log_file, 'r') as f:
                # Move to end of file
                f.seek(0, 2)

                while time.time() - start_time < duration_seconds:
                    line = f.readline()
                    if line:
                        self._parse_log_line(line, patterns)
                    else:
                        await asyncio.sleep(0.1)

        except FileNotFoundError:
            logger.error(f"❌ Log file not found: {log_file}")
        except Exception as e:
            logger.error(f"❌ Error monitoring logs: {e}")

        logger.info(f"✅ Log monitoring complete. Collected {len(self.log_events)} events")

    def _parse_log_line(self, line: str, patterns: Dict):
        """Parse log line and extract events"""
        timestamp_match = line.split(' - ')[0] if ' - ' in line else datetime.now().isoformat()

        for event_type, pattern_list in patterns.items():
            if any(pattern.lower() in line.lower() for pattern in pattern_list):
                event = {
                    'type': event_type,
                    'timestamp': timestamp_match,
                    'raw_line': line.strip(),
                    'extracted_data': self._extract_event_data(line, event_type)
                }
                self.log_events.append(event)

                # Special handling for deletions
                if event_type == 'zombie_deleted':
                    logger.info(f"  ⚠️  Deletion detected: {line[:100]}...")
                elif event_type == 'sl_deleted':
                    logger.warning(f"  🚨 STOP-LOSS deletion detected: {line[:100]}...")

    def _extract_event_data(self, line: str, event_type: str) -> Dict:
        """Extract structured data from log line"""
        data = {}

        # Extract order_id if present
        if 'order' in line.lower():
            # Try to find order ID patterns
            for part in line.split():
                if len(part) > 10 and part.isdigit():
                    data['order_id'] = part
                    break

        # Extract symbol if present
        for part in line.split():
            if 'USDT' in part.upper() or 'BTC' in part.upper():
                data['symbol'] = part
                break

        return data

    def compare_snapshots(self):
        """
        Compare before and after snapshots to detect changes
        """
        logger.info("\n" + "="*80)
        logger.info("📊 ANALYZING SNAPSHOT DIFFERENCES")
        logger.info("="*80)

        before = self.snapshots['before']
        after = self.snapshots['after']

        # Analyze each exchange
        for exchange_name in self.exchanges.keys():
            logger.info(f"\n🔍 Analyzing {exchange_name}...")

            orders_before = {o.order_id: o for o in before['orders'].get(exchange_name, [])}
            orders_after = {o.order_id: o for o in after['orders'].get(exchange_name, [])}

            positions_before = {(p.symbol, p.position_idx): p for p in before['positions'].get(exchange_name, [])}
            positions_after = {(p.symbol, p.position_idx): p for p in after['positions'].get(exchange_name, [])}

            # Find deleted orders
            deleted_order_ids = set(orders_before.keys()) - set(orders_after.keys())
            added_order_ids = set(orders_after.keys()) - set(orders_before.keys())

            # Find closed/opened positions
            closed_position_keys = set(positions_before.keys()) - set(positions_after.keys())
            opened_position_keys = set(positions_after.keys()) - set(positions_before.keys())

            logger.info(f"  📉 Orders deleted: {len(deleted_order_ids)}")
            logger.info(f"  📈 Orders added: {len(added_order_ids)}")
            logger.info(f"  🔴 Positions closed: {len(closed_position_keys)}")
            logger.info(f"  🟢 Positions opened: {len(opened_position_keys)}")

            # Update stats
            self.stats['orders_deleted'] += len(deleted_order_ids)
            self.stats['orders_added'] += len(added_order_ids)
            self.stats['positions_closed'] += len(closed_position_keys)
            self.stats['positions_opened'] += len(opened_position_keys)

            # Analyze each deleted order
            for order_id in deleted_order_ids:
                order = orders_before[order_id]
                self._analyze_deleted_order(order, positions_before, positions_after, exchange_name)

    def _analyze_deleted_order(
        self,
        order: OrderSnapshot,
        positions_before: Dict,
        positions_after: Dict,
        exchange_name: str
    ):
        """
        Deep analysis of deleted order

        Checks:
        - Was it a legitimate zombie?
        - Was there an open position?
        - Was it a protective order (SL/TP)?
        """
        logger.info(f"\n  🔍 Analyzing deleted order: {order.order_id}")
        logger.info(f"     Symbol: {order.symbol}")
        logger.info(f"     Type: {order.order_type}, Side: {order.side}")
        logger.info(f"     Status: {order.status}")

        # Check if position existed
        position_key = (order.symbol, order.position_idx)
        had_position_before = position_key in positions_before
        has_position_after = position_key in positions_after

        logger.info(f"     Position before: {'✅ YES' if had_position_before else '❌ NO'}")
        logger.info(f"     Position after: {'✅ YES' if has_position_after else '❌ NO'}")

        # Detect issues
        is_protective_type = any(keyword in order.order_type.upper() for keyword in [
            'STOP', 'TAKE_PROFIT', 'TRAILING'
        ])

        if is_protective_type and had_position_before:
            # CRITICAL: Protective order deleted while position was open!
            issue = DiagnosticIssue(
                severity='CRITICAL',
                issue_type='protective_order_deleted_with_open_position',
                description=f'Protective order {order.order_id} ({order.order_type}) deleted while position was open',
                evidence={
                    'order': asdict(order),
                    'position_before': asdict(positions_before[position_key]),
                    'had_position_after': has_position_after
                }
            )
            self.issues.append(issue)
            logger.error(f"     🚨 CRITICAL ISSUE: Protective order deleted with open position!")

        elif is_protective_type and not had_position_before:
            logger.info(f"     ✅ OK: Protective order for closed position (legitimate zombie)")

        elif order.reduce_only and had_position_before:
            issue = DiagnosticIssue(
                severity='HIGH',
                issue_type='reduce_only_deleted_with_position',
                description=f'ReduceOnly order {order.order_id} deleted while position was open',
                evidence={
                    'order': asdict(order),
                    'position_before': asdict(positions_before[position_key])
                }
            )
            self.issues.append(issue)
            logger.warning(f"     ⚠️  HIGH RISK: ReduceOnly order deleted with open position")

        elif not had_position_before:
            logger.info(f"     ✅ OK: Order without position (legitimate zombie)")

        else:
            logger.info(f"     ℹ️  Order deleted (may be legitimate)")

    def generate_report(self) -> str:
        """
        Generate comprehensive diagnostic report
        """
        report_lines = []

        report_lines.append("\n" + "="*80)
        report_lines.append("📋 ZOMBIE MANAGER DIAGNOSTIC REPORT")
        report_lines.append("="*80)
        report_lines.append(f"\nGenerated: {datetime.now().isoformat()}")
        report_lines.append(f"Monitoring duration: {self.config.get('duration_minutes', 10)} minutes")

        # Snapshot summary
        report_lines.append("\n" + "-"*80)
        report_lines.append("📸 SNAPSHOT SUMMARY")
        report_lines.append("-"*80)
        report_lines.append(f"Before: {self.snapshots['before']['timestamp']}")
        report_lines.append(f"  Orders: {self.stats['total_orders_before']}")
        report_lines.append(f"  Positions: {self.stats['total_positions_before']}")
        report_lines.append(f"\nAfter: {self.snapshots['after']['timestamp']}")
        report_lines.append(f"  Orders: {self.stats['total_orders_after']}")
        report_lines.append(f"  Positions: {self.stats['total_positions_after']}")

        # Changes
        report_lines.append("\n" + "-"*80)
        report_lines.append("📊 DETECTED CHANGES")
        report_lines.append("-"*80)
        report_lines.append(f"Orders deleted: {self.stats['orders_deleted']}")
        report_lines.append(f"Orders added: {self.stats['orders_added']}")
        report_lines.append(f"Positions closed: {self.stats['positions_closed']}")
        report_lines.append(f"Positions opened: {self.stats['positions_opened']}")

        # Issues
        report_lines.append("\n" + "-"*80)
        report_lines.append("⚠️  ISSUES DETECTED")
        report_lines.append("-"*80)

        critical_issues = [i for i in self.issues if i.severity == 'CRITICAL']
        high_issues = [i for i in self.issues if i.severity == 'HIGH']
        medium_issues = [i for i in self.issues if i.severity == 'MEDIUM']

        report_lines.append(f"🔴 CRITICAL: {len(critical_issues)}")
        report_lines.append(f"🟠 HIGH: {len(high_issues)}")
        report_lines.append(f"🟡 MEDIUM: {len(medium_issues)}")

        if critical_issues:
            report_lines.append("\n🔴 CRITICAL ISSUES:")
            for i, issue in enumerate(critical_issues, 1):
                report_lines.append(f"\n  {i}. {issue.issue_type}")
                report_lines.append(f"     {issue.description}")
                report_lines.append(f"     Timestamp: {issue.timestamp}")

        if high_issues:
            report_lines.append("\n🟠 HIGH PRIORITY ISSUES:")
            for i, issue in enumerate(high_issues, 1):
                report_lines.append(f"\n  {i}. {issue.issue_type}")
                report_lines.append(f"     {issue.description}")

        # Final verdict
        report_lines.append("\n" + "="*80)
        report_lines.append("📈 FINAL VERDICT")
        report_lines.append("="*80)

        if critical_issues:
            report_lines.append("\n❌ STATUS: CRITICAL ISSUES DETECTED")
            report_lines.append("   Zombie Manager has SERIOUS BUGS that can cause:")
            report_lines.append("   - Loss of position protection (SL deletion)")
            report_lines.append("   - Incorrect order management")
            report_lines.append("   ⚠️  REQUIRES IMMEDIATE FIX BEFORE PRODUCTION USE")
        elif high_issues:
            report_lines.append("\n⚠️  STATUS: HIGH PRIORITY ISSUES DETECTED")
            report_lines.append("   Module requires fixes before production use")
        elif medium_issues:
            report_lines.append("\n🟡 STATUS: MINOR ISSUES DETECTED")
            report_lines.append("   Module works but has areas for improvement")
        else:
            report_lines.append("\n✅ STATUS: ALL CHECKS PASSED")
            report_lines.append("   Zombie Manager appears to be working correctly")

        report_lines.append("="*80)

        return "\n".join(report_lines)

    def save_report(self, report: str, data_filename: str):
        """Save report and diagnostic data"""
        # Save text report
        report_filename = f"zombie_diagnostics_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_filename, 'w', encoding='utf-8') as f:
            f.write(report)
        logger.info(f"💾 Report saved: {report_filename}")

        # Save detailed data as JSON
        data = {
            'config': self.config,
            'snapshots': {
                'before': {
                    'timestamp': self.snapshots['before']['timestamp'],
                    'orders': {
                        ex: [asdict(o) for o in orders]
                        for ex, orders in self.snapshots['before']['orders'].items()
                    },
                    'positions': {
                        ex: [asdict(p) for p in positions]
                        for ex, positions in self.snapshots['before']['positions'].items()
                    }
                },
                'after': {
                    'timestamp': self.snapshots['after']['timestamp'],
                    'orders': {
                        ex: [asdict(o) for o in orders]
                        for ex, orders in self.snapshots['after']['orders'].items()
                    },
                    'positions': {
                        ex: [asdict(p) for p in positions]
                        for ex, positions in self.snapshots['after']['positions'].items()
                    }
                }
            },
            'log_events': self.log_events,
            'issues': [asdict(i) for i in self.issues],
            'stats': self.stats
        }

        with open(data_filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
        logger.info(f"💾 Detailed data saved: {data_filename}")

    async def cleanup(self):
        """Clean up resources"""
        logger.info("🧹 Cleaning up...")
        for exchange_name, exchange in self.exchanges.items():
            try:
                await exchange.close()
                logger.info(f"  ✅ Closed {exchange_name}")
            except Exception as e:
                logger.error(f"  ❌ Error closing {exchange_name}: {e}")


async def main():
    """Main diagnostic workflow"""
    parser = argparse.ArgumentParser(description='Zombie Manager Diagnostics')
    parser.add_argument('--duration', type=int, default=10, help='Monitoring duration in minutes')
    parser.add_argument('--mode', choices=['dry-run', 'verify'], default='dry-run', help='Diagnostic mode')
    parser.add_argument('--exchanges', nargs='+', choices=['binance', 'bybit'], default=['binance', 'bybit'], help='Exchanges to monitor')
    args = parser.parse_args()

    logger.info("="*80)
    logger.info("🚀 ZOMBIE MANAGER DIAGNOSTICS")
    logger.info("="*80)
    logger.info(f"Mode: {args.mode}")
    logger.info(f"Duration: {args.duration} minutes")
    logger.info(f"Exchanges: {', '.join(args.exchanges)}")

    # Configuration
    config = {
        'duration_minutes': args.duration,
        'mode': args.mode,
        'binance_enabled': 'binance' in args.exchanges,
        'bybit_enabled': 'bybit' in args.exchanges,
        'bot_log_path': 'logs/trading_bot.log'
    }

    diagnostics = ZombieManagerDiagnostics(config)

    try:
        # Initialize
        await diagnostics.initialize_exchanges()

        # BEFORE snapshot
        logger.info("\n" + "="*80)
        logger.info("PHASE 1: TAKING BEFORE SNAPSHOT")
        logger.info("="*80)
        await diagnostics.take_snapshot('before')

        # Monitor logs
        logger.info("\n" + "="*80)
        logger.info("PHASE 2: MONITORING BOT LOGS")
        logger.info("="*80)
        await diagnostics.monitor_logs(duration_minutes=args.duration)

        # AFTER snapshot
        logger.info("\n" + "="*80)
        logger.info("PHASE 3: TAKING AFTER SNAPSHOT")
        logger.info("="*80)
        await diagnostics.take_snapshot('after')

        # Analysis
        logger.info("\n" + "="*80)
        logger.info("PHASE 4: ANALYZING RESULTS")
        logger.info("="*80)
        diagnostics.compare_snapshots()

        # Generate report
        logger.info("\n" + "="*80)
        logger.info("PHASE 5: GENERATING REPORT")
        logger.info("="*80)
        report = diagnostics.generate_report()
        print(report)

        # Save report
        data_filename = f"zombie_diagnostics_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        diagnostics.save_report(report, data_filename)

        logger.info("\n✅ DIAGNOSTICS COMPLETE")

    except Exception as e:
        logger.error(f"\n❌ DIAGNOSTICS FAILED: {e}", exc_info=True)
    finally:
        await diagnostics.cleanup()


if __name__ == '__main__':
    asyncio.run(main())
