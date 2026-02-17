"""
Unit tests for MarkPricePerSymbolPool

Tests per-symbol WebSocket pool that replaces the combined-stream
MarkPriceConnectionPool. Verifies:
- add/remove symbol isolation
- diff-based set_symbols
- connection lifecycle
- status reporting
- edge cases (duplicates, nonexistent removals)
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from websocket.mark_price_per_symbol_pool import (
    PerSymbolConnection,
    MarkPricePerSymbolPool,
)


# ==================== PerSymbolConnection Tests ====================


class TestPerSymbolConnection:
    """Tests for individual per-symbol WS connection"""

    def test_init_builds_correct_url(self):
        """URL format: wss://fstream.binance.com/ws/btcusdt@markPrice@1s"""
        conn = PerSymbolConnection(
            symbol="BTCUSDT",
            callback=AsyncMock(),
            frequency="1s",
        )
        assert "btcusdt@markPrice@1s" in conn._url
        assert conn.symbol == "BTCUSDT"
        assert conn.connected is False
        assert conn._messages_received == 0

    def test_init_3s_frequency(self):
        """3s frequency variant"""
        conn = PerSymbolConnection(
            symbol="ETHUSDT",
            callback=AsyncMock(),
            frequency="3s",
        )
        assert "ethusdt@markPrice@3s" in conn._url

    @pytest.mark.asyncio
    async def test_start_creates_task(self):
        """start() should create a background task"""
        conn = PerSymbolConnection(
            symbol="BTCUSDT",
            callback=AsyncMock(),
        )
        with patch.object(conn, '_run_forever', new_callable=AsyncMock):
            await conn.start()
            assert conn._running is True
            assert conn._task is not None
            # Cleanup
            await conn.stop()

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        """Second start() call should be a no-op"""
        conn = PerSymbolConnection(
            symbol="BTCUSDT",
            callback=AsyncMock(),
        )
        with patch.object(conn, '_run_forever', new_callable=AsyncMock):
            await conn.start()
            first_task = conn._task
            await conn.start()  # Should not create second task
            assert conn._task is first_task
            await conn.stop()

    @pytest.mark.asyncio
    async def test_stop_clears_state(self):
        """stop() should cancel task and reset connected"""
        conn = PerSymbolConnection(
            symbol="BTCUSDT",
            callback=AsyncMock(),
        )
        with patch.object(conn, '_run_forever', new_callable=AsyncMock):
            await conn.start()
            await conn.stop()
            assert conn._running is False
            assert conn.connected is False

    def test_reconnect_delay_exponential(self):
        """Delay should increase exponentially up to 60s"""
        conn = PerSymbolConnection(
            symbol="BTCUSDT",
            callback=AsyncMock(),
        )
        # First attempt: ~1s (±jitter)
        conn._reconnect_count = 0
        delay0 = conn._get_reconnect_delay()
        assert 0.5 <= delay0 <= 1.5

        # Third attempt: ~4s (±jitter)
        conn._reconnect_count = 2
        delay2 = conn._get_reconnect_delay()
        assert 2.0 <= delay2 <= 6.0

        # Tenth attempt: capped at ~60s
        conn._reconnect_count = 10
        delay10 = conn._get_reconnect_delay()
        assert delay10 <= 75.0  # 60 + 25% jitter

    def test_get_status(self):
        """Status dict should contain expected fields"""
        conn = PerSymbolConnection(
            symbol="BTCUSDT",
            callback=AsyncMock(),
        )
        status = conn.get_status()
        assert status['symbol'] == 'BTCUSDT'
        assert status['connected'] is False
        assert status['messages_received'] == 0
        assert status['reconnect_count'] == 0


# ==================== MarkPricePerSymbolPool Tests ====================


class TestMarkPricePerSymbolPool:
    """Tests for the per-symbol connection pool"""

    @pytest.fixture
    def pool(self):
        """Create pool with mock callback"""
        return MarkPricePerSymbolPool(
            on_price_update=AsyncMock(),
            frequency="1s",
        )

    # --- Properties ---

    def test_initial_state(self, pool):
        """Pool starts with no connections"""
        assert pool.connected is False
        assert pool.all_connected is False
        assert pool.symbols == set()

    # --- add_symbol ---

    @pytest.mark.asyncio
    async def test_add_symbol_creates_connection(self, pool):
        """add_symbol should create and start a PerSymbolConnection"""
        with patch.object(
            PerSymbolConnection, 'start', new_callable=AsyncMock
        ):
            await pool.add_symbol("BTCUSDT")
            assert "BTCUSDT" in pool.symbols
            assert len(pool._connections) == 1

    @pytest.mark.asyncio
    async def test_add_symbol_duplicate_ignored(self, pool):
        """Adding same symbol twice should not create second connection"""
        with patch.object(
            PerSymbolConnection, 'start', new_callable=AsyncMock
        ):
            await pool.add_symbol("BTCUSDT")
            await pool.add_symbol("BTCUSDT")
            assert len(pool._connections) == 1

    @pytest.mark.asyncio
    async def test_add_multiple_symbols(self, pool):
        """Each symbol gets its own connection"""
        with patch.object(
            PerSymbolConnection, 'start', new_callable=AsyncMock
        ):
            await pool.add_symbol("BTCUSDT")
            await pool.add_symbol("ETHUSDT")
            await pool.add_symbol("SOLUSDT")
            assert pool.symbols == {"BTCUSDT", "ETHUSDT", "SOLUSDT"}
            assert len(pool._connections) == 3

    # --- remove_symbol ---

    @pytest.mark.asyncio
    async def test_remove_symbol_stops_only_target(self, pool):
        """Removing one symbol should not affect others"""
        with patch.object(
            PerSymbolConnection, 'start', new_callable=AsyncMock
        ), patch.object(
            PerSymbolConnection, 'stop', new_callable=AsyncMock
        ):
            await pool.add_symbol("BTCUSDT")
            await pool.add_symbol("ETHUSDT")
            await pool.add_symbol("SOLUSDT")

            await pool.remove_symbol("ETHUSDT")

            assert pool.symbols == {"BTCUSDT", "SOLUSDT"}
            assert len(pool._connections) == 2

    @pytest.mark.asyncio
    async def test_remove_nonexistent_no_error(self, pool):
        """Removing unknown symbol should be a no-op"""
        await pool.remove_symbol("NONEXISTENT")
        assert len(pool._connections) == 0

    # --- set_symbols (diff-based) ---

    @pytest.mark.asyncio
    async def test_set_symbols_initial(self, pool):
        """set_symbols with initial set should start all"""
        with patch.object(
            PerSymbolConnection, 'start', new_callable=AsyncMock
        ):
            await pool.set_symbols({"BTCUSDT", "ETHUSDT"})
            assert pool.symbols == {"BTCUSDT", "ETHUSDT"}

    @pytest.mark.asyncio
    async def test_set_symbols_diff_add_remove(self, pool):
        """set_symbols should only add/remove the diff"""
        with patch.object(
            PerSymbolConnection, 'start', new_callable=AsyncMock
        ), patch.object(
            PerSymbolConnection, 'stop', new_callable=AsyncMock
        ):
            # Initial: A, B
            await pool.set_symbols({"A", "B"})
            assert pool.symbols == {"A", "B"}

            # Change to: B, C → remove A, keep B, add C
            await pool.set_symbols({"B", "C"})
            assert pool.symbols == {"B", "C"}

    @pytest.mark.asyncio
    async def test_set_symbols_no_change_noop(self, pool):
        """set_symbols with same set should be a no-op"""
        with patch.object(
            PerSymbolConnection, 'start', new_callable=AsyncMock
        ) as mock_start:
            await pool.set_symbols({"A", "B"})
            assert mock_start.call_count == 2

            await pool.set_symbols({"A", "B"})
            # No additional starts
            assert mock_start.call_count == 2

    @pytest.mark.asyncio
    async def test_set_symbols_immediate_same_as_set_symbols(self, pool):
        """set_symbols_immediate should behave identically"""
        with patch.object(
            PerSymbolConnection, 'start', new_callable=AsyncMock
        ):
            await pool.set_symbols_immediate({"BTCUSDT", "ETHUSDT"})
            assert pool.symbols == {"BTCUSDT", "ETHUSDT"}

    @pytest.mark.asyncio
    async def test_set_symbols_to_empty(self, pool):
        """set_symbols to empty should stop all connections"""
        with patch.object(
            PerSymbolConnection, 'start', new_callable=AsyncMock
        ), patch.object(
            PerSymbolConnection, 'stop', new_callable=AsyncMock
        ):
            await pool.set_symbols({"A", "B"})
            await pool.set_symbols(set())
            assert pool.symbols == set()
            assert len(pool._connections) == 0

    # --- stop ---

    @pytest.mark.asyncio
    async def test_stop_all(self, pool):
        """stop() should stop all connections and clear state"""
        with patch.object(
            PerSymbolConnection, 'start', new_callable=AsyncMock
        ), patch.object(
            PerSymbolConnection, 'stop', new_callable=AsyncMock
        ) as mock_stop:
            await pool.add_symbol("BTCUSDT")
            await pool.add_symbol("ETHUSDT")

            await pool.stop()

            assert mock_stop.call_count == 2
            assert len(pool._connections) == 0
            assert pool.symbols == set()

    # --- connected properties ---

    @pytest.mark.asyncio
    async def test_connected_when_any_active(self, pool):
        """connected should be True when at least one connection is active"""
        with patch.object(
            PerSymbolConnection, 'start', new_callable=AsyncMock
        ):
            await pool.add_symbol("BTCUSDT")
            pool._connections["BTCUSDT"]._connected = True
            assert pool.connected is True

    @pytest.mark.asyncio
    async def test_all_connected(self, pool):
        """all_connected should be True only when ALL are connected"""
        with patch.object(
            PerSymbolConnection, 'start', new_callable=AsyncMock
        ):
            await pool.add_symbol("BTCUSDT")
            await pool.add_symbol("ETHUSDT")

            pool._connections["BTCUSDT"]._connected = True
            pool._connections["ETHUSDT"]._connected = False
            assert pool.all_connected is False

            pool._connections["ETHUSDT"]._connected = True
            assert pool.all_connected is True

    # --- get_status ---

    @pytest.mark.asyncio
    async def test_get_status(self, pool):
        """get_status should return correct monitoring dict"""
        with patch.object(
            PerSymbolConnection, 'start', new_callable=AsyncMock
        ):
            await pool.add_symbol("BTCUSDT")
            await pool.add_symbol("ETHUSDT")

            pool._connections["BTCUSDT"]._connected = True
            pool._connections["ETHUSDT"]._connected = False

            status = pool.get_status()
            assert status['total_connections'] == 2
            assert status['connected_count'] == 1
            assert status['total_symbols'] == 2
            assert len(status['connections']) == 2

    # --- callback forwarding ---

    @pytest.mark.asyncio
    async def test_callback_receives_data(self, pool):
        """Pool callback should be passed to each connection"""
        callback = AsyncMock()
        pool = MarkPricePerSymbolPool(
            on_price_update=callback,
        )
        with patch.object(
            PerSymbolConnection, 'start', new_callable=AsyncMock
        ):
            await pool.add_symbol("BTCUSDT")
            conn = pool._connections["BTCUSDT"]
            assert conn.callback is callback
