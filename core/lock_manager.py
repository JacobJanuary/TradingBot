"""
Lock Manager - централизованное управление блокировками для предотвращения race conditions

CRITICAL: Этот модуль обеспечивает правильную синхронизацию операций
⚠️ DO NOT MODIFY без полного понимания последствий!
"""
import asyncio
import time
import logging
from typing import Dict, Optional, Set
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class LockInfo:
    """Information about a lock"""
    resource: str
    operation: str
    holder_id: str
    acquired_at: float
    lock: asyncio.Lock


class LockManager:
    """
    Централизованный менеджер блокировок

    Features:
    - Async locks для каждого ресурса
    - Deadlock detection
    - Lock timeout
    - Statistics and monitoring
    - Automatic cleanup
    """

    def __init__(self):
        self._locks: Dict[str, asyncio.Lock] = {}
        self._lock_info: Dict[str, LockInfo] = {}
        self._lock_creation = asyncio.Lock()
        self._lock_wait_times: list = []  # For statistics
        self._deadlock_threshold = 30.0  # seconds

    @asynccontextmanager
    async def acquire_lock(
        self,
        resource: str,
        operation: str,
        timeout: float = 30.0,
        priority: int = 0
    ):
        """
        Acquire lock with timeout and monitoring

        Args:
            resource: Resource to lock (e.g., "position_BTC/USDT")
            operation: Operation name (for debugging)
            timeout: Maximum wait time in seconds
            priority: Priority level (higher = more important)

        Raises:
            asyncio.TimeoutError: If lock cannot be acquired within timeout
        """
        lock_key = f"lock_{resource}"
        holder_id = f"{operation}_{time.time()}_{id(asyncio.current_task())}"

        # Create lock if doesn't exist (thread-safe)
        async with self._lock_creation:
            if lock_key not in self._locks:
                self._locks[lock_key] = asyncio.Lock()
                logger.debug(f"Created new lock for {resource}")

        lock = self._locks[lock_key]
        wait_start = time.time()

        try:
            # Try to acquire lock with timeout
            logger.debug(f"🔒 Acquiring lock for {resource} by {operation}")

            await asyncio.wait_for(
                lock.acquire(),
                timeout=timeout
            )

            wait_time = time.time() - wait_start
            self._lock_wait_times.append(wait_time)

            # Record lock info
            self._lock_info[lock_key] = LockInfo(
                resource=resource,
                operation=operation,
                holder_id=holder_id,
                acquired_at=time.time(),
                lock=lock
            )

            logger.debug(
                f"✅ Lock acquired: {resource} by {operation} "
                f"(waited {wait_time:.3f}s)"
            )

            # Check for potential deadlock
            self._check_for_deadlock()

            yield

        except asyncio.TimeoutError:
            wait_time = time.time() - wait_start
            current_holder = self._lock_info.get(lock_key)

            if current_holder:
                hold_time = time.time() - current_holder.acquired_at
                logger.error(
                    f"❌ Lock timeout for {resource} after {wait_time:.1f}s. "
                    f"Current holder: {current_holder.operation} "
                    f"(holding for {hold_time:.1f}s)"
                )
            else:
                logger.error(f"❌ Lock timeout for {resource} after {wait_time:.1f}s")

            raise

        finally:
            # Release lock if we hold it
            if lock_key in self._lock_info and \
               self._lock_info[lock_key].holder_id == holder_id:
                lock.release()
                del self._lock_info[lock_key]
                logger.debug(f"🔓 Lock released: {resource}")

    def _check_for_deadlock(self):
        """Check for potential deadlock situations"""
        now = time.time()
        long_held_locks = []

        for lock_key, info in self._lock_info.items():
            hold_time = now - info.acquired_at
            if hold_time > self._deadlock_threshold:
                long_held_locks.append((info.resource, info.operation, hold_time))

        if long_held_locks:
            logger.warning(
                f"⚠️ Potential deadlock detected! Locks held > {self._deadlock_threshold}s:"
            )
            for resource, operation, hold_time in long_held_locks:
                logger.warning(f"  - {resource}: {operation} ({hold_time:.1f}s)")

    def get_lock_stats(self) -> Dict:
        """Get lock statistics"""
        now = time.time()

        active_locks = []
        for lock_key, info in self._lock_info.items():
            active_locks.append({
                'resource': info.resource,
                'operation': info.operation,
                'hold_time': now - info.acquired_at
            })

        avg_wait_time = (
            sum(self._lock_wait_times) / len(self._lock_wait_times)
            if self._lock_wait_times else 0
        )

        return {
            'total_locks': len(self._locks),
            'active_locks': len(active_locks),
            'active_lock_details': active_locks,
            'avg_wait_time': avg_wait_time,
            'max_wait_time': max(self._lock_wait_times, default=0)
        }

    async def force_release(self, resource: str):
        """Force release a lock (emergency use only)"""
        lock_key = f"lock_{resource}"

        if lock_key in self._lock_info:
            info = self._lock_info[lock_key]
            logger.warning(
                f"⚠️ Force releasing lock for {resource} "
                f"(held by {info.operation})"
            )

            if lock_key in self._locks:
                lock = self._locks[lock_key]
                if lock.locked():
                    lock.release()

            del self._lock_info[lock_key]

    def is_locked(self, resource: str) -> bool:
        """Check if resource is currently locked"""
        lock_key = f"lock_{resource}"
        return lock_key in self._lock_info


# Global singleton instance
_lock_manager = None


def get_lock_manager() -> LockManager:
    """Get global lock manager instance"""
    global _lock_manager
    if _lock_manager is None:
        _lock_manager = LockManager()
    return _lock_manager


# Convenience function
async def with_lock(resource: str, operation: str, timeout: float = 30.0):
    """Convenience decorator/context manager for locks"""
    manager = get_lock_manager()
    async with manager.acquire_lock(resource, operation, timeout):
        yield