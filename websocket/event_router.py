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
        event = Event(
            name=event_name,
            data=data or {},
            source=kwargs.get('source'),
            timestamp=kwargs.get('timestamp', datetime.now())
        )

        await self._event_queue.put(event)

        # Start processing if not already running
        if not self._processing:
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
            # Apply middleware
            for middleware in self._middleware:
                if asyncio.iscoroutinefunction(middleware):
                    event = await middleware(event)
                else:
                    event = middleware(event)

                if not event:
                    return

            # Get handlers for event
            handlers = self._handlers.get(event.name, [])

            # Also check for wildcard handlers
            if '*' in self._handlers:
                handlers.extend(self._handlers['*'])

            # Log event handling (only for position.update)
            if event.name == 'position.update':
                logger.info(f"📡 Event '{event.name}': {len(handlers)} handlers")

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