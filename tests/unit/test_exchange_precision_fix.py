import pytest
from unittest.mock import AsyncMock, MagicMock
from core.exchange_manager import ExchangeManager
from decimal import Decimal

@pytest.mark.asyncio
async def test_validate_amount_with_step_size_precision():
    """Test that step size precision (< 1.0) is handled correctly"""

    # Mock exchange instance
    mock_exchange = MagicMock()

    # Create ExchangeManager
    manager = ExchangeManager('binance', mock_exchange, None)

    # Mock market with step size precision (ZECUSDT case)
    manager.markets = {
        'ZEC/USDT:USDT': {
            'symbol': 'ZEC/USDT:USDT',
            'precision': {'amount': 0.001},  # Step size, NOT decimal places!
            'limits': {
                'amount': {'min': 0.001, 'max': 6000.0}
            }
        }
    }

    # Test small quantity (the failing case)
    result = await manager._validate_and_adjust_amount('ZECUSDT', 0.021)
    assert result == 0.021, f"Expected 0.021, got {result}"

    # Test edge case (should round down)
    result = await manager._validate_and_adjust_amount('ZECUSDT', 0.0215)
    assert result == 0.021, f"Expected 0.021, got {result}"

    # Test exact minimum
    result = await manager._validate_and_adjust_amount('ZECUSDT', 0.001)
    assert result == 0.001, f"Expected 0.001, got {result}"

    # Test larger quantity
    result = await manager._validate_and_adjust_amount('ZECUSDT', 1.234)
    assert result == 1.234, f"Expected 1.234, got {result}"


@pytest.mark.asyncio
async def test_validate_amount_with_decimal_places_precision():
    """Test that decimal places precision (>= 1.0) still works"""

    # Mock exchange instance
    mock_exchange = MagicMock()

    # Create ExchangeManager
    manager = ExchangeManager('binance', mock_exchange, None)

    # Mock market with decimal places precision (if any exists)
    manager.markets = {
        'BTC/USDT:USDT': {
            'symbol': 'BTC/USDT:USDT',
            'precision': {'amount': 8.0},  # Decimal places
            'limits': {
                'amount': {'min': 0.001, 'max': 1000.0}
            }
        }
    }

    # Test quantity
    result = await manager._validate_and_adjust_amount('BTCUSDT', 0.12345678912)
    assert result == 0.12345678, f"Expected 0.12345678, got {result}"


@pytest.mark.asyncio
async def test_validate_amount_regression():
    """Regression test: ensure existing symbols still work"""

    mock_exchange = MagicMock()
    manager = ExchangeManager('binance', mock_exchange, None)

    # Test various symbols
    test_cases = [
        # (symbol, precision, amount, expected)
        ('ZECUSDT', 0.001, 0.021, 0.021),
        ('ATOMUSDT', 0.01, 0.5, 0.5),
        ('INJUSDT', 0.001, 0.3, 0.3),
        ('BTCUSDT', 0.001, 1.523, 1.523),
    ]

    for symbol, precision, amount, expected in test_cases:
        manager.markets = {
            f'{symbol.replace("USDT", "/USDT:USDT")}': {
                'symbol': f'{symbol.replace("USDT", "/USDT:USDT")}',
                'precision': {'amount': precision},
                'limits': {
                    'amount': {'min': precision, 'max': 10000.0}
                }
            }
        }

        result = await manager._validate_and_adjust_amount(symbol, amount)
        assert result == expected, f"{symbol}: Expected {expected}, got {result}"
