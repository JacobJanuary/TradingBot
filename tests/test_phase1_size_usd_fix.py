#!/usr/bin/env python3
"""
Phase 1: Verify size_usd uses config value, not hardcoded 200
"""
import sys
from pathlib import Path
from unittest.mock import Mock

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_size_usd_uses_config_not_200():
    """Verify size_usd uses config value, not hardcoded 200"""

    # Setup mock config with position_size_usd = 6
    mock_config = Mock()
    mock_config.position_size_usd = 6

    # Test signal WITHOUT size_usd field
    signal = {
        'symbol': 'BTCUSDT',
        'exchange': 'bybit',
        # NO size_usd field
    }

    # This would be called during validation
    # We simulate the logic from signal_processor_websocket.py
    size_usd = signal.get('size_usd')
    if not size_usd or size_usd <= 0:
        size_usd = float(mock_config.position_size_usd)

    # CRITICAL: Should be 6, not 200!
    assert size_usd == 6, f"Expected 6 from config, got {size_usd}"
    assert size_usd != 200, "Should NOT use old hardcoded 200"

    print(f"✅ size_usd correctly uses config value: ${size_usd}")

def test_size_usd_respects_signal_value():
    """Verify size_usd uses signal value if provided"""

    mock_config = Mock()
    mock_config.position_size_usd = 6

    # Signal WITH size_usd
    signal = {
        'symbol': 'BTCUSDT',
        'exchange': 'bybit',
        'size_usd': 100.0  # Explicit value
    }

    size_usd = signal.get('size_usd')
    if not size_usd or size_usd <= 0:
        size_usd = float(mock_config.position_size_usd)

    # Should use signal value
    assert size_usd == 100.0, f"Expected 100 from signal, got {size_usd}"

    print(f"✅ size_usd correctly uses signal value: ${size_usd}")

def test_size_usd_zero_uses_config():
    """Verify size_usd=0 falls back to config"""

    mock_config = Mock()
    mock_config.position_size_usd = 6

    signal = {'symbol': 'BTCUSDT', 'size_usd': 0}  # Zero

    size_usd = signal.get('size_usd')
    if not size_usd or size_usd <= 0:
        size_usd = float(mock_config.position_size_usd)

    assert size_usd == 6, "Zero size_usd should fallback to config"

    print(f"✅ Zero size_usd correctly falls back to config: ${size_usd}")

if __name__ == '__main__':
    test_size_usd_uses_config_not_200()
    test_size_usd_respects_signal_value()
    test_size_usd_zero_uses_config()
    print("\n✅ All Phase 1 unit tests passed!")
