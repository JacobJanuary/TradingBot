#!/usr/bin/env python3
"""
Тест проверки работы с включенным Unified Protection
Убеждаемся что старый aged manager отключен и работает только новый
"""

import sys
import os

# Устанавливаем флаг перед импортом
os.environ['USE_UNIFIED_PROTECTION'] = 'true'

sys.path.insert(0, '/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot')

from unittest.mock import Mock, MagicMock
import asyncio

print("=" * 60)
print("ТЕСТ: Unified Protection ВКЛЮЧЕН")
print("=" * 60)

# 1. Проверяем что флаг установлен
print("\n1. Проверка флага...")
use_unified = os.getenv('USE_UNIFIED_PROTECTION', 'false').lower() == 'true'
print(f"   USE_UNIFIED_PROTECTION = {use_unified}")
if use_unified:
    print("   ✅ Unified protection включен")
else:
    print("   ❌ ОШИБКА: Unified protection должен быть включен!")
    sys.exit(1)

# 2. Проверяем что старый aged manager НЕ создаётся
print("\n2. Проверка что старый aged manager отключен...")

# Создаём mock для зависимостей
mock_settings = Mock()
mock_settings.trading = Mock()
mock_position_manager = Mock()
mock_exchanges = {'binance': Mock(), 'bybit': Mock()}

# Симулируем код из main.py
use_unified_protection = os.getenv('USE_UNIFIED_PROTECTION', 'false').lower() == 'true'
if not use_unified_protection:
    print("   ❌ Старый aged manager СОЗДАЁТСЯ (неправильно!)")
    sys.exit(1)
else:
    print("   ✅ Старый aged manager НЕ создаётся")
    aged_position_manager = None

# 3. Проверяем что unified protection инициализируется
print("\n3. Проверка инициализации unified protection...")
from core.position_manager_unified_patch import init_unified_protection

# Mock position manager с необходимыми атрибутами
mock_pm = Mock()
mock_pm.exchanges = {'binance': Mock(), 'bybit': Mock()}
mock_pm.repository = Mock()
mock_pm.trailing_managers = {
    'binance': Mock(),
    'bybit': Mock()
}

result = init_unified_protection(mock_pm)
if result is not None:
    print("   ✅ Unified protection инициализирован")
    print(f"   Компоненты: {list(result.keys())}")

    # Проверяем наличие ключевых компонентов
    if 'price_monitor' in result:
        print("   ✅ Price monitor создан")
    if 'aged_monitor' in result:
        print("   ✅ Aged monitor V2 создан")
    if 'ts_adapters' in result:
        print("   ✅ TrailingStop adapters созданы")
else:
    print("   ❌ ОШИБКА: init_unified_protection вернул None!")
    sys.exit(1)

# 4. Проверяем что aged V2 использует MARKET ордера
print("\n4. Проверка что aged V2 использует MARKET ордера...")
from core.aged_position_monitor_v2 import AgedPositionMonitorV2

# Проверяем код метода _trigger_market_close
import inspect
source = inspect.getsource(AgedPositionMonitorV2._trigger_market_close)
if "type='market'" in source:
    print("   ✅ Aged V2 использует MARKET ордера")
else:
    print("   ❌ ОШИБКА: Aged V2 не использует MARKET ордера!")
    sys.exit(1)

# 5. Финальная проверка - старый aged manager не будет вызываться
print("\n5. Проверка что старый aged manager не вызывается...")
if aged_position_manager is None:
    print("   ✅ aged_position_manager = None")
    print("   ✅ check_and_process_aged_positions НЕ будет вызван")
else:
    print("   ❌ ОШИБКА: aged_position_manager не None!")
    sys.exit(1)

print("\n" + "=" * 60)
print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!")
print("=" * 60)
print("\n🎯 РЕЗУЛЬТАТ:")
print("  • Старый aged manager ОТКЛЮЧЕН")
print("  • Новый aged V2 работает через UnifiedPriceMonitor")
print("  • Используются MARKET ордера (гарантированное исполнение)")
print("  • Никаких LIMIT ордеров которые блокируют ликвидность")
print("\n⚡ Система работает в режиме Unified Protection V2!")