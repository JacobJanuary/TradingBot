"""
Unit tests for ReentryManager critical cases.

Tests:
- Signal creation and state management
- Price tracking (max/min after exit)
- Trigger price calculation
- Multiple reentries flow
- Cooldown enforcement
- Delta confirmation
- Terminal states (expired, max_reached)

Run with: pytest tests/unit/test_reentry_manager.py -v
"""

import pytest
import asyncio
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.reentry_manager import ReentryManager, ReentrySignal


@pytest.fixture
def mock_position_manager():
    """Create mock position manager"""
    pm = MagicMock()
    pm.positions = {}
    pm.open_position = AsyncMock(return_value=True)
    return pm


@pytest.fixture
def mock_aggtrades_stream():
    """Create mock aggtrades stream"""
    stream = MagicMock()
    stream.get_large_trade_counts = MagicMock(return_value=(10, 5))  # buys > sells
    stream.subscribe = AsyncMock()
    return stream


@pytest.fixture
def mock_mark_price_stream():
    """Create mock mark price stream"""
    stream = MagicMock()
    stream.subscribe_symbol = AsyncMock()
    return stream


@pytest.fixture
async def reentry_manager(mock_position_manager, mock_aggtrades_stream, mock_mark_price_stream):
    """Create ReentryManager with mocked dependencies"""
    manager = ReentryManager(
        position_manager=mock_position_manager,
        aggtrades_stream=mock_aggtrades_stream,
        mark_price_stream=mock_mark_price_stream,
        cooldown_sec=300,
        drop_percent=5.0,
        max_reentries=3,
        instant_reentry_enabled=False,
        repository=None
    )
    manager._save_signal_state = AsyncMock()
    manager._load_active_signals = AsyncMock()
    return manager


class TestReentrySignal:
    """Tests for ReentrySignal dataclass"""
    
    def test_is_expired_false(self):
        """Signal should not be expired within 24h"""
        signal = ReentrySignal(
            signal_id=1,
            symbol="TEST",
            exchange="binance",
            side="long",
            original_entry_price=Decimal("100"),
            original_entry_time=datetime.now(timezone.utc),
            last_exit_price=Decimal("105"),
            last_exit_time=datetime.now(timezone.utc),
            last_exit_reason="ts",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24)
        )
        assert not signal.is_expired()
    
    def test_is_expired_true(self):
        """Signal should be expired after 24h"""
        signal = ReentrySignal(
            signal_id=1,
            symbol="TEST",
            exchange="binance",
            side="long",
            original_entry_price=Decimal("100"),
            original_entry_time=datetime.now(timezone.utc) - timedelta(hours=25),
            last_exit_price=Decimal("105"),
            last_exit_time=datetime.now(timezone.utc),
            last_exit_reason="ts",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1)
        )
        assert signal.is_expired()
    
    def test_is_in_cooldown_true(self):
        """Signal should be in cooldown right after exit"""
        signal = ReentrySignal(
            signal_id=1,
            symbol="TEST",
            exchange="binance",
            side="long",
            original_entry_price=Decimal("100"),
            original_entry_time=datetime.now(timezone.utc),
            last_exit_price=Decimal("105"),
            last_exit_time=datetime.now(timezone.utc),
            last_exit_reason="ts",
            cooldown_sec=300
        )
        assert signal.is_in_cooldown()
    
    def test_is_in_cooldown_false(self):
        """Signal should not be in cooldown after cooldown period"""
        signal = ReentrySignal(
            signal_id=1,
            symbol="TEST",
            exchange="binance",
            side="long",
            original_entry_price=Decimal("100"),
            original_entry_time=datetime.now(timezone.utc),
            last_exit_price=Decimal("105"),
            last_exit_time=datetime.now(timezone.utc) - timedelta(seconds=400),
            last_exit_reason="ts",
            cooldown_sec=300
        )
        assert not signal.is_in_cooldown()
    
    def test_trigger_price_long(self):
        """LONG: trigger = max * (1 - drop_percent/100)"""
        signal = ReentrySignal(
            signal_id=1,
            symbol="TEST",
            exchange="binance",
            side="long",
            original_entry_price=Decimal("100"),
            original_entry_time=datetime.now(timezone.utc),
            last_exit_price=Decimal("100"),
            last_exit_time=datetime.now(timezone.utc),
            last_exit_reason="ts",
            drop_percent=Decimal("5.0")
        )
        signal.max_price_after_exit = Decimal("110")
        
        trigger = signal.get_reentry_trigger_price()
        expected = Decimal("110") * Decimal("0.95")  # 104.5
        assert trigger == expected
    
    def test_trigger_price_short(self):
        """SHORT: trigger = min * (1 + drop_percent/100)"""
        signal = ReentrySignal(
            signal_id=1,
            symbol="TEST",
            exchange="binance",
            side="short",
            original_entry_price=Decimal("100"),
            original_entry_time=datetime.now(timezone.utc),
            last_exit_price=Decimal("100"),
            last_exit_time=datetime.now(timezone.utc),
            last_exit_reason="ts",
            drop_percent=Decimal("5.0")
        )
        signal.min_price_after_exit = Decimal("90")
        
        trigger = signal.get_reentry_trigger_price()
        expected = Decimal("90") * Decimal("1.05")  # 94.5
        assert trigger == expected
    
    def test_can_reenter_all_conditions(self):
        """can_reenter should check all conditions"""
        signal = ReentrySignal(
            signal_id=1,
            symbol="TEST",
            exchange="binance",
            side="long",
            original_entry_price=Decimal("100"),
            original_entry_time=datetime.now(timezone.utc),
            last_exit_price=Decimal("105"),
            last_exit_time=datetime.now(timezone.utc) - timedelta(seconds=400),
            last_exit_reason="ts",
            cooldown_sec=300,
            max_reentries=3,
            reentry_count=1,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=23)
        )
        signal.status = "active"
        
        assert signal.can_reenter()
    
    def test_can_reenter_max_reached(self):
        """can_reenter should be False when count >= max"""
        signal = ReentrySignal(
            signal_id=1,
            symbol="TEST",
            exchange="binance",
            side="long",
            original_entry_price=Decimal("100"),
            original_entry_time=datetime.now(timezone.utc),
            last_exit_price=Decimal("105"),
            last_exit_time=datetime.now(timezone.utc) - timedelta(seconds=400),
            last_exit_reason="ts",
            cooldown_sec=300,
            max_reentries=3,
            reentry_count=3,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=23)
        )
        signal.status = "active"
        
        assert not signal.can_reenter()


class TestReentryManagerRegisterExit:
    """Tests for register_exit method"""
    
    @pytest.mark.asyncio
    async def test_creates_new_signal(self, reentry_manager):
        """register_exit should create new signal for new symbol"""
        await reentry_manager.register_exit(
            signal_id=1,
            symbol="TESTUSDT",
            exchange="binance",
            side="long",
            original_entry_price=Decimal("100"),
            original_entry_time=datetime.now(timezone.utc),
            exit_price=Decimal("105"),
            exit_reason="trailing_stop"
        )
        
        assert "TESTUSDT" in reentry_manager.signals
        signal = reentry_manager.signals["TESTUSDT"]
        assert signal.status == "active"
        assert signal.reentry_count == 0
    
    @pytest.mark.asyncio
    async def test_reactivates_after_reentry_exit(self, reentry_manager):
        """After reentry position exits, signal should reactivate to 'active'"""
        # Create initial signal
        await reentry_manager.register_exit(
            signal_id=1,
            symbol="TESTUSDT",
            exchange="binance",
            side="long",
            original_entry_price=Decimal("100"),
            original_entry_time=datetime.now(timezone.utc),
            exit_price=Decimal("105"),
            exit_reason="trailing_stop"
        )
        
        # Simulate reentry happened
        signal = reentry_manager.signals["TESTUSDT"]
        signal.status = "reentered"
        signal.reentry_count = 1
        
        # Exit from reentry position
        await reentry_manager.register_exit(
            signal_id=1,
            symbol="TESTUSDT",
            exchange="binance",
            side="long",
            original_entry_price=Decimal("100"),
            original_entry_time=datetime.now(timezone.utc),
            exit_price=Decimal("108"),
            exit_reason="trailing_stop"
        )
        
        # Should reactivate (not expire!)
        assert signal.status == "active"
        assert signal.reentry_count == 1  # Count NOT incremented
    
    @pytest.mark.asyncio
    async def test_max_reached_terminal(self, reentry_manager):
        """When count >= max, status should be max_reached"""
        # Create signal at max
        await reentry_manager.register_exit(
            signal_id=1,
            symbol="TESTUSDT",
            exchange="binance",
            side="long",
            original_entry_price=Decimal("100"),
            original_entry_time=datetime.now(timezone.utc),
            exit_price=Decimal("105"),
            exit_reason="trailing_stop"
        )
        
        signal = reentry_manager.signals["TESTUSDT"]
        signal.status = "reentered"
        signal.reentry_count = 3  # SIMULATE that 3rd reentry happened
        
        # Trigger reentry (not needed if we simulate count=3 directly)
        
        # Now count = 3, exit again
        await reentry_manager.register_exit(
            signal_id=1,
            symbol="TESTUSDT",
            exchange="binance",
            side="long",
            original_entry_price=Decimal("100"),
            original_entry_time=datetime.now(timezone.utc),
            exit_price=Decimal("108"),
            exit_reason="trailing_stop"
        )
        
        assert signal.status == "max_reached"
    
    @pytest.mark.asyncio
    async def test_ignores_locked_signal(self, reentry_manager):
        """register_exit should ignore signal if it's being processed"""
        # Create signal
        await reentry_manager.register_exit(
            signal_id=1,
            symbol="TESTUSDT",
            exchange="binance",
            side="long",
            original_entry_price=Decimal("100"),
            original_entry_time=datetime.now(timezone.utc),
            exit_price=Decimal("105"),
            exit_reason="trailing_stop"
        )
        
        signal = reentry_manager.signals["TESTUSDT"]
        signal.status = "reentered"
        
        # Lock the signal
        reentry_manager._processing_signals.add("TESTUSDT")
        
        # Try to register exit (should be ignored)
        await reentry_manager.register_exit(
            signal_id=1,
            symbol="TESTUSDT",
            exchange="binance",
            side="long",
            original_entry_price=Decimal("100"),
            original_entry_time=datetime.now(timezone.utc),
            exit_price=Decimal("108"),
            exit_reason="trailing_stop"
        )
        
        # Status should remain 'reentered' (not changed to 'active')
        assert signal.status == "reentered"


class TestReentryManagerUpdatePrice:
    """Tests for update_price method"""
    
    @pytest.mark.asyncio
    async def test_tracks_max_price(self, reentry_manager):
        """update_price should track max_price_after_exit"""
        await reentry_manager.register_exit(
            signal_id=1,
            symbol="TESTUSDT",
            exchange="binance",
            side="long",
            original_entry_price=Decimal("100"),
            original_entry_time=datetime.now(timezone.utc),
            exit_price=Decimal("105"),
            exit_reason="ts"
        )
        
        await reentry_manager.update_price("TESTUSDT", Decimal("107"))
        await reentry_manager.update_price("TESTUSDT", Decimal("110"))
        await reentry_manager.update_price("TESTUSDT", Decimal("108"))
        
        signal = reentry_manager.signals["TESTUSDT"]
        assert signal.max_price_after_exit == Decimal("110")
    
    @pytest.mark.asyncio
    async def test_triggers_reentry_at_drop(self, reentry_manager):
        """update_price should trigger reentry when drop% reached"""
        await reentry_manager.register_exit(
            signal_id=1,
            symbol="TESTUSDT",
            exchange="binance",
            side="long",
            original_entry_price=Decimal("100"),
            original_entry_time=datetime.now(timezone.utc) - timedelta(hours=1),
            exit_price=Decimal("105"),
            exit_reason="ts"
        )
        
        signal = reentry_manager.signals["TESTUSDT"]
        signal.cooldown_sec = 0
        signal.last_exit_time = datetime.now(timezone.utc) - timedelta(seconds=10)
        signal.max_price_after_exit = Decimal("110")
        signal.min_price_after_exit = Decimal("105")  # Initialize min too
        
        # Trigger price = 110 * 0.95 = 104.5
        await reentry_manager.update_price("TESTUSDT", Decimal("104"))  # Below trigger
        
        assert signal.status == "reentered"
        assert signal.reentry_count == 1


class TestDeltaConfirmation:
    """Tests for delta confirmation logic"""
    
    @pytest.mark.asyncio
    async def test_long_positive_delta_confirms(self, reentry_manager):
        """LONG: large_buys > large_sells should confirm"""
        signal = ReentrySignal(
            signal_id=1,
            symbol="TEST",
            exchange="binance",
            side="long",
            original_entry_price=Decimal("100"),
            original_entry_time=datetime.now(timezone.utc),
            last_exit_price=Decimal("105"),
            last_exit_time=datetime.now(timezone.utc),
            last_exit_reason="ts"
        )
        
        reentry_manager.aggtrades_stream.get_large_trade_counts.return_value = (10, 5)
        result = await reentry_manager._check_delta_confirmation(signal)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_long_negative_delta_rejects(self, reentry_manager):
        """LONG: large_buys < large_sells should reject"""
        signal = ReentrySignal(
            signal_id=1,
            symbol="TEST",
            exchange="binance",
            side="long",
            original_entry_price=Decimal("100"),
            original_entry_time=datetime.now(timezone.utc),
            last_exit_price=Decimal("105"),
            last_exit_time=datetime.now(timezone.utc),
            last_exit_reason="ts"
        )
        
        reentry_manager.aggtrades_stream.get_large_trade_counts.return_value = (5, 10)
        result = await reentry_manager._check_delta_confirmation(signal)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_no_stream_allows(self, reentry_manager):
        """Without aggtrades stream, should allow"""
        reentry_manager.aggtrades_stream = None
        
        signal = ReentrySignal(
            signal_id=1,
            symbol="TEST",
            exchange="binance",
            side="long",
            original_entry_price=Decimal("100"),
            original_entry_time=datetime.now(timezone.utc),
            last_exit_price=Decimal("105"),
            last_exit_time=datetime.now(timezone.utc),
            last_exit_reason="ts"
        )
        
        result = await reentry_manager._check_delta_confirmation(signal)
        assert result is True
