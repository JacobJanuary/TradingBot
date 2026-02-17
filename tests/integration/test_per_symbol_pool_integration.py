"""
Integration tests for MarkPricePerSymbolPool → BinanceHybridStream bridge

Verifies the pool integrates correctly with the existing hybrid stream:
- Pool callback → _on_pool_price_update → SymbolStateManager
- add/remove during active operation (no impact on other symbols)
- Batch sync_positions flows through set_symbols
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from websocket.mark_price_per_symbol_pool import (
    PerSymbolConnection,
    MarkPricePerSymbolPool,
)
from websocket.symbol_state import SymbolStateManager, SymbolState


class TestPerSymbolPoolIntegration:
    """Integration tests for per-symbol pool with dependent systems"""

    # --- Test 1: add/remove ZERO impact on others ---

    @pytest.mark.asyncio
    async def test_add_remove_no_impact_on_others(self):
        """
        Scenario: 3 symbols active. Remove middle one.
        Verify: other 2 connections untouched.
        """
        callback = AsyncMock()
        pool = MarkPricePerSymbolPool(on_price_update=callback)

        with patch.object(
            PerSymbolConnection, 'start', new_callable=AsyncMock
        ):
            await pool.add_symbol("BTCUSDT")
            await pool.add_symbol("ETHUSDT")
            await pool.add_symbol("SOLUSDT")

        # Record connection objects before remove
        btc_conn = pool._connections["BTCUSDT"]
        sol_conn = pool._connections["SOLUSDT"]

        with patch.object(
            PerSymbolConnection, 'stop', new_callable=AsyncMock
        ):
            await pool.remove_symbol("ETHUSDT")

        # Verify: BTC and SOL connections are SAME objects (untouched)
        assert pool._connections["BTCUSDT"] is btc_conn
        assert pool._connections["SOLUSDT"] is sol_conn
        assert "ETHUSDT" not in pool._connections

    # --- Test 2: batch sync_positions ---

    @pytest.mark.asyncio
    async def test_batch_sync_positions(self):
        """
        Scenario: Cold start with 5 positions.
        Verify: All 5 get independent connections.
        """
        callback = AsyncMock()
        pool = MarkPricePerSymbolPool(on_price_update=callback)

        symbols = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "DOGEUSDT"}

        with patch.object(
            PerSymbolConnection, 'start', new_callable=AsyncMock
        ):
            await pool.set_symbols(symbols)

        assert pool.symbols == symbols
        assert len(pool._connections) == 5

        # Each connection has unique symbol
        conn_symbols = {c.symbol for c in pool._connections.values()}
        assert conn_symbols == symbols

    # --- Test 3: pool callback → SymbolStateManager ---

    @pytest.mark.asyncio
    async def test_pool_callback_bridge_updates_state_manager(self):
        """
        Scenario: Pool receives markPriceUpdate.
        Verify: SymbolStateManager transitions to SUBSCRIBED.
        """
        state_mgr = SymbolStateManager(stale_threshold=3.0)
        state_mgr.add("BTCUSDT")
        state_mgr.mark_subscribing("BTCUSDT")

        # Before WS data: should be SUBSCRIBING
        assert state_mgr.get_entry("BTCUSDT").state == SymbolState.SUBSCRIBING

        # Simulate what _on_pool_price_update does:
        data = {
            'e': 'markPriceUpdate',
            's': 'BTCUSDT',
            'p': '65000.50',
            'i': 'BTCUSDT',
            'P': '65005.00',
            'r': '0.00010000',
            'T': 1739800000000,
        }
        symbol = data.get('s')
        price = data.get('p')
        state_mgr.record_ws_update(symbol, price)

        # After WS data: should be SUBSCRIBED
        entry = state_mgr.get_entry("BTCUSDT")
        assert entry.state == SymbolState.SUBSCRIBED
        assert entry.last_price == '65000.50'
        assert entry.retry_count == 0

    # --- Test 4: diff-based set_symbols preserves connections ---

    @pytest.mark.asyncio
    async def test_set_symbols_diff_preserves_existing(self):
        """
        Scenario: {A,B,C} → {B,C,D}
        Verify: B and C connections are same objects, A stopped, D new.
        """
        callback = AsyncMock()
        pool = MarkPricePerSymbolPool(on_price_update=callback)

        with patch.object(
            PerSymbolConnection, 'start', new_callable=AsyncMock
        ):
            await pool.set_symbols({"A", "B", "C"})

        # Save refs
        b_conn = pool._connections["B"]
        c_conn = pool._connections["C"]

        with patch.object(
            PerSymbolConnection, 'start', new_callable=AsyncMock
        ), patch.object(
            PerSymbolConnection, 'stop', new_callable=AsyncMock
        ):
            await pool.set_symbols({"B", "C", "D"})

        # B and C should be SAME objects
        assert pool._connections["B"] is b_conn
        assert pool._connections["C"] is c_conn
        # A gone, D added
        assert "A" not in pool._connections
        assert "D" in pool._connections

    # --- Test 5: SymbolStateManager state transitions during lifecycle ---

    @pytest.mark.asyncio
    async def test_full_symbol_lifecycle_with_state_manager(self):
        """
        Full lifecycle: add → subscribe → receive data → remove
        Verify state transitions at each step.
        """
        state_mgr = SymbolStateManager(stale_threshold=3.0)

        # 1. Add
        entry = state_mgr.add("RAYSOLUSDT")
        assert entry.state == SymbolState.INIT

        # 2. Mark subscribing (pool is connecting)
        state_mgr.mark_subscribing("RAYSOLUSDT")
        assert state_mgr.get_entry("RAYSOLUSDT").state == SymbolState.SUBSCRIBING

        # 3. WS data arrives
        state_mgr.record_ws_update("RAYSOLUSDT", "0.01234")
        assert state_mgr.get_entry("RAYSOLUSDT").state == SymbolState.SUBSCRIBED
        assert state_mgr.get_entry("RAYSOLUSDT").last_price == "0.01234"

        # 4. Position closed → remove
        state_mgr.remove("RAYSOLUSDT")
        assert state_mgr.get_entry("RAYSOLUSDT").state == SymbolState.REMOVED

        # 5. Cleanup
        state_mgr.cleanup_removed()
        assert state_mgr.get_entry("RAYSOLUSDT") is None

    # --- Test 6: concurrent add/remove safety ---

    @pytest.mark.asyncio
    async def test_concurrent_add_remove_safe(self):
        """
        Concurrent add and remove should not corrupt state (lock-protected).
        """
        callback = AsyncMock()
        pool = MarkPricePerSymbolPool(on_price_update=callback)

        with patch.object(
            PerSymbolConnection, 'start', new_callable=AsyncMock
        ), patch.object(
            PerSymbolConnection, 'stop', new_callable=AsyncMock
        ):
            # Fire off many concurrent operations
            tasks = [
                pool.add_symbol(f"SYM{i}")
                for i in range(10)
            ]
            await asyncio.gather(*tasks)

            assert len(pool._connections) == 10

            # Remove half concurrently
            remove_tasks = [
                pool.remove_symbol(f"SYM{i}")
                for i in range(0, 10, 2)
            ]
            await asyncio.gather(*remove_tasks)

            assert len(pool._connections) == 5
            expected = {f"SYM{i}" for i in range(1, 10, 2)}
            assert pool.symbols == expected
