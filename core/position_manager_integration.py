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
    original_trailing_stop_check = position_manager.trailing_stop_check

    # Patch _set_stop_loss with proper locking
    async def patched_set_stop_loss(position, exchange_name):
        """Patched version with LockManager"""
        resource = f"position_{position['symbol']}_{position['id']}"

        async with lock_manager.acquire_lock(
            resource=resource,
            operation="set_stop_loss",
            timeout=30.0
        ):
            # Log event
            await log_event(
                EventType.STOP_LOSS_PLACED,
                {
                    'position_id': position['id'],
                    'symbol': position['symbol'],
                    'stop_price': position.get('stop_loss_price')
                },
                position_id=position['id'],
                symbol=position['symbol'],
                exchange=exchange_name
            )

            # Call original method
            result = await original_set_stop_loss(position, exchange_name)

            if result:
                await log_event(
                    EventType.STOP_LOSS_PLACED,
                    {'status': 'success', 'order_id': result},
                    position_id=position['id']
                )
            else:
                await log_event(
                    EventType.STOP_LOSS_ERROR,
                    {'status': 'failed'},
                    position_id=position['id'],
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

    # Patch trailing_stop_check with proper locking
    async def patched_trailing_stop_check():
        """Patched version with LockManager"""
        resource = "trailing_stop_global"

        async with lock_manager.acquire_lock(
            resource=resource,
            operation="trailing_stop_check",
            timeout=120.0
        ):
            # Call original method
            return await original_trailing_stop_check()

    # Apply patches
    position_manager._set_stop_loss = patched_set_stop_loss
    position_manager.close_position = patched_close_position
    position_manager.trailing_stop_check = patched_trailing_stop_check

    # Fix 3: Add TransactionalRepository
    if hasattr(position_manager, 'repository'):
        position_manager.transactional_repo = TransactionalRepository(
            position_manager.repository
        )
        logger.info("  ✅ Added TransactionalRepository for ACID compliance")

    # Fix 4: Patch open_position to use atomic operations
    original_open_position = position_manager.open_position

    async def patched_open_position(
        signal_id: int,
        symbol: str,
        exchange: str,
        side: str,
        quantity: float,
        entry_price: float,
        stop_loss_price: float,
        take_profit_price: Optional[float] = None,
        metadata: Optional[Dict] = None
    ):
        """Patched version with atomic operations"""
        correlation_id = f"open_position_{signal_id}_{datetime.now(timezone.utc).timestamp()}"

        # Log event
        await log_event(
            EventType.POSITION_CREATED,
            {
                'signal_id': signal_id,
                'symbol': symbol,
                'exchange': exchange,
                'side': side,
                'quantity': quantity,
                'entry_price': entry_price,
                'stop_loss_price': stop_loss_price
            },
            correlation_id=correlation_id,
            symbol=symbol,
            exchange=exchange
        )

        # Use atomic manager if available
        try:
            from core.atomic_position_manager import AtomicPositionManager

            if not hasattr(position_manager, '_atomic_manager'):
                position_manager._atomic_manager = AtomicPositionManager(
                    repository=position_manager.repository,
                    exchange_manager=position_manager.exchanges,
                    stop_loss_manager=position_manager
                )

            # Try atomic creation
            result = await position_manager._atomic_manager.open_position_atomic(
                signal_id=signal_id,
                symbol=symbol,
                exchange=exchange,
                side=side,
                quantity=quantity,
                entry_price=entry_price,
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
                metadata=metadata
            )

            await log_event(
                EventType.POSITION_CREATED,
                {'status': 'success', 'position_id': result.get('position_id')},
                correlation_id=correlation_id,
                position_id=result.get('position_id')
            )

            return result

        except Exception as e:
            logger.warning(f"Atomic creation failed, using original: {e}")

            await log_event(
                EventType.POSITION_ERROR,
                {'error': str(e), 'fallback': 'original_method'},
                correlation_id=correlation_id,
                severity='WARNING'
            )

            # Fallback to original
            return await original_open_position(
                signal_id=signal_id,
                symbol=symbol,
                exchange=exchange,
                side=side,
                quantity=quantity,
                entry_price=entry_price,
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
                metadata=metadata
            )

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