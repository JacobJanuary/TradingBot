"""
Aged Position Events for event-driven architecture
Part of Phase 5: Events implementation
DO NOT modify existing code - this is an addition only!
"""

import asyncio
import logging
from typing import Dict, Optional, Any, List, Callable
from datetime import datetime, timezone
from decimal import Decimal
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class AgedEventType(Enum):
    """Types of aged position events"""
    POSITION_DETECTED = "aged_position_detected"
    PHASE_CHANGED = "aged_phase_changed"
    TARGET_REACHED = "aged_target_reached"
    CLOSE_TRIGGERED = "aged_close_triggered"
    CLOSE_SUCCESS = "aged_close_success"
    CLOSE_FAILED = "aged_close_failed"
    POSITION_RECOVERED = "aged_position_recovered"
    POSITION_STALE = "aged_position_stale"
    METRICS_UPDATED = "aged_metrics_updated"


@dataclass
class AgedPositionEvent:
    """Event data for aged position events"""
    event_type: AgedEventType
    timestamp: datetime
    position_id: str
    symbol: str
    exchange: str
    phase: str
    data: Dict[str, Any]

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        result = asdict(self)
        result['event_type'] = self.event_type.value
        result['timestamp'] = self.timestamp.isoformat()
        return result


class AgedPositionEventEmitter:
    """
    Event emitter for aged position events
    Integrates with existing EventRouter if available
    """

    def __init__(self, event_router=None):
        self.event_router = event_router
        self.listeners: Dict[AgedEventType, List[Callable]] = {}
        self.event_queue: asyncio.Queue = asyncio.Queue()
        self.webhook_urls: List[str] = []
        self.stats = {
            'events_emitted': 0,
            'events_processed': 0,
            'webhook_sent': 0,
            'webhook_failed': 0
        }

        logger.info("AgedPositionEventEmitter initialized")

    def add_listener(self, event_type: AgedEventType, callback: Callable):
        """Add event listener for specific event type"""
        if event_type not in self.listeners:
            self.listeners[event_type] = []
        self.listeners[event_type].append(callback)
        logger.debug(f"Added listener for {event_type.value}")

    def remove_listener(self, event_type: AgedEventType, callback: Callable):
        """Remove event listener"""
        if event_type in self.listeners:
            self.listeners[event_type].remove(callback)

    def add_webhook(self, url: str):
        """Add webhook URL for notifications"""
        if url not in self.webhook_urls:
            self.webhook_urls.append(url)
            logger.info(f"Added webhook: {url}")

    async def emit(self, event: AgedPositionEvent):
        """Emit event to all listeners and systems"""
        self.stats['events_emitted'] += 1

        # Add to queue
        await self.event_queue.put(event)

        # Notify local listeners
        if event.event_type in self.listeners:
            for callback in self.listeners[event.event_type]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(event)
                    else:
                        callback(event)
                except Exception as e:
                    logger.error(f"Listener error for {event.event_type}: {e}")

        # Send to EventRouter if available
        if self.event_router:
            try:
                await self._send_to_event_router(event)
            except Exception as e:
                logger.debug(f"EventRouter send failed (non-critical): {e}")

        # Send webhooks
        if self.webhook_urls:
            asyncio.create_task(self._send_webhooks(event))

        self.stats['events_processed'] += 1

    async def _send_to_event_router(self, event: AgedPositionEvent):
        """Send event to existing EventRouter system"""
        if hasattr(self.event_router, 'emit'):
            await self.event_router.emit(
                event_type=event.event_type.value,
                data=event.to_dict()
            )

    async def _send_webhooks(self, event: AgedPositionEvent):
        """Send event to webhook URLs"""
        import aiohttp

        for url in self.webhook_urls:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url,
                        json=event.to_dict(),
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as response:
                        if response.status == 200:
                            self.stats['webhook_sent'] += 1
                        else:
                            self.stats['webhook_failed'] += 1
                            logger.warning(f"Webhook failed: {url} - {response.status}")
            except Exception as e:
                self.stats['webhook_failed'] += 1
                logger.error(f"Webhook error: {url} - {e}")

    def get_stats(self) -> Dict:
        """Get event statistics"""
        return self.stats.copy()


class AgedEventFactory:
    """Factory for creating aged position events"""

    @staticmethod
    def create_detection_event(position, phase: str) -> AgedPositionEvent:
        """Create position detected event"""
        return AgedPositionEvent(
            event_type=AgedEventType.POSITION_DETECTED,
            timestamp=datetime.now(timezone.utc),
            position_id=getattr(position, 'id', position.symbol),
            symbol=position.symbol,
            exchange=position.exchange,
            phase=phase,
            data={
                'age_hours': getattr(position, 'age_hours', 0),
                'entry_price': str(position.entry_price),
                'current_price': str(position.current_price),
                'unrealized_pnl': str(getattr(position, 'unrealized_pnl', 0))
            }
        )

    @staticmethod
    def create_phase_change_event(
        position_id: str,
        symbol: str,
        exchange: str,
        old_phase: str,
        new_phase: str,
        age_hours: float
    ) -> AgedPositionEvent:
        """Create phase change event"""
        return AgedPositionEvent(
            event_type=AgedEventType.PHASE_CHANGED,
            timestamp=datetime.now(timezone.utc),
            position_id=position_id,
            symbol=symbol,
            exchange=exchange,
            phase=new_phase,
            data={
                'old_phase': old_phase,
                'new_phase': new_phase,
                'age_hours': age_hours
            }
        )

    @staticmethod
    def create_close_success_event(
        position,
        phase: str,
        order_id: str,
        order_type: str,
        execution_time: float,
        attempts: int
    ) -> AgedPositionEvent:
        """Create close success event"""
        return AgedPositionEvent(
            event_type=AgedEventType.CLOSE_SUCCESS,
            timestamp=datetime.now(timezone.utc),
            position_id=getattr(position, 'id', position.symbol),
            symbol=position.symbol,
            exchange=position.exchange,
            phase=phase,
            data={
                'order_id': order_id,
                'order_type': order_type,
                'execution_time': execution_time,
                'attempts': attempts,
                'close_price': str(position.current_price)
            }
        )

    @staticmethod
    def create_close_failed_event(
        position,
        phase: str,
        error_message: str,
        attempts: int
    ) -> AgedPositionEvent:
        """Create close failed event"""
        return AgedPositionEvent(
            event_type=AgedEventType.CLOSE_FAILED,
            timestamp=datetime.now(timezone.utc),
            position_id=getattr(position, 'id', position.symbol),
            symbol=position.symbol,
            exchange=position.exchange,
            phase=phase,
            data={
                'error_message': error_message,
                'attempts': attempts
            }
        )


class EventOrchestrator:
    """
    Orchestrates aged position events with other systems
    Provides integration points without modifying existing code
    """

    def __init__(self, emitter: AgedPositionEventEmitter):
        self.emitter = emitter
        self.rules: List[Dict] = []

    def add_rule(self, rule: Dict):
        """Add orchestration rule"""
        self.rules.append(rule)

    async def process_event(self, event: AgedPositionEvent):
        """Process event according to orchestration rules"""
        for rule in self.rules:
            if self._matches_rule(event, rule):
                await self._execute_rule(event, rule)

    def _matches_rule(self, event: AgedPositionEvent, rule: Dict) -> bool:
        """Check if event matches rule conditions"""
        if 'event_type' in rule:
            if event.event_type != rule['event_type']:
                return False

        if 'phase' in rule:
            if event.phase != rule['phase']:
                return False

        if 'exchange' in rule:
            if event.exchange != rule['exchange']:
                return False

        return True

    async def _execute_rule(self, event: AgedPositionEvent, rule: Dict):
        """Execute rule action"""
        try:
            action = rule.get('action')
            if action and callable(action):
                if asyncio.iscoroutinefunction(action):
                    await action(event)
                else:
                    action(event)
        except Exception as e:
            logger.error(f"Rule execution error: {e}")