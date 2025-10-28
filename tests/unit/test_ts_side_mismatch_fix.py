"""
Unit test for TS side mismatch fix

Tests that save_trailing_stop_state() correctly updates all fields
including side, entry_price, quantity on CONFLICT.

Regression test for CRITICAL bug found 2025-10-28.
See: docs/investigations/CRITICAL_TS_SIDE_MISMATCH_ROOT_CAUSE_20251028.md
"""
import pytest
import asyncpg
from decimal import Decimal
from database.repository import Repository
from config.settings import config


@pytest.mark.asyncio
async def test_save_trailing_stop_state_updates_side_on_conflict():
    """
    Test that ON CONFLICT DO UPDATE correctly updates side field

    Scenario: Fast position reopen (SHORT → LONG)
    Expected: side updated from 'short' to 'long'
    """
    # Setup
    pool = await asyncpg.create_pool(
        host=config.database.host,
        port=config.database.port,
        database=config.database.database,
        user=config.database.user,
        password=config.database.password,
        min_size=1,
        max_size=2
    )

    repo = Repository(pool)

    symbol = "TESTUSDT"
    exchange = "binance"

    try:
        # STEP 1: Create initial SHORT position TS state
        state_short = {
            'symbol': symbol,
            'exchange': exchange,
            'position_id': 1,
            'state': 'waiting',
            'is_activated': False,
            'highest_price': Decimal('100'),
            'lowest_price': Decimal('98'),
            'current_stop_price': Decimal('96'),
            'stop_order_id': 'order_123',
            'activation_price': Decimal('102'),
            'activation_percent': Decimal('2.0'),
            'callback_percent': Decimal('0.5'),
            'entry_price': Decimal('100'),
            'side': 'short',  # ← SHORT
            'quantity': Decimal('10'),
            'update_count': 0,
            'highest_profit_percent': Decimal('0'),
            'activated_at': None,
            'last_update_time': None,
            'last_sl_update_time': None,
            'last_updated_sl_price': None,
            'last_peak_save_time': None,
            'last_saved_peak_price': None,
            'created_at': None
        }

        result = await repo.save_trailing_stop_state(state_short)
        assert result is True, "Initial save should succeed"

        # Verify SHORT state saved
        db_state = await repo.get_trailing_stop_state(symbol, exchange)
        assert db_state is not None
        assert db_state['side'] == 'short'
        assert float(db_state['entry_price']) == 100.0
        assert db_state['position_id'] == 1

        # STEP 2: Save LONG position TS state (same symbol, exchange)
        # This triggers ON CONFLICT
        state_long = state_short.copy()
        state_long.update({
            'position_id': 2,  # ← NEW position
            'entry_price': Decimal('105'),  # ← NEW entry price
            'side': 'long',  # ← LONG (opposite side)
            'quantity': Decimal('15'),  # ← NEW quantity
            'activation_price': Decimal('107.1'),
            'activation_percent': Decimal('2.5'),  # ← NEW
            'callback_percent': Decimal('0.7'),  # ← NEW
        })

        result = await repo.save_trailing_stop_state(state_long)
        assert result is True, "Update on conflict should succeed"

        # STEP 3: Verify ALL fields updated (including side, entry_price, quantity)
        db_state = await repo.get_trailing_stop_state(symbol, exchange)
        assert db_state is not None

        # CRITICAL CHECKS:
        assert db_state['side'] == 'long', "❌ SIDE NOT UPDATED! Bug still exists!"
        assert float(db_state['entry_price']) == 105.0, "❌ ENTRY_PRICE NOT UPDATED!"
        assert float(db_state['quantity']) == 15.0, "❌ QUANTITY NOT UPDATED!"
        assert float(db_state['activation_percent']) == 2.5, "❌ ACTIVATION_PERCENT NOT UPDATED!"
        assert float(db_state['callback_percent']) == 0.7, "❌ CALLBACK_PERCENT NOT UPDATED!"

        # Other fields should also update
        assert db_state['position_id'] == 2, "position_id should update"

        print("✅ Test PASSED: All fields updated correctly on conflict")

    finally:
        # Cleanup
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM monitoring.trailing_stop_state WHERE symbol = $1 AND exchange = $2",
                symbol, exchange
            )
        await pool.close()


@pytest.mark.asyncio
async def test_save_trailing_stop_state_same_side_update():
    """
    Test that ON CONFLICT DO UPDATE works for same-side reopens

    Scenario: LONG → LONG (update, not conflict)
    Expected: entry_price, quantity updated
    """
    # Setup
    pool = await asyncpg.create_pool(
        host=config.database.host,
        port=config.database.port,
        database=config.database.database,
        user=config.database.user,
        password=config.database.password,
        min_size=1,
        max_size=2
    )

    repo = Repository(pool)

    symbol = "TESTUSDT2"
    exchange = "bybit"

    try:
        # STEP 1: Create initial LONG position
        state_long_1 = {
            'symbol': symbol,
            'exchange': exchange,
            'position_id': 10,
            'state': 'waiting',
            'is_activated': False,
            'highest_price': Decimal('200'),
            'lowest_price': Decimal('198'),
            'current_stop_price': Decimal('196'),
            'stop_order_id': 'order_456',
            'activation_price': Decimal('204'),
            'activation_percent': Decimal('2.0'),
            'callback_percent': Decimal('0.5'),
            'entry_price': Decimal('200'),
            'side': 'long',
            'quantity': Decimal('5'),
            'update_count': 0,
            'highest_profit_percent': Decimal('0'),
            'activated_at': None,
            'last_update_time': None,
            'last_sl_update_time': None,
            'last_updated_sl_price': None,
            'last_peak_save_time': None,
            'last_saved_peak_price': None,
            'created_at': None
        }

        result = await repo.save_trailing_stop_state(state_long_1)
        assert result is True

        # STEP 2: Reopen LONG position (same side, different entry)
        state_long_2 = state_long_1.copy()
        state_long_2.update({
            'position_id': 11,
            'entry_price': Decimal('210'),  # ← NEW entry
            'quantity': Decimal('8'),  # ← NEW quantity
            'activation_price': Decimal('214.2'),
        })

        result = await repo.save_trailing_stop_state(state_long_2)
        assert result is True

        # STEP 3: Verify fields updated
        db_state = await repo.get_trailing_stop_state(symbol, exchange)
        assert db_state is not None
        assert db_state['side'] == 'long'
        assert float(db_state['entry_price']) == 210.0
        assert float(db_state['quantity']) == 8.0
        assert db_state['position_id'] == 11

        print("✅ Test PASSED: Same-side reopen updates correctly")

    finally:
        # Cleanup
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM monitoring.trailing_stop_state WHERE symbol = $1 AND exchange = $2",
                symbol, exchange
            )
        await pool.close()


if __name__ == "__main__":
    import asyncio

    async def main():
        print("Running TS side mismatch fix tests...")
        await test_save_trailing_stop_state_updates_side_on_conflict()
        await test_save_trailing_stop_state_same_side_update()
        print("\n✅ ALL TESTS PASSED")

    asyncio.run(main())
