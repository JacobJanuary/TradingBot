"""
Aged Position Metrics for Prometheus monitoring
Part of Phase 4: Metrics implementation
DO NOT modify existing code - this is an addition only!
"""

import time
from typing import Dict, Optional
from datetime import datetime, timezone
from decimal import Decimal
from prometheus_client import Counter, Gauge, Histogram, Summary
import logging

logger = logging.getLogger(__name__)


class AgedPositionMetrics:
    """
    Prometheus metrics for aged position monitoring
    Tracks all important metrics without modifying existing code
    """

    def __init__(self):
        # Counters
        self.positions_detected = Counter(
            'aged_positions_detected_total',
            'Total aged positions detected',
            ['exchange', 'phase']
        )

        self.positions_closed = Counter(
            'aged_positions_closed_total',
            'Total aged positions closed',
            ['exchange', 'phase', 'order_type']
        )

        self.close_failures = Counter(
            'aged_positions_close_failures_total',
            'Total failed close attempts',
            ['exchange', 'reason']
        )

        self.phase_transitions = Counter(
            'aged_phase_transitions_total',
            'Total phase transitions',
            ['from_phase', 'to_phase']
        )

        # Gauges
        self.active_aged_positions = Gauge(
            'aged_positions_active',
            'Current number of active aged positions',
            ['exchange', 'phase']
        )

        self.oldest_position_age = Gauge(
            'aged_position_oldest_hours',
            'Age of oldest position in hours'
        )

        self.total_loss_tolerance = Gauge(
            'aged_positions_total_loss_tolerance_percent',
            'Total loss tolerance across all positions'
        )

        # Histograms
        self.close_execution_time = Histogram(
            'aged_position_close_duration_seconds',
            'Time to close aged position',
            buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)
        )

        self.position_age_at_close = Histogram(
            'aged_position_age_at_close_hours',
            'Age of position when closed',
            buckets=(3, 6, 12, 24, 48, 72, 168)  # 3h to 1 week
        )

        self.close_attempts = Histogram(
            'aged_position_close_attempts',
            'Number of attempts to close position',
            buckets=(1, 2, 3, 5, 7, 10)
        )

        # Summary
        self.pnl_at_close = Summary(
            'aged_position_pnl_at_close_percent',
            'PnL percentage at close'
        )

        logger.info("AgedPositionMetrics initialized")

    def record_detection(self, exchange: str, phase: str):
        """Record aged position detection"""
        self.positions_detected.labels(exchange=exchange, phase=phase).inc()

    def record_close_success(
        self,
        exchange: str,
        phase: str,
        order_type: str,
        execution_time: float,
        attempts: int,
        age_hours: float,
        pnl_percent: float
    ):
        """Record successful close with all metrics"""
        # Increment counter
        self.positions_closed.labels(
            exchange=exchange,
            phase=phase,
            order_type=order_type
        ).inc()

        # Record histograms
        self.close_execution_time.observe(execution_time)
        self.position_age_at_close.observe(age_hours)
        self.close_attempts.observe(attempts)

        # Record PnL
        self.pnl_at_close.observe(pnl_percent)

    def record_close_failure(self, exchange: str, reason: str):
        """Record failed close attempt"""
        self.close_failures.labels(exchange=exchange, reason=reason).inc()

    def record_phase_transition(self, from_phase: str, to_phase: str):
        """Record phase transition"""
        self.phase_transitions.labels(
            from_phase=from_phase,
            to_phase=to_phase
        ).inc()

    def update_active_positions(self, positions_by_phase: Dict[str, int]):
        """Update active position gauges"""
        # Clear all gauges first
        self.active_aged_positions._metrics.clear()

        # Set new values
        for phase, count in positions_by_phase.items():
            for exchange in ['binance', 'bybit']:  # Known exchanges
                if count > 0:
                    self.active_aged_positions.labels(
                        exchange=exchange,
                        phase=phase
                    ).set(count)

    def update_oldest_age(self, age_hours: float):
        """Update oldest position age"""
        self.oldest_position_age.set(age_hours)

    def update_total_loss_tolerance(self, total_tolerance: float):
        """Update total loss tolerance"""
        self.total_loss_tolerance.set(total_tolerance)

    def get_metrics_summary(self) -> Dict:
        """Get summary of all metrics for logging"""
        try:
            return {
                'positions_detected': self.positions_detected._value._value,
                'positions_closed': self.positions_closed._value._value,
                'close_failures': self.close_failures._value._value,
                'active_positions': self.active_aged_positions._value._value,
                'oldest_age_hours': self.oldest_position_age._value
            }
        except:
            return {}


class MetricsCollector:
    """
    Collector for periodic metrics updates
    Runs independently without modifying existing code
    """

    def __init__(self, metrics: AgedPositionMetrics, monitor=None):
        self.metrics = metrics
        self.monitor = monitor
        self.last_update = time.time()

    async def update_metrics(self):
        """Update all metrics from monitor state"""
        if not self.monitor:
            return

        try:
            # Count positions by phase
            positions_by_phase = {}
            oldest_age = 0
            total_tolerance = Decimal('0')

            for symbol, target in self.monitor.aged_targets.items():
                phase = target.phase
                positions_by_phase[phase] = positions_by_phase.get(phase, 0) + 1

                if target.hours_aged > oldest_age:
                    oldest_age = target.hours_aged

                total_tolerance += target.loss_tolerance

            # Update gauges
            self.metrics.update_active_positions(positions_by_phase)
            self.metrics.update_oldest_age(oldest_age)
            self.metrics.update_total_loss_tolerance(float(total_tolerance))

            # Log update
            current_time = time.time()
            if current_time - self.last_update > 60:  # Log every minute
                logger.debug(f"Metrics updated: {positions_by_phase}")
                self.last_update = current_time

        except Exception as e:
            logger.error(f"Failed to update metrics: {e}")