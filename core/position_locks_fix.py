"""
Position Locks Fix - Обновление для использования правильных asyncio.Lock вместо set

Этот модуль содержит исправление для race conditions в PositionManager
"""
import asyncio
from typing import Dict


class PositionLocksManager:
    """
    Менеджер блокировок для позиций

    Заменяет set на Dict[str, asyncio.Lock] для правильной синхронизации
    """

    def __init__(self):
        self.locks: Dict[str, asyncio.Lock] = {}
        self._creation_lock = asyncio.Lock()

    async def acquire(self, key: str) -> asyncio.Lock:
        """Get or create lock for key"""
        async with self._creation_lock:
            if key not in self.locks:
                self.locks[key] = asyncio.Lock()
        return self.locks[key]

    async def is_locked(self, key: str) -> bool:
        """Check if key is currently locked"""
        if key in self.locks:
            return self.locks[key].locked()
        return False


# Monkey patch для PositionManager
def fix_position_locks(position_manager):
    """
    Применяет исправление к существующему PositionManager

    Заменяет set на правильные asyncio.Lock
    """
    # Сохраняем старый set для обратной совместимости
    old_locks = position_manager.position_locks if hasattr(position_manager, 'position_locks') else set()

    # Заменяем на правильную реализацию
    position_manager._position_locks = {}
    position_manager._lock_creation = asyncio.Lock()

    # Переопределяем property
    def get_position_locks(self):
        return self._position_locks

    def set_position_locks(self, value):
        if isinstance(value, set):
            # Конвертируем set в dict для обратной совместимости
            self._position_locks = {key: asyncio.Lock() for key in value}
        else:
            self._position_locks = value

    # Применяем property
    type(position_manager).position_locks = property(get_position_locks, set_position_locks)

    # Инициализируем если были старые locks
    if old_locks:
        position_manager.position_locks = old_locks

    return position_manager