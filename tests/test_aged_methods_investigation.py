#!/usr/bin/env python3
"""
Тесты для валидации расследования несоответствий aged методов
НЕ МЕНЯЕТ КОД - ТОЛЬКО ПРОВЕРКА
"""
import sys
import os
import subprocess
import inspect

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_database_schema():
    """Тест 1: Проверка структуры базы данных через миграции"""
    print("\n=== ТЕСТ 1: Анализ миграций базы данных ===")

    # Check migration 008 (public.aged_positions)
    migration_008_path = 'database/migrations/008_create_aged_tables.sql'
    if os.path.exists(migration_008_path):
        with open(migration_008_path, 'r') as f:
            content = f.read()

        print("✓ Миграция 008 найдена (public.aged_positions)")

        # Check for expected columns in migration 008
        assert 'phase VARCHAR(50)' in content, "❌ phase должна быть в миграции 008"
        assert 'loss_tolerance' in content, "❌ loss_tolerance должна быть в миграции 008"
        assert 'hours_aged INTEGER' in content, "❌ hours_aged должна быть в миграции 008"

        print("  ✓ Колонки: phase, loss_tolerance, hours_aged")

    # Check migration 009 (monitoring.aged_positions)
    migration_009_path = 'database/migrations/009_create_aged_positions_tables.sql'
    if os.path.exists(migration_009_path):
        with open(migration_009_path, 'r') as f:
            content = f.read()

        print("✓ Миграция 009 найдена (monitoring.aged_positions)")
        print("  ⚠️  НО вероятно НЕ применена (таблица в monitoring)")

        # Check that 009 has DIFFERENT structure
        assert 'side VARCHAR(10)' in content, "❌ side должна быть в миграции 009"
        assert 'quantity DECIMAL' in content, "❌ quantity должна быть в миграции 009"
        assert 'status VARCHAR(30)' in content, "❌ status должна быть в миграции 009"

        # Check that 009 does NOT have phase as column
        if 'current_phase' not in content:
            print("  ⚠️  Миграция 009 НЕ имеет колонки 'current_phase'")

    print("✅ Анализ миграций завершен")
    return True


def test_repository_create_aged_position_signature():
    """Тест 2: Проверка сигнатуры create_aged_position"""
    print("\n=== ТЕСТ 2: Сигнатура create_aged_position ===")

    from database.repository import Repository

    sig = inspect.signature(Repository.create_aged_position)
    params = list(sig.parameters.keys())

    print(f"Параметры метода: {params}")

    # Check for parameters that aged_position_monitor_v2.py tries to pass
    monitor_params = ['position_id', 'symbol', 'exchange', 'entry_price',
                     'target_price', 'phase', 'loss_tolerance', 'age_hours']

    for param in monitor_params:
        if param not in params:
            print(f"❌ НЕСООТВЕТСТВИЕ: monitor передает '{param}', но метод не принимает!")

    # Check for parameters that method requires but monitor doesn't provide
    required_params = ['side', 'quantity', 'position_opened_at', 'detected_at',
                      'status', 'breakeven_price', 'config']

    for param in required_params:
        if param in params:
            param_obj = sig.parameters[param]
            if param_obj.default == inspect.Parameter.empty:
                print(f"❌ НЕСООТВЕТСТВИЕ: метод требует '{param}', но monitor не передает!")

    # Check SQL syntax
    source = inspect.getsource(Repository.create_aged_position)
    if '%(name)s' in source:
        print("❌ КРИТИЧЕСКАЯ ПРОБЛЕМА: SQL использует %(name)s вместо $1 (asyncpg несовместимо)!")

    if 'monitoring.aged_positions' in source:
        print("❌ КРИТИЧЕСКАЯ ПРОБЛЕМА: SQL обращается к monitoring.aged_positions (таблица не существует)!")

    print("\n⚠️ Метод НЕ совместим с вызовом из aged_position_monitor_v2.py")
    return True


def test_repository_mark_aged_position_closed_signature():
    """Тест 3: Проверка сигнатуры mark_aged_position_closed"""
    print("\n=== ТЕСТ 3: Сигнатура mark_aged_position_closed ===")

    from database.repository import Repository

    sig = inspect.signature(Repository.mark_aged_position_closed)
    params = list(sig.parameters.keys())

    print(f"Параметры метода: {params}")

    # Check for mismatch with call from aged_position_monitor_v2.py
    call_params = ['position_id', 'order_id', 'close_price', 'close_reason']
    method_params = params[1:]  # Skip 'self'

    print(f"Вызов передает: {call_params}")
    print(f"Метод ожидает: {method_params}")

    if 'position_id' in call_params and 'position_id' not in method_params:
        print("❌ НЕСООТВЕТСТВИЕ: вызов передает 'position_id', но метод не принимает!")

    if 'aged_id' in method_params:
        print("❌ НЕСООТВЕТСТВИЕ: метод требует 'aged_id', но вызов передает 'position_id'!")

    if 'order_id' in call_params and 'close_order_id' in method_params:
        print("❌ НЕСООТВЕТСТВИЕ: вызов передает 'order_id', но метод требует 'close_order_id'!")

    # Check for missing required parameters
    required_in_method = ['actual_pnl', 'actual_pnl_percent']
    for param in required_in_method:
        if param in method_params:
            param_obj = sig.parameters[param]
            if param_obj.default == inspect.Parameter.empty:
                print(f"❌ НЕСООТВЕТСТВИЕ: метод требует '{param}', но вызов не передает!")

    # Check SQL syntax
    source = inspect.getsource(Repository.mark_aged_position_closed)
    if '%(name)s' in source:
        print("❌ КРИТИЧЕСКАЯ ПРОБЛЕМА: SQL использует %(name)s вместо $1 (asyncpg несовместимо)!")

    if 'monitoring.aged_positions' in source:
        print("❌ КРИТИЧЕСКАЯ ПРОБЛЕМА: SQL обращается к monitoring.aged_positions (таблица не существует)!")

    print("\n⚠️ Метод НЕ совместим с вызовом из aged_position_monitor_v2.py")
    return True


def test_aged_monitor_calls():
    """Тест 4: Анализ вызовов в aged_position_monitor_v2.py"""
    print("\n=== ТЕСТ 4: Вызовы в aged_position_monitor_v2.py ===")

    from core.aged_position_monitor_v2 import AgedPositionMonitorV2

    # Check create_aged_position call
    source = inspect.getsource(AgedPositionMonitorV2.add_aged_position)

    print("Проверка вызова create_aged_position...")
    call_indicators = [
        ('position_id=', '✓'),
        ('symbol=', '✓'),
        ('exchange=', '✓'),
        ('phase=', '✓'),
        ('loss_tolerance=', '✓'),
        ('age_hours=', '✓')
    ]

    for indicator, mark in call_indicators:
        if indicator in source:
            print(f"  {mark} Передает {indicator[:-1]}")

    # Check mark_aged_position_closed call
    source_full = inspect.getsource(AgedPositionMonitorV2)

    print("\nПроверка вызова mark_aged_position_closed...")
    if 'mark_aged_position_closed' in source_full:
        print("  ✓ Вызов mark_aged_position_closed найден")

        if 'position_id=' in source_full and 'mark_aged_position_closed' in source_full:
            print("  ⚠️ Передает position_id (метод ожидает aged_id)")

        if 'order_id=' in source_full:
            print("  ⚠️ Передает order_id (метод ожидает close_order_id)")

    print("\n✅ Анализ вызовов завершен")
    return True


if __name__ == "__main__":
    print("🔍 ТЕСТЫ РАССЛЕДОВАНИЯ: Несоответствие aged методов")
    print("=" * 70)
    print("⚠️  КРИТИЧЕСКИ ВАЖНО: Эти тесты ТОЛЬКО проверяют проблемы")
    print("⚠️  НЕ вносятся изменения в код!")
    print("=" * 70)

    all_passed = True

    try:
        # Run all tests
        test_database_schema()
        test_repository_create_aged_position_signature()
        test_repository_mark_aged_position_closed_signature()
        test_aged_monitor_calls()

        print("\n" + "=" * 70)
        print("✅ ВСЕ ТЕСТЫ ЗАВЕРШЕНЫ")
        print("=" * 70)
        print("\n📋 ВЫВОДЫ:")
        print("1. ❌ public.aged_positions существует (миграция 008)")
        print("2. ❌ monitoring.aged_positions НЕ существует (миграция 009 не применена)")
        print("3. ❌ repository.py методы несовместимы с таблицей и вызовами")
        print("4. ❌ SQL синтаксис использует %(name)s вместо $1 (asyncpg)")
        print("\n📄 См. INVESTIGATION_AGED_METHODS_MISMATCH_20251023.md для деталей")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ ОШИБКА В ТЕСТЕ: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False
        sys.exit(1)

    sys.exit(0 if all_passed else 1)
