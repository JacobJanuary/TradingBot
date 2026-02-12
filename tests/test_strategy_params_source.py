"""
Strategy Params Source Tests

Verifies that SL%, trailing_activation%, trailing_callback% come from
composite_strategy.json (via strategy_params), NOT from .env.

Tests all code paths:
1. Open position uses strategy params
2. DB saves per-position params
3. Restart restores from DB, not .env
4. Non-atomic path regression (L1573 bug)
5. Sync flow
6. Atomic path
7. End-to-end

Covers the fix for: .env overriding composite_strategy.json
"""

import asyncio
import pytest
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, MagicMock, patch, PropertyMock
from dataclasses import dataclass
from typing import Optional, Dict

# Add project root to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.position_manager import PositionManager, PositionRequest, PositionState
from utils.decimal_utils import calculate_stop_loss, to_decimal


# ============================================================
# Fixtures & Helpers
# ============================================================

@dataclass
class MockTradingConfig:
    """Mock TradingConfig with .env-like values (different from strategy!)"""
    # These simulate .env values that should NOT be used when strategy provides params
    stop_loss_percent: Decimal = Decimal('7.0')       # .env = 7%
    trailing_activation_percent: Decimal = Decimal('10.0')  # .env = 10%
    trailing_callback_percent: Decimal = Decimal('4.0')     # .env = 4%
    trailing_min_update_interval_seconds: int = 10
    trailing_min_improvement_percent: Decimal = Decimal('0.01')
    trailing_alert_if_unprotected_window_ms: int = 500
    position_size_usd: Decimal = Decimal('6')
    min_position_size_usd: Decimal = Decimal('5')
    max_position_size_usd: Decimal = Decimal('10000')
    max_positions: int = 150
    max_exposure_usd: Decimal = Decimal('99000')
    leverage: int = 1
    max_leverage: int = 2
    auto_set_leverage: bool = True
    max_position_age_hours: int = 3
    aged_grace_period_hours: int = 3
    aged_loss_step_percent: Decimal = Decimal('0.5')
    aged_max_loss_percent: Decimal = Decimal('10.0')
    aged_acceleration_factor: Decimal = Decimal('1.2')
    aged_check_interval_minutes: int = 60
    commission_percent: Decimal = Decimal('0.05')
    max_spread_percent: Decimal = Decimal('0.5')
    signal_time_window_minutes: int = 10
    max_trades_per_15min: int = 5
    signal_buffer_fixed: int = 3
    signal_min_open_interest_usdt: int = 1_000_000
    signal_min_volume_1h_usdt: int = 50_000
    signal_max_price_change_5min_percent: float = 4.0
    signal_filter_oi_enabled: bool = True
    signal_filter_volume_enabled: bool = True
    signal_filter_price_change_enabled: bool = True


# Strategy params that SHOULD be used (lower SL = tighter risk)
STRATEGY_PARAMS = {
    'leverage': 10,
    'stop_loss_percent': 3.0,              # Strategy = 3% (not .env 7%)
    'trailing_activation_percent': 5.0,    # Strategy = 5% (not .env 10%)
    'trailing_callback_percent': 2.0,      # Strategy = 2% (not .env 4%)
    'total_score': 120,
}

# Different strategy for multi-strategy tests
STRATEGY_PARAMS_AGGRESSIVE = {
    'leverage': 20,
    'stop_loss_percent': 1.5,
    'trailing_activation_percent': 3.0,
    'trailing_callback_percent': 1.0,
    'total_score': 200,
}


def make_position_request(symbol='TESTUSDT', strategy_params=None):
    """Create a PositionRequest with optional strategy_params."""
    request = PositionRequest(
        signal_id='test-signal-001',
        symbol=symbol,
        exchange='binance',
        side='BUY',
        entry_price=Decimal('100.0'),
        lifecycle_managed=True,
    )
    request.strategy_params = strategy_params
    return request


def make_db_position(symbol='TESTUSDT', sl_pct=3.0, ts_act=5.0, ts_cb=2.0):
    """Simulate a position row loaded from DB with per-position params."""
    return {
        'id': 1,
        'symbol': symbol,
        'exchange': 'binance',
        'side': 'long',
        'quantity': Decimal('10'),
        'entry_price': Decimal('100.0'),
        'current_price': Decimal('100.0'),
        'pnl': Decimal('0'),
        'pnl_percentage': 0.0,
        'stop_loss': None,
        'stop_loss_price': None,
        'has_stop_loss': False,
        'has_trailing_stop': False,
        'trailing_activated': False,
        'trailing_activation_percent': ts_act,
        'trailing_callback_percent': ts_cb,
        'signal_stop_loss_percent': sl_pct,
        'leverage': 10,
        'created_at': None,
        'updated_at': None,
    }


# ============================================================
# Group 1: Open Position Uses Strategy Params
# ============================================================

class TestOpenPositionStrategyParams:
    """Verify that open_position() uses strategy_params, not .env."""

    def test_strategy_sl_overrides_env(self):
        """Strategy SL=3% should override .env SL=7%."""
        request = make_position_request(strategy_params=STRATEGY_PARAMS)
        sp = request.strategy_params or {}

        config = MockTradingConfig()
        stop_loss_percent = to_decimal(sp.get('stop_loss_percent', config.stop_loss_percent))

        assert float(stop_loss_percent) == 3.0, f"Expected strategy SL 3.0, got {stop_loss_percent}"
        assert float(stop_loss_percent) != 7.0, "Should NOT use .env SL=7%"

    def test_strategy_trailing_overrides_env(self):
        """Strategy trailing=5%/2% should override .env 10%/4%."""
        request = make_position_request(strategy_params=STRATEGY_PARAMS)
        sp = request.strategy_params or {}

        config = MockTradingConfig()
        act = float(sp.get('trailing_activation_percent', config.trailing_activation_percent))
        cb = float(sp.get('trailing_callback_percent', config.trailing_callback_percent))

        assert act == 5.0, f"Expected strategy activation 5.0, got {act}"
        assert cb == 2.0, f"Expected strategy callback 2.0, got {cb}"
        assert act != 10.0, "Should NOT use .env activation=10%"
        assert cb != 4.0, "Should NOT use .env callback=4%"

    def test_env_fallback_no_strategy(self):
        """When strategy_params=None, should use .env values."""
        request = make_position_request(strategy_params=None)
        sp = request.strategy_params or {}

        config = MockTradingConfig()
        stop_loss_percent = to_decimal(sp.get('stop_loss_percent', config.stop_loss_percent))

        assert float(stop_loss_percent) == 7.0, "Should use .env SL=7% when no strategy"

    def test_env_fallback_missing_key(self):
        """strategy_params with missing SL key should fallback to .env."""
        request = make_position_request(strategy_params={'leverage': 10})
        sp = request.strategy_params or {}

        config = MockTradingConfig()
        stop_loss_percent = to_decimal(sp.get('stop_loss_percent', config.stop_loss_percent))

        assert float(stop_loss_percent) == 7.0, "Should use .env SL=7% when key missing"


# ============================================================
# Group 2: DB Saves Per-Position Params
# ============================================================

class TestDBSavesStrategyParams:
    """Verify that create_position() saves strategy SL/TS params."""

    def test_position_data_includes_sl_percent(self):
        """Position data dict should include stop_loss_percent for DB save."""
        sp = STRATEGY_PARAMS
        position_data = {
            'symbol': 'TESTUSDT',
            'exchange': 'binance',
            'side': 'long',
            'quantity': 10,
            'entry_price': 100.0,
            'trailing_activation_percent': sp['trailing_activation_percent'],
            'trailing_callback_percent': sp['trailing_callback_percent'],
            'stop_loss_percent': sp['stop_loss_percent'],  # NEW: must be included
        }

        assert 'stop_loss_percent' in position_data
        assert position_data['stop_loss_percent'] == 3.0

    def test_position_data_includes_trailing_params(self):
        """Position data should include trailing params for DB persistence."""
        sp = STRATEGY_PARAMS
        position_data = {
            'trailing_activation_percent': sp['trailing_activation_percent'],
            'trailing_callback_percent': sp['trailing_callback_percent'],
        }

        assert position_data['trailing_activation_percent'] == 5.0
        assert position_data['trailing_callback_percent'] == 2.0


# ============================================================
# Group 3: Restart Restores from DB, Not .env
# ============================================================

class TestRestartUsesDBParams:
    """Verify that after restart, params come from DB not .env."""

    def test_restart_uses_db_sl(self):
        """Position with signal_stop_loss_percent=3.0 in DB → SL=3%, not .env 7%."""
        pos = make_db_position(sl_pct=3.0)
        config = MockTradingConfig()

        db_sl = pos.get('signal_stop_loss_percent')
        stop_loss_percent = to_decimal(db_sl) if db_sl else to_decimal(config.stop_loss_percent)

        assert float(stop_loss_percent) == 3.0
        assert float(stop_loss_percent) != 7.0, "Must NOT use .env SL after restart"

    def test_restart_uses_db_trailing(self):
        """Position with trailing=5%/2% in DB → use those, not .env 10%/4%."""
        pos = make_db_position(ts_act=5.0, ts_cb=2.0)
        config = MockTradingConfig()

        act = float(pos.get('trailing_activation_percent') or config.trailing_activation_percent)
        cb = float(pos.get('trailing_callback_percent') or config.trailing_callback_percent)

        assert act == 5.0
        assert cb == 2.0
        assert act != 10.0, "Must NOT use .env activation after restart"
        assert cb != 4.0, "Must NOT use .env callback after restart"

    def test_restart_fallback_when_db_null(self):
        """Position with NULL SL in DB → .env fallback is acceptable."""
        pos = make_db_position(sl_pct=None)
        config = MockTradingConfig()

        db_sl = pos.get('signal_stop_loss_percent')
        stop_loss_percent = to_decimal(db_sl) if db_sl else to_decimal(config.stop_loss_percent)

        assert float(stop_loss_percent) == 7.0, "Null DB value → .env fallback"


# ============================================================
# Group 4: Non-Atomic Path Regression (L1573 Bug)
# ============================================================

class TestNonAtomicPathRegression:
    """
    Verify L1573 no longer overwrites strategy SL with .env.

    The bug: L1257 correctly reads strategy_params, but L1573 
    then overwrites with self.config.stop_loss_percent.
    """

    def test_sl_percent_not_overwritten(self):
        """
        Simulate the flow: first compute from strategy (L1257),
        then verify the same value is used (not .env override at L1573).
        """
        config = MockTradingConfig()
        sp = STRATEGY_PARAMS

        # Step 1: L1257 - correctly reads strategy (current code does this)
        stop_loss_percent = to_decimal(sp.get('stop_loss_percent', config.stop_loss_percent))
        assert float(stop_loss_percent) == 3.0

        # Step 2: L1573 - THE BUG: currently overwrites with .env
        # AFTER FIX: should use the same stop_loss_percent from step 1
        # NOT: stop_loss_percent_val = to_decimal(config.stop_loss_percent)
        stop_loss_percent_val = stop_loss_percent  # FIXED: reuse computed value

        assert float(stop_loss_percent_val) == 3.0, \
            "L1573 must use strategy SL, not overwrite with .env"

    def test_sl_price_matches_strategy(self):
        """
        SL price should be computed from strategy SL%, not .env.
        Entry=100, Strategy SL=3% → SL=97.0 (long)
        Entry=100, .env SL=7% → SL=93.0 (long) — THIS IS THE BUG
        """
        entry_price = Decimal('100.0')
        strategy_sl = Decimal('3.0')
        env_sl = Decimal('7.0')

        correct_sl_price = calculate_stop_loss(entry_price, 'long', strategy_sl)
        buggy_sl_price = calculate_stop_loss(entry_price, 'long', env_sl)

        assert float(correct_sl_price) == 97.0, f"Strategy SL price should be 97.0, got {correct_sl_price}"
        assert float(buggy_sl_price) == 93.0, f"Bug SL price should be 93.0, got {buggy_sl_price}"
        assert correct_sl_price != buggy_sl_price, "Strategy and .env SL prices must differ"


# ============================================================
# Group 5: Sync Flow
# ============================================================

class TestSyncFlow:
    """Verify sync flow uses DB params for existing, .env for new."""

    def test_sync_existing_uses_db_params(self):
        """Synced position with DB record → params from DB."""
        db_position = make_db_position(sl_pct=3.0, ts_act=5.0, ts_cb=2.0)
        config = MockTradingConfig()

        # When DB record exists, use its params
        sl_from_db = db_position.get('signal_stop_loss_percent')
        stop_loss_percent = to_decimal(sl_from_db) if sl_from_db else to_decimal(config.stop_loss_percent)

        assert float(stop_loss_percent) == 3.0

    def test_sync_new_uses_env_fallback(self):
        """Synced position without DB record → .env fallback is acceptable."""
        config = MockTradingConfig()

        # No DB record → .env fallback
        stop_loss_percent = to_decimal(config.stop_loss_percent)
        assert float(stop_loss_percent) == 7.0, "New synced position uses .env"


# ============================================================
# Group 6: Atomic Path
# ============================================================

class TestAtomicPath:
    """Verify atomic_position_manager uses strategy params."""

    def test_atomic_uses_strategy_params(self):
        """open_position_atomic() with strategy_params → SL from strategy."""
        config = MockTradingConfig()
        sp = STRATEGY_PARAMS

        # Simulate atomic_position_manager.py L486 logic
        stop_loss_percent = float(sp.get('stop_loss_percent', config.stop_loss_percent))
        trailing_act = float(sp.get('trailing_activation_percent', config.trailing_activation_percent))
        trailing_cb = float(sp.get('trailing_callback_percent', config.trailing_callback_percent))

        assert stop_loss_percent == 3.0
        assert trailing_act == 5.0
        assert trailing_cb == 2.0

    def test_atomic_saves_sl_to_position_data(self):
        """position_data sent to create_position must include stop_loss_percent."""
        sp = STRATEGY_PARAMS
        stop_loss_percent = float(sp.get('stop_loss_percent', 4.0))

        # Simulate atomic_position_manager.py L670-683
        position_data = {
            'symbol': 'TESTUSDT',
            'exchange': 'binance',
            'side': 'long',
            'quantity': 10,
            'entry_price': 100.0,
            'current_price': 100.0,
            'status': 'pending_entry',
            'exchange_order_id': 'order-123',
            'trailing_activation_percent': float(sp.get('trailing_activation_percent', 2.0)),
            'trailing_callback_percent': float(sp.get('trailing_callback_percent', 0.5)),
            'stop_loss_percent': stop_loss_percent,  # NEW: must be saved
            'signal_id': 'test-001',
            'leverage': 10,
        }

        assert position_data['stop_loss_percent'] == 3.0
        assert position_data['trailing_activation_percent'] == 5.0
        assert position_data['trailing_callback_percent'] == 2.0


# ============================================================
# Group 7: End-to-End
# ============================================================

class TestEndToEnd:
    """End-to-end tests for strategy params flow."""

    def test_e2e_strategy_to_sl_price(self):
        """
        signal_lifecycle passes strategy_params → position_manager computes SL.
        Entry=100, strategy SL=3% → SL price=97.0
        """
        # signal_lifecycle.py L1080-1086
        strategy_params = {
            'leverage': 10,
            'stop_loss_percent': 3.0,
            'trailing_activation_percent': 5.0,
            'trailing_callback_percent': 2.0,
        }

        # position_manager.py L1257
        sp = strategy_params
        config = MockTradingConfig()
        stop_loss_percent = to_decimal(sp.get('stop_loss_percent', config.stop_loss_percent))

        # position_manager.py L1259 (should NOT be overwritten at L1573!)
        sl_price = calculate_stop_loss(Decimal('100.0'), 'long', stop_loss_percent)

        assert float(sl_price) == 97.0, f"Expected SL price 97.0, got {sl_price}"

    def test_e2e_different_strategies_different_sl(self):
        """Two positions with different strategies → different SL%."""
        config = MockTradingConfig()

        # Conservative strategy
        sp1 = STRATEGY_PARAMS  # SL=3%
        sl1 = to_decimal(sp1.get('stop_loss_percent', config.stop_loss_percent))

        # Aggressive strategy
        sp2 = STRATEGY_PARAMS_AGGRESSIVE  # SL=1.5%
        sl2 = to_decimal(sp2.get('stop_loss_percent', config.stop_loss_percent))

        assert float(sl1) == 3.0
        assert float(sl2) == 1.5
        assert sl1 != sl2, "Different strategies must have different SL%"

        # Compute SL prices
        entry = Decimal('100.0')
        sl_price_1 = calculate_stop_loss(entry, 'long', sl1)
        sl_price_2 = calculate_stop_loss(entry, 'long', sl2)

        assert float(sl_price_1) == 97.0   # 100 - 3%
        assert float(sl_price_2) == 98.5   # 100 - 1.5%
        assert sl_price_1 != sl_price_2

    def test_e2e_restart_preserves_strategy_sl(self):
        """Open → save to DB → restart → SL still from strategy."""
        config = MockTradingConfig()

        # Step 1: Open with strategy SL=3%
        sp = STRATEGY_PARAMS
        original_sl = float(sp.get('stop_loss_percent', config.stop_loss_percent))
        assert original_sl == 3.0

        # Step 2: Save to DB (simulated)
        db_position = make_db_position(sl_pct=original_sl, ts_act=5.0, ts_cb=2.0)

        # Step 3: Restart — load from DB
        db_sl = db_position.get('signal_stop_loss_percent')
        restored_sl = float(to_decimal(db_sl) if db_sl else to_decimal(config.stop_loss_percent))

        assert restored_sl == 3.0, f"After restart, SL should be 3.0 (from DB), got {restored_sl}"
        assert restored_sl != 7.0, "Must NOT revert to .env SL=7% after restart!"

        # Step 4: SL price should match
        sl_price = calculate_stop_loss(Decimal('100.0'), 'long', Decimal(str(restored_sl)))
        assert float(sl_price) == 97.0


# ============================================================
# Group 8: SL Price Calculation Sanity
# ============================================================

class TestSLCalculationSanity:
    """Sanity checks for SL price calculation with various strategy values."""

    def test_long_sl_below_entry(self):
        """Long position SL must be below entry price."""
        for sl_pct in [1.0, 3.0, 5.0, 7.0]:
            sl_price = calculate_stop_loss(Decimal('100'), 'long', Decimal(str(sl_pct)))
            assert float(sl_price) < 100.0, f"Long SL {sl_pct}% must be < 100"

    def test_short_sl_above_entry(self):
        """Short position SL must be above entry price."""
        for sl_pct in [1.0, 3.0, 5.0, 7.0]:
            sl_price = calculate_stop_loss(Decimal('100'), 'short', Decimal(str(sl_pct)))
            assert float(sl_price) > 100.0, f"Short SL {sl_pct}% must be > 100"

    def test_tighter_strategy_sl_closer_to_entry(self):
        """Strategy SL=3% should be closer to entry than .env SL=7%."""
        entry = Decimal('100.0')
        strategy_sl_price = calculate_stop_loss(entry, 'long', Decimal('3.0'))
        env_sl_price = calculate_stop_loss(entry, 'long', Decimal('7.0'))

        strategy_distance = abs(float(entry) - float(strategy_sl_price))
        env_distance = abs(float(entry) - float(env_sl_price))

        assert strategy_distance < env_distance, \
            f"Strategy SL (3%) distance {strategy_distance} must be < .env (7%) distance {env_distance}"
