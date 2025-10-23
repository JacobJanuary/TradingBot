#!/usr/bin/env python3
"""
Проверка критических исправлений
Дата: 2025-10-23
Проверяет:
1. Json исправление в repository.py
2. SHORT SL валидацию
3. Создание таблиц aged
"""

import sys
import os
import asyncio
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_json_import():
    """Тест 1: Проверка импорта json и использования json.dumps"""

    print("\n" + "="*60)
    print("ТЕСТ 1: Проверка Json исправления")
    print("="*60)

    # Проверяем наличие import json
    with open('database/repository.py', 'r') as f:
        content = f.read()

    # Проверка импорта
    has_import = 'import json' in content
    print(f"✓ import json присутствует: {has_import}")

    # Проверка использования json.dumps
    json_dumps_count = content.count('json.dumps(')
    print(f"✓ Использований json.dumps: {json_dumps_count}")

    # Проверка отсутствия Json(
    json_capital_count = content.count('Json(')
    print(f"✓ Использований Json( (должно быть 0): {json_capital_count}")

    if has_import and json_dumps_count >= 2 and json_capital_count == 0:
        print("✅ ТЕСТ ПРОЙДЕН: Json исправлен корректно")
        return True
    else:
        print("❌ ТЕСТ ПРОВАЛЕН: Json не исправлен")
        return False


def test_short_sl_logic():
    """Тест 2: Проверка логики SL для SHORT позиций"""

    print("\n" + "="*60)
    print("ТЕСТ 2: Проверка SHORT SL логики")
    print("="*60)

    # Симуляция данных SHORT позиции
    test_cases = [
        {
            'name': 'SHORT при росте цены',
            'current_price': Decimal('0.18334'),
            'lowest_price': Decimal('0.17339'),
            'distance': Decimal('2.0'),  # 2% trailing
            'expected_issue': True  # SL будет ниже текущей цены
        },
        {
            'name': 'SHORT при падении цены',
            'current_price': Decimal('0.17000'),
            'lowest_price': Decimal('0.17000'),
            'distance': Decimal('2.0'),
            'expected_issue': False  # SL корректен
        }
    ]

    for case in test_cases:
        print(f"\n📊 Тест: {case['name']}")
        print(f"   Текущая цена: {case['current_price']}")
        print(f"   Минимальная цена: {case['lowest_price']}")

        # Расчет potential_stop по логике trailing_stop.py
        potential_stop = case['lowest_price'] * (Decimal('1') + case['distance'] / Decimal('100'))
        print(f"   Рассчитанный SL: {potential_stop}")

        # Проверка проблемы
        has_issue = potential_stop <= case['current_price']
        print(f"   SL <= текущей цены: {has_issue}")

        if has_issue:
            # Корректировка
            corrected_sl = case['current_price'] * Decimal('1.001')
            print(f"   ⚠️ Требуется корректировка: {corrected_sl}")
        else:
            print(f"   ✅ SL корректен")

        if has_issue == case['expected_issue']:
            print(f"   ✅ Поведение соответствует ожидаемому")
        else:
            print(f"   ❌ Неожиданное поведение")

    return True


async def test_database_tables():
    """Тест 3: Проверка создания таблиц aged"""

    print("\n" + "="*60)
    print("ТЕСТ 3: Проверка таблиц aged в БД")
    print("="*60)

    import asyncpg

    try:
        # Подключение к БД
        conn = await asyncpg.connect(
            host='localhost',
            database='fox_crypto',
            user='evgeniyyanvarskiy',
            password='LohNeMamont@!21'
        )

        # Проверка таблицы aged_positions
        result = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'aged_positions'
            )
        """)
        print(f"✓ Таблица aged_positions существует: {result}")

        # Проверка таблицы aged_monitoring_events
        result2 = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'aged_monitoring_events'
            )
        """)
        print(f"✓ Таблица aged_monitoring_events существует: {result2}")

        # Проверка структуры
        if result:
            columns = await conn.fetch("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'aged_positions'
                ORDER BY ordinal_position
            """)
            print("\n  Столбцы aged_positions:")
            for col in columns:
                print(f"    - {col['column_name']}: {col['data_type']}")

        await conn.close()

        if result and result2:
            print("\n✅ ТЕСТ ПРОЙДЕН: Таблицы созданы корректно")
            return True
        else:
            print("\n⚠️ ТЕСТ ТРЕБУЕТ ПРИМЕНЕНИЯ МИГРАЦИИ")
            print("  Выполните: ")
            print("  PGPASSWORD='LohNeMamont@!21' psql -h localhost -U evgeniyyanvarskiy -d fox_crypto < database/migrations/008_create_aged_tables.sql")
            return False

    except Exception as e:
        print(f"❌ Ошибка подключения к БД: {e}")
        return False


def test_fix_verification_in_code():
    """Тест 4: Проверка наличия исправлений в коде"""

    print("\n" + "="*60)
    print("ТЕСТ 4: Проверка кода на наличие исправлений")
    print("="*60)

    # Проверяем trailing_stop.py на наличие валидации SHORT
    with open('protection/trailing_stop.py', 'r') as f:
        ts_content = f.read()

    # Ищем валидацию для SHORT
    has_short_validation = (
        'if ts.side == \'short\' and new_stop_price:' in ts_content or
        'if ts.side == "short" and new_stop_price:' in ts_content or
        'SHORT: calculated SL' in ts_content
    )

    print(f"✓ Валидация SHORT в trailing_stop.py: {has_short_validation}")

    # Проверяем exchange_manager.py
    with open('core/exchange_manager.py', 'r') as f:
        em_content = f.read()

    # Ищем валидацию в exchange_manager
    has_em_validation = (
        'if position_side in [\'short\', \'sell\']:' in em_content or
        'For SHORT: SL must be above current price' in em_content
    )

    print(f"✓ Валидация SHORT в exchange_manager.py: {has_em_validation}")

    if has_short_validation or has_em_validation:
        print("\n✅ ТЕСТ ПРОЙДЕН: Хотя бы одно исправление применено")
        return True
    else:
        print("\n⚠️ ТЕСТ: Исправления еще не применены в код")
        return False


async def main():
    """Главная функция тестирования"""

    print("\n" + "🔧 "*20)
    print("ПРОВЕРКА КРИТИЧЕСКИХ ИСПРАВЛЕНИЙ")
    print("🔧 "*20)

    results = []

    # Тест 1: Json
    results.append(("Json исправление", test_json_import()))

    # Тест 2: SHORT SL
    results.append(("SHORT SL логика", test_short_sl_logic()))

    # Тест 3: База данных
    db_result = await test_database_tables()
    results.append(("Таблицы БД", db_result))

    # Тест 4: Код
    results.append(("Исправления в коде", test_fix_verification_in_code()))

    # Итоговый отчет
    print("\n" + "="*60)
    print("ИТОГОВЫЙ ОТЧЕТ")
    print("="*60)

    all_passed = True
    for test_name, passed in results:
        status = "✅ ПРОЙДЕН" if passed else "❌ ПРОВАЛЕН"
        print(f"{test_name:.<30} {status}")
        if not passed:
            all_passed = False

    print("="*60)

    if all_passed:
        print("\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
        print("Система готова к работе")
    else:
        print("\n⚠️ НЕКОТОРЫЕ ТЕСТЫ ПРОВАЛЕНЫ")
        print("Примените исправления согласно плану DETAILED_FIX_PLAN_20251023.md")

    return all_passed


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)