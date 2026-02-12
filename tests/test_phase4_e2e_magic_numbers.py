#!/usr/bin/env python3
"""
Phase 4: End-to-end validation of magic numbers fix
"""
import sys
from pathlib import Path
from decimal import Decimal

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_config_loads_correctly():
    """Test config loads all values from .env"""
    from config.settings import config

    # Critical values
    assert config.trading.position_size_usd == Decimal('6')
    assert config.trading.aged_grace_period_hours == 1
    assert config.trading.commission_percent == Decimal('0.05')

    print("✅ Config loads correctly from .env")

def test_no_magic_numbers_in_critical_files():
    """Verify no magic numbers in critical files"""
    import subprocess

    critical_checks = [
        # Phase 1: No 200.0 as default value in signal_processor_websocket
        # Note: 200.0 in comments is OK (documents the fix)
        {
            'file': 'core/signal_processor_websocket.py',
            'pattern': r"get\('size_usd',\s*200\.0\)",
            'should_find': False,
            'description': 'hardcoded 200.0 as default'
        },
        # Phase 2: No os.getenv with numeric defaults
        {
            'file': 'core/aged_position_monitor_v2.py',
            'pattern': r"os\.getenv.*,\s*[0-9]",
            'should_find': False,
            'description': 'os.getenv with numeric defaults'
        },
        # Phase 3: No hardcoded safety margins
        {
            'file': 'core/stop_loss_manager.py',
            'pattern': r"Decimal\('0\.995'\)",
            'should_find': False,
            'description': 'hardcoded 0.995'
        },
    ]

    for check in critical_checks:
        result = subprocess.run(
            ['grep', '-n', check['pattern'], check['file']],
            capture_output=True,
            text=True,
            cwd=str(project_root)
        )

        if check['should_find']:
            assert result.stdout, f"Should find {check['description']} in {check['file']}"
        else:
            assert not result.stdout, f"Should NOT find {check['description']} in {check['file']}"

    print("✅ No magic numbers in critical files")

def test_safety_constants_available():
    """Test safety constants are available"""
    from config.settings import config

    assert hasattr(config, 'safety')
    assert config.safety.STOP_LOSS_SAFETY_MARGIN_PERCENT == Decimal('0.5')
    assert config.safety.POSITION_SIZE_TOLERANCE_PERCENT == Decimal('10.0')

    print("✅ Safety constants available")

def test_all_modules_importable():
    """Test all modified modules can be imported"""
    try:
        from core.signal_processor_websocket import WebSocketSignalProcessor
        from core.position_manager import PositionManager
        from core.aged_position_monitor_v2 import AgedPositionMonitorV2
        from config.settings import config, TradingSafetyConstants

        print("✅ All modules importable")
    except ImportError as e:
        print(f"❌ Import error: {e}")
        raise

if __name__ == '__main__':
    print("=" * 80)
    print("PHASE 4: E2E VALIDATION")
    print("=" * 80)
    print()

    try:
        test_config_loads_correctly()
        test_no_magic_numbers_in_critical_files()
        test_safety_constants_available()
        test_all_modules_importable()

        print()
        print("=" * 80)
        print("✅ ALL E2E TESTS PASSED")
        print("=" * 80)
        print()
        print("Magic numbers fix complete!")
        print()
        print("Summary:")
        print("- Phase 0: Config defaults aligned ✅")
        print("- Phase 1: Critical 200.0 removed ✅")
        print("- Phase 2: os.getenv() centralized ✅")
        print("- Phase 3: Safety constants extracted ✅")
        print("- Phase 4: E2E validation passed ✅")
        print()

    except AssertionError as e:
        print()
        print("=" * 80)
        print(f"❌ E2E TEST FAILED: {e}")
        print("=" * 80)
        sys.exit(1)
