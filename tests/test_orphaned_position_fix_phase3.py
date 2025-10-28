"""
Test Phase 3 Monitoring Features

Verifies that:
1. Orphaned Position Monitor detects orphans correctly
2. Position Reconciliation detects mismatches correctly
"""

import pytest
from unittest.mock import Mock, AsyncMock
import asyncio
from datetime import datetime, timezone


class TestPhase3Monitoring:
    """
    Test that Phase 3 monitoring features work correctly.
    """

    @pytest.mark.asyncio
    async def test_orphaned_position_detection(self):
        """
        Test that orphaned position monitor detects positions on exchange but not in DB.
        """
        from core.orphaned_position_monitor import OrphanedPositionMonitor

        # Mock repository (symbols are normalized in DB)
        repository = Mock()
        repository.get_active_positions = AsyncMock(return_value=[
            {'symbol': 'BTCUSDT', 'quantity': 1.0}
            # AVLUSDT not in DB!
        ])

        # Mock exchange_instance
        exchange_instance = Mock()
        exchange_instance.exchange = Mock()
        exchange_instance.exchange.fetch_positions = AsyncMock(return_value=[
            {
                'symbol': 'BTC/USDT:USDT',
                'contracts': 1.0,
                'side': 'long',
                'entryPrice': 50000.0,
                'markPrice': 51000.0,
                'unrealizedPnl': 1000.0,
                'leverage': 1
            },
            {
                'symbol': 'AVL/USDT:USDT',  # ORPHAN!
                'contracts': 86.0,
                'side': 'long',
                'entryPrice': 0.1358,
                'markPrice': 0.1360,
                'unrealized_pnl': 1.72,
                'leverage': 1
            }
        ])

        exchange_managers = {'bybit': exchange_instance}

        # Create monitor
        monitor = OrphanedPositionMonitor(
            repository=repository,
            exchange_managers=exchange_managers,
            position_manager=None,
            alert_callback=None
        )

        # Scan for orphans
        orphans = await monitor._scan_exchange('bybit', exchange_instance)

        # Should detect AVLUSDT as orphan
        assert len(orphans) == 1
        assert orphans[0]['symbol'] == 'AVLUSDT'
        assert orphans[0]['contracts'] == 86.0
        print("✅ Orphaned position detection works correctly")

    @pytest.mark.asyncio
    async def test_no_orphans_when_all_tracked(self):
        """
        Test that monitor finds no orphans when all positions are tracked.
        """
        from core.orphaned_position_monitor import OrphanedPositionMonitor

        # Mock repository - all positions tracked (normalized symbols)
        repository = Mock()
        repository.get_active_positions = AsyncMock(return_value=[
            {'symbol': 'BTCUSDT', 'quantity': 1.0},
            {'symbol': 'ETHUSDT', 'quantity': 10.0}
        ])

        # Mock exchange - same positions
        exchange_instance = Mock()
        exchange_instance.exchange = Mock()
        exchange_instance.exchange.fetch_positions = AsyncMock(return_value=[
            {
                'symbol': 'BTC/USDT:USDT',
                'contracts': 1.0,
                'side': 'long',
                'entryPrice': 50000.0,
                'markPrice': 51000.0,
                'unrealizedPnl': 1000.0,
                'leverage': 1
            },
            {
                'symbol': 'ETH/USDT:USDT',
                'contracts': 10.0,
                'side': 'long',
                'entryPrice': 3000.0,
                'markPrice': 3100.0,
                'unrealizedPnl': 1000.0,
                'leverage': 1
            }
        ])

        exchange_managers = {'bybit': exchange_instance}

        monitor = OrphanedPositionMonitor(
            repository=repository,
            exchange_managers=exchange_managers,
            position_manager=None,
            alert_callback=None
        )

        # Scan for orphans
        orphans = await monitor._scan_exchange('bybit', exchange_instance)

        # Should find no orphans
        assert len(orphans) == 0
        print("✅ No false positives when all positions tracked")

    @pytest.mark.asyncio
    async def test_reconciliation_missing_on_exchange(self):
        """
        Test that reconciliation detects positions in DB but not on exchange.
        """
        from core.position_reconciliation import PositionReconciliation

        # Mock repository - position in DB (normalized symbol)
        repository = Mock()
        repository.get_active_positions = AsyncMock(return_value=[
            {
                'id': 123,
                'symbol': 'BTCUSDT',
                'quantity': 1.0,
                'side': 'long'
            }
        ])
        repository.update_position = AsyncMock()

        # Mock exchange - position NOT on exchange
        exchange_instance = Mock()
        exchange_instance.exchange = Mock()
        exchange_instance.exchange.fetch_positions = AsyncMock(return_value=[])

        exchange_managers = {'bybit': exchange_instance}

        # Create reconciliation
        reconciliation = PositionReconciliation(
            repository=repository,
            exchange_managers=exchange_managers,
            position_manager=None,
            alert_callback=None
        )

        # Reconcile
        mismatches = await reconciliation._reconcile_exchange('bybit', exchange_instance)

        # Should detect mismatch
        assert len(mismatches) == 1
        assert mismatches[0]['type'] == 'missing_on_exchange'
        assert mismatches[0]['symbol'] == 'BTCUSDT'

        # Should auto-fix by marking as closed
        repository.update_position.assert_called_once()
        print("✅ Reconciliation detects missing positions on exchange")

    @pytest.mark.asyncio
    async def test_reconciliation_quantity_mismatch(self):
        """
        Test that reconciliation detects quantity mismatches.
        """
        from core.position_reconciliation import PositionReconciliation

        # Mock repository - position with quantity 1.0 (normalized symbol)
        repository = Mock()
        repository.get_active_positions = AsyncMock(return_value=[
            {
                'id': 123,
                'symbol': 'BTCUSDT',
                'quantity': 1.0,  # DB says 1.0
                'side': 'long'
            }
        ])

        # Mock exchange - position with quantity 0.5 (mismatch!)
        exchange_instance = Mock()
        exchange_instance.exchange = Mock()
        exchange_instance.exchange.fetch_positions = AsyncMock(return_value=[
            {
                'symbol': 'BTC/USDT:USDT',
                'contracts': 0.5,  # Exchange says 0.5!
                'side': 'long',
                'entryPrice': 50000.0
            }
        ])

        exchange_managers = {'bybit': exchange_instance}

        reconciliation = PositionReconciliation(
            repository=repository,
            exchange_managers=exchange_managers,
            position_manager=None,
            alert_callback=None
        )

        # Reconcile
        mismatches = await reconciliation._reconcile_exchange('bybit', exchange_instance)

        # Should detect quantity mismatch
        assert len(mismatches) == 1
        assert mismatches[0]['type'] == 'quantity_mismatch'
        assert mismatches[0]['db_quantity'] == 1.0
        assert mismatches[0]['exchange_quantity'] == 0.5
        print("✅ Reconciliation detects quantity mismatches")

    @pytest.mark.asyncio
    async def test_reconciliation_no_mismatches(self):
        """
        Test that reconciliation finds no issues when everything matches.
        """
        from core.position_reconciliation import PositionReconciliation

        # Mock repository (normalized symbol)
        repository = Mock()
        repository.get_active_positions = AsyncMock(return_value=[
            {
                'id': 123,
                'symbol': 'BTCUSDT',
                'quantity': 1.0,
                'side': 'long'
            }
        ])

        # Mock exchange - matching position
        exchange_instance = Mock()
        exchange_instance.exchange = Mock()
        exchange_instance.exchange.fetch_positions = AsyncMock(return_value=[
            {
                'symbol': 'BTC/USDT:USDT',
                'contracts': 1.0,  # Perfect match!
                'side': 'long',
                'entryPrice': 50000.0
            }
        ])

        exchange_managers = {'bybit': exchange_instance}

        reconciliation = PositionReconciliation(
            repository=repository,
            exchange_managers=exchange_managers,
            position_manager=None,
            alert_callback=None
        )

        # Reconcile
        mismatches = await reconciliation._reconcile_exchange('bybit', exchange_instance)

        # Should find no mismatches
        assert len(mismatches) == 0
        print("✅ No false positives when everything matches")


if __name__ == '__main__':
    print("\n" + "=" * 80)
    print("PHASE 3 MONITORING FEATURES VERIFICATION TESTS")
    print("=" * 80)

    test = TestPhase3Monitoring()

    async def run_tests():
        print("\nTEST 1: Orphaned position detection")
        print("-" * 80)
        await test.test_orphaned_position_detection()

        print("\nTEST 2: No false positives for orphans")
        print("-" * 80)
        await test.test_no_orphans_when_all_tracked()

        print("\nTEST 3: Reconciliation - missing on exchange")
        print("-" * 80)
        await test.test_reconciliation_missing_on_exchange()

        print("\nTEST 4: Reconciliation - quantity mismatch")
        print("-" * 80)
        await test.test_reconciliation_quantity_mismatch()

        print("\nTEST 5: Reconciliation - no false positives")
        print("-" * 80)
        await test.test_reconciliation_no_mismatches()

        print("\n" + "=" * 80)
        print("ALL PHASE 3 MONITORING TESTS VERIFIED ✅")
        print("=" * 80)

    asyncio.run(run_tests())
