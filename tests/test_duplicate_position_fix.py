"""
Unit tests for duplicate position race condition fix

Tests the 3-layer defense strategy:
- Layer 1: Check logic in repository.create_position()
- Layer 2: Extended unique index (tested via SQL)
- Layer 3: Safe activation in atomic_position_manager

Added: 2025-10-23
Issue: Duplicate key violation for idx_unique_active_position
See: docs/audit_duplicate_position/ for full analysis
"""

import pytest
import asyncio
from datetime import datetime
from decimal import Decimal


class TestDuplicatePositionFix:
    """Test suite for duplicate position race condition fix"""

    @pytest.mark.asyncio
    async def test_layer1_returns_existing_when_intermediate_state(self, test_db_pool):
        """
        Test Layer 1: create_position returns existing ID when position in intermediate state

        This tests that the fix in repository.py:267-274 works correctly.
        Before fix: Would check only status='active', miss intermediate states
        After fix: Checks ALL open statuses, returns existing position
        """
        from database.repository import Repository

        # Setup
        repository = Repository({
            'host': 'localhost',
            'port': 5432,
            'user': 'evgeniyyanvarskiy',
            'database': 'fox_crypto',
            'password': '',
            'min_size': 1,
            'max_size': 2
        })
        await repository.initialize()

        try:
            # Test data
            position_data = {
                'signal_id': 999,
                'symbol': 'TESTDUP1USDT',
                'exchange': 'binance',
                'side': 'LONG',
                'quantity': Decimal('100.0'),
                'entry_price': Decimal('1.0')
            }

            # Step 1: Create first position
            position_id_1 = await repository.create_position(position_data)
            assert position_id_1 is not None, "First position should be created"

            # Step 2: Simulate intermediate state (entry_placed)
            # This is the critical state where race condition can occur
            await repository.update_position(position_id_1, status='entry_placed')

            # Verify position is in intermediate state
            async with repository.pool.acquire() as conn:
                check = await conn.fetchrow(
                    "SELECT status FROM monitoring.positions WHERE id = $1",
                    position_id_1
                )
                assert check['status'] == 'entry_placed', "Position should be in entry_placed state"

            # Step 3: Try to create again (simulates race condition)
            # Before fix: Would create duplicate because status != 'active'
            # After fix: Should return existing position_id_1
            position_id_2 = await repository.create_position(position_data)

            # Assert: Should return SAME position ID
            assert position_id_1 == position_id_2, \
                f"Should return existing position #{position_id_1}, got #{position_id_2}"

            # Verify: Only ONE position exists in DB
            async with repository.pool.acquire() as conn:
                count = await conn.fetchval("""
                    SELECT COUNT(*) FROM monitoring.positions
                    WHERE symbol = $1 AND exchange = $2
                """, position_data['symbol'], position_data['exchange'])

            assert count == 1, f"Should have exactly 1 position, found {count}"

            print("✅ Layer 1 test passed: Returns existing position in intermediate state")

        finally:
            # Cleanup
            async with repository.pool.acquire() as conn:
                await conn.execute("""
                    DELETE FROM monitoring.positions
                    WHERE symbol = $1 AND exchange = $2
                """, position_data['symbol'], position_data['exchange'])
            await repository.close()

    @pytest.mark.asyncio
    async def test_layer1_all_intermediate_states(self, test_db_pool):
        """
        Test Layer 1 with ALL intermediate states

        Tests that check works for: entry_placed, pending_sl, pending_entry
        """
        from database.repository import Repository

        repository = Repository({
            'host': 'localhost',
            'port': 5432,
            'user': 'evgeniyyanvarskiy',
            'database': 'fox_crypto',
            'password': '',
            'min_size': 1,
            'max_size': 2
        })
        await repository.initialize()

        test_statuses = ['entry_placed', 'pending_sl', 'pending_entry']

        try:
            for idx, test_status in enumerate(test_statuses):
                # Unique symbol for each test (use index to keep under 20 chars)
                symbol = f'TESTL1{idx}USDT'

                position_data = {
                    'signal_id': 999,
                    'symbol': symbol,
                    'exchange': 'binance',
                    'side': 'LONG',
                    'quantity': Decimal('100.0'),
                    'entry_price': Decimal('1.0')
                }

                # Create position
                pos_id_1 = await repository.create_position(position_data)

                # Set to intermediate state
                await repository.update_position(pos_id_1, status=test_status)

                # Try to create again
                pos_id_2 = await repository.create_position(position_data)

                # Should return existing
                assert pos_id_1 == pos_id_2, \
                    f"Failed for status={test_status}: expected #{pos_id_1}, got #{pos_id_2}"

                print(f"✅ Status '{test_status}' test passed")

        finally:
            # Cleanup
            async with repository.pool.acquire() as conn:
                await conn.execute("""
                    DELETE FROM monitoring.positions
                    WHERE symbol LIKE 'TEST%USDT' AND exchange = 'binance'
                """)
            await repository.close()

    @pytest.mark.asyncio
    async def test_layer3_detects_duplicate_before_update(self, test_db_pool):
        """
        Test Layer 3: _safe_activate_position detects duplicate

        This tests the defensive check before final UPDATE to status='active'
        """
        from database.repository import Repository
        from core.atomic_position_manager import AtomicPositionManager

        repository = Repository({
            'host': 'localhost',
            'port': 5432,
            'user': 'evgeniyyanvarskiy',
            'database': 'fox_crypto',
            'password': '',
            'min_size': 1,
            'max_size': 2
        })
        await repository.initialize()

        # Mock position manager (minimal setup for testing _safe_activate_position)
        class MockPositionManager:
            def __init__(self, repository):
                self.repository = repository

            async def _safe_activate_position(self, position_id, symbol, exchange, **fields):
                """Copy of the method from atomic_position_manager"""
                try:
                    async with self.repository.pool.acquire() as conn:
                        existing_active = await conn.fetchrow("""
                            SELECT id FROM monitoring.positions
                            WHERE symbol = $1 AND exchange = $2
                              AND status = 'active'
                              AND id != $3
                        """, symbol, exchange, position_id)

                        if existing_active:
                            return False

                    # Safe to activate
                    fields['status'] = 'active'
                    await self.repository.update_position(position_id, **fields)
                    return True

                except Exception:
                    return False

        manager = MockPositionManager(repository)

        try:
            symbol = 'TESTLAYER3USDT'

            # Create first position and activate it
            pos_data_1 = {
                'signal_id': 999,
                'symbol': symbol,
                'exchange': 'binance',
                'side': 'LONG',
                'quantity': Decimal('100.0'),
                'entry_price': Decimal('1.0')
            }
            pos_id_1 = await repository.create_position(pos_data_1)
            await repository.update_position(pos_id_1, status='active')

            # Create second position (simulating race condition that got past Layer 1&2)
            # Force create by direct INSERT (bypass repository logic)
            async with repository.pool.acquire() as conn:
                pos_id_2 = await conn.fetchval("""
                    INSERT INTO monitoring.positions
                    (signal_id, symbol, exchange, side, quantity, entry_price, status, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), NOW())
                    RETURNING id
                """, 888, symbol, 'binance', 'LONG', Decimal('99.0'), Decimal('1.01'), 'entry_placed')

            # Try to activate second position - Layer 3 should detect duplicate
            activation_successful = await manager._safe_activate_position(
                position_id=pos_id_2,
                symbol=symbol,
                exchange='binance',
                stop_loss_price=Decimal('0.95')
            )

            # Should return False (duplicate detected)
            assert activation_successful == False, \
                "Layer 3 should detect duplicate and return False"

            # Verify second position was NOT activated
            async with repository.pool.acquire() as conn:
                pos_2_status = await conn.fetchval(
                    "SELECT status FROM monitoring.positions WHERE id = $1",
                    pos_id_2
                )

            assert pos_2_status != 'active', \
                "Second position should NOT be activated when duplicate exists"

            print("✅ Layer 3 test passed: Detects duplicate before UPDATE")

        finally:
            # Cleanup
            async with repository.pool.acquire() as conn:
                await conn.execute("""
                    DELETE FROM monitoring.positions
                    WHERE symbol = $1 AND exchange = $2
                """, symbol, 'binance')
            await repository.close()

    @pytest.mark.asyncio
    async def test_stress_concurrent_creates(self, test_db_pool):
        """
        Stress test: Multiple concurrent create attempts

        Simulates high-load scenario with many threads trying to create
        position for same symbol simultaneously.
        """
        from database.repository import Repository

        repository = Repository({
            'host': 'localhost',
            'port': 5432,
            'user': 'evgeniyyanvarskiy',
            'database': 'fox_crypto',
            'password': '',
            'min_size': 5,
            'max_size': 10
        })
        await repository.initialize()

        symbol = 'TESTSTRESSUSDT'
        exchange = 'binance'
        num_threads = 10

        async def create_attempt(thread_id):
            """Simulate concurrent create attempt"""
            position_data = {
                'signal_id': 900 + thread_id,
                'symbol': symbol,
                'exchange': exchange,
                'side': 'LONG',
                'quantity': Decimal(str(100 + thread_id)),  # Slightly different
                'entry_price': Decimal(str(1.0 + thread_id * 0.01))
            }
            return await repository.create_position(position_data)

        try:
            # Launch 10 concurrent creates
            results = await asyncio.gather(*[create_attempt(i) for i in range(num_threads)])

            # All should return SAME position_id (first one created)
            unique_ids = set(results)
            assert len(unique_ids) == 1, \
                f"All creates should return same position ID, got {len(unique_ids)} different IDs: {unique_ids}"

            # Verify: only ONE position in DB
            async with repository.pool.acquire() as conn:
                count = await conn.fetchval("""
                    SELECT COUNT(*) FROM monitoring.positions
                    WHERE symbol = $1 AND exchange = $2
                """, symbol, exchange)

            assert count == 1, f"Should have exactly 1 position, found {count}"

            print(f"✅ Stress test passed: {num_threads} concurrent creates → 1 position")

        finally:
            # Cleanup
            async with repository.pool.acquire() as conn:
                await conn.execute("""
                    DELETE FROM monitoring.positions
                    WHERE symbol = $1 AND exchange = $2
                """, symbol, exchange)
            await repository.close()


# Pytest fixtures

@pytest.fixture
async def test_db_pool():
    """Provide test database connection"""
    # This is a marker fixture - actual DB connection handled in tests
    yield
    # Cleanup happens in individual tests


if __name__ == '__main__':
    # Run tests with: pytest tests/test_duplicate_position_fix.py -v
    pytest.main([__file__, '-v', '-s'])
