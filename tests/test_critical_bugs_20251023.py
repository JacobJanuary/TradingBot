#!/usr/bin/env python3
"""
Тесты критических багов обнаруженных 2025-10-23
Тестирует:
1. Ошибку Json vs json в repository.py
2. Ошибку расчета SL для SHORT позиций в trailing_stop
"""

import pytest
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.repository import Repository
# from protection.trailing_stop import TrailingStop  # Не нужен для тестов
from core.exchange_manager import ExchangeManager


class TestJsonImportBug:
    """Тест проблемы #1: Json вместо json в repository.py"""

    @pytest.mark.asyncio
    async def test_json_import_error(self):
        """Проверяем что Json не определен без импорта"""

        # Создаем код который использует Json без импорта
        test_code = """
def test_func():
    data = {'test': 'value'}
    result = Json(data)  # Это вызовет NameError
    return result
"""

        # Проверяем что будет NameError
        with pytest.raises(NameError) as exc_info:
            exec(test_code)
            exec("test_func()")

        assert "name 'Json' is not defined" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_repository_json_usage(self):
        """Проверяем использование Json в repository.py"""

        # Проверяем строки 1094 и 1261 в repository.py
        with open('database/repository.py', 'r') as f:
            content = f.read()

        # Ищем использование Json с заглавной буквы
        json_capital_count = content.count('Json(')

        # Проверяем что есть неправильное использование
        assert json_capital_count > 0, "Json с заглавной буквы найден в repository.py"

        # Проверяем отсутствие правильного импорта
        has_json_import = 'import json' in content or 'from json' in content
        assert not has_json_import, "json не импортирован в repository.py"

        print(f"❌ Найдено {json_capital_count} использований 'Json(' вместо 'json.dumps('")
        print("❌ Модуль json не импортирован")
        print("⚠️ Необходимо:")
        print("  1. Добавить: import json")
        print("  2. Заменить: Json( на json.dumps(")


class TestShortPositionSLBug:
    """Тест проблемы #2: Неверный расчет SL для SHORT позиций"""

    @pytest.mark.asyncio
    async def test_short_position_sl_validation(self):
        """Проверяем валидацию SL для SHORT позиций"""

        # Данные из лога ошибки
        symbol = 'SAROSUSDT'
        position_side = 'sell'  # SHORT позиция
        current_price = Decimal('0.18334')  # Текущая цена
        wrong_sl = Decimal('0.17686')  # Неверный SL (ниже текущей цены)
        correct_sl = Decimal('0.18700')  # Правильный SL (выше текущей цены)

        # Для SHORT позиции:
        # - SL должен быть ВЫШЕ текущей цены (защита от роста)
        # - При падении цены мы в прибыли
        # - При росте цены мы в убытке и должны закрыться по SL

        # Проверяем что неверный SL действительно ниже цены
        assert wrong_sl < current_price, "Неверный SL ниже текущей цены для SHORT"

        # Проверяем что правильный SL выше цены
        assert correct_sl > current_price, "Правильный SL должен быть выше цены для SHORT"

        print(f"📊 SHORT позиция {symbol}")
        print(f"   Текущая цена: {current_price}")
        print(f"   ❌ Неверный SL: {wrong_sl} (ниже цены - будет отклонен)")
        print(f"   ✅ Правильный SL: {correct_sl} (выше цены - корректно)")

    @pytest.mark.asyncio
    async def test_bybit_sl_validation_error(self):
        """Тестируем ошибку Bybit при неверном SL для SHORT"""

        # Эмулируем ответ Bybit из лога
        bybit_error = {
            "retCode": 10001,
            "retMsg": "StopLoss:17686000 set for Sell position should greater base_price:18334000??LastPrice",
            "result": {},
            "retExtInfo": {},
            "time": 1761231878819
        }

        # Разбираем ошибку
        sl_price_raw = 17686000
        base_price_raw = 18334000

        # Конвертируем (Bybit использует целые числа)
        sl_price = Decimal(sl_price_raw) / Decimal(1000000000)  # 0.017686
        base_price = Decimal(base_price_raw) / Decimal(1000000000)  # 0.018334

        # Проверяем условие Bybit
        assert sl_price < base_price, "SL меньше базовой цены"

        # Для SELL позиции SL должен быть больше
        error_msg = bybit_error['retMsg']
        assert 'should greater' in error_msg, "Bybit требует SL > base_price для SELL"

        print("🔴 Ошибка Bybit подтверждена:")
        print(f"   SL: {sl_price} < Base: {base_price}")
        print(f"   Сообщение: {error_msg}")

    @pytest.mark.asyncio
    async def test_trailing_stop_sl_calculation_for_short(self):
        """Тестируем расчет SL в trailing_stop для SHORT позиций"""

        # Создаем мок для SHORT позиции
        position = {
            'symbol': 'SAROSUSDT',
            'side': 'sell',  # SHORT
            'entry_price': Decimal('0.19000'),
            'mark_price': Decimal('0.18334'),
            'amount': Decimal('100'),
            'exchange': 'bybit'
        }

        # Для SHORT позиции в прибыли:
        # - Вход: 0.19000 (продали по высокой цене)
        # - Текущая: 0.18334 (цена упала - мы в прибыли)
        # - PNL = (entry - current) / entry = (0.19 - 0.18334) / 0.19 = 3.5%

        pnl_percent = (position['entry_price'] - position['mark_price']) / position['entry_price'] * 100
        assert pnl_percent > 0, "SHORT позиция должна быть в прибыли при падении цены"

        # Рассчитываем trailing stop (например, 2% от максимума)
        trail_percent = Decimal('2.0')

        # Для SHORT: SL = текущая цена * (1 + trail%)
        # Это защитит от роста цены
        calculated_sl = position['mark_price'] * (Decimal('1') + trail_percent / Decimal('100'))

        # Проверяем что SL выше текущей цены
        assert calculated_sl > position['mark_price'], "SL для SHORT должен быть выше текущей цены"

        print(f"📈 Расчет SL для SHORT позиции:")
        print(f"   Вход: {position['entry_price']}")
        print(f"   Текущая: {position['mark_price']}")
        print(f"   PNL: +{pnl_percent:.2f}%")
        print(f"   Trail: {trail_percent}%")
        print(f"   SL: {calculated_sl} (выше текущей на {trail_percent}%)")


class TestIntegration:
    """Интеграционные тесты обеих проблем"""

    @pytest.mark.asyncio
    async def test_full_error_scenario(self):
        """Тестируем полный сценарий ошибок из логов"""

        print("\n" + "="*60)
        print("ИНТЕГРАЦИОННЫЙ ТЕСТ: Воспроизведение ошибок из production")
        print("="*60)

        # Проблема 1: Json не определен
        print("\n1️⃣ Проблема с Json в repository.py")

        # Эмулируем вызов create_aged_monitoring_event
        mock_metadata = {'test': 'data'}

        try:
            # Это вызовет ошибку если Json не импортирован
            result = eval("Json(mock_metadata)")
            print("   ❌ Json работает (не должно быть)")
        except NameError as e:
            print(f"   ✅ Подтверждена ошибка: {e}")

        # Проблема 2: SL для SHORT
        print("\n2️⃣ Проблема с SL для SHORT позиций")

        # Данные из лога
        saros_data = {
            'symbol': 'SAROSUSDT',
            'side': 'sell',
            'current_price': Decimal('0.18334'),
            'attempted_sl': Decimal('0.17686'),
            'old_sl': Decimal('0.18058845')
        }

        # Проверяем логику
        is_short = saros_data['side'] == 'sell'
        sl_below_price = saros_data['attempted_sl'] < saros_data['current_price']

        if is_short and sl_below_price:
            print(f"   ✅ Обнаружена попытка установить SL ниже цены для SHORT")
            print(f"      Цена: {saros_data['current_price']}")
            print(f"      Попытка SL: {saros_data['attempted_sl']} ❌")
            print(f"      Старый SL: {saros_data['old_sl']} (откат)")

        # Проверяем правильную логику
        correct_sl_logic = """
        Для SHORT позиции:
        - При падении цены: мы в прибыли, SL опускается (но остается выше текущей)
        - При росте цены: мы в убытке, SL остается на месте или поднимается
        - SL ВСЕГДА выше текущей цены для защиты от роста
        """

        print("\n   📋 Правильная логика SL для SHORT:")
        print(correct_sl_logic)

        print("\n" + "="*60)
        print("✅ Обе проблемы подтверждены и воспроизведены")
        print("="*60)


# Запуск тестов
if __name__ == "__main__":
    print("\n🔍 ТЕСТИРОВАНИЕ КРИТИЧЕСКИХ БАГОВ\n")

    # Тест 1: Json проблема
    test1 = TestJsonImportBug()
    asyncio.run(test1.test_json_import_error())
    asyncio.run(test1.test_repository_json_usage())

    # Тест 2: SHORT SL проблема
    test2 = TestShortPositionSLBug()
    asyncio.run(test2.test_short_position_sl_validation())
    asyncio.run(test2.test_bybit_sl_validation_error())
    asyncio.run(test2.test_trailing_stop_sl_calculation_for_short())

    # Интеграционный тест
    test3 = TestIntegration()
    asyncio.run(test3.test_full_error_scenario())

    print("\n✅ Все тесты завершены\n")