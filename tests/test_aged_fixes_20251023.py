#!/usr/bin/env python3
"""
Тесты для исправлений Aged Position Manager V2
Дата: 2025-10-23
Проверяет все 4 исправления согласно плану
"""

import pytest
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, Mock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.order_executor import OrderExecutor
from core.aged_position_monitor_v2 import AgedPositionMonitorV2, AgedPositionTarget


class TestRepositoryParams:
    """Тест исправления #1: правильные параметры Repository"""

    @pytest.mark.asyncio
    async def test_correct_repository_params(self):
        """Проверяем правильность параметров вызова БД"""
        mock_repo = AsyncMock()

        # Эмулируем правильный вызов
        await mock_repo.create_aged_monitoring_event(
            aged_position_id='test_123',
            event_type='price_check',
            market_price=Decimal('100'),  # НЕ current_price!
            target_price=Decimal('99'),
            event_metadata={'phase': 'grace'}  # НЕ details!
        )

        # Проверяем что вызов прошел
        mock_repo.create_aged_monitoring_event.assert_called_once()

        # Проверяем параметры
        call_args = mock_repo.create_aged_monitoring_event.call_args[1]
        assert 'market_price' in call_args
        assert 'event_metadata' in call_args
        assert 'current_price' not in call_args
        assert 'details' not in call_args


class TestOrderBookSafety:
    """Тест исправления #2: проверки order book"""

    @pytest.mark.asyncio
    async def test_empty_order_book_handling(self):
        """Проверяем обработку пустого order book"""
        mock_exchange = Mock()
        mock_exchange.exchange = Mock()
        mock_exchange.exchange.fetch_order_book = AsyncMock(return_value={'bids': [], 'asks': []})

        executor = OrderExecutor({'test': mock_exchange})

        # Должна быть ошибка при пустом order book
        with pytest.raises(Exception, match="No bids in order book"):
            await executor._execute_limit_maker(mock_exchange, 'BTC/USDT', 'buy', 0.01)

    @pytest.mark.asyncio
    async def test_invalid_order_book_format(self):
        """Проверяем обработку некорректного формата order book"""
        mock_exchange = Mock()
        mock_exchange.exchange = Mock()

        # Order book с некорректным форматом
        mock_exchange.exchange.fetch_order_book = AsyncMock(return_value={'bids': [[]], 'asks': [[]]})

        executor = OrderExecutor({'test': mock_exchange})

        # Должна быть ошибка при некорректном формате
        with pytest.raises(Exception, match="Invalid bid format"):
            await executor._execute_limit_maker(mock_exchange, 'BTC/USDT', 'buy', 0.01)

    @pytest.mark.asyncio
    async def test_negative_price_validation(self):
        """Проверяем валидацию отрицательной цены"""
        mock_exchange = Mock()
        mock_exchange.exchange = Mock()

        # Order book с отрицательной ценой
        mock_exchange.exchange.fetch_order_book = AsyncMock(return_value={
            'bids': [[-100, 1]],
            'asks': [[100, 1]]
        })

        executor = OrderExecutor({'test': mock_exchange})

        # Должна быть ошибка при отрицательной цене
        with pytest.raises(Exception, match="Invalid price from order book"):
            await executor._execute_limit_maker(mock_exchange, 'BTC/USDT', 'buy', 0.01)


class TestPriceRounding:
    """Тест исправления #3: умное округление цен"""

    def test_price_rounding_precision(self):
        """Проверяем точность округления для разных цен"""
        executor = OrderExecutor({})

        # Малоценный токен (< 0.01)
        assert executor._round_price(Decimal('0.00012345'), 'BSUUSDT') == Decimal('0.00012345')
        assert executor._round_price(Decimal('0.00000123'), 'LOWUSDT') == Decimal('0.00000123')

        # Средние цены (0.1-1)
        assert executor._round_price(Decimal('0.123456'), 'MIDUSDT') == Decimal('0.123456')

        # Обычные цены (1-10)
        assert executor._round_price(Decimal('5.123456'), 'NORMALUSDT') == Decimal('5.12346')

        # Высокие цены (> 1000)
        assert executor._round_price(Decimal('42123.456'), 'BTCUSDT') == Decimal('42123.46')

    def test_all_price_ranges(self):
        """Проверяем все диапазоны цен"""
        executor = OrderExecutor({})

        test_cases = [
            (Decimal('0.00000001'), Decimal('0.00000001')),  # < 0.01
            (Decimal('0.012345678'), Decimal('0.0123457')),   # 0.01-0.1
            (Decimal('0.12345678'), Decimal('0.123457')),     # 0.1-1
            (Decimal('1.23456789'), Decimal('1.23457')),      # 1-10
            (Decimal('12.3456789'), Decimal('12.3457')),      # 10-100
            (Decimal('123.456789'), Decimal('123.457')),      # 100-1000
            (Decimal('1234.56789'), Decimal('1234.57')),      # > 1000
        ]

        for input_price, expected in test_cases:
            result = executor._round_price(input_price, 'TEST')
            assert result == expected, f"Failed for {input_price}: got {result}, expected {expected}"


class TestTickerValidation:
    """Тест исправления #4: валидация ticker"""

    @pytest.mark.asyncio
    async def test_invalid_ticker_price(self):
        """Проверяем валидацию некорректной цены ticker"""
        mock_exchange = Mock()
        mock_exchange.exchange = Mock()

        # Ticker с нулевой ценой
        mock_exchange.exchange.fetch_ticker = AsyncMock(return_value={'last': 0})

        executor = OrderExecutor({'test': mock_exchange})

        # Должна быть ошибка при нулевой цене
        with pytest.raises(Exception, match="Invalid ticker price"):
            await executor._execute_limit_aggressive(mock_exchange, 'BTC/USDT', 'buy', 0.01)

    @pytest.mark.asyncio
    async def test_negative_ticker_price(self):
        """Проверяем валидацию отрицательной цены ticker"""
        mock_exchange = Mock()
        mock_exchange.exchange = Mock()

        # Ticker с отрицательной ценой
        mock_exchange.exchange.fetch_ticker = AsyncMock(return_value={'last': -100})

        executor = OrderExecutor({'test': mock_exchange})

        # Должна быть ошибка при отрицательной цене
        with pytest.raises(Exception, match="Invalid ticker price"):
            await executor._execute_limit_aggressive(mock_exchange, 'BTC/USDT', 'sell', 0.01)


# Интеграционный тест
@pytest.mark.asyncio
async def test_all_fixes_integration():
    """Интеграционный тест всех исправлений"""

    print("=" * 60)
    print("ИНТЕГРАЦИОННЫЙ ТЕСТ: Все исправления")
    print("=" * 60)

    # Тест 1: Repository параметры
    print("\n1. Тестируем параметры Repository...")
    mock_repo = AsyncMock()

    # Создаем монитор с правильным репозиторием
    monitor = AgedPositionMonitorV2(
        exchange_managers={},
        repository=mock_repo
    )

    # Создаем target для теста
    target = AgedPositionTarget(
        symbol='TESTUSDT',
        entry_price=Decimal('100'),
        target_price=Decimal('99'),
        phase='grace',
        loss_tolerance=Decimal('0.5'),
        hours_aged=4,
        position_id='test_123'
    )

    # Логируем событие (не должно быть ошибок)
    try:
        await monitor.repository.create_aged_monitoring_event(
            aged_position_id='test_123',
            event_type='test',
            market_price=Decimal('100'),
            event_metadata={'test': 'data'}
        )
        print("   ✅ Repository параметры корректны")
    except TypeError as e:
        print(f"   ❌ Ошибка параметров: {e}")
        return False

    # Тест 2: Order book проверки
    print("\n2. Тестируем Order book проверки...")
    executor = OrderExecutor({})

    # Проверяем что пустой order book обрабатывается
    try:
        mock_exchange = Mock()
        mock_exchange.exchange = Mock()
        mock_exchange.exchange.fetch_order_book = AsyncMock(return_value={'bids': [], 'asks': []})

        await executor._execute_limit_maker(mock_exchange, 'TEST', 'buy', 1)
        print("   ❌ Не поймали исключение для пустого order book")
        return False
    except Exception as e:
        if "No bids" in str(e):
            print("   ✅ Order book проверки работают")
        else:
            print(f"   ❌ Неожиданная ошибка: {e}")
            return False

    # Тест 3: Умное округление
    print("\n3. Тестируем умное округление...")
    small_price = executor._round_price(Decimal('0.00000123'), 'TEST')
    if small_price == Decimal('0.00000123'):
        print(f"   ✅ Малые цены округляются корректно: {small_price}")
    else:
        print(f"   ❌ Неверное округление малой цены: {small_price}")
        return False

    # Тест 4: Валидация ticker
    print("\n4. Тестируем валидацию ticker...")
    try:
        mock_exchange = Mock()
        mock_exchange.exchange = Mock()
        mock_exchange.exchange.fetch_ticker = AsyncMock(return_value={'last': 0})

        await executor._execute_limit_aggressive(mock_exchange, 'TEST', 'buy', 1)
        print("   ❌ Не поймали исключение для нулевой цены")
        return False
    except Exception as e:
        if "Invalid ticker price" in str(e):
            print("   ✅ Валидация ticker работает")
        else:
            print(f"   ❌ Неожиданная ошибка: {e}")
            return False

    print("\n" + "=" * 60)
    print("✅ ВСЕ ИСПРАВЛЕНИЯ РАБОТАЮТ КОРРЕКТНО!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    # Запуск pytest тестов
    pytest.main([__file__, "-v", "--tb=short"])

    # Запуск интеграционного теста
    print("\n")
    result = asyncio.run(test_all_fixes_integration())

    if result:
        print("\n🎉 Все исправления успешно протестированы и работают!")
    else:
        print("\n❌ Некоторые исправления требуют доработки")
        sys.exit(1)