#!/usr/bin/env python3
"""
Тесты для фаз 3-5 Aged Position Manager V2
Phase 3: Recovery & Persistence
Phase 4: Metrics
Phase 5: Events
"""

import asyncio
import sys
import os
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.aged_position_monitor_v2 import AgedPositionMonitorV2, AgedPositionTarget
from core.position_manager import PositionState


class TestPhase3Recovery:
    """Тесты Phase 3: Recovery & Persistence"""

    @pytest.fixture
    def mock_repository(self):
        """Создание мок репозитория"""
        repo = AsyncMock()
        repo.update_aged_position_status = AsyncMock()
        repo.get_active_aged_positions = AsyncMock(return_value=[])
        return repo

    @pytest.fixture
    def mock_position_manager(self):
        """Создание мок position_manager"""
        pm = Mock()
        pm.positions = {}
        return pm

    @pytest.fixture
    async def aged_monitor(self, mock_repository, mock_position_manager):
        """Создание монитора с моками"""
        monitor = AgedPositionMonitorV2(
            exchange_managers={},
            repository=mock_repository,
            position_manager=mock_position_manager
        )
        return monitor

    @pytest.mark.asyncio
    async def test_persist_state(self, aged_monitor, mock_repository):
        """Тест: сохранение состояния в БД"""
        # Добавляем targets
        aged_monitor.aged_targets['BTCUSDT'] = AgedPositionTarget(
            symbol='BTCUSDT',
            entry_price=Decimal('42000'),
            target_price=Decimal('41500'),
            phase='grace',
            loss_tolerance=Decimal('0.2'),
            hours_aged=4.5,
            position_id='btc_123'
        )

        # Сохраняем состояние
        result = await aged_monitor.persist_state()

        # Проверяем
        assert result is True
        mock_repository.update_aged_position_status.assert_called_once()
        call_args = mock_repository.update_aged_position_status.call_args[1]
        assert call_args['position_id'] == 'btc_123'
        assert call_args['phase'] == 'grace'

    @pytest.mark.asyncio
    async def test_recover_state(self, aged_monitor, mock_repository, mock_position_manager):
        """Тест: восстановление состояния из БД"""
        # Настраиваем БД ответ
        mock_repository.get_active_aged_positions.return_value = [
            {
                'position_id': 'eth_456',
                'symbol': 'ETHUSDT',
                'entry_price': '2000',
                'target_price': '1980',
                'phase': 'progressive',
                'loss_tolerance': '1.0',
                'age_hours': 12,
                'exchange': 'binance'
            }
        ]

        # Добавляем позицию в position_manager
        mock_position_manager.positions['ETHUSDT'] = PositionState(
            id='eth_456',
            symbol='ETHUSDT',
            exchange='binance',
            side='long',
            quantity=Decimal('1'),
            entry_price=Decimal('2000'),
            current_price=Decimal('1990'),
            unrealized_pnl=Decimal('-10'),
            unrealized_pnl_percent=Decimal('-0.5'),
            opened_at=datetime.now(timezone.utc) - timedelta(hours=12)
        )

        # Восстанавливаем
        count = await aged_monitor.recover_state()

        # Проверяем
        assert count == 1
        assert 'ETHUSDT' in aged_monitor.aged_targets
        target = aged_monitor.aged_targets['ETHUSDT']
        assert target.phase == 'progressive'
        assert target.position_id == 'eth_456'

    @pytest.mark.asyncio
    async def test_cleanup_stale_records(self, aged_monitor, mock_repository, mock_position_manager):
        """Тест: очистка устаревших записей"""
        # Настраиваем активные записи в БД
        mock_repository.get_active_aged_positions.return_value = [
            {'position_id': 'old_123', 'symbol': 'OLDUSDT'},
            {'position_id': 'active_456', 'symbol': 'ACTIVEUSDT'}
        ]

        # Только одна позиция существует
        mock_position_manager.positions = {
            'ACTIVEUSDT': Mock()  # Существует
            # 'OLDUSDT' не существует
        }

        # Очищаем
        cleaned = await aged_monitor.cleanup_stale_records()

        # Проверяем
        assert cleaned == 1
        # Должен был пометить OLDUSDT как stale
        calls = mock_repository.update_aged_position_status.call_args_list
        assert len(calls) == 1
        assert calls[0][1]['position_id'] == 'old_123'
        assert calls[0][1]['status'] == 'stale'


class TestPhase4Metrics:
    """Тесты Phase 4: Metrics"""

    @pytest.mark.asyncio
    async def test_metrics_initialization(self):
        """Тест: инициализация метрик"""
        # Мокаем импорт
        with patch('core.aged_position_monitor_v2.AgedPositionMetrics') as MockMetrics:
            MockMetrics.return_value = Mock()

            monitor = AgedPositionMonitorV2(
                exchange_managers={},
                repository=None
            )

            # Проверяем что метрики инициализированы
            assert monitor.metrics is not None
            assert monitor.metrics_collector is not None

    @pytest.mark.asyncio
    async def test_record_detection_metrics(self):
        """Тест: запись метрик обнаружения"""
        with patch('core.aged_position_monitor_v2.AgedPositionMetrics') as MockMetrics:
            mock_metrics = Mock()
            MockMetrics.return_value = mock_metrics

            monitor = AgedPositionMonitorV2(
                exchange_managers={},
                repository=None
            )

            # Создаем позицию
            position = PositionState(
                id='test_123',
                symbol='BTCUSDT',
                exchange='binance',
                side='long',
                quantity=Decimal('0.01'),
                entry_price=Decimal('42000'),
                current_price=Decimal('41000'),
                unrealized_pnl=Decimal('-10'),
                unrealized_pnl_percent=Decimal('-2.38'),
                opened_at=datetime.now(timezone.utc) - timedelta(hours=4)
            )

            # Записываем метрики
            monitor.record_detection_metrics(position)

            # Проверяем
            mock_metrics.record_detection.assert_called_once()
            call_args = mock_metrics.record_detection.call_args[0]
            assert call_args[0] == 'binance'  # exchange
            assert call_args[1] in ['grace', 'progressive']  # phase

    @pytest.mark.asyncio
    async def test_update_metrics(self):
        """Тест: обновление метрик"""
        with patch('core.aged_position_monitor_v2.MetricsCollector') as MockCollector:
            mock_collector = AsyncMock()
            MockCollector.return_value = mock_collector

            monitor = AgedPositionMonitorV2(
                exchange_managers={},
                repository=None
            )

            # Обновляем метрики
            await monitor.update_metrics()

            # Проверяем
            mock_collector.update_metrics.assert_called_once()


class TestPhase5Events:
    """Тесты Phase 5: Events"""

    @pytest.mark.asyncio
    async def test_events_initialization(self):
        """Тест: инициализация событий"""
        with patch('core.aged_position_monitor_v2.AgedPositionEventEmitter') as MockEmitter:
            MockEmitter.return_value = Mock()

            monitor = AgedPositionMonitorV2(
                exchange_managers={},
                repository=None
            )

            # Проверяем что события инициализированы
            assert monitor.event_emitter is not None
            assert monitor.event_factory is not None
            assert monitor.event_orchestrator is not None

    @pytest.mark.asyncio
    async def test_emit_detection_event(self):
        """Тест: эмиссия события обнаружения"""
        with patch('core.aged_position_monitor_v2.AgedPositionEventEmitter') as MockEmitter:
            mock_emitter = AsyncMock()
            MockEmitter.return_value = mock_emitter

            monitor = AgedPositionMonitorV2(
                exchange_managers={},
                repository=None
            )

            # Создаем позицию
            position = Mock()
            position.symbol = 'ETHUSDT'
            position.exchange = 'bybit'

            # Эмитим событие
            await monitor.emit_detection_event(position, 'grace')

            # Проверяем
            mock_emitter.emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_webhook(self):
        """Тест: добавление webhook"""
        with patch('core.aged_position_monitor_v2.AgedPositionEventEmitter') as MockEmitter:
            mock_emitter = Mock()
            MockEmitter.return_value = mock_emitter

            monitor = AgedPositionMonitorV2(
                exchange_managers={},
                repository=None
            )

            # Добавляем webhook
            monitor.add_webhook('https://example.com/webhook')

            # Проверяем
            mock_emitter.add_webhook.assert_called_once_with('https://example.com/webhook')

    @pytest.mark.asyncio
    async def test_event_listener(self):
        """Тест: добавление listener"""
        with patch('core.aged_position_monitor_v2.AgedPositionEventEmitter') as MockEmitter:
            mock_emitter = Mock()
            MockEmitter.return_value = mock_emitter

            with patch('core.aged_position_monitor_v2.AgedEventType') as MockEventType:
                MockEventType.POSITION_DETECTED = 'aged_position_detected'

                monitor = AgedPositionMonitorV2(
                    exchange_managers={},
                    repository=None
                )

                # Добавляем listener
                callback = Mock()
                monitor.add_event_listener('POSITION_DETECTED', callback)

                # Проверяем
                mock_emitter.add_listener.assert_called_once()


@pytest.mark.asyncio
async def test_full_integration_phases_3_5():
    """Интеграционный тест всех фаз 3-5"""

    print("=" * 60)
    print("ИНТЕГРАЦИОННЫЙ ТЕСТ: Фазы 3-5")
    print("=" * 60)

    # Создаем моки
    mock_repo = AsyncMock()
    mock_repo.get_active_aged_positions.return_value = []
    mock_repo.update_aged_position_status = AsyncMock()

    mock_pm = Mock()
    mock_pm.positions = {}

    # Патчим импорты
    with patch('core.aged_position_monitor_v2.AgedPositionMetrics') as MockMetrics:
        with patch('core.aged_position_monitor_v2.AgedPositionEventEmitter') as MockEmitter:
            MockMetrics.return_value = Mock()
            MockEmitter.return_value = AsyncMock()

            # Создаем монитор
            monitor = AgedPositionMonitorV2(
                exchange_managers={},
                repository=mock_repo,
                position_manager=mock_pm
            )

            print("\n1. Проверка инициализации...")
            assert monitor.metrics is not None
            assert monitor.event_emitter is not None
            print("   ✅ Все компоненты инициализированы")

            print("\n2. Добавляем aged позицию...")
            target = AgedPositionTarget(
                symbol='TESTUSDT',
                entry_price=Decimal('100'),
                target_price=Decimal('99'),
                phase='grace',
                loss_tolerance=Decimal('0.5'),
                hours_aged=4,
                position_id='test_123'
            )
            monitor.aged_targets['TESTUSDT'] = target
            print("   ✅ Позиция добавлена")

            print("\n3. Сохраняем состояние...")
            result = await monitor.persist_state()
            assert result is True
            assert mock_repo.update_aged_position_status.called
            print("   ✅ Состояние сохранено")

            print("\n4. Обновляем метрики...")
            await monitor.update_metrics()
            print("   ✅ Метрики обновлены")

            print("\n5. Эмитим событие...")
            position = Mock(symbol='TESTUSDT', exchange='binance')
            await monitor.emit_detection_event(position, 'grace')
            print("   ✅ Событие отправлено")

            print("\n✅ ВСЕ ТЕСТЫ ФАЗЫ 3-5 ПРОЙДЕНЫ!")
            print("=" * 60)
            return True


if __name__ == "__main__":
    # Запускаем pytest тесты
    pytest.main([__file__, "-v", "--tb=short", "-k", "not full_integration"])

    # Запускаем интеграционный тест
    print("\n")
    asyncio.run(test_full_integration_phases_3_5())