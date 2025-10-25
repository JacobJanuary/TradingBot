#!/usr/bin/env python3
"""
Phase 2: Verify no os.getenv() with numeric defaults in core files
"""
import sys
from pathlib import Path
import subprocess

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_no_magic_number_getenv_in_core():
    """Verify no os.getenv() with numeric defaults in core files"""

    # Files that were updated in Phase 2
    files_to_check = [
        'core/aged_position_monitor_v2.py',
        'core/aged_position_manager.py',
        'core/exchange_manager_enhanced.py',
        'core/position_manager.py',
    ]

    found_issues = []

    for file_path in files_to_check:
        # Search for pattern: os.getenv('...', NUMBER)
        result = subprocess.run(
            ['grep', '-n', r"os\.getenv.*,\s*[0-9]", file_path],
            capture_output=True,
            text=True,
            cwd=str(project_root)
        )

        if result.stdout:
            lines = result.stdout.strip().split('\n')
            # Filter out acceptable patterns (WebSocket config, etc.)
            problematic_lines = [l for l in lines
                                if 'SIGNAL_WS_' not in l
                                and 'WAVE_CHECK_' not in l
                                and l.strip()]

            if problematic_lines:
                found_issues.append(f"\n{file_path}:")
                for line in problematic_lines:
                    found_issues.append(f"  {line}")

    if found_issues:
        print("❌ Found os.getenv() with numeric defaults:")
        for issue in found_issues:
            print(issue)
        assert False, "Should not have os.getenv() with numeric defaults in updated files"

    print("✅ No os.getenv() with numeric defaults in Phase 2 files")

def test_all_aged_params_use_config():
    """Verify all aged position files import correctly after changes"""

    try:
        # These should work after Phase 2 changes
        from core.aged_position_monitor_v2 import AgedPositionMonitorV2
        from core.aged_position_manager import AgedPositionManager

        print("✅ All aged modules import successfully")
    except ImportError as e:
        print(f"❌ Import error: {e}")
        raise

if __name__ == '__main__':
    test_no_magic_number_getenv_in_core()
    test_all_aged_params_use_config()
    print("\n✅ All Phase 2 tests passed!")
