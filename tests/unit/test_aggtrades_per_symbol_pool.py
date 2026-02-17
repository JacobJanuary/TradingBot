"""
Unit tests for AggTradesPerSymbolPool

Tests cover:
1. Subscribe/unsubscribe with ref counting
2. Delta calculations (get_rolling_delta, get_avg_delta, get_large_trade_counts)
3. _trade_handlers callback dispatching
4. Symbol normalization (CCXT → raw format)
5. Connection isolation
6. Pool lifecycle (start/stop)
7. subscribed_symbols compatibility

Date: 2026-02-17
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal

from websocket.aggtrades_per_symbol_pool import (
    AggTradesPerSymbolPool,
    AggTradePerSymbolConnection,
    SymbolDeltaState,
    TradeData,
)


# ══════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════

def make_trade(price: float, qty: float, is_buyer_maker: bool, ts: float = 0) -> TradeData:
    """Create a TradeData for testing"""
    return TradeData(
        timestamp=ts,
        price=Decimal(str(price)),
        quantity=Decimal(str(qty)),
        is_buyer_maker=is_buyer_maker,
    )


# ══════════════════════════════════════════════════════
# TradeData tests
# ══════════════════════════════════════════════════════

class TestTradeData:
    def test_buy_side(self):
        trade = make_trade(100.0, 1.0, is_buyer_maker=False)
        assert trade.side == 'buy'

    def test_sell_side(self):
        trade = make_trade(100.0, 1.0, is_buyer_maker=True)
        assert trade.side == 'sell'

    def test_volume_usdt(self):
        trade = make_trade(100.0, 2.5, is_buyer_maker=False)
        assert trade.volume_usdt == Decimal('250.0')


# ══════════════════════════════════════════════════════
# Pool lifecycle tests
# ══════════════════════════════════════════════════════

class TestPoolLifecycle:
    @pytest.fixture
    def pool(self):
        return AggTradesPerSymbolPool(testnet=False)

    @pytest.mark.asyncio
    async def test_start_sets_running(self, pool):
        await pool.start()
        assert pool.running is True
        assert pool.connected is True

    @pytest.mark.asyncio
    async def test_double_start_is_safe(self, pool):
        await pool.start()
        await pool.start()  # Should not raise
        assert pool.running is True

    @pytest.mark.asyncio
    async def test_stop_cleans_up(self, pool):
        await pool.start()
        await pool.stop()
        assert pool.running is False
        assert pool.connected is False
        assert len(pool._connections) == 0
        assert len(pool.subscribed_symbols) == 0

    @pytest.mark.asyncio
    async def test_stop_without_start(self, pool):
        await pool.stop()  # Should not raise


# ══════════════════════════════════════════════════════
# Subscribe/Unsubscribe tests
# ══════════════════════════════════════════════════════

class TestSubscription:
    @pytest.fixture
    async def pool(self):
        p = AggTradesPerSymbolPool(testnet=False)
        await p.start()
        yield p
        await p.stop()

    @pytest.mark.asyncio
    async def test_subscribe_creates_connection(self, pool):
        with patch.object(AggTradePerSymbolConnection, 'start', new_callable=AsyncMock):
            await pool.subscribe('BTCUSDT')
            assert 'BTCUSDT' in pool.subscribed_symbols
            assert 'BTCUSDT' in pool._connections
            assert pool._subscription_refcount['BTCUSDT'] == 1

    @pytest.mark.asyncio
    async def test_subscribe_normalizes_ccxt_symbol(self, pool):
        """CCXT format BTC/USDT:USDT → BTCUSDT"""
        with patch.object(AggTradePerSymbolConnection, 'start', new_callable=AsyncMock):
            await pool.subscribe('BTC/USDT:USDT')
            assert 'BTCUSDT' in pool.subscribed_symbols
            assert 'BTCUSDT' in pool._connections

    @pytest.mark.asyncio
    async def test_subscribe_normalizes_slash_format(self, pool):
        """BTC/USDT → BTCUSDT"""
        with patch.object(AggTradePerSymbolConnection, 'start', new_callable=AsyncMock):
            await pool.subscribe('BTC/USDT')
            assert 'BTCUSDT' in pool.subscribed_symbols

    @pytest.mark.asyncio
    async def test_duplicate_subscribe_increments_refcount(self, pool):
        with patch.object(AggTradePerSymbolConnection, 'start', new_callable=AsyncMock):
            await pool.subscribe('BTCUSDT')
            await pool.subscribe('BTCUSDT')
            assert pool._subscription_refcount['BTCUSDT'] == 2
            assert len(pool._connections) == 1  # Still only 1 connection

    @pytest.mark.asyncio
    async def test_unsubscribe_with_remaining_refs(self, pool):
        with patch.object(AggTradePerSymbolConnection, 'start', new_callable=AsyncMock):
            await pool.subscribe('BTCUSDT')
            await pool.subscribe('BTCUSDT')

            await pool.unsubscribe('BTCUSDT')
            # Still has 1 ref, connection should remain
            assert 'BTCUSDT' in pool._connections
            assert pool._subscription_refcount['BTCUSDT'] == 1

    @pytest.mark.asyncio
    async def test_unsubscribe_last_ref_removes_connection(self, pool):
        with patch.object(AggTradePerSymbolConnection, 'start', new_callable=AsyncMock):
            with patch.object(AggTradePerSymbolConnection, 'stop', new_callable=AsyncMock):
                await pool.subscribe('BTCUSDT')
                await pool.unsubscribe('BTCUSDT')
                assert 'BTCUSDT' not in pool._connections
                assert 'BTCUSDT' not in pool.subscribed_symbols

    @pytest.mark.asyncio
    async def test_unsubscribe_nonexistent_is_safe(self, pool):
        await pool.unsubscribe('NONEXISTENT')  # Should not raise

    @pytest.mark.asyncio
    async def test_multiple_symbols_isolated(self, pool):
        with patch.object(AggTradePerSymbolConnection, 'start', new_callable=AsyncMock):
            await pool.subscribe('BTCUSDT')
            await pool.subscribe('ETHUSDT')
            await pool.subscribe('SOLUSDT')

            assert len(pool._connections) == 3
            assert pool.subscribed_symbols == {'BTCUSDT', 'ETHUSDT', 'SOLUSDT'}

            # Removing one doesn't affect others
            with patch.object(AggTradePerSymbolConnection, 'stop', new_callable=AsyncMock):
                await pool.unsubscribe('ETHUSDT')

            assert len(pool._connections) == 2
            assert 'BTCUSDT' in pool._connections
            assert 'SOLUSDT' in pool._connections
            assert 'ETHUSDT' not in pool._connections


# ══════════════════════════════════════════════════════
# Delta calculation tests
# ══════════════════════════════════════════════════════

class TestDeltaCalculations:
    @pytest.fixture
    def pool(self):
        p = AggTradesPerSymbolPool(testnet=False)
        p.running = True
        p.connected = True
        return p

    def _seed_trades(self, pool, symbol, trades):
        """Helper: seed trades into delta state"""
        state = SymbolDeltaState()
        for trade in trades:
            state.trades.append(trade)
        state.last_update = asyncio.get_event_loop().time()
        pool.delta_states[symbol] = state

    def test_rolling_delta_empty_state(self, pool):
        delta = pool.get_rolling_delta('BTCUSDT', 20)
        assert delta == Decimal('0')

    def test_rolling_delta_no_state(self, pool):
        delta = pool.get_rolling_delta('NONEXISTENT', 20)
        assert delta == Decimal('0')

    def test_rolling_delta_positive_buying_pressure(self, pool):
        loop = asyncio.get_event_loop()
        now = loop.time()

        trades = [
            make_trade(100.0, 10.0, is_buyer_maker=False, ts=now - 5),  # buy $1000
            make_trade(100.0, 3.0, is_buyer_maker=True, ts=now - 3),    # sell $300
        ]
        self._seed_trades(pool, 'BTCUSDT', trades)

        delta = pool.get_rolling_delta('BTCUSDT', 20)
        assert delta == Decimal('700.0')

    def test_rolling_delta_negative_selling_pressure(self, pool):
        loop = asyncio.get_event_loop()
        now = loop.time()

        trades = [
            make_trade(100.0, 2.0, is_buyer_maker=False, ts=now - 5),   # buy $200
            make_trade(100.0, 10.0, is_buyer_maker=True, ts=now - 3),   # sell $1000
        ]
        self._seed_trades(pool, 'BTCUSDT', trades)

        delta = pool.get_rolling_delta('BTCUSDT', 20)
        assert delta == Decimal('-800.0')

    def test_rolling_delta_respects_window(self, pool):
        loop = asyncio.get_event_loop()
        now = loop.time()

        trades = [
            make_trade(100.0, 10.0, is_buyer_maker=False, ts=now - 100),  # old buy — outside window
            make_trade(100.0, 5.0, is_buyer_maker=True, ts=now - 5),      # recent sell
        ]
        self._seed_trades(pool, 'BTCUSDT', trades)

        delta = pool.get_rolling_delta('BTCUSDT', 20)
        # Only the recent sell counts
        assert delta == Decimal('-500.0')

    def test_avg_delta_empty_state(self, pool):
        avg = pool.get_avg_delta('BTCUSDT', 100)
        assert avg == Decimal('1')  # Default to avoid division by zero

    def test_large_trade_counts_empty_state(self, pool):
        buys, sells = pool.get_large_trade_counts('BTCUSDT', 60)
        assert buys == 0
        assert sells == 0

    def test_large_trade_counts_detects_whales(self, pool):
        loop = asyncio.get_event_loop()
        now = loop.time()

        trades = [
            make_trade(50000.0, 1.0, is_buyer_maker=False, ts=now - 10),   # buy $50k ✓
            make_trade(100.0, 1.0, is_buyer_maker=False, ts=now - 8),      # buy $100 ✗
            make_trade(20000.0, 1.0, is_buyer_maker=True, ts=now - 5),     # sell $20k ✓
            make_trade(15000.0, 1.0, is_buyer_maker=True, ts=now - 3),     # sell $15k ✓
        ]
        self._seed_trades(pool, 'BTCUSDT', trades)

        buys, sells = pool.get_large_trade_counts('BTCUSDT', 60)
        assert buys == 1
        assert sells == 2

    def test_get_stats_returns_dict(self, pool):
        loop = asyncio.get_event_loop()
        now = loop.time()

        trades = [
            make_trade(100.0, 5.0, is_buyer_maker=False, ts=now - 5),
        ]
        self._seed_trades(pool, 'BTCUSDT', trades)

        stats = pool.get_stats('BTCUSDT')
        assert 'symbol' in stats
        assert stats['symbol'] == 'BTCUSDT'
        assert 'rolling_delta_20s' in stats
        assert 'trade_count' in stats
        assert stats['trade_count'] == 1

    def test_get_stats_empty_symbol(self, pool):
        stats = pool.get_stats('NONEXISTENT')
        assert stats == {}


# ══════════════════════════════════════════════════════
# Symbol normalization tests
# ══════════════════════════════════════════════════════

class TestSymbolNormalization:
    @pytest.fixture
    async def pool(self):
        p = AggTradesPerSymbolPool(testnet=False)
        await p.start()
        yield p
        await p.stop()

    @pytest.mark.asyncio
    async def test_ccxt_format_normalized_on_subscribe(self, pool):
        with patch.object(AggTradePerSymbolConnection, 'start', new_callable=AsyncMock):
            await pool.subscribe('MMT/USDT:USDT')
            assert 'MMTUSDT' in pool.subscribed_symbols
            assert 'MMT/USDT:USDT' not in pool.subscribed_symbols

    @pytest.mark.asyncio
    async def test_ccxt_format_normalized_on_unsubscribe(self, pool):
        with patch.object(AggTradePerSymbolConnection, 'start', new_callable=AsyncMock):
            with patch.object(AggTradePerSymbolConnection, 'stop', new_callable=AsyncMock):
                await pool.subscribe('BTC/USDT:USDT')
                await pool.unsubscribe('BTC/USDT:USDT')
                assert 'BTCUSDT' not in pool.subscribed_symbols

    def test_delta_lookups_normalize(self, pool):
        """Delta methods should normalize symbols too"""
        pool.delta_states['BTCUSDT'] = SymbolDeltaState()
        # Should work with CCXT format
        delta = pool.get_rolling_delta('BTC/USDT:USDT', 20)
        assert delta == Decimal('0')

    def test_get_stats_normalizes(self, pool):
        pool.delta_states['BTCUSDT'] = SymbolDeltaState()
        stats = pool.get_stats('BTC/USDT:USDT')
        assert stats['symbol'] == 'BTCUSDT'


# ══════════════════════════════════════════════════════
# Trade handler callback tests
# ══════════════════════════════════════════════════════

class TestTradeHandlers:
    def test_trade_handlers_called_on_process(self):
        """_trade_handlers list callbacks are invoked for each trade"""
        handler_calls = []
        handlers = [lambda data: handler_calls.append(data)]

        state = SymbolDeltaState()
        conn = AggTradePerSymbolConnection.__new__(AggTradePerSymbolConnection)
        conn.symbol = 'BTCUSDT'
        conn.delta_state = state
        conn._trade_handlers = handlers

        trade_data = {
            'e': 'aggTrade',
            's': 'BTCUSDT',
            'p': '100.0',
            'q': '1.0',
            'T': 1000000,
            'm': False,
        }

        conn._process_trade(trade_data)

        assert len(handler_calls) == 1
        assert handler_calls[0] == trade_data
        assert len(state.trades) == 1

    def test_non_aggtrade_event_ignored(self):
        """Non-aggTrade events should be silently ignored"""
        state = SymbolDeltaState()
        conn = AggTradePerSymbolConnection.__new__(AggTradePerSymbolConnection)
        conn.symbol = 'BTCUSDT'
        conn.delta_state = state
        conn._trade_handlers = []

        conn._process_trade({'e': 'depthUpdate', 's': 'BTCUSDT'})
        assert len(state.trades) == 0

    def test_handler_error_does_not_crash(self):
        """One broken handler should not prevent others from running"""
        calls = []

        def bad_handler(data):
            raise RuntimeError("broken")

        def good_handler(data):
            calls.append(data)

        handlers = [bad_handler, good_handler]

        state = SymbolDeltaState()
        conn = AggTradePerSymbolConnection.__new__(AggTradePerSymbolConnection)
        conn.symbol = 'BTCUSDT'
        conn.delta_state = state
        conn._trade_handlers = handlers

        trade_data = {
            'e': 'aggTrade',
            's': 'BTCUSDT',
            'p': '100.0',
            'q': '1.0',
            'T': 1000000,
            'm': False,
        }

        conn._process_trade(trade_data)  # Should not raise
        assert len(calls) == 1


# ══════════════════════════════════════════════════════
# Connection status tests
# ══════════════════════════════════════════════════════

class TestPoolStatus:
    @pytest.mark.asyncio
    async def test_get_pool_status(self):
        pool = AggTradesPerSymbolPool(testnet=False)
        await pool.start()

        with patch.object(AggTradePerSymbolConnection, 'start', new_callable=AsyncMock):
            await pool.subscribe('BTCUSDT')
            await pool.subscribe('ETHUSDT')

        status = pool.get_pool_status()
        assert status['total_connections'] == 2
        assert 'BTCUSDT' in status['subscribed_symbols']
        assert 'ETHUSDT' in status['subscribed_symbols']
        assert len(status['connections']) == 2

        await pool.stop()
