#!/usr/bin/env python3
"""
Phase 3: Verify TradingSafetyConstants class and usage
"""
import sys
from pathlib import Path
from decimal import Decimal

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_safety_constants_exist():
    """Verify TradingSafetyConstants class exists and has correct defaults"""

    from config.settings import TradingSafetyConstants

    constants = TradingSafetyConstants()

    assert constants.STOP_LOSS_SAFETY_MARGIN_PERCENT == Decimal('0.5')
    assert constants.POSITION_SIZE_TOLERANCE_PERCENT == Decimal('10.0')
    assert constants.PRICE_UPDATE_THRESHOLD_PERCENT == Decimal('0.5')
    assert constants.MINIMUM_ACTIVE_BALANCE_USD == Decimal('10.0')
    assert constants.DEFAULT_PRICE_PRECISION == 8
    assert constants.DEFAULT_MIN_QUANTITY == Decimal('0.001')
    assert constants.DEFAULT_TICK_SIZE == Decimal('0.01')
    assert constants.DEFAULT_STEP_SIZE == Decimal('0.001')

    print("✅ Safety constants class exists with correct defaults")

def test_config_has_safety():
    """Verify Config object has safety constants"""

    from config.settings import config

    assert hasattr(config, 'safety'), "Config should have safety attribute"
    assert hasattr(config.safety, 'STOP_LOSS_SAFETY_MARGIN_PERCENT')
    assert hasattr(config.safety, 'POSITION_SIZE_TOLERANCE_PERCENT')
    assert hasattr(config.safety, 'PRICE_UPDATE_THRESHOLD_PERCENT')

    # Test actual values
    assert config.safety.STOP_LOSS_SAFETY_MARGIN_PERCENT == Decimal('0.5')
    assert config.safety.POSITION_SIZE_TOLERANCE_PERCENT == Decimal('10.0')

    print("✅ Config object has safety constants")

def test_no_hardcoded_margins():
    """Verify specific hardcoded patterns were replaced"""
    import subprocess

    # Check stop_loss_manager.py - should not have 0.995 or 1.005 in code
    result = subprocess.run(
        ['grep', '-n', r"Decimal('0\.995')", 'core/stop_loss_manager.py'],
        capture_output=True,
        text=True,
        cwd=str(project_root)
    )
    assert not result.stdout, "Should not have hardcoded 0.995"

    result = subprocess.run(
        ['grep', '-n', r"Decimal('1\.005')", 'core/stop_loss_manager.py'],
        capture_output=True,
        text=True,
        cwd=str(project_root)
    )
    assert not result.stdout, "Should not have hardcoded 1.005"

    # Check position_manager.py - should not have * 1.1 on line 1734
    result = subprocess.run(
        ['grep', '-n', r'\* 1\.1\s*#', 'core/position_manager.py'],
        capture_output=True,
        text=True,
        cwd=str(project_root)
    )
    assert not result.stdout, "Should not have hardcoded * 1.1"

    # Check exchange_manager_enhanced.py - should not have > 0.5 hardcode
    result = subprocess.run(
        ['grep', '-n', r'> 0\.5\s*#.*difference', 'core/exchange_manager_enhanced.py'],
        capture_output=True,
        text=True,
        cwd=str(project_root)
    )
    assert not result.stdout, "Should not have hardcoded > 0.5"

    print("✅ No hardcoded safety margins in code")

if __name__ == '__main__':
    test_safety_constants_exist()
    test_config_has_safety()
    test_no_hardcoded_margins()
    print("\n✅ All Phase 3 tests passed!")
