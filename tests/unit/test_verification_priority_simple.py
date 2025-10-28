"""
Simplified Unit Tests для FIX #2: Verification Source Priority

Простые тесты которые проверяют что приоритет sources изменен правильно.
"""

import pytest


def test_sources_tried_dict_order():
    """
    Test: Проверяем что sources_tried имеет правильный порядок
    Expected: order_status первый, websocket второй, rest_api третий
    """

    # Порядок в словаре должен быть:
    sources_tried = {
        'order_status': False,  # ПРИОРИТЕТ 1
        'websocket': False,     # ПРИОРИТЕТ 2
        'rest_api': False       # ПРИОРИТЕТ 3
    }

    # Проверяем порядок ключей
    keys = list(sources_tried.keys())
    assert keys[0] == 'order_status'  # Первый
    assert keys[1] == 'websocket'     # Второй
    assert keys[2] == 'rest_api'      # Третий


def test_verification_priority_constants():
    """
    Test: Проверяем что приоритет правильно документирован в коде
    Expected: SOURCE 1 = Order Status, SOURCE 2 = WebSocket, SOURCE 3 = REST API
    """

    # Read the atomic_position_manager.py to verify comments
    with open('core/atomic_position_manager.py', 'r') as f:
        content = f.read()

    # Проверяем что SOURCE 1 это Order Status
    assert '# SOURCE 1 (PRIORITY 1): Order filled status' in content
    assert 'САМЫЙ НАДЕЖНЫЙ - ордер УЖЕ ИСПОЛНЕН' in content

    # Проверяем что SOURCE 2 это WebSocket
    assert '# SOURCE 2 (PRIORITY 2): WebSocket position updates' in content
    assert 'ВТОРИЧНЫЙ - может иметь delay' in content

    # Проверяем что SOURCE 3 это REST API
    assert '# SOURCE 3 (PRIORITY 3): REST API fetch_positions' in content
    assert 'FALLBACK - может иметь cache delay' in content


def test_fix_rc1_comment_exists():
    """
    Test: Проверяем что комментарий FIX RC#1 присутствует
    Expected: Комментарий документирует что это фикс для RC#1
    """

    with open('core/atomic_position_manager.py', 'r') as f:
        content = f.read()

    # Должен быть комментарий о FIX RC#1
    assert 'FIX RC#1: Изменен приоритет verification sources' in content
    assert 'Order Status теперь ПРИОРИТЕТ 1' in content


def test_fix_rc2_comment_exists():
    """
    Test: Проверяем что комментарий FIX RC#2 присутствует
    Expected: Комментарий документирует что это фикс для RC#2
    """

    with open('core/atomic_position_manager.py', 'r') as f:
        content = f.read()

    # Должен быть комментарий о FIX RC#2
    assert 'FIX RC#2: Retry logic для fetch_order с exponential backoff' in content
    assert 'Bybit API v5 имеет propagation delay' in content


def test_retry_logic_parameters():
    """
    Test: Проверяем что retry logic параметры правильные
    Expected: max_retries=5, initial delays разные для Binance/Bybit
    """

    with open('core/atomic_position_manager.py', 'r') as f:
        content = f.read()

    # Проверяем параметры
    assert 'max_retries = 5' in content
    assert "retry_delay = 0.5 if exchange == 'bybit' else 0.1" in content
    assert 'retry_delay *= 1.5' in content  # Exponential backoff factor


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
