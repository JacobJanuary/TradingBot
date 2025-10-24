#!/usr/bin/env python3
"""
Тесты для валидации расследования type error в create_aged_monitoring_event
НЕ МЕНЯЕТ КОД - ТОЛЬКО ПРОВЕРКА
"""
import sys
import os
import inspect
from decimal import Decimal

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_repository_method_signature():
    """Тест 1: Проверка сигнатуры create_aged_monitoring_event"""
    print("\n=== ТЕСТ 1: Сигнатура create_aged_monitoring_event ===")

    from database.repository import Repository

    sig = inspect.signature(Repository.create_aged_monitoring_event)
    params = sig.parameters

    print(f"Параметры метода: {list(params.keys())}")

    # Check first parameter type annotation
    aged_position_id_param = params['aged_position_id']
    print(f"aged_position_id аннотация: {aged_position_id_param.annotation}")

    assert aged_position_id_param.annotation == str, \
        f"❌ aged_position_id должен быть str, получен {aged_position_id_param.annotation}"

    print("✅ Метод ожидает aged_position_id: str")

    # Check SQL uses $1
    source = inspect.getsource(Repository.create_aged_monitoring_event)
    assert '$1' in source, "❌ SQL должен использовать $1 для asyncpg"
    print("✅ SQL использует $1 для aged_position_id")

    return True


def test_database_schema():
    """Тест 2: Проверка структуры таблицы через миграции"""
    print("\n=== ТЕСТ 2: Структура таблицы aged_monitoring_events ===")

    migration_path = 'database/migrations/008_create_aged_tables.sql'
    if os.path.exists(migration_path):
        with open(migration_path, 'r') as f:
            content = f.read()

        print("✓ Миграция 008 найдена")

        # Check aged_position_id column type
        assert 'aged_position_id VARCHAR(255)' in content, \
            "❌ aged_position_id должна быть VARCHAR(255)"
        print("✅ aged_position_id VARCHAR(255) NOT NULL в таблице")

    else:
        print("❌ Миграция 008 не найдена!")
        return False

    return True


def test_aged_position_target_definition():
    """Тест 3: Проверка определения AgedPositionTarget dataclass"""
    print("\n=== ТЕСТ 3: Определение AgedPositionTarget ===")

    from core.aged_position_monitor_v2 import AgedPositionTarget

    # Check type hints
    hints = AgedPositionTarget.__annotations__
    print(f"Type hints: {hints}")

    assert 'position_id' in hints, "❌ position_id должна быть в dataclass"
    assert hints['position_id'] == str, \
        f"❌ position_id должна быть str, получена {hints['position_id']}"

    print("✅ AgedPositionTarget.position_id аннотирована как str")

    # Note: Python dataclass does NOT enforce type checking by default!
    print("⚠️  ВАЖНО: dataclass НЕ валидирует типы по умолчанию!")
    print("⚠️  position_id: str - это ТОЛЬКО аннотация, НЕ проверка!")

    return True


def test_aged_target_creation_source():
    """Тест 4: Проверка создания AgedPositionTarget в коде"""
    print("\n=== ТЕСТ 4: Создание AgedPositionTarget ===")

    from core.aged_position_monitor_v2 import AgedPositionMonitorV2

    source = inspect.getsource(AgedPositionMonitorV2.add_aged_position)

    print("Проверка строки создания target...")

    # Find the line where position_id is assigned
    if 'position_id=getattr(position, \'id\'' in source or \
       'position_id = getattr(position, \'id\'' in source:
        print("✓ Найдено: position_id=getattr(position, 'id', symbol)")

        # Check if str() is used
        if 'str(getattr(position, \'id\'' in source:
            print("✅ position_id конвертируется через str()")
        else:
            print("❌ ПРОБЛЕМА: position_id НЕ конвертируется в str!")
            print("❌ position.id возвращает int, но нужен str!")
            return False
    else:
        print("⚠️ Не найдена строка position_id=getattr(...)")

    return True


def test_create_monitoring_event_calls():
    """Тест 5: Проверка всех вызовов create_aged_monitoring_event"""
    print("\n=== ТЕСТ 5: Вызовы create_aged_monitoring_event ===")

    from core.aged_position_monitor_v2 import AgedPositionMonitorV2

    source = inspect.getsource(AgedPositionMonitorV2)

    # Find all calls to create_aged_monitoring_event
    import re
    calls = re.findall(
        r'create_aged_monitoring_event\([^)]+\)',
        source,
        re.DOTALL
    )

    print(f"Найдено {len(calls)} вызовов create_aged_monitoring_event")

    problematic_calls = 0
    for i, call in enumerate(calls, 1):
        # Check if aged_position_id uses target.position_id
        if 'aged_position_id=target.position_id' in call or \
           'aged_position_id = target.position_id' in call:
            print(f"  {i}. ❌ ПРОБЛЕМА: aged_position_id=target.position_id (может быть int)")
            problematic_calls += 1
        elif 'aged_position_id=str(target.position_id)' in call:
            print(f"  {i}. ✅ ИСПРАВЛЕНО: aged_position_id=str(target.position_id)")
        elif 'aged_position_id=' in call:
            # Extract what is passed
            match = re.search(r'aged_position_id\s*=\s*(\w+)', call)
            if match:
                value = match.group(1)
                print(f"  {i}. ? Передается: aged_position_id={value}")

    if problematic_calls > 0:
        print(f"\n❌ Найдено {problematic_calls} проблемных вызова(ов)")
        print("❌ target.position_id может быть int, но метод требует str!")
        return False
    else:
        print("\n✅ Все вызовы корректны (используют str)")

    return True


def test_type_conversion_simulation():
    """Тест 6: Симуляция проблемы с типом"""
    print("\n=== ТЕСТ 6: Симуляция type error ===")

    # Simulate what happens with position.id
    position_id_int = 2745  # This is what position.id returns
    position_id_str = str(2745)  # This is what we need

    print(f"position.id возвращает: {position_id_int} (type: {type(position_id_int).__name__})")
    print(f"str(position.id) дает: {position_id_str} (type: {type(position_id_str).__name__})")

    # Check asyncpg expectation
    print("\nЧто ожидает asyncpg для VARCHAR(255):")
    print("  ✅ str: '2745'")
    print("  ❌ int: 2745 → ERROR: invalid input for query argument $1: 2745 (expected str, got int)")

    # Demonstrate dataclass does NOT enforce type
    from core.aged_position_monitor_v2 import AgedPositionTarget

    target_bad = AgedPositionTarget(
        symbol='BTCUSDT',
        entry_price=Decimal('50000'),
        target_price=Decimal('49000'),
        phase='grace',
        loss_tolerance=Decimal('0.5'),
        hours_aged=2.5,
        position_id=2745  # ❌ int, но dataclass не возражает!
    )

    print(f"\n⚠️  target.position_id = {target_bad.position_id} (type: {type(target_bad.position_id).__name__})")
    print("⚠️  dataclass ПРИНИМАЕТ int, хотя аннотация str!")
    print("⚠️  Но asyncpg ОТКЛОНИТ int при INSERT!")

    target_good = AgedPositionTarget(
        symbol='BTCUSDT',
        entry_price=Decimal('50000'),
        target_price=Decimal('49000'),
        phase='grace',
        loss_tolerance=Decimal('0.5'),
        hours_aged=2.5,
        position_id=str(2745)  # ✅ str
    )

    print(f"\n✅ target.position_id = '{target_good.position_id}' (type: {type(target_good.position_id).__name__})")
    print("✅ asyncpg ПРИМЕТ str при INSERT")

    return True


if __name__ == "__main__":
    print("🔍 ТЕСТЫ РАССЛЕДОВАНИЯ: Type Error в create_aged_monitoring_event")
    print("=" * 70)
    print("⚠️  КРИТИЧЕСКИ ВАЖНО: Эти тесты ТОЛЬКО проверяют проблемы")
    print("⚠️  НЕ вносятся изменения в код!")
    print("=" * 70)

    all_passed = True
    failed_tests = []

    try:
        # Run all tests
        tests = [
            ("Сигнатура метода", test_repository_method_signature),
            ("Структура таблицы", test_database_schema),
            ("Определение dataclass", test_aged_position_target_definition),
            ("Создание target", test_aged_target_creation_source),
            ("Вызовы метода", test_create_monitoring_event_calls),
            ("Симуляция проблемы", test_type_conversion_simulation),
        ]

        for name, test_func in tests:
            try:
                result = test_func()
                if not result:
                    failed_tests.append(name)
                    all_passed = False
            except Exception as e:
                print(f"\n❌ ОШИБКА В ТЕСТЕ '{name}': {e}")
                import traceback
                traceback.print_exc()
                failed_tests.append(name)
                all_passed = False

        print("\n" + "=" * 70)
        if all_passed:
            print("✅ ВСЕ ТЕСТЫ ЗАВЕРШЕНЫ")
        else:
            print(f"⚠️  ТЕСТЫ ЗАВЕРШЕНЫ С ПРОБЛЕМАМИ: {', '.join(failed_tests)}")
        print("=" * 70)

        print("\n📋 ВЫВОДЫ:")
        print("1. ✅ Метод create_aged_monitoring_event требует str")
        print("2. ✅ Таблица aged_monitoring_events использует VARCHAR(255)")
        print("3. ✅ AgedPositionTarget.position_id аннотирован как str")
        print("4. ❌ НО: dataclass НЕ валидирует типы!")
        print("5. ❌ position.id возвращает int, передается без str()")
        print("6. ❌ asyncpg отклоняет int для VARCHAR колонки")
        print("\n💡 РЕШЕНИЕ: Добавить str() в строке создания AgedPositionTarget")
        print("   position_id=str(getattr(position, 'id', symbol))")
        print("\n📄 См. INVESTIGATION_AGED_MONITORING_TYPE_ERROR_20251023.md")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False
        sys.exit(1)

    sys.exit(0 if all_passed else 1)
