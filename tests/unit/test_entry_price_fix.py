"""
Unit test for entry_price fix (CRVUSDT bug)

Tests that position is created with REAL execution price, not signal price.

Regression test for bug found 2025-10-28.
See: docs/investigations/CRVUSDT_SL_INCORRECT_ROOT_CAUSE_20251028.md
"""
import pytest
import asyncpg
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from database.repository import Repository
from core.atomic_position_manager import AtomicPositionManager
from config.settings import config


@pytest.mark.asyncio
async def test_position_created_with_execution_price_not_signal():
    """
    Test that position is created with REAL execution price from exchange.

    Scenario:
    - Signal price: 0.556
    - Execution price from exchange: 0.557 (different!)
    - Expected: DB entry_price = 0.557 (execution)
    - Expected: SL calculated from 0.557
    """
    # Setup DB connection
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

    symbol = "TESTENTRYFIX"
    exchange = "binance"
    signal_price = 0.556
    execution_price = 0.557  # Different from signal!
    quantity = 10.0
    stop_loss_percent = 5.0

    try:
        # Mock exchange instance
        mock_exchange = MagicMock()
        mock_exchange.set_leverage = AsyncMock(return_value=True)

        # Mock order response with execution price
        mock_order = MagicMock()
        mock_order.id = "test_order_12345"
        mock_order.status = "closed"
        mock_order.filled = quantity
        mock_order.amount = quantity
        mock_order.price = execution_price  # avgPrice from exchange
        mock_order.side = "buy"
        mock_order.raw_data = {"orderId": "test_order_12345"}
        mock_order.fee = 0.001
        mock_order.feeCurrency = "USDT"

        mock_exchange.create_market_order = AsyncMock(return_value=mock_order)
        mock_exchange.fetch_order = AsyncMock(return_value=mock_order)
        mock_exchange.fetch_positions = AsyncMock(return_value=[
            {
                'symbol': symbol,
                'contracts': quantity,
                'entryPrice': execution_price,
                'side': 'long'
            }
        ])

        # Mock stop loss manager
        mock_sl_manager = MagicMock()
        mock_sl_manager.set_stop_loss = AsyncMock(return_value={
            'status': 'created',
            'orderId': 'sl_order_123',
            'orderType': 'STOP_MARKET'
        })

        # Create atomic manager with mocks
        exchange_manager = {exchange: mock_exchange}

        # Mock config with required attributes
        mock_config = MagicMock()
        mock_config.auto_set_leverage = False  # Disable leverage setting in tests
        mock_config.trading = MagicMock()
        mock_config.trading.trailing_activation_percent = 2.0
        mock_config.trading.trailing_callback_percent = 0.5

        atomic_mgr = AtomicPositionManager(
            repository=repo,
            exchange_manager=exchange_manager,
            stop_loss_manager=mock_sl_manager,
            config=mock_config
        )

        # Mock get_params_by_exchange_name to return None (use fallback from config)
        async def mock_get_params(exchange_name):
            return None

        repo.get_params_by_exchange_name = mock_get_params

        # Mock duplicate check
        async def mock_check_duplicate(symbol, exchange):
            return False

        atomic_mgr._check_duplicate_position = mock_check_duplicate

        # Mock safe activate
        async def mock_activate(position_id, symbol, exchange, stop_loss_price):
            await repo.update_position(position_id, status='active')
            return True

        atomic_mgr._safe_activate_position = mock_activate

        # EXECUTE: Open position with SIGNAL price
        result = await atomic_mgr.open_position_atomic(
            signal_id=99999,
            symbol=symbol,
            exchange=exchange,
            side='buy',
            quantity=quantity,
            entry_price=signal_price,  # ← Signal price (0.556)
            stop_loss_percent=stop_loss_percent
        )

        assert result is not None, "Position creation should succeed"
        position_id = result['position_id']

        # VERIFY #1: Position in DB has EXECUTION price, not signal price
        pos = await repo.get_position(position_id)
        assert pos is not None

        db_entry_price = float(pos['entry_price'])
        print(f"\n📊 Signal price: {signal_price}")
        print(f"📊 Execution price: {execution_price}")
        print(f"📊 DB entry_price: {db_entry_price}")

        # CRITICAL CHECK: DB must have execution price, NOT signal price
        assert abs(db_entry_price - execution_price) < 0.0001, \
            f"❌ DB entry_price ({db_entry_price}) != execution price ({execution_price})! " \
            f"Position was created with signal price instead of real execution price."

        assert abs(db_entry_price - signal_price) > 0.0001, \
            f"❌ DB entry_price ({db_entry_price}) == signal price ({signal_price})! " \
            f"Bug not fixed - still using signal price."

        print(f"✅ DB entry_price correctly set to execution price: {db_entry_price}")

        # VERIFY #2: Stop-loss calculated from EXECUTION price
        db_sl = float(pos['stop_loss_price'])
        expected_sl = execution_price * (1 - stop_loss_percent / 100)

        print(f"📊 DB stop_loss: {db_sl}")
        print(f"📊 Expected SL (5% from {execution_price}): {expected_sl}")

        sl_diff_pct = abs(db_sl - expected_sl) / expected_sl * 100
        assert sl_diff_pct < 0.1, \
            f"❌ SL not calculated from execution price! " \
            f"Expected {expected_sl}, got {db_sl} (diff {sl_diff_pct:.2f}%)"

        print(f"✅ Stop-loss correctly calculated from execution price")

        # VERIFY #3: Returned entry_price is execution price
        assert abs(result['entry_price'] - execution_price) < 0.0001, \
            f"❌ Returned entry_price != execution price"

        print(f"✅ Returned entry_price correct: {result['entry_price']}")

        print("\n✅ TEST PASSED: Position created with execution price, not signal price")

    finally:
        # Cleanup
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM monitoring.positions WHERE symbol = $1 AND exchange = $2",
                symbol, exchange
            )
        await pool.close()


@pytest.mark.asyncio
async def test_stop_loss_percentage_correct_with_execution_price():
    """
    Test that SL percentage is exactly correct when calculated from execution price.

    Scenario (from CRVUSDT bug):
    - Signal: 0.556
    - Execution: 0.557
    - SL should be: 0.557 * 0.95 = 0.52915 (5% from execution)
    - NOT: 0.556 * 0.95 = 0.5282 (5% from signal)
    """
    # Setup DB connection
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

    symbol = "TESTSLPCT"
    exchange = "binance"
    signal_price = 0.556
    execution_price = 0.557
    quantity = 10.0
    stop_loss_percent = 5.0

    try:
        # Mock exchange
        mock_exchange = MagicMock()
        mock_exchange.set_leverage = AsyncMock(return_value=True)

        mock_order = MagicMock()
        mock_order.id = "test_order_sl"
        mock_order.status = "closed"
        mock_order.filled = quantity
        mock_order.amount = quantity
        mock_order.price = execution_price
        mock_order.side = "buy"
        mock_order.raw_data = {"orderId": "test_order_sl"}
        mock_order.fee = 0.001
        mock_order.feeCurrency = "USDT"

        mock_exchange.create_market_order = AsyncMock(return_value=mock_order)
        mock_exchange.fetch_order = AsyncMock(return_value=mock_order)
        mock_exchange.fetch_positions = AsyncMock(return_value=[
            {
                'symbol': symbol,
                'contracts': quantity,
                'entryPrice': execution_price
            }
        ])

        mock_sl_manager = MagicMock()
        mock_sl_manager.set_stop_loss = AsyncMock(return_value={
            'status': 'created',
            'orderId': 'sl_123'
        })

        exchange_manager = {exchange: mock_exchange}

        # Mock config with required attributes
        mock_config = MagicMock()
        mock_config.auto_set_leverage = False  # Disable leverage setting in tests
        mock_config.trading = MagicMock()
        mock_config.trading.trailing_activation_percent = 2.0
        mock_config.trading.trailing_callback_percent = 0.5

        atomic_mgr = AtomicPositionManager(
            repository=repo,
            exchange_manager=exchange_manager,
            stop_loss_manager=mock_sl_manager,
            config=mock_config
        )

        # Mock get_params_by_exchange_name to return None (use fallback from config)
        async def mock_get_params(exchange_name):
            return None

        repo.get_params_by_exchange_name = mock_get_params

        async def mock_check_duplicate(symbol, exchange):
            return False

        atomic_mgr._check_duplicate_position = mock_check_duplicate

        async def mock_activate(position_id, symbol, exchange, stop_loss_price):
            await repo.update_position(position_id, status='active')
            return True

        atomic_mgr._safe_activate_position = mock_activate

        # Open position
        result = await atomic_mgr.open_position_atomic(
            signal_id=99998,
            symbol=symbol,
            exchange=exchange,
            side='buy',
            quantity=quantity,
            entry_price=signal_price,
            stop_loss_percent=stop_loss_percent
        )

        position_id = result['position_id']
        pos = await repo.get_position(position_id)

        # Calculate expected SL from EXECUTION price
        expected_sl_from_exec = execution_price * (1 - stop_loss_percent / 100)

        # Calculate what SL would be if calculated from SIGNAL price (WRONG)
        wrong_sl_from_signal = signal_price * (1 - stop_loss_percent / 100)

        db_entry = float(pos['entry_price'])
        db_sl = float(pos['stop_loss_price'])

        print(f"\n📊 Signal price: {signal_price}")
        print(f"📊 Execution price: {execution_price}")
        print(f"📊 DB entry_price: {db_entry}")
        print(f"📊 DB stop_loss: {db_sl}")
        print(f"📊 Expected SL (from exec {execution_price}): {expected_sl_from_exec}")
        print(f"📊 WRONG SL (from signal {signal_price}): {wrong_sl_from_signal}")

        # Verify SL matches execution-based calculation
        assert abs(db_sl - expected_sl_from_exec) < 0.0001, \
            f"❌ SL calculated from WRONG price! Expected {expected_sl_from_exec}, got {db_sl}"

        # Verify SL does NOT match signal-based calculation
        assert abs(db_sl - wrong_sl_from_signal) > 0.0001, \
            f"❌ SL calculated from signal price! Should be from execution price."

        # Verify SL percentage from entry_price
        actual_sl_pct = (db_entry - db_sl) / db_entry * 100
        print(f"📊 Actual SL %: {actual_sl_pct:.2f}%")

        assert abs(actual_sl_pct - stop_loss_percent) < 0.01, \
            f"❌ SL percentage incorrect! Expected {stop_loss_percent}%, got {actual_sl_pct:.2f}%"

        print(f"✅ SL percentage exactly {stop_loss_percent}% from entry_price")
        print("✅ TEST PASSED: SL calculated correctly from execution price")

    finally:
        # Cleanup
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM monitoring.positions WHERE symbol = $1 AND exchange = $2",
                symbol, exchange
            )
        await pool.close()


if __name__ == "__main__":
    import asyncio

    async def main():
        print("=" * 80)
        print("Running entry_price fix tests...")
        print("=" * 80)

        print("\n" + "=" * 80)
        print("TEST 1: Position created with execution price, not signal")
        print("=" * 80)
        await test_position_created_with_execution_price_not_signal()

        print("\n" + "=" * 80)
        print("TEST 2: Stop-loss percentage correct with execution price")
        print("=" * 80)
        await test_stop_loss_percentage_correct_with_execution_price()

        print("\n" + "=" * 80)
        print("✅ ALL TESTS PASSED")
        print("=" * 80)

    asyncio.run(main())
