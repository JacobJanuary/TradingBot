"""
UTC Datetime Helper Utilities

Централизованный модуль для работы с UTC временем.
Все datetime объекты в боте должны быть timezone-aware и в UTC.
"""

from datetime import datetime, timezone
from typing import Optional


def now_utc() -> datetime:
    """
    Возвращает текущее время в UTC с timezone информацией.

    Используйте эту функцию вместо datetime.now() везде в коде.

    Returns:
        datetime: Текущее время в UTC (timezone-aware)

    Example:
        >>> current_time = now_utc()
        >>> print(current_time.tzinfo)  # timezone.utc
    """
    return datetime.now(timezone.utc)


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Гарантирует, что datetime объект имеет UTC timezone.

    - Если dt is None, возвращает None
    - Если dt naive (без timezone), добавляет UTC timezone
    - Если dt имеет другой timezone, конвертирует в UTC

    Args:
        dt: datetime объект (может быть None или naive/aware)

    Returns:
        datetime: UTC timezone-aware datetime или None

    Example:
        >>> naive_dt = datetime(2025, 10, 24, 12, 0, 0)
        >>> utc_dt = ensure_utc(naive_dt)
        >>> print(utc_dt.tzinfo)  # timezone.utc

        >>> msk_dt = datetime(2025, 10, 24, 15, 0, 0, tzinfo=ZoneInfo('Europe/Moscow'))
        >>> utc_dt = ensure_utc(msk_dt)
        >>> print(utc_dt.hour)  # 12 (converted from MSK 15:00)
    """
    if dt is None:
        return None

    if dt.tzinfo is None:
        # Naive datetime - добавляем UTC timezone
        return dt.replace(tzinfo=timezone.utc)

    # Aware datetime - конвертируем в UTC если нужно
    return dt.astimezone(timezone.utc)


def parse_db_timestamp(ts: Optional[datetime]) -> Optional[datetime]:
    """
    Обрабатывает timestamp из базы данных.

    После миграции все timestamp'ы будут timezone-aware (timestamptz),
    но эта функция обеспечивает корректную обработку в переходный период.

    Args:
        ts: Timestamp из базы данных

    Returns:
        datetime: UTC timezone-aware datetime или None
    """
    return ensure_utc(ts)


def format_age_hours(opened_at: datetime, now: Optional[datetime] = None) -> float:
    """
    Вычисляет возраст позиции в часах.

    Args:
        opened_at: Время открытия позиции
        now: Текущее время (если None, используется now_utc())

    Returns:
        float: Возраст в часах

    Example:
        >>> opened = datetime(2025, 10, 24, 10, 0, 0, tzinfo=timezone.utc)
        >>> now = datetime(2025, 10, 24, 14, 30, 0, tzinfo=timezone.utc)
        >>> age = format_age_hours(opened, now)
        >>> print(age)  # 4.5
    """
    if now is None:
        now = now_utc()

    # Обеспечиваем UTC для обоих datetime
    opened_at = ensure_utc(opened_at)
    now = ensure_utc(now)

    age = now - opened_at
    return age.total_seconds() / 3600
