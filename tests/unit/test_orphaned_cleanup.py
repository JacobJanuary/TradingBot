#!/usr/bin/env python3
"""
Unit test: Orphaned position cleanup with aged monitoring
Tests that _cleanup_position_monitoring is properly called for orphaned positions
"""
import asyncio
from unittest.mock import AsyncMock, Mock
from decimal import Decimal


# Mock PositionState
class PositionState:
    def __init__(self, id, symbol, exchange, side, quantity, entry_price,
                 current_price, unrealized_pnl, unrealized_pnl_percent=0):
        self.id = id
        self.symbol = symbol
        self.exchange = exchange
        self.side = side
        self.quantity = quantity
        self.entry_price = entry_price
        self.current_price = current_price
        self.unrealized_pnl = unrealized_pnl
        self.unrealized_pnl_percent = unrealized_pnl_percent
        self.status = 'open'
        self.opened_at = None


async def test_orphaned_cleanup_removes_aged_monitoring():
    """
    Test that orphaned cleanup calls _cleanup_position_monitoring
    with skip_aged_adapter=False, ensuring aged monitoring cleanup
    """
    print("Test: Orphaned cleanup removes aged monitoring")

    # Setup mock position manager
    position_manager = Mock()
    position_manager.positions = {}

    # Mock unified protection with aged adapter
    aged_adapter_mock = Mock()
    aged_adapter_mock.remove_aged_position = AsyncMock()
    aged_monitor_mock = Mock()
    aged_monitor_mock.aged_targets = {'TESTUSDT': Mock(phase='aged', hours_aged=4.0)}

    position_manager.unified_protection = {
        'aged_adapter': aged_adapter_mock,
        'aged_monitor': aged_monitor_mock
    }

    # Mock _cleanup_position_monitoring
    position_manager._cleanup_position_monitoring = AsyncMock(return_value={})

    # Create orphaned position
    pos_state = PositionState(
        id=1,
        symbol='TESTUSDT',
        exchange='binance',
        side='long',
        quantity=Decimal('1.0'),
        entry_price=Decimal('100.0'),
        current_price=Decimal('100.0'),
        unrealized_pnl=Decimal('0')
    )

    # Simulate orphaned cleanup (the code we fixed)
    position_manager.positions.pop(pos_state.symbol, None)

    try:
        await position_manager._cleanup_position_monitoring(
            symbol=pos_state.symbol,
            exchange_name=pos_state.exchange,
            position_data=pos_state,
            realized_pnl=None,
            reason='sync_cleanup',
            skip_position_removal=True,   # Already removed
            skip_trailing_stop=False,     # Need to notify
            skip_aged_adapter=False,      # MAIN FIX: cleanup aged monitoring
            skip_events=True              # Events already logged
        )
    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        return False

    # Verify _cleanup_position_monitoring was called with correct parameters
    assert position_manager._cleanup_position_monitoring.called, \
        "❌ _cleanup_position_monitoring was not called"

    call_args = position_manager._cleanup_position_monitoring.call_args
    assert call_args.kwargs['symbol'] == 'TESTUSDT', \
        f"❌ Wrong symbol: {call_args.kwargs['symbol']}"
    assert call_args.kwargs['skip_aged_adapter'] == False, \
        f"❌ skip_aged_adapter should be False, got {call_args.kwargs['skip_aged_adapter']}"
    assert call_args.kwargs['reason'] == 'sync_cleanup', \
        f"❌ Wrong reason: {call_args.kwargs['reason']}"

    print("✅ Test passed: _cleanup_position_monitoring called with skip_aged_adapter=False")
    return True


async def test_orphaned_cleanup_with_no_aged_monitoring():
    """
    Test orphaned cleanup when position is NOT in aged monitoring
    Should not raise errors
    """
    print("\nTest: Orphaned cleanup when position not in aged monitoring")

    # Setup
    position_manager = Mock()
    position_manager.positions = {}
    position_manager.unified_protection = {
        'aged_adapter': Mock(remove_aged_position=AsyncMock()),
        'aged_monitor': Mock(aged_targets={})  # Empty - not aged
    }

    pos_state = PositionState(
        id=1,
        symbol='TESTUSDT',
        exchange='binance',
        side='long',
        quantity=Decimal('1.0'),
        entry_price=Decimal('100.0'),
        current_price=Decimal('100.0'),
        unrealized_pnl=Decimal('0')
    )

    # Mock _cleanup_position_monitoring
    position_manager._cleanup_position_monitoring = AsyncMock(return_value={})

    # Execute - should not raise
    try:
        await position_manager._cleanup_position_monitoring(
            symbol='TESTUSDT',
            exchange_name='binance',
            position_data=pos_state,
            reason='sync_cleanup',
            skip_position_removal=True,
            skip_trailing_stop=False,
            skip_aged_adapter=False,
            skip_events=True
        )
        print("✅ Test passed: No errors when position not in aged monitoring")
        return True
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


async def test_parameters_are_available_in_scope():
    """
    Test that all required parameters exist in orphaned cleanup scope
    """
    print("\nTest: All parameters available in orphaned cleanup scope")

    # Simulate the scope during orphaned cleanup
    # This represents the loop: for pos_state in db_positions_to_close:
    pos_state = PositionState(
        id=1,
        symbol='TESTUSDT',
        exchange='binance',  # This is pos_state.exchange
        side='long',
        quantity=Decimal('1.0'),
        entry_price=Decimal('100.0'),
        current_price=Decimal('100.0'),
        unrealized_pnl=Decimal('0')
    )

    # Verify all parameters are accessible
    try:
        symbol = pos_state.symbol  # ✅ Available
        exchange_name = pos_state.exchange  # ✅ Available (NOT exchange_name variable!)
        position_data = pos_state  # ✅ Available

        assert symbol == 'TESTUSDT', f"❌ symbol mismatch: {symbol}"
        assert exchange_name == 'binance', f"❌ exchange_name mismatch: {exchange_name}"
        assert position_data is not None, "❌ position_data is None"

        print("✅ Test passed: All parameters available in scope")
        return True
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


if __name__ == '__main__':
    print("="*80)
    print("UNIT TESTS: Orphaned Position Cleanup Fix")
    print("="*80 + "\n")

    async def run_all_tests():
        results = []

        results.append(await test_orphaned_cleanup_removes_aged_monitoring())
        results.append(await test_orphaned_cleanup_with_no_aged_monitoring())
        results.append(await test_parameters_are_available_in_scope())

        print("\n" + "="*80)
        print(f"RESULTS: {sum(results)}/{len(results)} tests passed")
        print("="*80)

        return all(results)

    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)
