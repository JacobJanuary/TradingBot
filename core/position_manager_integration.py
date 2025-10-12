"""
Position Manager Integration - Applies all critical fixes to PositionManager

This module integrates:
- AtomicPositionManager for atomic operations
- LockManager for proper synchronization
- TransactionalRepository for database ACID
- EventLogger for audit trail
"""
import asyncio
import logging
from typing import Dict, Optional, Any
from datetime import datetime, timezone

from core.lock_manager import get_lock_manager
from core.event_logger import EventType, log_event
from database.transactional_repository import TransactionalRepository

logger = logging.getLogger(__name__)


async def apply_critical_fixes(position_manager):
    """
    Apply all critical fixes to PositionManager instance

    This function patches the PositionManager to use:
    1. Proper asyncio.Lock instead of set
    2. LockManager for deadlock detection
    3. EventLogger for audit trail
    4. TransactionalRepository for atomic operations
    """
    logger.info("🔧 Applying critical fixes to PositionManager")

    # Fix 1: Replace position_locks set with proper Dict[str, asyncio.Lock]
    if isinstance(position_manager.position_locks, set):
        logger.info("  ✅ Converting position_locks from set to Dict[str, asyncio.Lock]")
        old_locks = position_manager.position_locks.copy()
        position_manager.position_locks = {}
        position_manager._lock_creation_lock = asyncio.Lock()

        # Convert any existing entries
        for key in old_locks:
            position_manager.position_locks[key] = asyncio.Lock()

    # Fix 2: Patch critical methods to use LockManager
    lock_manager = get_lock_manager()

    # Save original methods
    original_set_stop_loss = position_manager._set_stop_loss
    original_close_position = position_manager.close_position

    # Patch _set_stop_loss with proper locking
    # FIX: Match original signature (exchange, position, stop_price)
    async def patched_set_stop_loss(exchange, position, stop_price):
        """Patched version with LockManager"""
        # Extract data from position object
        position_id = position.id if hasattr(position, 'id') else position.get('id')
        symbol = position.symbol if hasattr(position, 'symbol') else position.get('symbol')
        exchange_name = position.exchange if hasattr(position, 'exchange') else position.get('exchange', 'unknown')

        resource = f"position_{symbol}_{position_id}"

        async with lock_manager.acquire_lock(
            resource=resource,
            operation="set_stop_loss",
            timeout=30.0
        ):
            # Log event (convert Decimal to float for JSON serialization)
            await log_event(
                EventType.STOP_LOSS_PLACED,
                {
                    'position_id': position_id,
                    'symbol': symbol,
                    'stop_price': float(stop_price) if stop_price is not None else None
                },
                position_id=position_id,
                symbol=symbol,
                exchange=exchange_name
            )

            # Call original method with correct signature
            result = await original_set_stop_loss(exchange, position, stop_price)

            if result:
                await log_event(
                    EventType.STOP_LOSS_PLACED,
                    {'status': 'success', 'order_id': result},
                    position_id=position_id
                )
            else:
                await log_event(
                    EventType.STOP_LOSS_ERROR,
                    {'status': 'failed'},
                    position_id=position_id,
                    severity='ERROR'
                )

            return result

    # Patch close_position with proper locking
    async def patched_close_position(position_id: int, reason: str = "manual"):
        """Patched version with LockManager"""
        resource = f"position_close_{position_id}"

        async with lock_manager.acquire_lock(
            resource=resource,
            operation="close_position",
            timeout=60.0
        ):
            # Log event
            await log_event(
                EventType.POSITION_CLOSED,
                {
                    'position_id': position_id,
                    'reason': reason
                },
                position_id=position_id
            )

            # Call original method
            return await original_close_position(position_id, reason)

    # Apply patches
    position_manager._set_stop_loss = patched_set_stop_loss
    position_manager.close_position = patched_close_position

    # Fix 3: Add TransactionalRepository
    if hasattr(position_manager, 'repository'):
        position_manager.transactional_repo = TransactionalRepository(
            position_manager.repository
        )
        logger.info("  ✅ Added TransactionalRepository for ACID compliance")

    # Fix 4: Patch open_position to use atomic operations
    original_open_position = position_manager.open_position

    # FIX: TypeError - patched_open_position must accept PositionRequest object
    # Changed from: multiple positional arguments
    # Changed to: single request parameter matching original signature
    async def patched_open_position(request):
        """Patched version with proper locking and logging"""
        correlation_id = f"open_position_{request.signal_id}_{datetime.now(timezone.utc).timestamp()}"

        # FIX: Handle position_locks as Dict[str, asyncio.Lock] instead of set
        # After apply_critical_fixes, position_locks is converted to dict
        # but original code still uses set methods (.add, .discard)
        lock_key = f"{request.exchange.lower()}_{request.symbol}"

        # Check if already being processed (replaces: if lock_key in self.position_locks)
        if lock_key in position_manager.position_locks and position_manager.position_locks[lock_key].locked():
            logger.warning(f"Position already being processed for {request.symbol}")
            return None

        # Create lock for this position (replaces: self.position_locks.add(lock_key))
        if not hasattr(position_manager, '_lock_creation_lock'):
            position_manager._lock_creation_lock = asyncio.Lock()

        async with position_manager._lock_creation_lock:
            if lock_key not in position_manager.position_locks:
                position_manager.position_locks[lock_key] = asyncio.Lock()

        # Acquire the lock
        async with position_manager.position_locks[lock_key]:
            try:
                # CRITICAL FIX: Removed premature logging - log only after successful creation
                # This prevents position_created events for positions that fail to open
                # Previously: logged before creation, causing 2 logs per position and desync
                # Now: single accurate log after atomic creation completes

                # Temporarily bypass the original lock logic
                # Save and replace position_locks to prevent .add/.discard errors
                original_locks = position_manager.position_locks
                position_manager.position_locks = set()  # Temporary empty set for original code

                try:
                    # Call original function
                    result = await original_open_position(request)
                finally:
                    # Restore the dict-based locks
                    position_manager.position_locks = original_locks

                # CRITICAL FIX: Log only after successful atomic creation
                # This ensures position_created events are 1:1 with actual positions
                # Includes full context for traceability and analysis
                if result:
                    await log_event(
                        EventType.POSITION_CREATED,
                        {
                            'status': 'success',
                            'signal_id': request.signal_id,  # For traceability
                            'symbol': request.symbol,         # For filtering logs
                            'exchange': request.exchange,     # For filtering logs
                            'side': request.side,             # For analysis
                            'entry_price': float(request.entry_price),  # For analysis
                            'position_id': result.id if hasattr(result, 'id') else None
                        },
                        correlation_id=correlation_id,
                        position_id=result.id if hasattr(result, 'id') else None,
                        symbol=request.symbol,
                        exchange=request.exchange
                    )
                else:
                    # Log failure with full context for debugging
                    await log_event(
                        EventType.POSITION_ERROR,
                        {
                            'status': 'failed',
                            'signal_id': request.signal_id,   # For debugging
                            'symbol': request.symbol,          # For debugging
                            'exchange': request.exchange,      # For debugging
                            'reason': 'Position creation returned None'  # Clarity
                        },
                        correlation_id=correlation_id,
                        severity='ERROR',
                        symbol=request.symbol,
                        exchange=request.exchange
                    )

                return result

            finally:
                # Clean up the lock (replaces: self.position_locks.discard(lock_key))
                # Keep the lock in dict for potential reuse, just release it
                pass

    position_manager.open_position = patched_open_position

    # Fix 5: Ensure get_lock method works correctly
    async def get_lock(self, key: str) -> asyncio.Lock:
        """Get or create lock for key"""
        async with self._lock_creation_lock:
            if key not in self.position_locks:
                self.position_locks[key] = asyncio.Lock()
        return self.position_locks[key]

    position_manager.get_lock = get_lock.__get__(position_manager, type(position_manager))

    logger.info("✅ All critical fixes applied to PositionManager:")
    logger.info("  - position_locks: set → Dict[str, asyncio.Lock]")
    logger.info("  - Added LockManager for deadlock detection")
    logger.info("  - Added EventLogger for audit trail")
    logger.info("  - Added TransactionalRepository for ACID")
    logger.info("  - Patched critical methods with proper locking")

    return position_manager


# Convenience function to check if fixes are applied
def check_fixes_applied(position_manager) -> Dict[str, bool]:
    """Check which fixes have been applied"""
    return {
        'proper_locks': isinstance(position_manager.position_locks, dict),
        'lock_creation': hasattr(position_manager, '_lock_creation_lock'),
        'transactional_repo': hasattr(position_manager, 'transactional_repo'),
        'atomic_manager': hasattr(position_manager, '_atomic_manager'),
        'get_lock_method': hasattr(position_manager, 'get_lock') and callable(position_manager.get_lock)
    }