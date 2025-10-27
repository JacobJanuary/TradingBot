#!/usr/bin/env python3
"""
Phase 0: Verify TradingConfig defaults match current .env values
"""
import sys
from pathlib import Path
from decimal import Decimal

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_config_defaults_match_env():
    """Verify TradingConfig defaults match current .env values"""
    from config.settings import TradingConfig

    config = TradingConfig()

    # Critical defaults
    assert config.position_size_usd == Decimal('6'), "position_size_usd should default to 6"
    assert config.aged_grace_period_hours == 1, "aged_grace_period_hours should default to 1"
    assert config.commission_percent == Decimal('0.05'), "commission_percent should default to 0.05"
    assert config.max_positions == 150, "max_positions should default to 150"
    assert config.max_exposure_usd == Decimal('99000'), "max_exposure_usd should default to 99000"

    # Additional defaults from plan
    assert config.min_position_size_usd == Decimal('5'), "min_position_size_usd should default to 5"
    assert config.trailing_activation_percent == Decimal('2.0'), "trailing_activation_percent should default to 2.0"
    assert config.leverage == 1, "leverage should default to 1"
    assert config.max_leverage == 2, "max_leverage should default to 2"
    assert config.trailing_min_update_interval_seconds == 30, "trailing_min_update_interval_seconds should default to 30"
    assert config.trailing_min_improvement_percent == Decimal('0.05'), "trailing_min_improvement_percent should default to 0.05"
    assert config.trailing_alert_if_unprotected_window_ms == 300, "trailing_alert_if_unprotected_window_ms should default to 300"
    assert config.max_trades_per_15min == 5, "max_trades_per_15min should default to 5"
    assert config.signal_buffer_fixed == 3, "signal_buffer_fixed should default to 3"

    print("✅ All config defaults match .env values")

if __name__ == '__main__':
    test_config_defaults_match_env()
