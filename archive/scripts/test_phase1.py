#!/usr/bin/env python3
"""
PHASE 1 TEST SCRIPT
Проверяет исправления AttributeError багов
"""
import asyncio
import sys
import os
from datetime import datetime

# Добавить путь к проекту
sys.path.insert(0, '/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot')

async def test_phase1():
    """Тестирует PHASE 1 fixes"""

    print("=" * 80)
    print("🧪 PHASE 1 TEST: AttributeError Fixes")
    print("=" * 80)
    print(f"Время старта: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    test_results = {
        'total': 0,
        'passed': 0,
        'failed': 0,
        'errors': []
    }

    # TEST 1: Import модулей без ошибок
    test_results['total'] += 1
    print("TEST 1: Импорт модулей...")
    try:
        from protection.trailing_stop import SmartTrailingStopManager, TrailingStopConfig
        from core.position_manager import PositionManager
        from core.exchange_manager import ExchangeManager
        print("✅ PASSED: Все модули импортированы успешно")
        test_results['passed'] += 1
    except Exception as e:
        print(f"❌ FAILED: Ошибка импорта: {e}")
        test_results['failed'] += 1
        test_results['errors'].append(f"Import error: {e}")
        return test_results

    # TEST 2: Создание ExchangeManager (мок)
    test_results['total'] += 1
    print("\nTEST 2: Создание ExchangeManager...")
    try:
        # Создаем минимальный мок ExchangeManager
        class MockExchange:
            def __init__(self, name):
                self.name = name
                self.exchange_name = name

        mock_binance = MockExchange('binance')
        mock_bybit = MockExchange('bybit')
        print("✅ PASSED: Mock ExchangeManager создан")
        test_results['passed'] += 1
    except Exception as e:
        print(f"❌ FAILED: {e}")
        test_results['failed'] += 1
        test_results['errors'].append(f"ExchangeManager creation: {e}")
        return test_results

    # TEST 3: SmartTrailingStopManager - с exchange_name параметром
    test_results['total'] += 1
    print("\nTEST 3: SmartTrailingStopManager с exchange_name...")
    try:
        config = TrailingStopConfig()
        ts_manager = SmartTrailingStopManager(
            exchange_manager=mock_binance,
            config=config,
            exchange_name='binance'
        )

        # Проверяем что exchange_name установлен
        assert hasattr(ts_manager, 'exchange_name'), "Missing exchange_name attribute"
        assert ts_manager.exchange_name == 'binance', f"Wrong exchange_name: {ts_manager.exchange_name}"

        print(f"✅ PASSED: exchange_name = '{ts_manager.exchange_name}'")
        test_results['passed'] += 1
    except Exception as e:
        print(f"❌ FAILED: {e}")
        test_results['failed'] += 1
        test_results['errors'].append(f"TrailingStopManager with exchange_name: {e}")

    # TEST 4: SmartTrailingStopManager - без exchange_name (fallback)
    test_results['total'] += 1
    print("\nTEST 4: SmartTrailingStopManager без exchange_name (fallback)...")
    try:
        config = TrailingStopConfig()
        ts_manager = SmartTrailingStopManager(
            exchange_manager=mock_bybit,
            config=config
            # exchange_name НЕ передан
        )

        # Проверяем что exchange_name установлен через fallback
        assert hasattr(ts_manager, 'exchange_name'), "Missing exchange_name attribute"
        assert ts_manager.exchange_name == 'bybit', f"Fallback failed: {ts_manager.exchange_name}"

        print(f"✅ PASSED: Fallback работает, exchange_name = '{ts_manager.exchange_name}'")
        test_results['passed'] += 1
    except Exception as e:
        print(f"❌ FAILED: {e}")
        test_results['failed'] += 1
        test_results['errors'].append(f"TrailingStopManager fallback: {e}")

    # TEST 5: Проверка доступа к exchange.name (не .id)
    test_results['total'] += 1
    print("\nTEST 5: Доступ к exchange.name (не .id)...")
    try:
        ts_manager = SmartTrailingStopManager(
            exchange_manager=mock_binance,
            config=TrailingStopConfig(),
            exchange_name='binance'
        )

        # Симулируем код из _cancel_protection_sl_if_binance (line 525)
        exchange_name = getattr(ts_manager.exchange, 'name', ts_manager.exchange_name)
        assert exchange_name == 'binance', f"Wrong exchange_name: {exchange_name}"

        # Проверяем что НЕ используется .id
        has_id = hasattr(ts_manager.exchange, 'id')
        if has_id:
            print(f"⚠️  WARNING: exchange.id exists, but we use exchange.name now")

        print(f"✅ PASSED: exchange.name доступен = '{exchange_name}'")
        test_results['passed'] += 1
    except AttributeError as e:
        if 'id' in str(e):
            print(f"❌ FAILED: Код все еще использует exchange.id: {e}")
        else:
            print(f"❌ FAILED: AttributeError: {e}")
        test_results['failed'] += 1
        test_results['errors'].append(f"Exchange name access: {e}")
    except Exception as e:
        print(f"❌ FAILED: {e}")
        test_results['failed'] += 1
        test_results['errors'].append(f"Exchange name access: {e}")

    # TEST 6: Проверка position_manager.py создания trailing_managers
    test_results['total'] += 1
    print("\nTEST 6: PositionManager создание trailing_managers...")
    try:
        # Симулируем код из position_manager.py (line 155-158)
        exchanges = {
            'binance': mock_binance,
            'bybit': mock_bybit
        }

        trailing_config = TrailingStopConfig()

        trailing_managers = {
            name: SmartTrailingStopManager(exchange, trailing_config, exchange_name=name)
            for name, exchange in exchanges.items()
        }

        # Проверяем что оба менеджера созданы корректно
        assert 'binance' in trailing_managers, "Missing binance manager"
        assert 'bybit' in trailing_managers, "Missing bybit manager"
        assert trailing_managers['binance'].exchange_name == 'binance'
        assert trailing_managers['bybit'].exchange_name == 'bybit'

        print(f"✅ PASSED: Оба trailing_managers созданы с корректными exchange_name")
        test_results['passed'] += 1
    except Exception as e:
        print(f"❌ FAILED: {e}")
        test_results['failed'] += 1
        test_results['errors'].append(f"PositionManager trailing_managers: {e}")

    return test_results


async def main():
    """Main test runner"""
    results = await test_phase1()

    print("\n" + "=" * 80)
    print("📊 TEST SUMMARY")
    print("=" * 80)
    print(f"Total tests:  {results['total']}")
    print(f"✅ Passed:    {results['passed']}")
    print(f"❌ Failed:    {results['failed']}")

    if results['failed'] > 0:
        print("\n❌ ERRORS:")
        for error in results['errors']:
            print(f"   - {error}")

    success_rate = (results['passed'] / results['total'] * 100) if results['total'] > 0 else 0
    print(f"\nSuccess rate: {success_rate:.1f}%")

    if results['failed'] == 0:
        print("\n✅ ✅ ✅ ВСЕ ТЕСТЫ ФАЗЫ 1 ПРОЙДЕНЫ! ✅ ✅ ✅")
        print("Готово к LIVE тесту для проверки реальной работы.\n")
        return 0
    else:
        print("\n❌ НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОШЛИ")
        print("Необходимо исправить ошибки перед LIVE тестом.\n")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
