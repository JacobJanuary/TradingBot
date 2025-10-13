#!/usr/bin/env python3
"""
TEST: Проверка фикса отката позиций

Цель: Протестировать что откат использует quantity вместо entry_order.filled

BEFORE FIX: entry_order.filled=0 → Amount 0.0 → FAIL
AFTER FIX: quantity=1298 → Amount 1298 → SUCCESS
"""

import asyncio
import sys
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch
from typing import Optional

# Add project root to path
sys.path.insert(0, '/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot')

from core.atomic_position_manager import AtomicPositionManager, PositionState
from core.exchange_response_adapter import NormalizedOrder


async def test_rollback_uses_quantity():
    """
    Тест: Откат должен использовать quantity, НЕ entry_order.filled
    """
    print("=" * 80)
    print("🧪 TEST: Rollback uses quantity instead of entry_order.filled")
    print("=" * 80)
    print()

    # Setup: Mock exchange manager
    mock_exchange_manager = Mock()
    mock_exchange_instance = AsyncMock()
    mock_exchange_manager.get_exchange.return_value = mock_exchange_instance

    # Setup: Mock database manager
    mock_db_manager = AsyncMock()
    mock_db_manager.delete_position = AsyncMock(return_value=True)

    # Create atomic manager
    atomic_mgr = AtomicPositionManager(
        exchange_manager=mock_exchange_manager,
        db_manager=mock_db_manager
    )

    # Test Case 1: Entry order with filled=0 (как в реальности)
    print("📋 Test Case 1: Entry order with filled=0")
    print()

    entry_order = NormalizedOrder(
        id='test_order_1',
        symbol='FRAGUSDT',
        side='sell',
        type='market',
        price=Decimal('1.5'),
        amount=Decimal('1298'),
        filled=Decimal('0'),  # ← ВАЖНО: filled=0 для нового ордера!
        status='unknown',
        timestamp=1234567890,
        raw={}
    )

    quantity = Decimal('1298')  # ← Правильное количество

    print(f"  Entry Order:")
    print(f"    - Symbol: {entry_order.symbol}")
    print(f"    - Side: {entry_order.side}")
    print(f"    - Amount: {entry_order.amount}")
    print(f"    - Filled: {entry_order.filled} ← THIS IS 0!")
    print(f"  Quantity parameter: {quantity} ← THIS IS CORRECT!")
    print()

    # Mock market order creation to capture what amount was used
    captured_amount = None

    async def mock_create_market_order(symbol, side, amount):
        nonlocal captured_amount
        captured_amount = amount
        return NormalizedOrder(
            id='close_order_1',
            symbol=symbol,
            side=side,
            type='market',
            price=Decimal('1.5'),
            amount=Decimal(str(amount)),
            filled=Decimal(str(amount)),
            status='closed',
            timestamp=1234567891,
            raw={}
        )

    mock_exchange_instance.create_market_order = mock_create_market_order

    # Execute rollback
    print("  🔄 Executing rollback...")

    try:
        await atomic_mgr._rollback_position(
            position_id=999,
            symbol='FRAGUSDT',
            exchange='bybit',
            state=PositionState.ENTRY_PLACED,
            entry_order=entry_order,
            quantity=quantity,
            error='Test error'
        )

        print(f"  ✅ Rollback completed")
        print()

        # Verify: Which amount was used?
        print("  📊 RESULT:")
        print(f"    Amount used for close: {captured_amount}")
        print()

        if captured_amount is None:
            print("  ❌ FAIL: create_market_order was NOT called!")
            return False
        elif float(captured_amount) == 0.0:
            print("  ❌ FAIL: Used entry_order.filled=0 (WRONG!)")
            print("     This is the BUG we're fixing!")
            return False
        elif float(captured_amount) == float(quantity):
            print("  ✅ SUCCESS: Used quantity parameter (CORRECT!)")
            print("     Fix is working!")
            return True
        else:
            print(f"  ⚠️  UNEXPECTED: Amount={captured_amount}, expected {quantity}")
            return False

    except Exception as e:
        print(f"  ❌ ERROR during rollback: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_multiple_symbols():
    """
    Тест: Проверка на нескольких проблемных символах из логов
    """
    print()
    print("=" * 80)
    print("🧪 TEST: Multiple problematic symbols")
    print("=" * 80)
    print()

    test_cases = [
        ('FRAGUSDT', 1298, 'bybit'),
        ('ORBSUSDT', 11990, 'bybit'),
        ('PEAQUSDT', 1280, 'bybit'),
        ('SOLAYERUSDT', 173, 'bybit'),
        ('WAVESUSDT', 200, 'bybit'),
    ]

    all_passed = True

    for symbol, qty, exchange in test_cases:
        print(f"📋 Testing {symbol} (quantity={qty})...")

        # Setup mocks
        mock_exchange_manager = Mock()
        mock_exchange_instance = AsyncMock()
        mock_exchange_manager.get_exchange.return_value = mock_exchange_instance
        mock_db_manager = AsyncMock()
        mock_db_manager.delete_position = AsyncMock(return_value=True)

        atomic_mgr = AtomicPositionManager(
            exchange_manager=mock_exchange_manager,
            db_manager=mock_db_manager
        )

        # Entry order with filled=0
        entry_order = NormalizedOrder(
            id=f'test_{symbol}',
            symbol=symbol,
            side='sell',
            type='market',
            price=Decimal('1.0'),
            amount=Decimal(str(qty)),
            filled=Decimal('0'),
            status='unknown',
            timestamp=1234567890,
            raw={}
        )

        captured_amount = None

        async def mock_create_market_order(sym, side, amount):
            nonlocal captured_amount
            captured_amount = amount
            return NormalizedOrder(
                id=f'close_{sym}',
                symbol=sym,
                side=side,
                type='market',
                price=Decimal('1.0'),
                amount=Decimal(str(amount)),
                filled=Decimal(str(amount)),
                status='closed',
                timestamp=1234567891,
                raw={}
            )

        mock_exchange_instance.create_market_order = mock_create_market_order

        try:
            await atomic_mgr._rollback_position(
                position_id=999,
                symbol=symbol,
                exchange=exchange,
                state=PositionState.ENTRY_PLACED,
                entry_order=entry_order,
                quantity=Decimal(str(qty)),
                error='Test error'
            )

            if captured_amount is None:
                print(f"  ❌ FAIL: No order created")
                all_passed = False
            elif float(captured_amount) == 0.0:
                print(f"  ❌ FAIL: Used filled=0 instead of quantity={qty}")
                all_passed = False
            elif float(captured_amount) == float(qty):
                print(f"  ✅ PASS: Correct amount {qty}")
            else:
                print(f"  ⚠️  UNEXPECTED: {captured_amount} != {qty}")
                all_passed = False

        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            all_passed = False

    print()
    return all_passed


async def main():
    print()
    print("🔬 TESTING ROLLBACK FIX")
    print("Проверяем: откат использует quantity вместо entry_order.filled")
    print()

    # Test 1: Basic functionality
    test1_passed = await test_rollback_uses_quantity()

    # Test 2: Multiple symbols
    test2_passed = await test_multiple_symbols()

    # Summary
    print()
    print("=" * 80)
    print("📊 TEST SUMMARY")
    print("=" * 80)
    print()

    if test1_passed and test2_passed:
        print("✅ ALL TESTS PASSED")
        print()
        print("🎯 ВЕРДИКТ:")
        print("  - Откат использует quantity (правильно)")
        print("  - НЕ использует entry_order.filled (bug исправлен)")
        print("  - Фикс работает корректно!")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        print()
        print("🎯 ВЕРДИКТ:")
        if not test1_passed:
            print("  - Основной тест failed")
        if not test2_passed:
            print("  - Тесты на нескольких символах failed")
        print()
        print("  ⚠️  Фикс НЕ работает или еще не применен!")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
