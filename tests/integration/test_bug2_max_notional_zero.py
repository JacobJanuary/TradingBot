#!/usr/bin/env python3
"""
Integration Test: БАГ #2 - maxNotionalValue = 0 Incorrectly Blocks Trading

Проверяет что maxNotionalValue = 0 не блокирует торговлю.
До исправления: maxNotional=0 трактуется как "limit is $0" → блокирует
После исправления: maxNotional=0 игнорируется (означает "no personal limit")
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from core.exchange_manager import ExchangeManager


@pytest.mark.asyncio
async def test_max_notional_zero_does_not_block_trading():
    """
    Test: maxNotionalValue = 0 НЕ должен блокировать торговлю

    Симулируем сценарий:
    1. Binance API возвращает maxNotionalValue = "0" для NEWTUSDT
    2. Баланс = $10,000, notional = $4,237
    3. До исправления: $4237 > $0 → блокирует
    4. После исправления: maxNotional=0 игнорируется → разрешает
    """

    # Create exchange manager
    config = {
        'apiKey': 'test_key',
        'secret': 'test_secret',
        'options': {
            'defaultType': 'future',
            'testnet': True
        }
    }
    exchange = ExchangeManager(
        exchange_name='binance',
        config=config,
        repository=None
    )

    # Mock fetch_balance
    exchange.fetch_balance = AsyncMock(return_value={
        'USDT': {'free': 10000.0, 'used': 0.0, 'total': 10000.0}
    })

    # Mock position risk API response with maxNotional = 0
    position_risk_response = [
        {
            'symbol': 'NEWTUSDT',
            'positionAmt': '0',
            'notional': '0',
            'leverage': '10',
            'maxNotionalValue': '0',  # CRITICAL: This is "0" not "INF"
        }
    ]

    # Mock fapiPrivateV2GetPositionRisk
    exchange.exchange.fapiPrivateV2GetPositionRisk = AsyncMock(
        return_value=position_risk_response
    )

    # Mock fetch_positions (no open positions)
    exchange.fetch_positions = AsyncMock(return_value=[])

    # Test parameters
    symbol = 'NEWT/USDT:USDT'
    notional_usd = 4237.15  # Actual notional from signal

    # Test: can_open_position should ALLOW this trade
    can_open, reason = await exchange.can_open_position(
        symbol=symbol,
        notional_usd=notional_usd
    )

    # Assertions
    # До исправления: can_open = False, reason = "Would exceed max notional: $4237.15 > $0.00"
    # После исправления: can_open = True (maxNotional=0 ignored)

    assert can_open is True, (
        f"❌ TEST FAILED: maxNotional=0 blocked trading!\n"
        f"   can_open = {can_open}\n"
        f"   reason = {reason}\n"
        f"   Expected: can_open=True (maxNotional=0 should be ignored)"
    )

    print(f"✅ TEST PASSED: maxNotional=0 does not block trading")
    print(f"   can_open = {can_open}")
    print(f"   reason = {reason if reason else 'None'}")


@pytest.mark.asyncio
async def test_max_notional_real_limit_still_enforced():
    """
    Test: Реальный maxNotional лимит все еще работает

    Проверяем что исправление не сломало нормальную валидацию:
    1. maxNotional = $100,000
    2. Текущий notional = $50,000
    3. Новый notional = $60,000
    4. Должно быть разрешено (не превышает лимит)
    """

    # Create exchange manager
    config = {
        'apiKey': 'test_key',
        'secret': 'test_secret',
        'options': {
            'defaultType': 'future',
            'testnet': True
        }
    }
    exchange = ExchangeManager(
        exchange_name='binance',
        config=config,
        repository=None
    )

    # Mock fetch_balance
    exchange.fetch_balance = AsyncMock(return_value={
        'USDT': {'free': 100000.0, 'used': 0.0, 'total': 100000.0}
    })

    # Mock position risk API response with REAL limit
    position_risk_response = [
        {
            'symbol': '1000RATSUSDT',
            'positionAmt': '10000',
            'notional': '50000',  # Current position $50k
            'leverage': '10',
            'maxNotionalValue': '100000',  # Real limit: $100k
        }
    ]

    exchange.exchange.fapiPrivateV2GetPositionRisk = AsyncMock(
        return_value=position_risk_response
    )

    # Mock fetch_positions
    exchange.fetch_positions = AsyncMock(return_value=[
        {
            'symbol': '1000RATS/USDT:USDT',
            'contracts': 10000,
            'notional': 50000
        }
    ])

    # Test 1: New position $40k → should PASS (50k + 40k = 90k < 100k limit)
    can_open_1, reason_1 = await exchange.can_open_position(
        symbol='1000RATS/USDT:USDT',
        notional_usd=40000
    )

    # Test 2: New position $60k → should FAIL (50k + 60k = 110k > 100k limit)
    can_open_2, reason_2 = await exchange.can_open_position(
        symbol='1000RATS/USDT:USDT',
        notional_usd=60000
    )

    # Assertions
    assert can_open_1 is True, (
        f"❌ TEST FAILED: Valid position blocked!\n"
        f"   can_open = {can_open_1}\n"
        f"   reason = {reason_1}\n"
        f"   Expected: can_open=True ($50k + $40k = $90k < $100k limit)"
    )

    assert can_open_2 is False, (
        f"❌ TEST FAILED: Invalid position allowed!\n"
        f"   can_open = {can_open_2}\n"
        f"   Expected: can_open=False ($50k + $60k = $110k > $100k limit)"
    )

    assert "exceed max notional" in reason_2.lower(), (
        f"❌ TEST FAILED: Wrong error message!\n"
        f"   reason = {reason_2}\n"
        f"   Expected: message about exceeding max notional"
    )

    print(f"✅ TEST PASSED: Real maxNotional limits still enforced")
    print(f"   Test 1 (within limit): can_open={can_open_1}")
    print(f"   Test 2 (exceeds limit): can_open={can_open_2}, reason={reason_2}")


@pytest.mark.asyncio
async def test_max_notional_inf_works():
    """
    Test: maxNotionalValue = "INF" работает корректно

    Проверяем что INF (без ограничений) все еще работает.
    """

    # Create exchange manager
    config = {
        'apiKey': 'test_key',
        'secret': 'test_secret',
        'options': {
            'defaultType': 'future',
            'testnet': True
        }
    }
    exchange = ExchangeManager(
        exchange_name='binance',
        config=config,
        repository=None
    )

    # Mock fetch_balance
    exchange.fetch_balance = AsyncMock(return_value={
        'USDT': {'free': 100000.0, 'used': 0.0, 'total': 100000.0}
    })

    # Mock position risk API response with INF
    position_risk_response = [
        {
            'symbol': 'BTCUSDT',
            'positionAmt': '0',
            'notional': '0',
            'leverage': '10',
            'maxNotionalValue': 'INF',  # No limit
        }
    ]

    exchange.exchange.fapiPrivateV2GetPositionRisk = AsyncMock(
        return_value=position_risk_response
    )

    exchange.fetch_positions = AsyncMock(return_value=[])

    # Test with very large notional
    can_open, reason = await exchange.can_open_position(
        symbol='BTC/USDT:USDT',
        notional_usd=1000000  # $1M
    )

    # Assertions
    assert can_open is True, (
        f"❌ TEST FAILED: maxNotional=INF blocked trading!\n"
        f"   can_open = {can_open}\n"
        f"   reason = {reason}\n"
        f"   Expected: can_open=True (INF means no limit)"
    )

    print(f"✅ TEST PASSED: maxNotional=INF allows unlimited trading")
    print(f"   can_open = {can_open}")


if __name__ == '__main__':
    import asyncio

    # Run tests
    asyncio.run(test_max_notional_zero_does_not_block_trading())
    asyncio.run(test_max_notional_real_limit_still_enforced())
    asyncio.run(test_max_notional_inf_works())
