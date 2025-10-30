#!/usr/bin/env python3
"""
Test script to verify signal filter configuration loads correctly from .env
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from config.settings import Config

def test_signal_filter_config():
    """Test that signal filter settings load from .env correctly."""
    print("=" * 80)
    print("🧪 TESTING SIGNAL FILTER CONFIGURATION")
    print("=" * 80)

    # Load settings
    settings = Config()
    config = settings.trading

    print("\n📋 LOADED VALUES:")
    print(f"  signal_min_open_interest_usdt: {config.signal_min_open_interest_usdt}")
    print(f"  signal_min_volume_1h_usdt: {config.signal_min_volume_1h_usdt}")
    print(f"  signal_max_price_change_5min_percent: {config.signal_max_price_change_5min_percent}")
    print(f"  signal_filter_oi_enabled: {config.signal_filter_oi_enabled}")
    print(f"  signal_filter_volume_enabled: {config.signal_filter_volume_enabled}")
    print(f"  signal_filter_price_change_enabled: {config.signal_filter_price_change_enabled}")

    print("\n📋 EXPECTED VALUES FROM .env:")
    print(f"  SIGNAL_MIN_OPEN_INTEREST_USDT: {os.getenv('SIGNAL_MIN_OPEN_INTEREST_USDT', 'NOT SET')}")
    print(f"  SIGNAL_MIN_VOLUME_1H_USDT: {os.getenv('SIGNAL_MIN_VOLUME_1H_USDT', 'NOT SET')}")
    print(f"  SIGNAL_MAX_PRICE_CHANGE_5MIN_PERCENT: {os.getenv('SIGNAL_MAX_PRICE_CHANGE_5MIN_PERCENT', 'NOT SET')}")
    print(f"  SIGNAL_FILTER_OI_ENABLED: {os.getenv('SIGNAL_FILTER_OI_ENABLED', 'NOT SET')}")
    print(f"  SIGNAL_FILTER_VOLUME_ENABLED: {os.getenv('SIGNAL_FILTER_VOLUME_ENABLED', 'NOT SET')}")
    print(f"  SIGNAL_FILTER_PRICE_CHANGE_ENABLED: {os.getenv('SIGNAL_FILTER_PRICE_CHANGE_ENABLED', 'NOT SET')}")

    print("\n🔍 VALIDATION:")

    # Validate SIGNAL_MIN_VOLUME_1H_USDT (the one user reported)
    expected_volume = int(os.getenv('SIGNAL_MIN_VOLUME_1H_USDT', '50000'))
    if config.signal_min_volume_1h_usdt == expected_volume:
        print(f"  ✅ signal_min_volume_1h_usdt matches .env: {expected_volume}")
    else:
        print(f"  ❌ signal_min_volume_1h_usdt MISMATCH!")
        print(f"     Expected: {expected_volume}")
        print(f"     Got: {config.signal_min_volume_1h_usdt}")

    # Validate SIGNAL_MIN_OPEN_INTEREST_USDT
    expected_oi = int(os.getenv('SIGNAL_MIN_OPEN_INTEREST_USDT', '1000000'))
    if config.signal_min_open_interest_usdt == expected_oi:
        print(f"  ✅ signal_min_open_interest_usdt matches .env: {expected_oi}")
    else:
        print(f"  ❌ signal_min_open_interest_usdt MISMATCH!")
        print(f"     Expected: {expected_oi}")
        print(f"     Got: {config.signal_min_open_interest_usdt}")

    # Validate SIGNAL_MAX_PRICE_CHANGE_5MIN_PERCENT
    expected_price_change = float(os.getenv('SIGNAL_MAX_PRICE_CHANGE_5MIN_PERCENT', '4.0'))
    if config.signal_max_price_change_5min_percent == expected_price_change:
        print(f"  ✅ signal_max_price_change_5min_percent matches .env: {expected_price_change}")
    else:
        print(f"  ❌ signal_max_price_change_5min_percent MISMATCH!")
        print(f"     Expected: {expected_price_change}")
        print(f"     Got: {config.signal_max_price_change_5min_percent}")

    print("\n" + "=" * 80)
    print("✅ TEST COMPLETE")
    print("=" * 80)

if __name__ == '__main__':
    test_signal_filter_config()
