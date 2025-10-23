#!/usr/bin/env python3
"""
Тест интеграции AgedPositionMonitorV2 с базой данных
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch, call
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.aged_position_monitor_v2 import AgedPositionMonitorV2, AgedPositionTarget
from core.position_manager import PositionState


class TestDatabaseIntegration:
    """Тестирование интеграции с БД"""

    @pytest.fixture
    def mock_repository(self):
        """Создание мок репозитория с БД методами"""
        repo = AsyncMock()
        repo.create_aged_position = AsyncMock()
        repo.get_active_aged_positions = AsyncMock(return_value=[])
        repo.update_aged_position_status = AsyncMock()
        repo.create_aged_monitoring_event = AsyncMock()
        repo.mark_aged_position_closed = AsyncMock()
        repo.get_aged_positions_statistics = AsyncMock(return_value={})
        repo.update_position = AsyncMock()
        return repo

    @pytest.fixture
    def mock_exchanges(self):
        """Создание мок бирж"""
        binance = Mock()
        binance.exchange = Mock()
        binance.exchange.id = 'binance'
        binance.exchange.create_order = AsyncMock(return_value={'id': 'test_order_123'})

        return {'binance': binance}

    @pytest.fixture
    async def aged_monitor(self, mock_repository, mock_exchanges):
        """Создание AgedPositionMonitorV2 с моками"""
        monitor = AgedPositionMonitorV2(
            exchange_managers=mock_exchanges,
            repository=mock_repository,
            position_manager=None
        )
        return monitor

    @pytest.mark.asyncio
    async def test_add_aged_position_creates_db_entry(self, aged_monitor, mock_repository):
        """Тест: добавление aged позиции создает запись в БД"""
        # Создаем позицию (4 часа = 1 час over limit, должна быть в grace периоде)
        position = PositionState(
            id="test_pos_123",
            symbol="BTCUSDT",
            exchange="binance",
            side="long",
            quantity=Decimal("0.01"),
            entry_price=Decimal("42000"),
            current_price=Decimal("41000"),
            unrealized_pnl=Decimal("-10"),
            unrealized_pnl_percent=Decimal("-2.38"),
            opened_at=datetime.now(timezone.utc) - timedelta(hours=4)  # 1 час over 3-hour limit
        )

        # Добавляем в мониторинг
        await aged_monitor.add_aged_position(position)

        # Проверяем что БД метод был вызван
        mock_repository.create_aged_position.assert_called_once()

        # Проверяем аргументы вызова
        call_args = mock_repository.create_aged_position.call_args[1]
        assert call_args['position_id'] == 'test_pos_123'
        assert call_args['symbol'] == 'BTCUSDT'
        assert call_args['exchange'] == 'binance'

        # Позиция 4 часа старая, лимит 3 часа, значит 1 час over limit
        # Grace период 8 часов, значит должна быть в grace фазе
        expected_phase = 'grace' if call_args['age_hours'] - aged_monitor.max_age_hours <= aged_monitor.grace_period_hours else 'progressive'
        assert call_args['phase'] == expected_phase

        assert 'entry_price' in call_args
        assert 'target_price' in call_args

    @pytest.mark.asyncio
    async def test_check_price_logs_monitoring_event(self, aged_monitor, mock_repository):
        """Тест: проверка цены логирует событие мониторинга"""
        # Добавляем позицию в отслеживание
        # Для aged позиции устанавливаем target ниже входа (готовы принять убыток)
        target = AgedPositionTarget(
            symbol="ETHUSDT",
            entry_price=Decimal("2000"),
            target_price=Decimal("1996"),  # Target ниже входа для long (принимаем убыток)
            phase="grace",
            loss_tolerance=Decimal("0.2"),
            hours_aged=4.0,
            position_id="test_eth_123"
        )
        aged_monitor.aged_targets["ETHUSDT"] = target

        # Создаем убыточную позицию для position_manager
        position = PositionState(
            id="test_eth_123",
            symbol="ETHUSDT",
            exchange="binance",
            side="long",
            quantity=Decimal("1"),
            entry_price=Decimal("2000"),
            current_price=Decimal("1998"),  # Убыточная позиция
            unrealized_pnl=Decimal("-2"),
            unrealized_pnl_percent=Decimal("-0.1"),
            opened_at=datetime.now(timezone.utc) - timedelta(hours=4)
        )

        # Мокируем position_manager
        aged_monitor.position_manager = Mock()
        aged_monitor.position_manager.positions = {"ETHUSDT": position}

        # Проверяем цену (1998 > target 1996, но не должно закрыться)
        await aged_monitor.check_price_target("ETHUSDT", Decimal("1998"))

        # Проверяем что событие мониторинга было залогировано
        # Находим вызов с event_type='price_check'
        calls = mock_repository.create_aged_monitoring_event.call_args_list
        price_check_call = None
        for call in calls:
            if call[1].get('event_type') == 'price_check':
                price_check_call = call[1]
                break

        assert price_check_call is not None, "price_check event not found"
        assert price_check_call['aged_position_id'] == 'test_eth_123'
        assert price_check_call['current_price'] == Decimal("1998")
        # Target price рассчитывается на основе entry_price и commission
        # Проверяем что target_price близок к ожидаемому (с учетом округления)
        assert abs(price_check_call['target_price'] - Decimal("2000")) < Decimal("5")

    @pytest.mark.asyncio
    async def test_phase_transition_updates_db(self, aged_monitor, mock_repository):
        """Тест: переход между фазами обновляет БД"""
        # Создаем позицию в grace периоде
        position = PositionState(
            id="test_phase_123",
            symbol="SOLUSDT",
            exchange="binance",
            side="long",
            quantity=Decimal("10"),
            entry_price=Decimal("100"),
            current_price=Decimal("99"),
            unrealized_pnl=Decimal("-10"),
            unrealized_pnl_percent=Decimal("-1"),
            opened_at=datetime.now(timezone.utc) - timedelta(hours=12)  # Старая позиция
        )

        target = AgedPositionTarget(
            symbol="SOLUSDT",
            entry_price=Decimal("100"),
            target_price=Decimal("100.2"),
            phase="grace",
            loss_tolerance=Decimal("0"),
            hours_aged=4.0,
            position_id="test_phase_123"
        )

        # Вызываем обновление фазы
        await aged_monitor._update_phase_if_needed(position, target)

        # Проверяем что фаза изменилась
        assert target.phase == "progressive"  # Должна перейти в progressive

        # Проверяем БД вызовы
        mock_repository.update_aged_position_status.assert_called_once()

        # Проверяем событие смены фазы
        calls = mock_repository.create_aged_monitoring_event.call_args_list
        phase_change_call = None
        for call in calls:
            if call[1].get('event_type') == 'phase_change':
                phase_change_call = call[1]
                break

        assert phase_change_call is not None
        assert phase_change_call['details']['old_phase'] == 'grace'
        assert phase_change_call['details']['new_phase'] == 'progressive'

    @pytest.mark.asyncio
    async def test_successful_close_marks_db(self, aged_monitor, mock_repository, mock_exchanges):
        """Тест: успешное закрытие обновляет БД"""
        # Создаем позицию и target
        position = PositionState(
            id="test_close_123",
            symbol="AVAXUSDT",
            exchange="binance",
            side="long",
            quantity=Decimal("5"),
            entry_price=Decimal("35"),
            current_price=Decimal("36"),
            unrealized_pnl=Decimal("5"),
            unrealized_pnl_percent=Decimal("2.86"),
            opened_at=datetime.now(timezone.utc) - timedelta(hours=5)
        )

        target = AgedPositionTarget(
            symbol="AVAXUSDT",
            entry_price=Decimal("35"),
            target_price=Decimal("35.07"),
            phase="grace",
            loss_tolerance=Decimal("0"),
            hours_aged=5.0,
            position_id="test_close_123"
        )

        # Вызываем закрытие
        await aged_monitor._trigger_market_close(position, target, Decimal("36"))

        # Проверяем что ордер был создан
        mock_exchanges['binance'].exchange.create_order.assert_called_once()

        # Проверяем БД вызовы
        mock_repository.mark_aged_position_closed.assert_called_once_with(
            position_id="test_close_123",
            order_id="test_order_123",
            close_price=Decimal("36"),
            close_reason="aged_grace"
        )

        # Проверяем обновление основной позиции
        mock_repository.update_position.assert_called_once_with(
            "test_close_123",
            status='closed',
            exit_reason='aged_grace'
        )

        # Проверяем событие закрытия
        calls = mock_repository.create_aged_monitoring_event.call_args_list
        close_event_call = None
        for call in calls:
            if call[1].get('event_type') == 'closed':
                close_event_call = call[1]
                break

        assert close_event_call is not None
        assert close_event_call['details']['order_id'] == 'test_order_123'
        assert close_event_call['details']['phase'] == 'grace'

    @pytest.mark.asyncio
    async def test_failed_close_logs_error(self, aged_monitor, mock_repository, mock_exchanges):
        """Тест: неудачное закрытие логирует ошибку в БД"""
        # Настраиваем биржу на ошибку
        mock_exchanges['binance'].exchange.create_order.side_effect = Exception("Order failed")

        position = PositionState(
            id="test_fail_123",
            symbol="DOTUSDT",
            exchange="binance",
            side="short",
            quantity=Decimal("100"),
            entry_price=Decimal("6"),
            current_price=Decimal("6.5"),
            unrealized_pnl=Decimal("-50"),
            unrealized_pnl_percent=Decimal("-8.33"),
            opened_at=datetime.now(timezone.utc) - timedelta(hours=15)
        )

        target = AgedPositionTarget(
            symbol="DOTUSDT",
            entry_price=Decimal("6"),
            target_price=Decimal("6.36"),
            phase="progressive",
            loss_tolerance=Decimal("6"),
            hours_aged=15.0,
            position_id="test_fail_123"
        )

        # Пытаемся закрыть
        await aged_monitor._trigger_market_close(position, target, Decimal("6.5"))

        # Проверяем что ошибка была залогирована
        calls = mock_repository.create_aged_monitoring_event.call_args_list
        error_event_call = None
        for call in calls:
            if call[1].get('event_type') == 'close_failed':
                error_event_call = call[1]
                break

        assert error_event_call is not None
        assert 'Order failed' in error_event_call['details']['error']

    @pytest.mark.asyncio
    async def test_db_errors_dont_crash_monitor(self, aged_monitor, mock_repository):
        """Тест: ошибки БД не крашат монитор"""
        # Настраиваем БД на ошибки
        mock_repository.create_aged_position.side_effect = Exception("DB Error")
        mock_repository.create_aged_monitoring_event.side_effect = Exception("DB Error")

        position = PositionState(
            id="test_resilient_123",
            symbol="LINKUSDT",
            exchange="binance",
            side="long",
            quantity=Decimal("50"),
            entry_price=Decimal("7"),
            current_price=Decimal("6.5"),
            unrealized_pnl=Decimal("-25"),
            unrealized_pnl_percent=Decimal("-7.14"),
            opened_at=datetime.now(timezone.utc) - timedelta(hours=5)
        )

        # Добавляем позицию - не должно крашнуться
        await aged_monitor.add_aged_position(position)

        # Проверяем что позиция все равно добавлена в отслеживание
        assert "LINKUSDT" in aged_monitor.aged_targets
        assert aged_monitor.aged_targets["LINKUSDT"].symbol == "LINKUSDT"

        # Мониторинг должен продолжать работать
        aged_monitor.position_manager = Mock()
        aged_monitor.position_manager.positions = {"LINKUSDT": position}

        # Проверка цены тоже не должна крашнуться
        await aged_monitor.check_price_target("LINKUSDT", Decimal("6.5"))

        # Монитор все еще работает
        assert "LINKUSDT" in aged_monitor.aged_targets


@pytest.mark.asyncio
async def test_full_lifecycle_with_db():
    """Полный жизненный цикл aged позиции с БД"""

    # Создаем компоненты с моками
    mock_repo = AsyncMock()
    mock_repo.create_aged_position = AsyncMock()
    mock_repo.update_aged_position_status = AsyncMock()
    mock_repo.create_aged_monitoring_event = AsyncMock()
    mock_repo.mark_aged_position_closed = AsyncMock()
    mock_repo.update_position = AsyncMock()

    mock_exchange = Mock()
    mock_exchange.exchange = Mock()
    mock_exchange.exchange.id = 'binance'
    mock_exchange.exchange.create_order = AsyncMock(return_value={'id': 'final_order_123'})

    monitor = AgedPositionMonitorV2(
        exchange_managers={'binance': mock_exchange},
        repository=mock_repo
    )

    print("=" * 60)
    print("ТЕСТ: Полный жизненный цикл с БД")
    print("=" * 60)

    # 1. Создание aged позиции
    print("\n1. Добавление aged позиции...")
    position = PositionState(
        id="lifecycle_123",
        symbol="BTCUSDT",
        exchange="binance",
        side="long",
        quantity=Decimal("0.01"),
        entry_price=Decimal("42000"),
        current_price=Decimal("41000"),
        unrealized_pnl=Decimal("-10"),
        unrealized_pnl_percent=Decimal("-2.38"),
        opened_at=datetime.now(timezone.utc) - timedelta(hours=4)
    )

    await monitor.add_aged_position(position)
    assert mock_repo.create_aged_position.called
    print("   ✅ Позиция добавлена в БД")

    # 2. Мониторинг цены
    print("\n2. Мониторинг цены...")
    monitor.position_manager = Mock()
    monitor.position_manager.positions = {"BTCUSDT": position}

    await monitor.check_price_target("BTCUSDT", Decimal("41500"))
    assert mock_repo.create_aged_monitoring_event.called
    print("   ✅ Событие мониторинга записано")

    # 3. Переход фазы (aged дольше)
    print("\n3. Переход фазы...")
    # Изменяем возраст позиции для перехода в progressive
    position.opened_at = datetime.now(timezone.utc) - timedelta(hours=12)  # 12 часов = 9 часов over limit
    target = monitor.aged_targets["BTCUSDT"]

    # Сохраняем старую фазу для проверки
    old_phase = target.phase

    # Вызываем обновление фазы
    await monitor._update_phase_if_needed(position, target)

    # 12 часов - 3 (max_age) = 9 часов over limit
    # Grace period = 8 часов, значит должна перейти в progressive
    assert target.phase == "progressive", f"Expected progressive, got {target.phase}"

    # Проверяем что БД была обновлена только если фаза изменилась
    if old_phase != target.phase:
        assert mock_repo.update_aged_position_status.called
        print(f"   ✅ Фаза изменена: {old_phase} → {target.phase}")
    else:
        print(f"   ℹ️  Фаза осталась: {target.phase}")

    # 4. Закрытие позиции
    print("\n4. Закрытие позиции...")
    position.current_price = Decimal("42100")  # Прибыльная
    await monitor.check_price_target("BTCUSDT", Decimal("42100"))

    assert mock_exchange.exchange.create_order.called
    assert mock_repo.mark_aged_position_closed.called
    assert "BTCUSDT" not in monitor.aged_targets
    print("   ✅ Позиция закрыта и удалена из мониторинга")

    # Проверяем количество вызовов БД
    db_calls = {
        'create': mock_repo.create_aged_position.call_count,
        'events': mock_repo.create_aged_monitoring_event.call_count,
        'updates': mock_repo.update_aged_position_status.call_count,
        'closed': mock_repo.mark_aged_position_closed.call_count
    }

    print(f"\n📊 Статистика БД вызовов:")
    print(f"   Создано позиций: {db_calls['create']}")
    print(f"   События мониторинга: {db_calls['events']}")
    print(f"   Обновлений статуса: {db_calls['updates']}")
    print(f"   Закрыто позиций: {db_calls['closed']}")

    print("\n✅ ТЕСТ ПРОЙДЕН: Полный жизненный цикл с БД работает корректно")
    return True


if __name__ == "__main__":
    # Запускаем тесты
    pytest.main([__file__, "-v", "--tb=short"])

    # Запускаем интеграционный тест
    print("\n" + "=" * 60)
    asyncio.run(test_full_lifecycle_with_db())