"""
Минимальный тест для проверки исправления CASE #1: Symbol Mismatch

Тестирует только добавленную функцию to_exchange_symbol()
Без рефакторинга, без лишнего кода.
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.position_manager import to_exchange_symbol


def test_bybit_symbol_conversion():
    """Тест конвертации для Bybit"""
    # HNTUSDT -> HNT/USDT:USDT
    result = to_exchange_symbol('HNTUSDT', 'bybit')
    assert result == 'HNT/USDT:USDT', f"Expected 'HNT/USDT:USDT', got '{result}'"

    # BTCUSDT -> BTC/USDT:USDT
    result = to_exchange_symbol('BTCUSDT', 'bybit')
    assert result == 'BTC/USDT:USDT', f"Expected 'BTC/USDT:USDT', got '{result}'"

    # ETHUSDT -> ETH/USDT:USDT
    result = to_exchange_symbol('ETHUSDT', 'bybit')
    assert result == 'ETH/USDT:USDT', f"Expected 'ETH/USDT:USDT', got '{result}'"

    print("✅ Bybit symbol conversion: OK")


def test_binance_symbol_unchanged():
    """Тест что для Binance символы не меняются"""
    # Binance использует тот же формат что и БД
    result = to_exchange_symbol('BTCUSDT', 'binance')
    assert result == 'BTCUSDT', f"Expected 'BTCUSDT', got '{result}'"

    result = to_exchange_symbol('ETHUSDT', 'binance')
    assert result == 'ETHUSDT', f"Expected 'ETHUSDT', got '{result}'"

    print("✅ Binance symbol unchanged: OK")


def test_unknown_exchange():
    """Тест что неизвестные биржи возвращают символ как есть"""
    result = to_exchange_symbol('BTCUSDT', 'unknown')
    assert result == 'BTCUSDT', f"Expected 'BTCUSDT', got '{result}'"

    print("✅ Unknown exchange fallback: OK")


def main():
    """Запуск всех тестов"""
    print("="*60)
    print("ТЕСТ: Symbol Conversion Fix (CASE #1)")
    print("="*60)

    try:
        test_bybit_symbol_conversion()
        test_binance_symbol_unchanged()
        test_unknown_exchange()

        print("\n" + "="*60)
        print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ")
        print("="*60)
        return 0

    except AssertionError as e:
        print(f"\n❌ ТЕСТ ПРОВАЛИЛСЯ: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit(main())
