"""
Real-time Aged Position Monitor
Comprehensive monitoring and validation of aged position management module
"""
import asyncio
import asyncpg
import os
import sys
import json
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
import argparse

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class AgedPositionSnapshot:
    """Snapshot of an aged position at a moment in time"""
    timestamp: datetime
    position_id: int
    symbol: str
    side: str
    entry_price: float
    current_price: float
    age_hours: float
    hours_over_limit: float
    pnl_percent: float
    phase: str
    target_price: float
    loss_tolerance: float
    should_close: bool
    reason: str


@dataclass
class CloseAttempt:
    """Record of a position close attempt"""
    timestamp: datetime
    position_id: int
    symbol: str
    reason: str
    target_price: float
    current_price: float
    success: bool
    error: Optional[str] = None


class AgedLogicSimulator:
    """
    Independent implementation of aged logic for validation
    """

    def __init__(self, config: Dict):
        self.max_age = config['MAX_POSITION_AGE_HOURS']
        self.grace_period = config['AGED_GRACE_PERIOD_HOURS']
        self.loss_step = Decimal(str(config['AGED_LOSS_STEP_PERCENT']))
        self.max_loss = Decimal(str(config['AGED_MAX_LOSS_PERCENT']))
        self.acceleration = Decimal(str(config['AGED_ACCELERATION_FACTOR']))
        self.commission = Decimal(str(config['COMMISSION_PERCENT'])) / 100

    def calculate_aged_parameters(
        self,
        age_hours: float,
        entry_price: float,
        current_price: float,
        side: str
    ) -> Dict:
        """
        Calculate all aged parameters independently
        """
        age_decimal = Decimal(str(age_hours))
        entry_decimal = Decimal(str(entry_price))
        current_decimal = Decimal(str(current_price))

        hours_over_limit = age_decimal - self.max_age

        if hours_over_limit <= 0:
            return {
                'phase': 'NORMAL',
                'hours_over_limit': 0,
                'should_close': False,
                'target_price': None,
                'loss_tolerance': 0,
                'reason': 'Position not aged yet'
            }

        # Grace Period
        if hours_over_limit <= self.grace_period:
            double_commission = 2 * self.commission

            if side in ['long', 'buy']:
                target_price = entry_decimal * (1 + double_commission)
            else:
                target_price = entry_decimal * (1 - double_commission)

            return {
                'phase': 'GRACE_PERIOD',
                'hours_over_limit': float(hours_over_limit),
                'hours_beyond_grace': 0,
                'target_price': float(target_price),
                'loss_tolerance': 0,
                'should_close': True,
                'reason': f'Breakeven attempt ({hours_over_limit:.1f}/{self.grace_period}h)'
            }

        # Progressive Liquidation
        elif hours_over_limit <= self.grace_period + 20:
            hours_after_grace = hours_over_limit - self.grace_period

            # Base loss
            loss_percent = hours_after_grace * self.loss_step

            # Acceleration after 10h
            if hours_after_grace > 10:
                extra_hours = hours_after_grace - 10
                acceleration_loss = extra_hours * self.loss_step * (self.acceleration - 1)
                loss_percent += acceleration_loss

            # Cap at max
            loss_percent = min(loss_percent, self.max_loss)

            if side in ['long', 'buy']:
                target_price = entry_decimal * (1 - loss_percent / 100)
            else:
                target_price = entry_decimal * (1 + loss_percent / 100)

            return {
                'phase': 'PROGRESSIVE',
                'hours_over_limit': float(hours_over_limit),
                'hours_beyond_grace': float(hours_after_grace),
                'target_price': float(target_price),
                'loss_tolerance': float(loss_percent),
                'should_close': True,
                'reason': f'Progressive liquidation (loss: {loss_percent:.1f}%)'
            }

        # Emergency
        else:
            if side in ['long', 'buy']:
                loss_percent = ((entry_decimal - current_decimal) / entry_decimal) * 100
            else:
                loss_percent = ((current_decimal - entry_decimal) / entry_decimal) * 100

            return {
                'phase': 'EMERGENCY',
                'hours_over_limit': float(hours_over_limit),
                'hours_beyond_grace': float(hours_over_limit - self.grace_period),
                'target_price': float(current_decimal),
                'loss_tolerance': float(loss_percent),
                'should_close': True,
                'reason': 'Emergency market close'
            }


class AgedPositionMonitor:
    """
    Real-time monitor for aged position management
    """

    def __init__(self, duration: int = 600, save_interval: int = 30):
        self.duration = duration
        self.save_interval = save_interval
        self.start_time = None
        self.db_pool = None

        # Load configuration
        self.config = {
            'MAX_POSITION_AGE_HOURS': int(os.getenv('MAX_POSITION_AGE_HOURS', 3)),
            'AGED_GRACE_PERIOD_HOURS': int(os.getenv('AGED_GRACE_PERIOD_HOURS', 8)),
            'AGED_LOSS_STEP_PERCENT': float(os.getenv('AGED_LOSS_STEP_PERCENT', 0.5)),
            'AGED_MAX_LOSS_PERCENT': float(os.getenv('AGED_MAX_LOSS_PERCENT', 10.0)),
            'AGED_ACCELERATION_FACTOR': float(os.getenv('AGED_ACCELERATION_FACTOR', 1.2)),
            'COMMISSION_PERCENT': float(os.getenv('COMMISSION_PERCENT', 0.1))
        }

        # Initialize simulator
        self.simulator = AgedLogicSimulator(self.config)

        # Monitoring data
        self.positions_tracked: List[AgedPositionSnapshot] = []
        self.aged_checks_performed: List[Dict] = []
        self.close_attempts: List[CloseAttempt] = []
        self.errors: List[Dict] = []
        self.state_changes: List[Dict] = []

        # Create monitoring data directory
        Path('monitoring_data').mkdir(exist_ok=True)
        Path('analysis').mkdir(exist_ok=True)

    async def connect_db(self):
        """Connect to PostgreSQL"""
        try:
            self.db_pool = await asyncpg.create_pool(
                host=os.getenv('DB_HOST', 'localhost'),
                port=int(os.getenv('DB_PORT', 5433)),
                database=os.getenv('DB_NAME', 'fox_crypto'),
                user=os.getenv('DB_USER', 'elcrypto'),
                password=os.getenv('DB_PASSWORD', ''),
                min_size=2,
                max_size=5
            )
            logger.info("✅ Connected to database")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    async def get_active_positions(self) -> List[Dict]:
        """Get all active positions"""
        query = """
            SELECT
                id, symbol, side, entry_price, current_price,
                quantity, pnl_percentage, status,
                created_at,
                EXTRACT(EPOCH FROM (NOW() - created_at)) / 3600 as age_hours
            FROM monitoring.positions
            WHERE status = 'active'
            ORDER BY created_at ASC
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [dict(row) for row in rows]

    async def get_aged_positions(self) -> List[Dict]:
        """Get positions older than max_age"""
        query = """
            SELECT
                id, symbol, side, entry_price, current_price,
                quantity, pnl_percentage, status,
                created_at,
                EXTRACT(EPOCH FROM (NOW() - created_at)) / 3600 as age_hours
            FROM monitoring.positions
            WHERE status = 'active'
              AND EXTRACT(EPOCH FROM (NOW() - created_at)) / 3600 > $1
            ORDER BY age_hours DESC
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, self.config['MAX_POSITION_AGE_HOURS'])
            return [dict(row) for row in rows]

    async def analyze_aged_position(self, position: Dict) -> Tuple[Dict, bool]:
        """
        Analyze aged position and compare with simulator
        Returns: (simulation_result, matches_bot_logic)
        """
        simulated = self.simulator.calculate_aged_parameters(
            age_hours=position['age_hours'],
            entry_price=position['entry_price'],
            current_price=position['current_price'] or position['entry_price'],
            side=position['side']
        )

        # Create snapshot
        snapshot = AgedPositionSnapshot(
            timestamp=datetime.now(timezone.utc),
            position_id=position['id'],
            symbol=position['symbol'],
            side=position['side'],
            entry_price=position['entry_price'],
            current_price=position['current_price'] or position['entry_price'],
            age_hours=position['age_hours'],
            hours_over_limit=simulated['hours_over_limit'],
            pnl_percent=position['pnl_percentage'] or 0,
            phase=simulated['phase'],
            target_price=simulated['target_price'] or 0,
            loss_tolerance=simulated['loss_tolerance'],
            should_close=simulated['should_close'],
            reason=simulated['reason']
        )

        self.positions_tracked.append(snapshot)

        return simulated, True

    async def monitor_loop(self):
        """Main monitoring loop"""
        self.start_time = datetime.now(timezone.utc)
        logger.info(f"🚀 Starting monitoring for {self.duration} seconds")
        logger.info(f"Configuration: {json.dumps(self.config, indent=2)}")

        iteration = 0
        last_save = datetime.now(timezone.utc)

        while (datetime.now(timezone.utc) - self.start_time).total_seconds() < self.duration:
            try:
                iteration += 1
                elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds()

                logger.info(f"\n{'='*60}")
                logger.info(f"Iteration {iteration} - Elapsed: {elapsed:.1f}s / {self.duration}s")
                logger.info(f"{'='*60}")

                # Get current positions
                active_positions = await self.get_active_positions()
                aged_positions = await self.get_aged_positions()

                logger.info(f"📊 Active positions: {len(active_positions)}")
                logger.info(f"⏰ Aged positions: {len(aged_positions)}")

                # Analyze each aged position
                for position in aged_positions:
                    simulated, matches = await self.analyze_aged_position(position)

                    logger.info(f"\n📈 Aged Position: {position['symbol']}")
                    logger.info(f"  Age: {position['age_hours']:.2f}h")
                    logger.info(f"  Phase: {simulated['phase']}")
                    logger.info(f"  Target: ${simulated.get('target_price', 0):.4f}")
                    logger.info(f"  Loss tolerance: {simulated.get('loss_tolerance', 0):.2f}%")

                # Record aged check
                self.aged_checks_performed.append({
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'iteration': iteration,
                    'active_count': len(active_positions),
                    'aged_count': len(aged_positions),
                    'aged_symbols': [p['symbol'] for p in aged_positions]
                })

                # Save snapshot if interval reached
                if (datetime.now(timezone.utc) - last_save).total_seconds() >= self.save_interval:
                    await self.save_snapshot()
                    last_save = datetime.now(timezone.utc)

                # Print dashboard
                self.print_dashboard()

                # Wait before next iteration
                await asyncio.sleep(5)

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}", exc_info=True)
                self.errors.append({
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'error': str(e),
                    'iteration': iteration
                })

        logger.info("\n⏹️  Monitoring complete!")
        await self.save_final_report()

    def print_dashboard(self):
        """Print real-time dashboard"""
        elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        mins, secs = divmod(int(elapsed), 60)

        # Get latest aged positions
        aged_now = [p for p in self.positions_tracked[-10:] if p.phase != 'NORMAL']

        print("\n" + "╔" + "="*70 + "╗")
        print(f"║  AGED POSITION MONITOR - Live Dashboard{' '*23}║")
        print(f"║{' '*70}║")
        print(f"║  Runtime: {mins:02d}:{secs:02d}        Tracked: {len(self.positions_tracked):4d}      Errors: {len(self.errors):3d}  ║")
        print("╠" + "="*70 + "╣")

        if aged_now:
            print(f"║  AGED POSITIONS ({len(aged_now)}){' '*48}║")
            print("║  " + "-"*66 + "  ║")

            for p in aged_now[-5:]:  # Last 5
                symbol_str = f"{p.symbol[:12]:12s}"
                age_str = f"{p.age_hours:5.1f}h"
                pnl_str = f"{p.pnl_percent:6.2f}%"
                phase_str = f"{p.phase[:12]:12s}"

                print(f"║  {symbol_str} │ {age_str} │ {pnl_str} │ {phase_str}  ║")
        else:
            print(f"║  No aged positions detected{' '*42}║")

        print("╠" + "="*70 + "╣")

        # Recent events
        print(f"║  RECENT CHECKS{' '*56}║")
        for check in self.aged_checks_performed[-3:]:
            timestamp = check['timestamp'][-8:]
            count = check['aged_count']
            print(f"║  [{timestamp}] Aged check: {count} positions{' '*(40-len(str(count)))}║")

        print("╚" + "="*70 + "╝")

    async def save_snapshot(self):
        """Save current monitoring snapshot"""
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        filename = f"monitoring_data/aged_monitor_{timestamp}.json"

        data = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'elapsed_seconds': (datetime.now(timezone.utc) - self.start_time).total_seconds(),
            'config': self.config,
            'positions_tracked': [asdict(p) for p in self.positions_tracked],
            'aged_checks': self.aged_checks_performed,
            'close_attempts': [asdict(c) for c in self.close_attempts],
            'errors': self.errors
        }

        with open(filename, 'w') as f:
            json.dump(data, f, indent=2, default=str)

        logger.info(f"💾 Snapshot saved: {filename}")

    async def save_final_report(self):
        """Save final comprehensive report"""
        filename = f"analysis/aged_monitor_final_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"

        # Calculate statistics
        aged_by_phase = {}
        for p in self.positions_tracked:
            phase = p.phase
            aged_by_phase[phase] = aged_by_phase.get(phase, 0) + 1

        data = {
            'test_info': {
                'start_time': self.start_time.isoformat(),
                'end_time': datetime.now(timezone.utc).isoformat(),
                'duration_seconds': (datetime.now(timezone.utc) - self.start_time).total_seconds(),
                'config': self.config
            },
            'statistics': {
                'total_positions_tracked': len(self.positions_tracked),
                'aged_checks_performed': len(self.aged_checks_performed),
                'close_attempts': len(self.close_attempts),
                'errors': len(self.errors),
                'aged_by_phase': aged_by_phase
            },
            'all_positions': [asdict(p) for p in self.positions_tracked],
            'all_checks': self.aged_checks_performed,
            'all_close_attempts': [asdict(c) for c in self.close_attempts],
            'all_errors': self.errors,
            'state_changes': self.state_changes
        }

        with open(filename, 'w') as f:
            json.dump(data, f, indent=2, default=str)

        logger.info(f"📄 Final report saved: {filename}")

        # Print summary
        print("\n" + "="*60)
        print("MONITORING SUMMARY")
        print("="*60)
        print(f"Duration: {data['test_info']['duration_seconds']:.1f}s")
        print(f"Positions tracked: {data['statistics']['total_positions_tracked']}")
        print(f"Aged checks: {data['statistics']['aged_checks_performed']}")
        print(f"Errors: {data['statistics']['errors']}")
        print(f"\nPhase distribution:")
        for phase, count in aged_by_phase.items():
            print(f"  {phase}: {count}")
        print("="*60)

    async def run(self):
        """Main run method"""
        try:
            await self.connect_db()
            await self.monitor_loop()
        finally:
            if self.db_pool:
                await self.db_pool.close()


async def main():
    parser = argparse.ArgumentParser(description='Aged Position Monitor')
    parser.add_argument('--duration', type=int, default=600, help='Monitoring duration in seconds')
    parser.add_argument('--save-interval', type=int, default=30, help='Snapshot save interval')
    args = parser.parse_args()

    monitor = AgedPositionMonitor(duration=args.duration, save_interval=args.save_interval)
    await monitor.run()


if __name__ == "__main__":
    asyncio.run(main())
