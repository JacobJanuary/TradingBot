#!/usr/bin/env python3
"""
Тесты для OrderExecutor - robust order execution
"""

import asyncio
import sys
import os
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch, call
import pytest
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.order_executor import OrderExecutor, OrderResult


class TestOrderExecutor:
    """Тестирование OrderExecutor"""

    @pytest.fixture
    def mock_exchange(self):
        """Создание мок биржи"""
        exchange = Mock()
        exchange.exchange = Mock()
        exchange.exchange.id = 'binance'
        exchange.exchange.create_order = AsyncMock()
        exchange.exchange.fetch_ticker = AsyncMock(return_value={'last': 100.0})
        exchange.exchange.fetch_order_book = AsyncMock(return_value={
            'bids': [[99.99, 10]],
            'asks': [[100.01, 10]]
        })
        exchange.exchange.fetch_time = AsyncMock()
        exchange.exchange.fetch_open_orders = AsyncMock(return_value=[])
        exchange.exchange.cancel_order = AsyncMock()
        return exchange

    @pytest.fixture
    def mock_repository(self):
        """Создание мок репозитория"""
        repo = AsyncMock()
        repo.create_aged_monitoring_event = AsyncMock()
        return repo

    @pytest.fixture
    async def order_executor(self, mock_exchange, mock_repository):
        """Создание OrderExecutor"""
        exchanges = {'binance': mock_exchange}
        executor = OrderExecutor(exchanges, mock_repository)
        return executor

    @pytest.mark.asyncio
    async def test_successful_market_order(self, order_executor, mock_exchange):
        """Тест: успешный market order с первой попытки"""
        # Настраиваем успешный ответ
        mock_exchange.exchange.create_order.return_value = {
            'id': 'order_123',
            'price': 100.0,
            'amount': 0.01
        }

        # Выполняем закрытие
        result = await order_executor.execute_close(
            symbol='BTC/USDT',
            exchange_name='binance',
            position_side='long',
            amount=0.01,
            reason='aged_grace'
        )

        # Проверяем результат
        assert result.success is True
        assert result.order_id == 'order_123'
        assert result.order_type == 'market'
        assert result.attempts == 1
        assert result.error_message is None

        # Проверяем вызов create_order
        mock_exchange.exchange.create_order.assert_called_once()
        call_args = mock_exchange.exchange.create_order.call_args[1]
        assert call_args['symbol'] == 'BTC/USDT'
        assert call_args['type'] == 'market'
        assert call_args['side'] == 'sell'  # Opposite of long
        assert call_args['amount'] == 0.01

    @pytest.mark.asyncio
    async def test_retry_on_failure(self, order_executor, mock_exchange):
        """Тест: повторные попытки при ошибках"""
        # Первые 2 попытки неудачные, третья успешная
        mock_exchange.exchange.create_order.side_effect = [
            Exception("Network error"),
            Exception("Insufficient balance"),
            {'id': 'order_456', 'price': 100.0, 'amount': 0.01}
        ]

        # Уменьшаем задержку для теста
        order_executor.retry_delay = 0.01

        # Выполняем закрытие
        result = await order_executor.execute_close(
            symbol='ETH/USDT',
            exchange_name='binance',
            position_side='short',
            amount=1.0
        )

        # Проверяем результат
        assert result.success is True
        assert result.order_id == 'order_456'
        assert result.attempts == 3  # Потребовалось 3 попытки

        # Проверяем что было 3 вызова
        assert mock_exchange.exchange.create_order.call_count == 3

    @pytest.mark.asyncio
    async def test_fallback_to_limit_order(self, order_executor, mock_exchange):
        """Тест: переход к limit ордеру при неудаче market"""
        # Market orders fail, limit aggressive succeeds
        async def create_order_side_effect(*args, **kwargs):
            if kwargs.get('type') == 'market':
                raise Exception("Market order disabled")
            else:
                return {'id': 'limit_789', 'price': 99.9, 'amount': 0.1}

        mock_exchange.exchange.create_order.side_effect = create_order_side_effect

        # Выполняем закрытие
        result = await order_executor.execute_close(
            symbol='SOL/USDT',
            exchange_name='binance',
            position_side='long',
            amount=0.1
        )

        # Проверяем результат
        assert result.success is True
        assert result.order_id == 'limit_789'
        assert result.order_type == 'limit_aggressive'
        assert result.attempts > 3  # Market failed 3 times, then limit succeeded

    @pytest.mark.asyncio
    async def test_complete_failure(self, order_executor, mock_exchange):
        """Тест: полный провал всех попыток"""
        # Все попытки неудачные
        mock_exchange.exchange.create_order.side_effect = Exception("Exchange down")

        # Уменьшаем задержку для теста
        order_executor.retry_delay = 0.01

        # Выполняем закрытие
        result = await order_executor.execute_close(
            symbol='AVAX/USDT',
            exchange_name='binance',
            position_side='long',
            amount=1.0
        )

        # Проверяем результат
        assert result.success is False
        assert result.order_id is None
        assert result.error_message == "Exchange down"
        assert result.attempts == 9  # 3 order types × 3 attempts each

        # Проверяем статистику
        stats = order_executor.get_stats()
        assert stats['failed_executions'] == 1

    @pytest.mark.asyncio
    async def test_limit_aggressive_pricing(self, order_executor, mock_exchange):
        """Тест: правильный расчет цены для aggressive limit"""
        # Настраиваем текущую цену
        mock_exchange.exchange.fetch_ticker.return_value = {'last': 100.0}

        # Market fails, limit works
        async def create_order_side_effect(*args, **kwargs):
            if kwargs.get('type') == 'market':
                raise Exception("No market")
            else:
                # Возвращаем переданную цену
                return {
                    'id': 'limit_price_test',
                    'price': kwargs.get('price'),
                    'amount': kwargs.get('amount')
                }

        mock_exchange.exchange.create_order.side_effect = create_order_side_effect

        # Выполняем закрытие LONG (sell)
        result = await order_executor.execute_close(
            symbol='BTC/USDT',
            exchange_name='binance',
            position_side='long',
            amount=0.01
        )

        # Для sell ордера цена должна быть ниже рынка (100 * 0.999 = 99.9)
        assert result.success is True
        assert result.price < Decimal('100')  # Ниже рыночной

        # Выполняем закрытие SHORT (buy)
        result = await order_executor.execute_close(
            symbol='BTC/USDT',
            exchange_name='binance',
            position_side='short',
            amount=0.01
        )

        # Для buy ордера цена должна быть выше рынка (100 * 1.001 = 100.1)
        assert result.success is True
        assert result.price > Decimal('100')  # Выше рыночной

    @pytest.mark.asyncio
    async def test_database_logging(self, order_executor, mock_exchange, mock_repository):
        """Тест: логирование в БД"""
        # Настраиваем успешный ордер
        mock_exchange.exchange.create_order.return_value = {
            'id': 'db_test_123',
            'price': 50.0,
            'amount': 1.0
        }

        # Выполняем закрытие
        result = await order_executor.execute_close(
            symbol='DOT/USDT',
            exchange_name='binance',
            position_side='long',
            amount=1.0,
            reason='aged_progressive'
        )

        # Проверяем что событие было залогировано
        mock_repository.create_aged_monitoring_event.assert_called_once()
        call_args = mock_repository.create_aged_monitoring_event.call_args[1]
        assert call_args['event_type'] == 'order_executed'
        assert call_args['details']['order_id'] == 'db_test_123'
        assert call_args['details']['reason'] == 'aged_progressive'

    @pytest.mark.asyncio
    async def test_cancel_open_orders(self, order_executor, mock_exchange):
        """Тест: отмена открытых ордеров"""
        # Настраиваем открытые ордера
        mock_exchange.exchange.fetch_open_orders.return_value = [
            {'id': 'open_1'},
            {'id': 'open_2'}
        ]

        # Отменяем ордера
        cancelled = await order_executor.cancel_open_orders('BTC/USDT', 'binance')

        assert cancelled == 2
        assert mock_exchange.exchange.cancel_order.call_count == 2

    @pytest.mark.asyncio
    async def test_connectivity_check(self, order_executor, mock_exchange):
        """Тест: проверка подключения к бирже"""
        # Успешное подключение
        mock_exchange.exchange.fetch_time.return_value = {'timestamp': 1234567890}
        assert await order_executor.test_connectivity('binance') is True

        # Неудачное подключение
        mock_exchange.exchange.fetch_time.side_effect = Exception("No connection")
        assert await order_executor.test_connectivity('binance') is False

    @pytest.mark.asyncio
    async def test_statistics_tracking(self, order_executor, mock_exchange):
        """Тест: отслеживание статистики"""
        # Выполняем несколько операций
        mock_exchange.exchange.create_order.side_effect = [
            {'id': 'stat_1', 'price': 100},  # Успех с первой попытки
            Exception("Error"),
            Exception("Error"),
            {'id': 'stat_2', 'price': 100},  # Успех с третьей попытки
        ]

        order_executor.retry_delay = 0.01

        # Первое закрытие - успех сразу
        await order_executor.execute_close(
            'BTC/USDT', 'binance', 'long', 0.01
        )

        # Второе закрытие - успех после retry
        await order_executor.execute_close(
            'ETH/USDT', 'binance', 'short', 1.0
        )

        # Проверяем статистику
        stats = order_executor.get_stats()
        assert stats['total_executions'] == 2
        assert stats['successful_market'] == 2
        assert stats['retries_needed'] == 1  # Второй ордер потребовал retry


@pytest.mark.asyncio
async def test_order_sequence_flow():
    """Тест полного flow последовательности ордеров"""

    # Создаем моки
    mock_exchange = Mock()
    mock_exchange.exchange = Mock()
    mock_exchange.exchange.id = 'binance'
    mock_exchange.exchange.fetch_ticker = AsyncMock(return_value={'last': 42000})
    mock_exchange.exchange.fetch_order_book = AsyncMock(return_value={
        'bids': [[41999, 1]],
        'asks': [[42001, 1]]
    })

    # Счетчик попыток для каждого типа
    attempt_counts = {'market': 0, 'limit': 0}

    async def create_order_mock(*args, **kwargs):
        order_type = kwargs.get('type')

        if order_type == 'market':
            attempt_counts['market'] += 1
            if attempt_counts['market'] <= 3:
                raise Exception("Market order failed")

        elif order_type == 'limit':
            attempt_counts['limit'] += 1
            if attempt_counts['limit'] == 1:
                # Первый limit (aggressive) успешен
                return {'id': 'limit_success', 'price': 41950}

        raise Exception("Unexpected order type")

    mock_exchange.exchange.create_order = AsyncMock(side_effect=create_order_mock)

    # Создаем executor
    executor = OrderExecutor({'binance': mock_exchange})
    executor.retry_delay = 0.01

    print("=" * 60)
    print("ТЕСТ: Последовательность попыток исполнения ордера")
    print("=" * 60)

    # Выполняем закрытие
    result = await executor.execute_close(
        symbol='BTC/USDT',
        exchange_name='binance',
        position_side='long',
        amount=0.01
    )

    print(f"\n📊 Результаты:")
    print(f"   Market попыток: {attempt_counts['market']}")
    print(f"   Limit попыток: {attempt_counts['limit']}")
    print(f"   Успешный тип: {result.order_type}")
    print(f"   Всего попыток: {result.attempts}")

    # Проверки
    assert result.success is True
    assert attempt_counts['market'] == 3  # 3 неудачные попытки market
    assert attempt_counts['limit'] == 1   # 1 успешная попытка limit
    assert result.order_type == 'limit_aggressive'
    assert result.order_id == 'limit_success'

    print("\n✅ ТЕСТ ПРОЙДЕН: Последовательность ордеров работает корректно")
    return True


if __name__ == "__main__":
    # Запускаем pytest
    pytest.main([__file__, "-v", "--tb=short"])

    # Запускаем flow тест
    print("\n")
    asyncio.run(test_order_sequence_flow())