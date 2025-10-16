#!/usr/bin/env python3
"""
Верификация инициализации Trailing Stop для всех позиций
ИСПРАВЛЕНО: Проверяем БД напрямую (source of truth), не создаём новые TS managers
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import config as settings
from database.repository import Repository

async def verify_ts_initialization():
    """Проверить инициализацию TS для всех открытых позиций через БД"""

    print("=" * 80)
    print("ВЕРИФИКАЦИЯ ИНИЦИАЛИЗАЦИИ TRAILING STOP")
    print("=" * 80)
    print()

    # Initialize repository
    print("📊 Инициализация базы данных...")
    db_config = {
        'host': settings.database.host,
        'port': settings.database.port,
        'database': settings.database.database,
        'user': settings.database.user,
        'password': settings.database.password,
        'pool_size': 5,
        'max_overflow': 10
    }
    repo = Repository(db_config)
    await repo.initialize()

    # Get open positions from DB
    print("📋 Получение открытых позиций из БД...")
    print("   (БД = единственный source of truth)")
    print()
    positions = await repo.get_open_positions()

    print(f"   Найдено позиций со status='active': {len(positions)}")

    if not positions:
        print()
        print("⚠️  НЕТ ОТКРЫТЫХ ПОЗИЦИЙ")
        print("   Невозможно верифицировать инициализацию TS.")
        print("   Рекомендация: откройте тестовую позицию и запустите снова.")
        print()
        await repo.close()
        return False

    # Analyze positions by TS status
    print()
    print("=" * 80)
    print("АНАЛИЗ TS СТАТУСОВ В БД")
    print("=" * 80)
    print()

    with_ts = []
    without_ts = []

    for pos in positions:
        has_ts = pos.get('has_trailing_stop', False)
        if has_ts:
            with_ts.append(pos)
        else:
            without_ts.append(pos)

    # Show positions WITH TS
    if with_ts:
        print(f"✅ Позиции С Trailing Stop ({len(with_ts)}):")
        for pos in with_ts:
            symbol = pos['symbol']
            exchange = pos['exchange']
            side = pos['side']
            trailing_activated = pos.get('trailing_activated', False)
            status = "🟢 АКТИВИРОВАН" if trailing_activated else "⚪ ОЖИДАНИЕ"
            print(f"   {symbol:12} ({exchange:8}) | {side:5} | {status}")
        print()

    # Show positions WITHOUT TS
    if without_ts:
        print(f"❌ Позиции БЕЗ Trailing Stop ({len(without_ts)}):")
        for pos in without_ts:
            symbol = pos['symbol']
            exchange = pos['exchange']
            side = pos['side']
            pos_id = pos.get('id', 'N/A')
            print(f"   {symbol:12} ({exchange:8}) | {side:5} | ID={pos_id}")
        print()

    # Summary
    print("=" * 80)
    print("ИТОГОВАЯ ОЦЕНКА")
    print("=" * 80)
    print()

    total = len(positions)
    with_ts_count = len(with_ts)
    without_ts_count = len(without_ts)
    coverage_percent = (with_ts_count / total * 100) if total > 0 else 0

    print(f"Всего позиций:        {total}")
    print(f"С TS:                 {with_ts_count}")
    print(f"Без TS:               {without_ts_count}")
    print(f"Покрытие:             {coverage_percent:.1f}%")
    print()

    # Verdict
    if without_ts_count == 0:
        print("✅ ОТЛИЧНО: 100% позиций имеют Trailing Stop!")
        print()
        print("   Система работает корректно.")
        print("   Все открытые позиции защищены TS.")
        print()
        result = True
    elif coverage_percent >= 95:
        print(f"⚠️  ПРИЕМЛЕМО: {coverage_percent:.1f}% позиций имеют TS")
        print()
        print("   Система работает в целом корректно.")
        print(f"   {without_ts_count} позиций без TS - возможно, недавно открыты.")
        print()
        print("   Рекомендация:")
        print("   - Проверить логи: grep 'Trailing stop initialized' logs/*.log")
        print("   - Убедиться что позиции без TS открыты недавно (<1 мин)")
        print()
        result = True
    else:
        print(f"❌ ПРОБЛЕМА: Только {coverage_percent:.1f}% позиций имеют TS!")
        print()
        print("   Система НЕ работает корректно.")
        print(f"   {without_ts_count} из {total} позиций НЕ имеют защиты TS.")
        print()
        print("   Возможные причины:")
        print("   1. TS Manager не инициализирован при старте бота")
        print("   2. Ошибка в create_trailing_stop() при открытии позиции")
        print("   3. БД не обновляется после создания TS")
        print()
        print("   Немедленные действия:")
        print("   1. Проверить логи: grep -i 'trailing' logs/*.log")
        print("   2. Проверить position_manager.py:522-547 (инициализация TS)")
        print("   3. Перезапустить бот если необходимо")
        print()
        result = False

    # Cleanup
    await repo.close()

    return result

if __name__ == "__main__":
    result = asyncio.run(verify_ts_initialization())
    sys.exit(0 if result else 1)
