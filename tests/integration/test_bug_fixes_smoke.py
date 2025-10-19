#!/usr/bin/env python3
"""
Smoke Test: Подтверждение что БАГ #1 и БАГ #2 исправлены

Quick verification что код изменений корректен.
"""
import pytest
import ast
import re


def test_bug1_event_logger_uses_create_task():
    """
    Smoke Test БАГ #1: Проверяем что event_logger.log_event() использует asyncio.create_task
    """
    with open('core/signal_processor_websocket.py', 'r') as f:
        content = f.read()

    # Найти функцию _execute_signal
    execute_signal_match = re.search(
        r'async def _execute_signal\(.*?\n(.*?)(?=\n    async def|\n    def|\Z)',
        content,
        re.DOTALL
    )

    assert execute_signal_match, "Cannot find _execute_signal function"

    execute_signal_code = execute_signal_match.group(1)

    # Проверить что в _execute_signal НЕТ await event_logger.log_event
    # (должно быть asyncio.create_task вместо await)
    assert 'await event_logger.log_event(' not in execute_signal_code, (
        "❌ BUG #1 NOT FIXED: Found 'await event_logger.log_event()' in _execute_signal!\n"
        "   Should be 'asyncio.create_task(event_logger.log_event(...))'"
    )

    # Проверить что есть asyncio.create_task(event_logger.log_event
    assert 'asyncio.create_task(' in execute_signal_code, (
        "❌ BUG #1 NOT FIXED: No 'asyncio.create_task()' found in _execute_signal!"
    )

    assert 'event_logger.log_event(' in execute_signal_code, (
        "❌ BUG #1 NOT FIXED: No 'event_logger.log_event()' found in _execute_signal!"
    )

    # Подсчитать сколько раз используется create_task с event_logger
    create_task_count = execute_signal_code.count('asyncio.create_task(')

    # Должно быть минимум 2 (success и failure logging)
    assert create_task_count >= 2, (
        f"❌ BUG #1 PARTIALLY FIXED: Found {create_task_count} asyncio.create_task() calls, "
        f"expected at least 2 (success and failure logging)"
    )

    print(f"✅ BUG #1 SMOKE TEST PASSED:")
    print(f"   - No blocking 'await event_logger.log_event()' found")
    print(f"   - Found {create_task_count} non-blocking 'asyncio.create_task()' calls")
    print(f"   - event_logger will run in background ✓")


def test_bug2_max_notional_zero_ignored():
    """
    Smoke Test БАГ #2: Проверяем что maxNotional=0 игнорируется
    """
    with open('core/exchange_manager.py', 'r') as f:
        content = f.read()

    # Найти функцию can_open_position
    can_open_match = re.search(
        r'async def can_open_position\(.*?\n(.*?)(?=\n    async def|\n    def|\Z)',
        content,
        re.DOTALL
    )

    assert can_open_match, "Cannot find can_open_position function"

    can_open_code = can_open_match.group(1)

    # Проверить что есть проверка maxNotional > 0
    assert 'if max_notional > 0:' in can_open_code, (
        "❌ BUG #2 NOT FIXED: No 'if max_notional > 0:' check found!\n"
        "   maxNotional=0 will still be treated as a $0 limit"
    )

    # Проверить что строка с ошибкой "Would exceed max notional" находится ПОСЛЕ проверки max_notional > 0
    max_notional_check_pos = can_open_code.find('if max_notional > 0:')
    exceed_error_pos = can_open_code.find('Would exceed max notional')

    assert max_notional_check_pos < exceed_error_pos, (
        "❌ BUG #2 NOT FIXED: 'if max_notional > 0:' check is not before the error!\n"
        "   The validation logic is incorrect"
    )

    # Проверить что есть комментарий FIX BUG #2
    assert 'FIX BUG #2' in can_open_code or 'BUG #2' in can_open_code, (
        "⚠️  WARNING: No 'FIX BUG #2' comment found (не критично, но желательно)"
    )

    print(f"✅ BUG #2 SMOKE TEST PASSED:")
    print(f"   - Found 'if max_notional > 0:' check ✓")
    print(f"   - Check is before error validation ✓")
    print(f"   - maxNotional=0 will be ignored (treated as 'no limit') ✓")


def test_imports_present():
    """
    Smoke Test: Проверяем что необходимые imports есть
    """
    with open('core/signal_processor_websocket.py', 'r') as f:
        content = f.read()

    # Проверить что asyncio импортирован
    assert 'import asyncio' in content or 'from asyncio' in content, (
        "❌ IMPORT ERROR: 'asyncio' not imported in signal_processor_websocket.py!\n"
        "   asyncio.create_task() will fail at runtime"
    )

    print(f"✅ IMPORTS SMOKE TEST PASSED:")
    print(f"   - asyncio imported ✓")


if __name__ == '__main__':
    print("=" * 80)
    print("SMOKE TESTS: БАГ #1 (P0) и БАГ #2 (P1)")
    print("=" * 80)
    print()

    try:
        test_bug1_event_logger_uses_create_task()
        print()
        test_bug2_max_notional_zero_ignored()
        print()
        test_imports_present()
        print()
        print("=" * 80)
        print("✅ ALL SMOKE TESTS PASSED")
        print("=" * 80)
    except AssertionError as e:
        print()
        print("=" * 80)
        print("❌ SMOKE TEST FAILED")
        print("=" * 80)
        print(str(e))
        exit(1)
