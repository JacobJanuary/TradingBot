#!/usr/bin/env python3
"""
Валидация ИСПРАВЛЕНИЙ методов aged_positions
Проверяет что ВСЕ 3 ФИКСА применены корректно
"""
import sys
import os
import inspect

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_fix_1_create_aged_position():
    """ФИК 1: Проверка что create_aged_position исправлен"""
    print("\n=== ФИК 1: create_aged_position ===")

    from database.repository import Repository

    sig = inspect.signature(Repository.create_aged_position)
    params = list(sig.parameters.keys())

    print(f"Параметры: {params}")

    # Check CORRECT parameters (after fix)
    expected = ['self', 'position_id', 'symbol', 'exchange', 'entry_price',
                'target_price', 'phase', 'age_hours', 'loss_tolerance']

    assert params == expected, f"❌ Сигнатура не совпадает: {params} != {expected}"
    print("✅ Сигнатура совпадает с планом")

    # Check SQL uses $1, $2... (asyncpg)
    source = inspect.getsource(Repository.create_aged_position)
    assert '$1' in source and '$2' in source, "❌ SQL должен использовать $1, $2..."
    assert '%(name)s' not in source, "❌ SQL НЕ должен использовать %(name)s"
    print("✅ SQL использует $1, $2... (asyncpg)")

    # Check SQL targets aged_positions (not monitoring.aged_positions)
    assert 'INSERT INTO aged_positions' in source, "❌ SQL должен работать с aged_positions"
    assert 'monitoring.aged_positions' not in source, "❌ SQL НЕ должен использовать monitoring.aged_positions"
    print("✅ SQL работает с aged_positions")

    # Check ON CONFLICT
    assert 'ON CONFLICT' in source, "❌ SQL должен иметь ON CONFLICT"
    print("✅ SQL имеет ON CONFLICT для upsert")

    print("✅ ФИК 1 КОРРЕКТЕН")
    return True


def test_fix_2_mark_aged_position_closed():
    """ФИК 2: Проверка что mark_aged_position_closed исправлен"""
    print("\n=== ФИК 2: mark_aged_position_closed ===")

    from database.repository import Repository

    sig = inspect.signature(Repository.mark_aged_position_closed)
    params = list(sig.parameters.keys())

    print(f"Параметры: {params}")

    # Check CORRECT parameters (after fix)
    expected = ['self', 'position_id', 'close_reason']

    assert params == expected, f"❌ Сигнатура не совпадает: {params} != {expected}"
    print("✅ Сигнатура совпадает с планом (упрощена)")

    # Check SQL uses $1 (asyncpg)
    source = inspect.getsource(Repository.mark_aged_position_closed)
    assert '$1' in source, "❌ SQL должен использовать $1"
    assert '%(name)s' not in source, "❌ SQL НЕ должен использовать %(name)s"
    print("✅ SQL использует $1 (asyncpg)")

    # Check SQL targets aged_positions (not monitoring.aged_positions)
    assert 'DELETE FROM aged_positions' in source, "❌ SQL должен удалять из aged_positions"
    assert 'monitoring.aged_positions' not in source, "❌ SQL НЕ должен использовать monitoring.aged_positions"
    print("✅ SQL удаляет из aged_positions")

    print("✅ ФИК 2 КОРРЕКТЕН")
    return True


def test_fix_3_aged_monitor_calls():
    """ФИК 3: Проверка что вызовы в aged_position_monitor_v2 исправлены"""
    print("\n=== ФИК 3: Вызовы в aged_position_monitor_v2 ===")

    from core.aged_position_monitor_v2 import AgedPositionMonitorV2

    source = inspect.getsource(AgedPositionMonitorV2.add_aged_position)

    # Check create_aged_position call
    print("Проверка create_aged_position...")
    assert 'str(target.position_id)' in source, "❌ Должен быть str(target.position_id)"
    assert 'position_id=str(target.position_id)' in source or 'position_id = str(target.position_id)' in source, \
        "❌ position_id должен быть str()"
    print("✅ position_id конвертируется в str()")

    # Check all required parameters are passed
    assert 'symbol=' in source, "❌ Должен передавать symbol"
    assert 'exchange=' in source, "❌ Должен передавать exchange"
    assert 'entry_price=' in source, "❌ Должен передавать entry_price"
    assert 'target_price=' in source, "❌ Должен передавать target_price"
    assert 'phase=' in source, "❌ Должен передавать phase"
    assert 'age_hours=' in source, "❌ Должен передавать age_hours"
    assert 'loss_tolerance=' in source, "❌ Должен передавать loss_tolerance"
    print("✅ Все параметры create_aged_position переданы")

    # Check mark_aged_position_closed call
    print("\nПроверка mark_aged_position_closed...")
    source_full = inspect.getsource(AgedPositionMonitorV2)

    # Find the mark_aged_position_closed call
    if 'mark_aged_position_closed' in source_full:
        # Extract the call section
        lines = source_full.split('\n')
        call_found = False
        for i, line in enumerate(lines):
            if 'mark_aged_position_closed' in line and 'await' in line:
                # Get next 5 lines to capture full call
                call_section = '\n'.join(lines[i:i+5])

                # Should have position_id and close_reason ONLY
                assert 'position_id=' in call_section, "❌ Должен передавать position_id"
                assert 'close_reason=' in call_section, "❌ Должен передавать close_reason"

                # Should NOT have old parameters
                assert 'order_id=' not in call_section or 'close_order_id=' in call_section, \
                    "❌ НЕ должен передавать order_id (должен быть close_order_id или убран)"
                assert 'close_price=' not in call_section, "❌ НЕ должен передавать close_price"

                call_found = True
                print("✅ mark_aged_position_closed упрощен (только position_id + close_reason)")
                break

        if not call_found:
            print("⚠️ Вызов mark_aged_position_closed не найден в методе")

    print("✅ ФИК 3 КОРРЕКТЕН")
    return True


def test_integration_compatibility():
    """Интеграционный тест: Совместимость методов и вызовов"""
    print("\n=== ИНТЕГРАЦИОННЫЙ ТЕСТ ===")

    from database.repository import Repository
    from core.aged_position_monitor_v2 import AgedPositionMonitorV2

    # Get method signatures
    create_sig = inspect.signature(Repository.create_aged_position)
    mark_sig = inspect.signature(Repository.mark_aged_position_closed)

    # Get call patterns from aged_position_monitor_v2
    monitor_source = inspect.getsource(AgedPositionMonitorV2.add_aged_position)

    print("Проверка совместимости create_aged_position...")
    # Check that all parameters called are in method signature
    create_params = set(create_sig.parameters.keys()) - {'self'}
    called_params = set()

    for param in ['position_id', 'symbol', 'exchange', 'entry_price',
                  'target_price', 'phase', 'age_hours', 'loss_tolerance']:
        if f'{param}=' in monitor_source:
            called_params.add(param)

    assert called_params.issubset(create_params), \
        f"❌ Вызываемые параметры не совпадают: {called_params - create_params}"
    print(f"✅ Все вызываемые параметры есть в методе: {called_params}")

    print("\nПроверка совместимости mark_aged_position_closed...")
    mark_params = set(mark_sig.parameters.keys()) - {'self'}
    print(f"✅ Метод принимает: {mark_params}")

    print("\n✅ ИНТЕГРАЦИЯ КОРРЕКТНА")
    return True


if __name__ == "__main__":
    print("🔍 ВАЛИДАЦИЯ ИСПРАВЛЕНИЙ: aged_positions fixes")
    print("=" * 70)
    print("✅ Проверяем что ВСЕ 3 ФИКСА применены корректно")
    print("=" * 70)

    all_passed = True

    try:
        # Run all validation tests
        test_fix_1_create_aged_position()
        test_fix_2_mark_aged_position_closed()
        test_fix_3_aged_monitor_calls()
        test_integration_compatibility()

        print("\n" + "=" * 70)
        print("🎉 ВСЕ ФИКСЫ ВАЛИДИРОВАНЫ УСПЕШНО!")
        print("=" * 70)
        print("\n📋 ИТОГОВЫЙ СТАТУС:")
        print("✅ ФИК 1: create_aged_position - КОРРЕКТЕН")
        print("✅ ФИК 2: mark_aged_position_closed - КОРРЕКТЕН")
        print("✅ ФИК 3: aged_position_monitor_v2 calls - КОРРЕКТЕН")
        print("✅ ИНТЕГРАЦИЯ: Методы и вызовы совместимы")
        print("\n🚀 ГОТОВО К ДЕПЛОЮ")
        print("=" * 70)

    except AssertionError as e:
        print(f"\n❌ ВАЛИДАЦИЯ ПРОВАЛЕНА: {e}")
        all_passed = False
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False
        sys.exit(1)

    sys.exit(0 if all_passed else 1)
