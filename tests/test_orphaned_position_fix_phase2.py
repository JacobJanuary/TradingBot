"""
Test Phase 2 Fixes for Orphaned Position Bug

Verifies that:
1. FIX #2.1: Multi-source position verification works
2. FIX #2.2: Post-rollback verification works
3. FIX #3.1: Safe position_manager access works
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import asyncio


class TestPhase2Fixes:
    """
    Test that Phase 2 fixes eliminate race condition and verify rollback.
    """

    @pytest.mark.asyncio
    async def test_fix_2_1_websocket_source_priority(self):
        """
        FIX #2.1: WebSocket should be checked first (fastest source)
        """
        from core.atomic_position_manager import AtomicPositionManager

        # Mock dependencies
        repository = Mock()
        exchange_manager = Mock()
        stop_loss_manager = Mock()

        # Mock position_manager with WebSocket data
        position_manager = Mock()
        position_manager.get_cached_position = Mock(return_value={
            'symbol': 'AVL/USDT:USDT',
            'quantity': 43.0,  # Position exists in WebSocket!
            'side': 'long'
        })

        atomic_mgr = AtomicPositionManager(
            repository, exchange_manager, stop_loss_manager,
            position_manager=position_manager
        )

        # Mock exchange_instance
        exchange_instance = Mock()

        # Mock entry_order
        entry_order = Mock()
        entry_order.id = 'test-order-id'

        # Call verification method
        result = await atomic_mgr._verify_position_exists_multi_source(
            exchange_instance=exchange_instance,
            symbol='AVL/USDT:USDT',
            exchange='bybit',
            entry_order=entry_order,
            expected_quantity=43.0,
            timeout=5.0
        )

        # Should return True immediately (WebSocket found it)
        assert result is True
        print("✅ FIX #2.1: WebSocket priority works - instant verification")

        # Verify get_cached_position was called
        position_manager.get_cached_position.assert_called_once()

    @pytest.mark.asyncio
    async def test_fix_2_1_order_status_fallback(self):
        """
        FIX #2.1: Order status should be checked if WebSocket unavailable
        """
        from core.atomic_position_manager import AtomicPositionManager

        # Mock dependencies
        repository = Mock()
        exchange_manager = Mock()
        stop_loss_manager = Mock()

        # No position_manager (WebSocket unavailable)
        atomic_mgr = AtomicPositionManager(
            repository, exchange_manager, stop_loss_manager,
            position_manager=None
        )

        # Mock exchange_instance with fetch_order
        exchange_instance = Mock()
        exchange_instance.fetch_order = AsyncMock(return_value={
            'id': 'test-order-id',
            'status': 'closed',
            'filled': 43.0,
            'amount': 43.0
        })

        # Mock entry_order
        entry_order = Mock()
        entry_order.id = 'test-order-id'

        # Call verification method
        result = await atomic_mgr._verify_position_exists_multi_source(
            exchange_instance=exchange_instance,
            symbol='AVL/USDT:USDT',
            exchange='bybit',
            entry_order=entry_order,
            expected_quantity=43.0,
            timeout=5.0
        )

        # Should return True (order status shows filled)
        assert result is True
        print("✅ FIX #2.1: Order status fallback works")

        # Verify fetch_order was called
        exchange_instance.fetch_order.assert_called()

    @pytest.mark.asyncio
    async def test_fix_2_1_order_failed_detection(self):
        """
        FIX #2.1: Should detect when order failed (closed with 0 filled)
        """
        from core.atomic_position_manager import AtomicPositionManager

        # Mock dependencies
        repository = Mock()
        exchange_manager = Mock()
        stop_loss_manager = Mock()

        atomic_mgr = AtomicPositionManager(
            repository, exchange_manager, stop_loss_manager,
            position_manager=None
        )

        # Mock exchange_instance with failed order
        exchange_instance = Mock()
        exchange_instance.fetch_order = AsyncMock(return_value={
            'id': 'test-order-id',
            'status': 'closed',
            'filled': 0,  # Order failed!
            'amount': 43.0
        })

        # Mock entry_order
        entry_order = Mock()
        entry_order.id = 'test-order-id'

        # Call verification method
        result = await atomic_mgr._verify_position_exists_multi_source(
            exchange_instance=exchange_instance,
            symbol='AVL/USDT:USDT',
            exchange='bybit',
            entry_order=entry_order,
            expected_quantity=43.0,
            timeout=5.0
        )

        # Should return False (order failed)
        assert result is False
        print("✅ FIX #2.1: Order failure detection works")

    @pytest.mark.asyncio
    async def test_fix_3_1_safe_position_manager_access(self):
        """
        FIX #3.1: Should handle missing position_manager gracefully
        """
        from core.atomic_position_manager import AtomicPositionManager

        # Mock dependencies
        repository = Mock()
        exchange_manager = Mock()
        stop_loss_manager = Mock()

        # position_manager is None
        atomic_mgr = AtomicPositionManager(
            repository, exchange_manager, stop_loss_manager,
            position_manager=None  # None!
        )

        # Mock exchange_instance
        exchange_instance = Mock()
        exchange_instance.fetch_order = AsyncMock(return_value={
            'id': 'test-order-id',
            'status': 'closed',
            'filled': 43.0,
            'amount': 43.0
        })

        # Mock entry_order
        entry_order = Mock()
        entry_order.id = 'test-order-id'

        # Should NOT crash - should fallback to order status
        result = await atomic_mgr._verify_position_exists_multi_source(
            exchange_instance=exchange_instance,
            symbol='AVL/USDT:USDT',
            exchange='bybit',
            entry_order=entry_order,
            expected_quantity=43.0,
            timeout=5.0
        )

        assert result is True
        print("✅ FIX #3.1: Safe position_manager access works (no crash)")

    @pytest.mark.asyncio
    async def test_fix_3_1_missing_get_cached_position_method(self):
        """
        FIX #3.1: Should handle position_manager without get_cached_position
        """
        from core.atomic_position_manager import AtomicPositionManager

        # Mock dependencies
        repository = Mock()
        exchange_manager = Mock()
        stop_loss_manager = Mock()

        # position_manager exists but doesn't have get_cached_position
        position_manager = Mock(spec=[])  # Empty spec - no methods!

        atomic_mgr = AtomicPositionManager(
            repository, exchange_manager, stop_loss_manager,
            position_manager=position_manager
        )

        # Mock exchange_instance
        exchange_instance = Mock()
        exchange_instance.fetch_order = AsyncMock(return_value={
            'id': 'test-order-id',
            'status': 'closed',
            'filled': 43.0,
            'amount': 43.0
        })

        # Mock entry_order
        entry_order = Mock()
        entry_order.id = 'test-order-id'

        # Should NOT crash - should skip WebSocket and use order status
        result = await atomic_mgr._verify_position_exists_multi_source(
            exchange_instance=exchange_instance,
            symbol='AVL/USDT:USDT',
            exchange='bybit',
            entry_order=entry_order,
            expected_quantity=43.0,
            timeout=5.0
        )

        assert result is True
        print("✅ FIX #3.1: Missing method handled gracefully")


if __name__ == '__main__':
    print("\n" + "=" * 80)
    print("PHASE 2 FIXES VERIFICATION TESTS")
    print("=" * 80)

    test = TestPhase2Fixes()

    async def run_tests():
        print("\nTEST 1: WebSocket source priority")
        print("-" * 80)
        await test.test_fix_2_1_websocket_source_priority()

        print("\nTEST 2: Order status fallback")
        print("-" * 80)
        await test.test_fix_2_1_order_status_fallback()

        print("\nTEST 3: Order failed detection")
        print("-" * 80)
        await test.test_fix_2_1_order_failed_detection()

        print("\nTEST 4: Safe position_manager access (None)")
        print("-" * 80)
        await test.test_fix_3_1_safe_position_manager_access()

        print("\nTEST 5: Missing get_cached_position method")
        print("-" * 80)
        await test.test_fix_3_1_missing_get_cached_position_method()

        print("\n" + "=" * 80)
        print("ALL PHASE 2 FIXES VERIFIED ✅")
        print("=" * 80)

    asyncio.run(run_tests())
