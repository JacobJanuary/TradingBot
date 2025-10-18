#!/usr/bin/env python3
"""
Bot Monitoring System
Real-time monitoring for 8-hour production audit
Collects metrics every minute, detects anomalies, generates reports
"""

import asyncio
import asyncpg
import logging
from datetime import datetime, timedelta
from collections import defaultdict, deque
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Set
import json
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class MinuteMetrics:
    """Metrics collected every minute"""
    timestamp: datetime

    # Positions
    binance_positions_count: int
    bybit_positions_count: int
    total_positions: int
    unprotected_positions: int

    # New positions in last minute
    new_positions_opened: int
    new_on_binance: int
    new_on_bybit: int

    # Updates
    prices_updated: int
    trailing_stops_activated: int
    sl_updates_with_active_ts: int

    # Problems
    aged_positions_detected: int
    positions_closed_on_exchange: int

    # Additional metrics
    zombie_orders_cleaned: int
    emergency_closes: int
    api_errors: int
    websocket_reconnects: int


@dataclass
class AggregatedMetrics:
    """Metrics over a period (10 minutes / all time)"""
    period_name: str

    # Totals
    total_positions_opened: int
    total_positions_closed: int
    total_sl_updates: int
    total_ts_activations: int

    # Averages
    avg_positions_count: float
    avg_unprotected: float

    # Problems
    total_aged: int
    total_zombies: int
    total_errors: int

    # PnL if available
    total_pnl: Optional[float]
    win_rate: Optional[float]


class BotMonitor:
    """Main monitoring class"""

    def __init__(self):
        self.db_pool: Optional[asyncpg.Pool] = None
        self.metrics_history: deque = deque(maxlen=600)  # 10 hours of history
        self.last_snapshot: Dict = {}
        self.alert_log: List = []

        # Tracking for calculating deltas
        self.last_position_ids: Set = set()
        self.last_ts_states: Dict = {}
        self.last_zombie_count: int = 0

    async def connect_db(self):
        """Connect to PostgreSQL database"""
        try:
            # Using .pgpass for authentication
            self.db_pool = await asyncpg.create_pool(
                host='localhost',
                port=5432,
                database='fox_crypto',
                user='evgeniyyanvarskiy',
                min_size=2,
                max_size=5,
                timeout=30
            )
            logger.info("✅ Connected to PostgreSQL database")

            # Test connection
            async with self.db_pool.acquire() as conn:
                version = await conn.fetchval('SELECT version()')
                logger.info(f"Database version: {version[:50]}...")

        except Exception as e:
            logger.error(f"❌ Failed to connect to database: {e}")
            raise

    async def collect_minute_metrics(self) -> MinuteMetrics:
        """Collect metrics for the current minute"""

        try:
            # 1. COUNT OPEN POSITIONS
            positions_query = """
                SELECT
                    exchange,
                    COUNT(*) as count,
                    COUNT(*) FILTER (WHERE has_stop_loss = false) as unprotected
                FROM monitoring.positions
                WHERE status IN ('active', 'trailing')
                GROUP BY exchange
            """

            positions = await self.db_pool.fetch(positions_query)
            binance_count = 0
            bybit_count = 0
            unprotected = 0

            for row in positions:
                if row['exchange'] == 'binance':
                    binance_count = row['count']
                elif row['exchange'] == 'bybit':
                    bybit_count = row['count']
                unprotected += row['unprotected']

            # 2. NEW POSITIONS IN LAST MINUTE
            new_positions_query = """
                SELECT
                    exchange,
                    COUNT(*) as count
                FROM monitoring.positions
                WHERE opened_at > NOW() - INTERVAL '1 minute'
                GROUP BY exchange
            """

            new_positions = await self.db_pool.fetch(new_positions_query)
            new_binance = 0
            new_bybit = 0

            for row in new_positions:
                if row['exchange'] == 'binance':
                    new_binance = row['count']
                elif row['exchange'] == 'bybit':
                    new_bybit = row['count']

            # 3. PRICE UPDATES (from events table)
            # FIXED: event type is 'position_updated', not 'price_update'
            price_updates_query = """
                SELECT COUNT(DISTINCT position_id) as count
                FROM monitoring.events
                WHERE event_type = 'position_updated'
                  AND created_at > NOW() - INTERVAL '1 minute'
            """
            price_updates = await self.db_pool.fetchval(price_updates_query) or 0

            # 4. TRAILING STOP ACTIVATIONS
            ts_activations_query = """
                SELECT COUNT(*) as count
                FROM monitoring.events
                WHERE event_type = 'trailing_stop_activated'
                  AND created_at > NOW() - INTERVAL '1 minute'
            """
            ts_activations = await self.db_pool.fetchval(ts_activations_query) or 0

            # 5. SL UPDATES WITH ACTIVE TS
            # FIXED: event type is 'trailing_stop_updated' or 'stop_loss_placed', not 'stop_loss_updated'
            sl_updates_query = """
                SELECT COUNT(DISTINCT e.position_id) as count
                FROM monitoring.events e
                INNER JOIN monitoring.trailing_stop_state ts
                    ON e.position_id = ts.position_id
                WHERE e.event_type IN ('trailing_stop_updated', 'stop_loss_placed')
                  AND ts.state = 'active'
                  AND e.created_at > NOW() - INTERVAL '1 minute'
            """
            sl_updates = await self.db_pool.fetchval(sl_updates_query) or 0

            # 6. AGED POSITIONS
            aged_query = """
                SELECT COUNT(*) as count
                FROM monitoring.positions
                WHERE status IN ('active', 'trailing')
                  AND opened_at < NOW() - INTERVAL '3 hours'
            """
            aged_count = await self.db_pool.fetchval(aged_query) or 0

            # 7. CLOSED ON EXCHANGE (from events)
            closed_on_exchange_query = """
                SELECT COUNT(*) as count
                FROM monitoring.events
                WHERE event_type IN ('stop_loss_triggered', 'position_closed')
                  AND created_at > NOW() - INTERVAL '1 minute'
            """
            closed_count = await self.db_pool.fetchval(closed_on_exchange_query) or 0

            # 8. ADDITIONAL METRICS
            zombies_query = """
                SELECT COUNT(*) as count
                FROM monitoring.events
                WHERE event_type = 'zombie_cleaned'
                  AND created_at > NOW() - INTERVAL '1 minute'
            """
            zombies = await self.db_pool.fetchval(zombies_query) or 0

            emergency_query = """
                SELECT COUNT(*) as count
                FROM monitoring.events
                WHERE event_type = 'emergency_close'
                  AND created_at > NOW() - INTERVAL '1 minute'
            """
            emergency = await self.db_pool.fetchval(emergency_query) or 0

            errors_query = """
                SELECT COUNT(*) as count
                FROM monitoring.events
                WHERE event_type LIKE '%error%'
                  AND created_at > NOW() - INTERVAL '1 minute'
            """
            errors = await self.db_pool.fetchval(errors_query) or 0

            # WebSocket reconnects - parse from events
            ws_reconnect_query = """
                SELECT COUNT(*) as count
                FROM monitoring.events
                WHERE event_type IN ('websocket_reconnect', 'websocket_reconnected')
                  AND created_at > NOW() - INTERVAL '1 minute'
            """
            ws_reconnects = await self.db_pool.fetchval(ws_reconnect_query) or 0

            return MinuteMetrics(
                timestamp=datetime.now(),
                binance_positions_count=binance_count,
                bybit_positions_count=bybit_count,
                total_positions=binance_count + bybit_count,
                unprotected_positions=unprotected,
                new_positions_opened=new_binance + new_bybit,
                new_on_binance=new_binance,
                new_on_bybit=new_bybit,
                prices_updated=price_updates,
                trailing_stops_activated=ts_activations,
                sl_updates_with_active_ts=sl_updates,
                aged_positions_detected=aged_count,
                positions_closed_on_exchange=closed_count,
                zombie_orders_cleaned=zombies,
                emergency_closes=emergency,
                api_errors=errors,
                websocket_reconnects=ws_reconnects
            )

        except Exception as e:
            logger.error(f"Error collecting metrics: {e}")
            # Return zero metrics on error
            return MinuteMetrics(
                timestamp=datetime.now(),
                binance_positions_count=0,
                bybit_positions_count=0,
                total_positions=0,
                unprotected_positions=0,
                new_positions_opened=0,
                new_on_binance=0,
                new_on_bybit=0,
                prices_updated=0,
                trailing_stops_activated=0,
                sl_updates_with_active_ts=0,
                aged_positions_detected=0,
                positions_closed_on_exchange=0,
                zombie_orders_cleaned=0,
                emergency_closes=0,
                api_errors=0,
                websocket_reconnects=0
            )

    def calculate_aggregated(self, minutes: int) -> Optional[AggregatedMetrics]:
        """Calculate aggregated metrics over N minutes"""
        relevant = list(self.metrics_history)[-minutes:]

        if not relevant:
            return None

        # Calculate PnL from database (optional)
        total_pnl = None
        win_rate = None

        return AggregatedMetrics(
            period_name=f"Last {minutes} min" if minutes < 600 else "All time",
            total_positions_opened=sum(m.new_positions_opened for m in relevant),
            total_positions_closed=sum(m.positions_closed_on_exchange for m in relevant),
            total_sl_updates=sum(m.sl_updates_with_active_ts for m in relevant),
            total_ts_activations=sum(m.trailing_stops_activated for m in relevant),
            avg_positions_count=sum(m.total_positions for m in relevant) / len(relevant),
            avg_unprotected=sum(m.unprotected_positions for m in relevant) / len(relevant),
            # FIXED: Show current count (last value), not sum of all minutes
            total_aged=relevant[-1].aged_positions_detected if relevant else 0,
            total_zombies=sum(m.zombie_orders_cleaned for m in relevant),
            total_errors=sum(m.api_errors for m in relevant),
            total_pnl=total_pnl,
            win_rate=win_rate
        )

    def print_metrics(self, current: MinuteMetrics):
        """Pretty print metrics to console"""

        print("\n" + "="*80)
        print(f"📊 BOT MONITORING - {current.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80)

        # CURRENT STATE
        print("\n🔹 CURRENT STATE")
        print(f"  Total Positions:     {current.total_positions}")
        print(f"    ├─ Binance:        {current.binance_positions_count}")
        print(f"    └─ Bybit:          {current.bybit_positions_count}")
        print(f"  🚨 Unprotected:      {current.unprotected_positions}")
        if current.unprotected_positions > 0:
            print(f"     ⚠️  WARNING: {current.unprotected_positions} positions without SL!")

        # LAST MINUTE
        print("\n🔹 LAST MINUTE")
        print(f"  New Positions:       {current.new_positions_opened}")
        if current.new_positions_opened > 0:
            print(f"    ├─ Binance:        {current.new_on_binance}")
            print(f"    └─ Bybit:          {current.new_on_bybit}")
        print(f"  Prices Updated:      {current.prices_updated}")
        print(f"  TS Activated:        {current.trailing_stops_activated}")
        print(f"  SL Updates (TS):     {current.sl_updates_with_active_ts}")
        print(f"  Aged Detected:       {current.aged_positions_detected}")
        print(f"  Closed on Exchange:  {current.positions_closed_on_exchange}")

        if current.zombie_orders_cleaned > 0:
            print(f"  🧹 Zombies Cleaned:  {current.zombie_orders_cleaned}")
        if current.emergency_closes > 0:
            print(f"  🚨 Emergency Closes: {current.emergency_closes}")
        if current.api_errors > 0:
            print(f"  ❌ API Errors:       {current.api_errors}")
        if current.websocket_reconnects > 0:
            print(f"  🔌 WS Reconnects:    {current.websocket_reconnects}")

        # LAST 10 MINUTES
        agg_10 = self.calculate_aggregated(10)
        if agg_10:
            print("\n🔹 LAST 10 MINUTES")
            print(f"  Positions Opened:    {agg_10.total_positions_opened}")
            print(f"  Positions Closed:    {agg_10.total_positions_closed}")
            print(f"  TS Activations:      {agg_10.total_ts_activations}")
            print(f"  SL Updates:          {agg_10.total_sl_updates}")
            print(f"  Avg Positions:       {agg_10.avg_positions_count:.1f}")
            print(f"  Avg Unprotected:     {agg_10.avg_unprotected:.1f}")

        # ALL TIME
        agg_all = self.calculate_aggregated(len(self.metrics_history))
        if agg_all and len(self.metrics_history) > 10:
            print("\n🔹 ALL TIME (since start)")
            print(f"  Total Opened:        {agg_all.total_positions_opened}")
            print(f"  Total Closed:        {agg_all.total_positions_closed}")
            print(f"  Total TS Act:        {agg_all.total_ts_activations}")
            print(f"  Current Aged (>3h):  {agg_all.total_aged}")  # FIXED: clarify this is current count
            print(f"  Total Zombies:       {agg_all.total_zombies}")
            print(f"  Total Errors:        {agg_all.total_errors}")

        print("="*80)

    async def check_anomalies(self, metrics: MinuteMetrics):
        """Check for anomalies and generate alerts"""
        alerts = []

        # CRITICAL ISSUES
        if metrics.unprotected_positions > 0:
            alerts.append({
                'severity': 'CRITICAL',
                'message': f'{metrics.unprotected_positions} positions without SL',
                'timestamp': metrics.timestamp
            })

        if metrics.emergency_closes > 0:
            alerts.append({
                'severity': 'CRITICAL',
                'message': f'{metrics.emergency_closes} emergency closes',
                'timestamp': metrics.timestamp
            })

        # SUSPICIOUS BEHAVIOR
        if metrics.new_positions_opened > 15:
            alerts.append({
                'severity': 'WARNING',
                'message': f'High position opening rate: {metrics.new_positions_opened} in 1 min',
                'timestamp': metrics.timestamp
            })

        if metrics.api_errors > 5:
            alerts.append({
                'severity': 'WARNING',
                'message': f'High API error rate: {metrics.api_errors} errors',
                'timestamp': metrics.timestamp
            })

        if metrics.prices_updated == 0 and metrics.total_positions > 0:
            alerts.append({
                'severity': 'WARNING',
                'message': 'No price updates for existing positions',
                'timestamp': metrics.timestamp
            })

        if metrics.websocket_reconnects > 0:
            alerts.append({
                'severity': 'WARNING',
                'message': f'{metrics.websocket_reconnects} WebSocket reconnections',
                'timestamp': metrics.timestamp
            })

        if metrics.aged_positions_detected > 5:
            alerts.append({
                'severity': 'INFO',
                'message': f'{metrics.aged_positions_detected} positions older than 3 hours',
                'timestamp': metrics.timestamp
            })

        # Log alerts
        for alert in alerts:
            self.alert_log.append(alert)
            severity_icon = {
                'CRITICAL': '🚨',
                'WARNING': '⚠️',
                'INFO': 'ℹ️'
            }.get(alert['severity'], '⚠️')
            print(f"\n{severity_icon} {alert['severity']}: {alert['message']}")

        return alerts

    async def save_snapshot(self, metrics: MinuteMetrics):
        """Save snapshot to file for later analysis"""

        snapshot = {
            'timestamp': metrics.timestamp.isoformat(),
            'metrics': {
                'positions': {
                    'total': metrics.total_positions,
                    'binance': metrics.binance_positions_count,
                    'bybit': metrics.bybit_positions_count,
                    'unprotected': metrics.unprotected_positions
                },
                'activity': {
                    'new_opened': metrics.new_positions_opened,
                    'prices_updated': metrics.prices_updated,
                    'ts_activated': metrics.trailing_stops_activated,
                    'sl_updates': metrics.sl_updates_with_active_ts,
                    'closed': metrics.positions_closed_on_exchange
                },
                'issues': {
                    'aged': metrics.aged_positions_detected,
                    'zombies': metrics.zombie_orders_cleaned,
                    'emergency': metrics.emergency_closes,
                    'errors': metrics.api_errors,
                    'ws_reconnects': metrics.websocket_reconnects
                }
            }
        }

        # Save to JSONL file (one line per snapshot)
        date_str = datetime.now().strftime("%Y%m%d")
        filename = f'monitoring_snapshots_{date_str}.jsonl'

        try:
            with open(filename, 'a') as f:
                f.write(json.dumps(snapshot) + '\n')
        except Exception as e:
            logger.error(f"Failed to save snapshot: {e}")

    async def save_final_report(self):
        """Save final monitoring report"""

        if not self.metrics_history:
            logger.warning("No metrics collected, skipping final report")
            return

        report = {
            'monitoring_duration_minutes': len(self.metrics_history),
            'monitoring_start': self.metrics_history[0].timestamp.isoformat(),
            'monitoring_end': self.metrics_history[-1].timestamp.isoformat(),
            'total_alerts': len(self.alert_log),
            'critical_alerts': len([a for a in self.alert_log if a['severity'] == 'CRITICAL']),
            'warning_alerts': len([a for a in self.alert_log if a['severity'] == 'WARNING']),
            'metrics_summary': {
                'total_positions_opened': sum(m.new_positions_opened for m in self.metrics_history),
                'total_positions_closed': sum(m.positions_closed_on_exchange for m in self.metrics_history),
                'total_ts_activations': sum(m.trailing_stops_activated for m in self.metrics_history),
                'total_sl_updates': sum(m.sl_updates_with_active_ts for m in self.metrics_history),
                'total_zombies': sum(m.zombie_orders_cleaned for m in self.metrics_history),
                'total_errors': sum(m.api_errors for m in self.metrics_history),
                'total_emergency_closes': sum(m.emergency_closes for m in self.metrics_history),
                'total_ws_reconnects': sum(m.websocket_reconnects for m in self.metrics_history)
            },
            'alerts': self.alert_log
        }

        filename = f'monitoring_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        try:
            with open(filename, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            print(f"\n📊 Final report saved: {filename}")
            logger.info(f"Final report saved: {filename}")
        except Exception as e:
            logger.error(f"Failed to save final report: {e}")

    async def run_monitoring(self, duration_hours: int = 8):
        """Main monitoring loop"""

        print("\n" + "="*80)
        print("🚀 STARTING BOT MONITORING SYSTEM")
        print("="*80)
        print(f"⏱️  Duration: {duration_hours} hours ({duration_hours * 60} minutes)")
        print(f"📊 Metrics collection: every 60 seconds")
        print(f"💾 Database: fox_crypto @ localhost:5432")
        print(f"📁 Snapshots will be saved to: monitoring_snapshots_*.jsonl")
        print(f"📋 Final report will be saved to: monitoring_report_*.json")
        print("="*80)

        # Connect to database
        await self.connect_db()

        print("\n✅ Monitoring started at:", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        print(f"🎯 Will run until: {(datetime.now() + timedelta(hours=duration_hours)).strftime('%Y-%m-%d %H:%M:%S')}")
        print("\nPress Ctrl+C to stop monitoring early\n")

        start_time = datetime.now()
        end_time = start_time + timedelta(hours=duration_hours)
        iteration = 0

        try:
            while datetime.now() < end_time:
                iteration += 1

                # Collect metrics
                metrics = await self.collect_minute_metrics()
                self.metrics_history.append(metrics)

                # Print statistics
                self.print_metrics(metrics)

                # Check for anomalies
                await self.check_anomalies(metrics)

                # Save snapshot
                await self.save_snapshot(metrics)

                # Calculate remaining time
                remaining = end_time - datetime.now()
                hours, remainder = divmod(remaining.seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                print(f"\n⏳ Iteration {iteration} complete. Remaining: {hours}h {minutes}m {seconds}s")

                # Wait for next minute
                await asyncio.sleep(60)

        except KeyboardInterrupt:
            print("\n\n⚠️  Monitoring interrupted by user (Ctrl+C)")
            logger.info("Monitoring interrupted by user")
        except Exception as e:
            print(f"\n\n❌ Monitoring error: {e}")
            logger.error(f"Monitoring error: {e}", exc_info=True)
        finally:
            # Save final report
            print("\n📊 Generating final report...")
            await self.save_final_report()

            # Close database connection
            if self.db_pool:
                await self.db_pool.close()
                print("✅ Database connection closed")

            print("\n" + "="*80)
            print("🏁 MONITORING COMPLETED")
            print("="*80)
            print(f"Total duration: {len(self.metrics_history)} minutes")
            print(f"Total alerts: {len(self.alert_log)}")
            print(f"Critical alerts: {len([a for a in self.alert_log if a['severity'] == 'CRITICAL'])}")
            print("="*80)


async def main():
    """Entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Bot Monitoring System')
    parser.add_argument(
        '--duration',
        type=int,
        default=8,
        help='Monitoring duration in hours (default: 8)'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='Test mode: run for 5 minutes only'
    )

    args = parser.parse_args()

    duration = 5/60 if args.test else args.duration  # 5 minutes if test mode

    monitor = BotMonitor()
    await monitor.run_monitoring(duration_hours=duration)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Monitoring stopped")
        sys.exit(0)
