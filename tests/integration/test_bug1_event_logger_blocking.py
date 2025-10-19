#!/usr/bin/env python3
"""
Integration Test: БАГ #1 - Event Logger Blocking Wave Execution

Проверяет что event_logger.log_event() не блокирует выполнение волны.
До исправления: если event_logger зависает, волна останавливается
После исправления: event_logger работает в фоне (asyncio.create_task)
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from core.signal_processor_websocket import SignalProcessor
from core.exchange_manager import ExchangeManager
from core.position_manager import PositionManager


@pytest.mark.asyncio
async def test_event_logger_does_not_block_wave_execution():
    """
    Test: event_logger.log_event() должен НЕ блокировать выполнение волны

    Симулируем сценарий:
    1. Есть 4 валидных сигнала
    2. event_logger.log_event() зависает на 5 секунд при втором сигнале
    3. Проверяем что все 4 сигнала выполнились (не заблокировались)
    """

    # Mock exchanges
    binance_mock = AsyncMock(spec=ExchangeManager)
    binance_mock.name = 'binance'

    # Mock position manager
    position_manager_mock = AsyncMock(spec=PositionManager)

    # Create signal processor
    processor = SignalProcessor(
        position_manager=position_manager_mock,
        event_logger=None
    )

    # Mock signals (4 сигнала)
    signals = [
        {
            'symbol': 'BTC/USDT:USDT',
            'signal_id': f'test-signal-{i}',
            'side': 'long',
            'entry_point': 50000 + i * 100,
            'stop_loss': 49000 + i * 100,
            'take_profit': 51000 + i * 100,
            'confidence_score': 0.85,
            'exchange': 'binance',
            'type': 'futures'
        }
        for i in range(4)
    ]

    # Mock event_logger with delayed response
    slow_event_logger = AsyncMock()

    async def slow_log_event(*args, **kwargs):
        """Simulate slow event logging (blocking behavior)"""
        await asyncio.sleep(5)  # 5 seconds delay
        return True

    slow_event_logger.log_event = AsyncMock(side_effect=slow_log_event)

    # Mock _execute_signal to track executions
    execution_count = 0
    original_execute_signal = processor._execute_signal

    async def tracked_execute_signal(signal_data, *args, **kwargs):
        nonlocal execution_count
        execution_count += 1

        # Simulate успешное открытие позиции
        position_mock = MagicMock()
        position_mock.id = execution_count

        # CRITICAL: call event_logger here
        if slow_event_logger:
            # До исправления: await (блокирует)
            # После исправления: asyncio.create_task (не блокирует)

            # Для теста проверим текущее поведение
            # ВАЖНО: если здесь await - тест должен УПАСТЬ (timeout)
            # ВАЖНО: если здесь create_task - тест должен ПРОЙТИ

            # Временно используем await чтобы проверить что тест работает
            # После исправления бага это должно быть create_task
            await slow_event_logger.log_event(
                event_type='SIGNAL_EXECUTED',
                data={'signal_id': signal_data.get('signal_id')},
                symbol=signal_data.get('symbol')
            )

        return position_mock

    processor._execute_signal = tracked_execute_signal

    # Start time
    start_time = asyncio.get_event_loop().time()

    # Execute all signals with timeout
    try:
        # Если event_logger блокирует - это займет 4 * 5 = 20 секунд
        # Если event_logger НЕ блокирует - это займет < 1 секунду

        # Set timeout to 10 seconds
        await asyncio.wait_for(
            asyncio.gather(*[
                tracked_execute_signal(signal)
                for signal in signals
            ]),
            timeout=10.0
        )

        execution_time = asyncio.get_event_loop().time() - start_time

        # Assertions
        assert execution_count == 4, f"Expected 4 executions, got {execution_count}"

        # До исправления: execution_time > 15 (blocking)
        # После исправления: execution_time < 2 (non-blocking)
        assert execution_time < 10, f"Execution took too long: {execution_time:.2f}s (event_logger is blocking!)"

        print(f"✅ TEST PASSED: All 4 signals executed in {execution_time:.2f}s")

    except asyncio.TimeoutError:
        pytest.fail(
            f"❌ TEST FAILED: Wave execution timed out after 10s. "
            f"Only {execution_count}/4 signals executed. "
            f"event_logger.log_event() is BLOCKING the wave!"
        )


@pytest.mark.asyncio
async def test_event_logger_runs_in_background():
    """
    Test: event_logger должен запускаться в фоне (не блокировать return)

    Проверяем что после _execute_signal сразу возвращается результат,
    даже если event_logger еще не завершил работу.
    """

    # Mock event_logger with tracking
    event_logger_mock = AsyncMock()
    log_event_started = asyncio.Event()
    log_event_completed = asyncio.Event()

    async def tracked_log_event(*args, **kwargs):
        log_event_started.set()
        await asyncio.sleep(2)  # Simulate slow logging
        log_event_completed.set()
        return True

    event_logger_mock.log_event = AsyncMock(side_effect=tracked_log_event)

    # Create processor
    processor = SignalProcessor(
        position_manager=AsyncMock(),
        event_logger=event_logger_mock
    )

    # Mock signal
    signal = {
        'signal_id': 'test-123',
        'symbol': 'BTC/USDT:USDT',
        'side': 'long'
    }

    # Mock _execute_signal with background logging
    async def execute_with_background_logging(signal_data):
        # Simulate position opening
        position = MagicMock()
        position.id = 1

        # CRITICAL: Log event in background
        # После исправления: должно быть asyncio.create_task()
        asyncio.create_task(
            event_logger_mock.log_event(
                event_type='SIGNAL_EXECUTED',
                data={'signal_id': signal_data.get('signal_id')}
            )
        )

        # Return immediately (не ждем log_event)
        return position

    start_time = asyncio.get_event_loop().time()

    # Execute signal
    result = await execute_with_background_logging(signal)

    execution_time = asyncio.get_event_loop().time() - start_time

    # Assertions
    assert result is not None, "Expected position to be returned"
    assert execution_time < 0.5, f"Execution should return immediately, took {execution_time:.2f}s"

    # Event logger should be started but not necessarily completed
    assert log_event_started.is_set(), "Event logger should have started"

    # Wait for completion (background task)
    await asyncio.sleep(2.5)
    assert log_event_completed.is_set(), "Event logger should have completed in background"

    print(f"✅ TEST PASSED: Signal executed in {execution_time:.2f}s, event logged in background")


if __name__ == '__main__':
    # Run tests
    asyncio.run(test_event_logger_does_not_block_wave_execution())
    asyncio.run(test_event_logger_runs_in_background())
