"""
Unit tests for Zombie Manager critical fixes

Tests cover:
- FIX #1: Binance protective order position check
- FIX #2: Bybit retry logic for fetch_positions
- FIX #3: EventLogger safe wrapper
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from typing import Dict, List


class TestBinanceZombieManagerFix1:
    """
    FIX #1: Binance - Check position before blocking deletion of protective orders

    Критический тест: Protective orders для ЗАКРЫТЫХ позиций должны удаляться
    """

    @pytest.fixture
    def mock_exchange(self):
        """Mock Binance exchange"""
        exchange = AsyncMock()
        exchange.name = 'binanceusdm'
        return exchange

    @pytest.fixture
    def binance_zombie_manager(self, mock_exchange):
        """Create BinanceZombieIntegration instance"""
        from core.binance_zombie_manager import BinanceZombieIntegration

        manager = BinanceZombieIntegration(
            exchange_connector=mock_exchange,
            protected_order_ids=set()
        )
        return manager

    @pytest.mark.asyncio
    async def test_protective_order_with_open_position_not_zombie(
        self, binance_zombie_manager, mock_exchange
    ):
        """
        Тест: Protective order для ОТКРЫТОЙ позиции НЕ должен быть zombie

        Сценарий:
        - Есть открытая позиция BTCUSDT
        - Есть STOP_MARKET ордер с reduceOnly=True
        - Результат: Ордер НЕ помечается как zombie (не удаляется)
        """
        # Setup: Позиция существует
        mock_exchange.fetch_positions.return_value = [
            {
                'symbol': 'BTC/USDT:USDT',
                'contracts': 0.001,
                'side': 'long',
                'entryPrice': 50000,
                'info': {'positionIdx': '0'}
            }
        ]

        # Setup: Protective order существует
        test_order = {
            'id': 'test-order-123',
            'clientOrderId': 'client-123',
            'symbol': 'BTC/USDT:USDT',
            'type': 'STOP_MARKET',
            'side': 'sell',
            'amount': 0.001,
            'price': 49000,
            'status': 'open',
            'timestamp': 1234567890000,
            'reduceOnly': True,
            'info': {'orderListId': -1}
        }

        # Mock активных символов (не важно для этого теста)
        active_symbols = {'BTC/USDT:USDT'}

        # Создаем кеш позиций
        await binance_zombie_manager._get_active_positions_cached()

        # Выполнение: Анализ ордера
        zombie_order = await binance_zombie_manager._analyze_order(
            order=test_order,
            active_symbols=active_symbols
        )

        # Проверка: НЕ должен быть zombie
        assert zombie_order is None, (
            "Protective order для ОТКРЫТОЙ позиции НЕ должен быть помечен как zombie"
        )

    @pytest.mark.asyncio
    async def test_protective_order_with_closed_position_is_zombie(
        self, binance_zombie_manager, mock_exchange
    ):
        """
        КРИТИЧЕСКИЙ ТЕСТ: Protective order для ЗАКРЫТОЙ позиции ДОЛЖЕН быть zombie

        Сценарий:
        - Позиция BTCUSDT ЗАКРЫТА (quantity = 0 или отсутствует)
        - Есть STOP_MARKET ордер с reduceOnly=True (осиротевший)
        - Результат: Ордер помечается как zombie (удаляется)

        Это основная проблема: сейчас такие ордера НЕ удаляются!
        """
        # Setup: Позиций НЕТ (закрыты)
        mock_exchange.fetch_positions.return_value = []

        # Setup: Protective order существует (осиротевший)
        test_order = {
            'id': 'zombie-order-456',
            'clientOrderId': 'client-456',
            'symbol': 'BTC/USDT:USDT',
            'type': 'STOP_MARKET',
            'side': 'sell',
            'amount': 0.001,
            'price': 49000,
            'status': 'open',
            'timestamp': 1234567890000,
            'reduceOnly': True,
            'info': {'orderListId': -1}
        }

        # Mock: Нет активных символов
        active_symbols = set()

        # Создаем кеш позиций (пустой)
        await binance_zombie_manager._get_active_positions_cached()

        # Выполнение: Анализ ордера
        zombie_order = await binance_zombie_manager._analyze_order(
            order=test_order,
            active_symbols=active_symbols
        )

        # Проверка: ДОЛЖЕН быть zombie
        assert zombie_order is not None, (
            "Protective order для ЗАКРЫТОЙ позиции ДОЛЖЕН быть помечен как zombie"
        )
        assert zombie_order.zombie_type == 'protective_for_closed_position', (
            f"Тип zombie должен быть 'protective_for_closed_position', "
            f"получено: {zombie_order.zombie_type}"
        )
        assert zombie_order.symbol == 'BTC/USDT:USDT'
        assert zombie_order.order_id == 'zombie-order-456'

    @pytest.mark.asyncio
    async def test_protective_order_types_coverage(
        self, binance_zombie_manager, mock_exchange
    ):
        """
        Тест: Проверка всех типов protective orders

        Все эти типы должны проверяться на существование позиции:
        - STOP_MARKET
        - STOP_LOSS
        - TAKE_PROFIT_MARKET
        - TRAILING_STOP_MARKET
        - Orders с reduceOnly=True
        """
        # Setup: Нет позиций
        mock_exchange.fetch_positions.return_value = []
        active_symbols = set()
        await binance_zombie_manager._get_active_positions_cached()

        protective_types = [
            'STOP_MARKET',
            'STOP_LOSS',
            'STOP_LOSS_LIMIT',
            'TAKE_PROFIT',
            'TAKE_PROFIT_MARKET',
            'TAKE_PROFIT_LIMIT',
            'TRAILING_STOP_MARKET'
        ]

        for order_type in protective_types:
            test_order = {
                'id': f'test-{order_type}',
                'clientOrderId': f'client-{order_type}',
                'symbol': 'ETH/USDT:USDT',
                'type': order_type,
                'side': 'sell',
                'amount': 0.1,
                'price': 3000,
                'status': 'open',
                'timestamp': 1234567890000,
                'reduceOnly': False,
                'info': {}
            }

            zombie_order = await binance_zombie_manager._analyze_order(
                order=test_order,
                active_symbols=active_symbols
            )

            assert zombie_order is not None, (
                f"Protective order типа {order_type} для закрытой позиции "
                f"должен быть zombie"
            )


class TestBybitZombieCleanerFix2:
    """
    FIX #2: Bybit - Add retry logic and validation for fetch_positions

    Критический тест: Пустой ответ API не должен вызывать массовое удаление
    """

    @pytest.fixture
    def mock_exchange(self):
        """Mock Bybit exchange"""
        exchange = AsyncMock()
        exchange.name = 'bybit'
        return exchange

    @pytest.fixture
    def bybit_zombie_cleaner(self, mock_exchange):
        """Create BybitZombieOrderCleaner instance"""
        from core.bybit_zombie_cleaner import BybitZombieOrderCleaner

        cleaner = BybitZombieOrderCleaner(exchange=mock_exchange)
        return cleaner

    @pytest.mark.asyncio
    async def test_empty_positions_triggers_retry(
        self, bybit_zombie_cleaner, mock_exchange
    ):
        """
        КРИТИЧЕСКИЙ ТЕСТ: Пустой список позиций должен вызвать retry

        Сценарий:
        - API возвращает пустой массив []
        - Система должна повторить попытку (подозрительно пустой результат)
        - После всех retry вернуть пустой словарь (безопасный fallback)
        """
        # Setup: API возвращает пустой массив при всех попытках
        mock_exchange.fetch_positions.return_value = []

        # Выполнение
        positions_map = await bybit_zombie_cleaner.get_active_positions_map()

        # Проверка: Должно быть 3 попытки (max_retries=3)
        assert mock_exchange.fetch_positions.call_count == 3, (
            f"Должно быть 3 попытки получения позиций при пустом результате, "
            f"фактически: {mock_exchange.fetch_positions.call_count}"
        )

        # Проверка: Возвращает пустой словарь (безопасный fallback)
        assert positions_map == {}, (
            "При пустом результате должен вернуться пустой словарь "
            "(безопасный fallback)"
        )

    @pytest.mark.asyncio
    async def test_api_exception_triggers_retry(
        self, bybit_zombie_cleaner, mock_exchange
    ):
        """
        Тест: Исключение API должно вызвать retry

        Сценарий:
        - API выбрасывает исключение при первых попытках
        - Последняя попытка успешна
        - Должны получить корректные позиции
        """
        # Setup: Первые 2 попытки - ошибка, 3-я успешна
        mock_exchange.fetch_positions.side_effect = [
            Exception("API error"),
            Exception("Rate limit"),
            [
                {
                    'symbol': 'BTC/USDT:USDT',
                    'contracts': 0.001,
                    'side': 'long',
                    'info': {'positionIdx': '0'}
                }
            ]
        ]

        # Выполнение
        positions_map = await bybit_zombie_cleaner.get_active_positions_map()

        # Проверка: 3 попытки
        assert mock_exchange.fetch_positions.call_count == 3

        # Проверка: Получили позицию
        assert len(positions_map) == 1
        assert ('BTC/USDT:USDT', 0) in positions_map

    @pytest.mark.asyncio
    async def test_all_retries_failed_returns_empty(
        self, bybit_zombie_cleaner, mock_exchange
    ):
        """
        КРИТИЧЕСКИЙ ТЕСТ: Все retry провалились → вернуть пустой словарь

        Безопасный fallback: Лучше НЕ удалять ордера, чем удалить по ошибке
        """
        # Setup: Все попытки проваливаются
        mock_exchange.fetch_positions.side_effect = Exception("API dead")

        # Выполнение
        positions_map = await bybit_zombie_cleaner.get_active_positions_map()

        # Проверка: 3 попытки
        assert mock_exchange.fetch_positions.call_count == 3

        # Проверка: Пустой словарь (безопасный fallback)
        assert positions_map == {}, (
            "При всех неудачных попытках должен вернуться пустой словарь"
        )

    @pytest.mark.asyncio
    async def test_successful_fetch_no_retry(
        self, bybit_zombie_cleaner, mock_exchange
    ):
        """
        Тест: Успешный fetch с первой попытки - no retry
        """
        # Setup: Успешный результат сразу
        mock_exchange.fetch_positions.return_value = [
            {
                'symbol': 'ETH/USDT:USDT',
                'contracts': 1.5,
                'side': 'short',
                'info': {'positionIdx': '0'}
            },
            {
                'symbol': 'BTC/USDT:USDT',
                'contracts': 0.1,
                'side': 'long',
                'info': {'positionIdx': '0'}
            }
        ]

        # Выполнение
        positions_map = await bybit_zombie_cleaner.get_active_positions_map()

        # Проверка: Только 1 попытка (успешна)
        assert mock_exchange.fetch_positions.call_count == 1

        # Проверка: Обе позиции в карте
        assert len(positions_map) == 2
        assert ('ETH/USDT:USDT', 0) in positions_map
        assert ('BTC/USDT:USDT', 0) in positions_map


class TestEventLoggerSafeWrapperFix3:
    """
    FIX #3: EventLogger safe wrapper

    Критический тест: Ошибка логирования НЕ должна останавливать cleanup
    """

    @pytest.fixture
    def mock_event_logger(self):
        """Mock EventLogger"""
        logger = AsyncMock()
        return logger

    @pytest.fixture
    def zombie_manager_with_logger(self, mock_event_logger):
        """Create EnhancedZombieOrderManager with mocked logger"""
        from core.zombie_manager import EnhancedZombieOrderManager

        mock_exchange_manager = AsyncMock()
        mock_exchange_manager.name = 'testexchange'

        manager = EnhancedZombieOrderManager(
            exchange_manager=mock_exchange_manager
        )

        # Inject mocked event logger
        with patch('core.zombie_manager.get_event_logger', return_value=mock_event_logger):
            yield manager

    @pytest.mark.asyncio
    async def test_eventlogger_exception_doesnt_stop_cleanup(
        self, zombie_manager_with_logger, mock_event_logger
    ):
        """
        КРИТИЧЕСКИЙ ТЕСТ: Исключение EventLogger не должно крашить cleanup

        Сценарий:
        - EventLogger.log_event() выбрасывает исключение
        - Cleanup должен продолжиться
        - Zombie ордера должны быть удалены
        """
        # Setup: EventLogger падает
        mock_event_logger.log_event.side_effect = Exception("Database connection lost")

        # Setup: Mock exchange с zombie ордерами
        mock_exchange = zombie_manager_with_logger.exchange
        mock_exchange.fetch_open_orders.return_value = [
            {
                'id': 'zombie-1',
                'symbol': 'BTC/USDT',
                'type': 'limit',
                'side': 'buy',
                'amount': 0.001,
                'price': 40000,
                'status': 'open',
                'timestamp': 1234567890000
            }
        ]
        mock_exchange.fetch_positions.return_value = []  # Нет позиций
        mock_exchange.fetch_balance.return_value = {'total': {}}  # Нет балансов

        # Mock cancel_order для успеха
        mock_exchange.cancel_order.return_value = {'status': 'canceled'}

        # Выполнение: Cleanup не должен упасть
        try:
            with patch('core.zombie_manager.get_event_logger', return_value=mock_event_logger):
                result = await zombie_manager_with_logger.cleanup_zombie_orders()

            # Проверка: Cleanup выполнен
            assert 'cancelled' in result or 'success' in str(result).lower(), (
                "Cleanup должен успешно завершиться несмотря на ошибку логирования"
            )

        except Exception as e:
            pytest.fail(
                f"Cleanup НЕ должен падать при ошибке EventLogger. "
                f"Получено исключение: {e}"
            )

    @pytest.mark.asyncio
    async def test_log_event_safe_wrapper_catches_all_exceptions(self):
        """
        Тест: _log_event_safe() должен ловить ВСЕ исключения

        Проверяем различные типы ошибок:
        - Database errors
        - Network errors
        - Validation errors
        - Unexpected errors
        """
        from core.zombie_manager import EnhancedZombieOrderManager

        mock_exchange_manager = AsyncMock()
        mock_exchange_manager.name = 'testexchange'
        manager = EnhancedZombieOrderManager(exchange_manager=mock_exchange_manager)

        # Тест различных исключений
        exceptions_to_test = [
            Exception("Database error"),
            ConnectionError("Network timeout"),
            ValueError("Invalid event data"),
            RuntimeError("Unexpected error"),
            KeyError("Missing field"),
        ]

        for exc in exceptions_to_test:
            mock_logger = AsyncMock()
            mock_logger.log_event.side_effect = exc

            # Выполнение: НЕ должно выбросить исключение
            try:
                with patch('core.zombie_manager.get_event_logger', return_value=mock_logger):
                    # Используем приватный метод _log_event_safe если он существует
                    # Иначе просто проверяем, что обертка работает в контексте cleanup
                    await manager._log_event_safe(
                        event_type='test_event',
                        data={'test': 'data'}
                    )
            except Exception as e:
                pytest.fail(
                    f"_log_event_safe() НЕ должен выбрасывать исключение. "
                    f"Получено: {type(exc).__name__}: {exc}"
                )


# Дополнительные интеграционные тесты

class TestZombieManagerIntegration:
    """
    Интеграционные тесты для проверки взаимодействия фиксов
    """

    @pytest.mark.asyncio
    async def test_binance_full_cycle_with_position_check(self):
        """
        Интеграционный тест: Полный цикл обнаружения и удаления zombie

        Проверяет FIX #1 в реальном сценарии
        """
        from core.binance_zombie_manager import BinanceZombieIntegration

        mock_exchange = AsyncMock()
        mock_exchange.name = 'binanceusdm'

        # Setup: 1 открытая позиция, 3 ордера (1 для открытой, 2 zombie)
        mock_exchange.fetch_positions.return_value = [
            {
                'symbol': 'BTC/USDT:USDT',
                'contracts': 0.001,
                'side': 'long',
                'info': {'positionIdx': '0'}
            }
        ]

        mock_exchange.fetch_open_orders.return_value = [
            # Protective order для ОТКРЫТОЙ позиции - НЕ zombie
            {
                'id': 'keep-this',
                'symbol': 'BTC/USDT:USDT',
                'type': 'STOP_MARKET',
                'side': 'sell',
                'amount': 0.001,
                'status': 'open',
                'reduceOnly': True,
                'info': {}
            },
            # Protective order для ЗАКРЫТОЙ позиции - ZOMBIE
            {
                'id': 'delete-this-1',
                'symbol': 'ETH/USDT:USDT',
                'type': 'STOP_MARKET',
                'side': 'sell',
                'amount': 0.1,
                'status': 'open',
                'reduceOnly': True,
                'info': {}
            },
            # Protective order для ЗАКРЫТОЙ позиции - ZOMBIE
            {
                'id': 'delete-this-2',
                'symbol': 'SOL/USDT:USDT',
                'type': 'TAKE_PROFIT_MARKET',
                'side': 'buy',
                'amount': 1.0,
                'status': 'open',
                'reduceOnly': True,
                'info': {}
            }
        ]

        mock_exchange.fetch_balance.return_value = {
            'total': {'USDT': 1000}
        }

        manager = BinanceZombieIntegration(
            exchange_connector=mock_exchange,
            protected_order_ids=set()
        )

        # Выполнение: Обнаружение zombie
        zombies = await manager.detect_zombie_orders()

        # Проверка: Должно быть 2 zombie (не 3!)
        total_zombies = len(zombies.get('all', []))
        assert total_zombies == 2, (
            f"Должно быть обнаружено 2 zombie (ETH и SOL), "
            f"фактически: {total_zombies}"
        )

        # Проверка: BTC ордер НЕ в списке zombie
        zombie_ids = [z.order_id for z in zombies.get('all', [])]
        assert 'keep-this' not in zombie_ids, (
            "Ордер для открытой позиции BTC НЕ должен быть в zombie"
        )
        assert 'delete-this-1' in zombie_ids
        assert 'delete-this-2' in zombie_ids
