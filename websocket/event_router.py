import asyncio
import logging
from typing import Dict, List, Callable, Any
from dataclasses import dataclass
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """Event data structure"""
    name: str
    data: Dict[str, Any]
    timestamp: datetime = None
    source: str = None

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now()


class EventRouter:
    """
    Central event routing system
    Inspired by Node.js EventEmitter pattern
    """

    def __init__(self):
        """Initialize event router"""
        self._handlers = defaultdict(list)
        self._middleware = []
        self._event_queue = asyncio.Queue()
        self._processing = False

        # Statistics
        self.stats = {
            'events_processed': 0,
            'events_failed': 0,
            'handlers_registered': 0
        }

        logger.info("EventRouter initialized")

    def on(self, event_name: str):
        """
        Decorator to register event handler

        Usage:
            @router.on('position.update')
            async def handle_position(data):
                pass
        """

        def decorator(func: Callable):
            self.add_handler(event_name, func)
            return func

        return decorator

    def add_handler(self, event_name: str, handler: Callable):
        """Add event handler"""
        self._handlers[event_name].append(handler)
        self.stats['handlers_registered'] += 1
        logger.debug(f"Handler registered for '{event_name}'")

    def remove_handler(self, event_name: str, handler: Callable):
        """Remove event handler"""
        if event_name in self._handlers:
            self._handlers[event_name].remove(handler)

    def use(self, middleware: Callable):
        """Add middleware for all events"""
        self._middleware.append(middleware)

    async def emit(self, event_name: str, data: Dict = None, **kwargs):
        """
        Emit event asynchronously

        Args:
            event_name: Name of the event
            data: Event data dictionary
            **kwargs: Additional event metadata
        """
        logger.debug(f"[EventRouter] emit() called: event='{event_name}', source={kwargs.get('source')}")
        
        event = Event(
            name=event_name,
            data=data or {},
            source=kwargs.get('source'),
            timestamp=kwargs.get('timestamp', datetime.now())
        )

        await self._event_queue.put(event)
        logger.debug(f"[EventRouter] Event '{event_name}' queued (queue_size={self._event_queue.qsize()})")

        # Start processing if not already running
        if not self._processing:
            logger.debug(f"[EventRouter] Starting event processing task")
            asyncio.create_task(self._process_events())

    async def _process_events(self):
        """Process events from queue"""
        self._processing = True

        try:
            while not self._event_queue.empty():
                event = await self._event_queue.get()
                await self._handle_event(event)

        finally:
            self._processing = False

    async def _handle_event(self, event: Event):
        """Handle single event"""
        try:
            logger.debug(f"[EventRouter] Handling event '{event.name}'...")
            
            # Apply middleware
            for middleware in self._middleware:
                if asyncio.iscoroutinefunction(middleware):
                    event = await middleware(event)
                else:
                    event = middleware(event)

                if not event:
                    logger.debug(f"[EventRouter] Event '{event.name}' blocked by middleware")
                    return

            # Get handlers for event
            handlers = self._handlers.get(event.name, [])

            # Also check for wildcard handlers
            if '*' in self._handlers:
                handlers.extend(self._handlers['*'])

            logger.debug(f"[EventRouter] Found {len(handlers)} handler(s) for '{event.name}'")

            # Execute handlers
            if handlers:
                tasks = []
                for handler in handlers:
                    if asyncio.iscoroutinefunction(handler):
                        tasks.append(handler(event.data))
                    else:
                        handler(event.data)

                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                    logger.debug(f"[EventRouter] All handlers for '{event.name}' completed")
            else:
                # Don't spam logs for known unhandled events (ticker, orderbook, price_update)
                if event.name not in ['ticker', 'orderbook', 'price_update']:
                    logger.warning(f"[EventRouter] No handlers registered for event '{event.name}'!")
                else:
                    logger.debug(f"[EventRouter] Ignoring unhandled market data event '{event.name}'")

            self.stats['events_processed'] += 1

        except Exception as e:
            logger.error(f"Error handling event '{event.name}': {e}")
            self.stats['events_failed'] += 1

            # Emit error event
            if event.name != 'error':
                await self.emit('error', {
                    'original_event': event.name,
                    'error': str(e),
                    'data': event.data
                })

    def get_stats(self) -> Dict:
        """Get router statistics"""
        return {
            **self.stats,
            'handlers': {
                event: len(handlers)
                for event, handlers in self._handlers.items()
            },
            'queue_size': self._event_queue.qsize()
        }