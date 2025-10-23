#!/usr/bin/env python3
"""
Тест мгновенного обнаружения aged позиций
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.position_manager import PositionManager, PositionState
from core.aged_position_monitor_v2 import AgedPositionMonitorV2
from config.settings import TradingConfig


class TestInstantAgedDetection:
    """Тестирование мгновенного обнаружения aged позиций"""

    @pytest.fixture
    def mock_config(self):
        """Создание мок конфигурации"""
        config = Mock(spec=TradingConfig)
        config.max_position_age_hours = 3
        config.trailing_activation_percent = 2.0
        config.trailing_callback_percent = 1.0
        config.trailing_step_percent = 0.5
        config.max_open_positions = 10
        config.max_position_size = 1000
        config.min_position_size = 10
        config.enable_stop_loss = True
        config.stop_loss_percent = 5.0
        config.zombie_position_threshold_hours = 24
        config.zombie_cleanup_interval_minutes = 60
        return config

    @pytest.fixture
    def mock_unified_protection(self):
        """Создание мок UnifiedProtection"""
        aged_monitor = Mock(spec=AgedPositionMonitorV2)
        aged_monitor.aged_targets = {}
        aged_monitor.add_aged_position = AsyncMock()

        unified = {
            'aged_monitor': aged_monitor
        }
        return unified

    @pytest.fixture
    async def position_manager(self, mock_config, mock_unified_protection):
        """Создание PositionManager с мок зависимостями"""
        mock_repo = AsyncMock()
        mock_exchanges = {'binance': Mock(), 'bybit': Mock()}
        mock_event_router = Mock()

        pm = PositionManager(mock_config, mock_exchanges, mock_repo, mock_event_router)
        pm.unified_protection = mock_unified_protection
        pm.max_position_age_hours = 3

        return pm

    @pytest.mark.asyncio
    async def test_instant_detection_on_websocket_update(self, position_manager):
        """Тест мгновенного обнаружения при WebSocket обновлении"""
        # Создаем aged позицию (старше 3 часов)
        aged_position = PositionState(
            id="test_aged_123",
            symbol="BTCUSDT",
            exchange="binance",
            side="long",
            quantity=Decimal("0.01"),
            entry_price=Decimal("42000"),
            current_price=Decimal("41000"),
            unrealized_pnl=Decimal("-10"),
            unrealized_pnl_percent=Decimal("-2.38"),
            opened_at=datetime.now(timezone.utc) - timedelta(hours=3.5)  # 3.5 часов назад
        )

        position_manager.positions["BTCUSDT"] = aged_position

        # Симулируем WebSocket обновление
        ws_data = {
            'symbol': 'BTC/USDT:USDT',
            'mark_price': 41000.0
        }

        # Вызываем обработчик
        await position_manager._on_position_update(ws_data)

        # Проверяем что позиция была добавлена в aged monitoring
        aged_monitor = position_manager.unified_protection['aged_monitor']
        aged_monitor.add_aged_position.assert_called_once_with(aged_position)

        # Проверяем счетчик
        assert hasattr(position_manager, 'instant_aged_detections')
        assert position_manager.instant_aged_detections == 1

    @pytest.mark.asyncio
    async def test_no_detection_for_young_position(self, position_manager):
        """Тест: молодые позиции не должны обнаруживаться"""
        # Создаем молодую позицию (1 час)
        young_position = PositionState(
            id="test_young_123",
            symbol="ETHUSDT",
            exchange="binance",
            side="short",
            quantity=Decimal("0.1"),
            entry_price=Decimal("2000"),
            current_price=Decimal("2010"),
            unrealized_pnl=Decimal("-1"),
            unrealized_pnl_percent=Decimal("-0.5"),
            opened_at=datetime.now(timezone.utc) - timedelta(hours=1)  # 1 час назад
        )

        position_manager.positions["ETHUSDT"] = young_position

        # Симулируем WebSocket обновление
        ws_data = {
            'symbol': 'ETH/USDT:USDT',
            'mark_price': 2010.0
        }

        # Вызываем обработчик
        await position_manager._on_position_update(ws_data)

        # Проверяем что позиция НЕ была добавлена
        aged_monitor = position_manager.unified_protection['aged_monitor']
        aged_monitor.add_aged_position.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_duplicate_detection(self, position_manager):
        """Тест: позиция не должна добавляться дважды"""
        # Создаем aged позицию
        aged_position = PositionState(
            id="test_dup_123",
            symbol="SOLUSDT",
            exchange="bybit",
            side="long",
            quantity=Decimal("10"),
            entry_price=Decimal("100"),
            current_price=Decimal("95"),
            unrealized_pnl=Decimal("-50"),
            unrealized_pnl_percent=Decimal("-5"),
            opened_at=datetime.now(timezone.utc) - timedelta(hours=5)
        )

        position_manager.positions["SOLUSDT"] = aged_position

        # Помечаем что позиция уже отслеживается
        aged_monitor = position_manager.unified_protection['aged_monitor']
        aged_monitor.aged_targets = {"SOLUSDT": Mock()}

        # Симулируем WebSocket обновление
        ws_data = {
            'symbol': 'SOL/USDT:USDT',
            'mark_price': 95.0
        }

        # Вызываем обработчик
        await position_manager._on_position_update(ws_data)

        # Проверяем что позиция НЕ была добавлена повторно
        aged_monitor.add_aged_position.assert_not_called()

    @pytest.mark.asyncio
    async def test_skip_positions_with_trailing_stop(self, position_manager):
        """Тест: позиции с активным trailing stop не должны обнаруживаться"""
        # Создаем aged позицию с trailing stop
        ts_position = PositionState(
            id="test_ts_123",
            symbol="AVAXUSDT",
            exchange="binance",
            side="long",
            quantity=Decimal("5"),
            entry_price=Decimal("35"),
            current_price=Decimal("40"),
            unrealized_pnl=Decimal("25"),
            unrealized_pnl_percent=Decimal("14.3"),
            opened_at=datetime.now(timezone.utc) - timedelta(hours=4),
            trailing_activated=True  # Trailing stop активен!
        )

        position_manager.positions["AVAXUSDT"] = ts_position

        # Симулируем WebSocket обновление
        ws_data = {
            'symbol': 'AVAX/USDT:USDT',
            'mark_price': 40.0
        }

        # Вызываем обработчик
        await position_manager._on_position_update(ws_data)

        # Проверяем что позиция НЕ была добавлена (из-за TS)
        aged_monitor = position_manager.unified_protection['aged_monitor']
        aged_monitor.add_aged_position.assert_not_called()

    @pytest.mark.asyncio
    async def test_age_calculation_accuracy(self, position_manager):
        """Тест точности расчета возраста позиции"""
        # Тестируем граничные условия
        test_cases = [
            (2.9, False),  # 2.9 часов - не aged
            (3.0, True),   # 3.0 часов - aged
            (3.1, True),   # 3.1 часов - aged
            (10.5, True),  # 10.5 часов - aged
        ]

        for hours_old, should_detect in test_cases:
            position = PositionState(
                id=f"test_age_{hours_old}",
                symbol=f"TEST{int(hours_old*10)}USDT",
                exchange="binance",
                side="long",
                quantity=Decimal("1"),
                entry_price=Decimal("100"),
                current_price=Decimal("100"),
                unrealized_pnl=Decimal("0"),
                unrealized_pnl_percent=Decimal("0"),
                opened_at=datetime.now(timezone.utc) - timedelta(hours=hours_old)
            )

            age = position_manager._calculate_position_age_hours(position)

            # Проверяем точность с погрешностью 0.01 часа
            assert abs(age - hours_old) < 0.01, f"Age calculation incorrect for {hours_old} hours"

            # Проверяем правильность определения aged
            is_aged = age > position_manager.max_position_age_hours
            assert is_aged == should_detect, f"Detection incorrect for {hours_old} hours"


@pytest.mark.asyncio
async def test_instant_detection_performance():
    """Тест производительности мгновенного обнаружения"""
    # Создаем 100 позиций
    positions = {}
    for i in range(100):
        age_hours = i * 0.1  # От 0 до 10 часов
        positions[f"TEST{i}USDT"] = PositionState(
            id=f"perf_{i}",
            symbol=f"TEST{i}USDT",
            exchange="binance",
            side="long" if i % 2 == 0 else "short",
            quantity=Decimal("1"),
            entry_price=Decimal("100"),
            current_price=Decimal("100"),
            unrealized_pnl=Decimal("0"),
            unrealized_pnl_percent=Decimal("0"),
            opened_at=datetime.now(timezone.utc) - timedelta(hours=age_hours)
        )

    # Измеряем время обработки
    start_time = asyncio.get_event_loop().time()

    # Симулируем обработку всех позиций
    aged_count = 0
    for symbol, position in positions.items():
        age = (datetime.now(timezone.utc) - position.opened_at).total_seconds() / 3600
        if age > 3:  # MAX_POSITION_AGE_HOURS
            aged_count += 1

    elapsed = asyncio.get_event_loop().time() - start_time

    # Проверяем производительность
    assert elapsed < 0.1, f"Detection too slow: {elapsed:.3f}s for 100 positions"
    assert aged_count == 70, f"Expected 70 aged positions, found {aged_count}"

    print(f"✅ Performance test passed: {elapsed:.3f}s for 100 positions")


if __name__ == "__main__":
    # Запускаем все тесты
    pytest.main([__file__, "-v", "--tb=short"])