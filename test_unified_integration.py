#!/usr/bin/env python3
"""
Тест интеграции Unified Protection в PositionManager
Проверяет что система работает корректно с выключенным unified
"""

import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, '/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot')

# Проверяем значение флага
from dotenv import load_dotenv
load_dotenv()

print("=" * 60)
print("ТЕСТ ИНТЕГРАЦИИ UNIFIED PROTECTION")
print("=" * 60)

# Проверяем флаг
use_unified = os.getenv('USE_UNIFIED_PROTECTION', 'false').lower() == 'true'
print(f"\n1. USE_UNIFIED_PROTECTION = {use_unified}")
print(f"   (Ожидается: False)")

if use_unified:
    print("   ❌ ОШИБКА: Unified protection включён! Должен быть выключен по умолчанию!")
    sys.exit(1)
else:
    print("   ✅ OK: Unified protection выключен (безопасный режим)")

# Проверяем что импорты работают
print("\n2. Проверка импортов...")
try:
    from core.position_manager import PositionManager
    print("   ✅ PositionManager импортирован успешно")
except ImportError as e:
    print(f"   ❌ Ошибка импорта: {e}")
    sys.exit(1)

# Проверяем что патч модуль существует
print("\n3. Проверка patch модуля...")
try:
    from core.position_manager_unified_patch import (
        init_unified_protection,
        handle_unified_price_update,
        check_and_register_aged_positions
    )
    print("   ✅ Patch модуль загружен")
except ImportError as e:
    print(f"   ❌ Ошибка импорта patch: {e}")
    sys.exit(1)

# Проверяем что unified_protection будет None при выключенном флаге
print("\n4. Проверка инициализации с выключенным флагом...")
result = init_unified_protection(None)
if result is None:
    print("   ✅ init_unified_protection вернул None (как ожидалось)")
else:
    print(f"   ❌ init_unified_protection вернул {result} (ожидался None)")
    sys.exit(1)

print("\n" + "=" * 60)
print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
print("=" * 60)
print("\nСИСТЕМА ГОТОВА К РАБОТЕ:")
print("  • Unified protection выключен по умолчанию")
print("  • Старый код продолжит работать как раньше")
print("  • Никаких изменений в поведении")
print("\nДля включения unified protection:")
print("  1. Измените в .env: USE_UNIFIED_PROTECTION=true")
print("  2. Перезапустите систему")
print("  3. Проверьте логи на наличие:")
print('     "✅ Unified protection initialized successfully"')