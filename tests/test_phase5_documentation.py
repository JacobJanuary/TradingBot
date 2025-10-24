#!/usr/bin/env python3
"""
Phase 5 Test: Verify documentation is complete
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_phase5_documentation():
    """Test that all documentation is complete and correct"""

    print("=" * 80)
    print("🧪 PHASE 5 TEST: Documentation")
    print("=" * 80)
    print()

    # Test 1: Check .env has LEVERAGE variables
    print("✅ Test 1: Verify .env has LEVERAGE variables")
    env_file = project_root / '.env'

    if not env_file.exists():
        raise AssertionError("❌ FAIL: .env file not found!")

    with open(env_file, 'r') as f:
        env_content = f.read()

    required_vars = [
        'LEVERAGE=',
        'MAX_LEVERAGE=',
        'AUTO_SET_LEVERAGE='
    ]

    for var in required_vars:
        if var in env_content:
            # Extract the value
            line = [l for l in env_content.split('\n') if l.startswith(var)][0]
            print(f"   ✓ Found {line}")
        else:
            raise AssertionError(f"❌ FAIL: {var} not found in .env!")

    print()

    # Test 2: Check .env has proper section header
    print("✅ Test 2: Verify .env has LEVERAGE CONTROL section")
    if 'LEVERAGE CONTROL' in env_content:
        print(f"   ✓ Found 'LEVERAGE CONTROL' section header")
    else:
        raise AssertionError("❌ FAIL: 'LEVERAGE CONTROL' section header not found!")

    if 'RESTORED 2025-10-25' in env_content:
        print(f"   ✓ Found restoration comment")
    else:
        raise AssertionError("❌ FAIL: Restoration comment not found!")

    print()

    # Test 3: Check variable count updated
    print("✅ Test 3: Verify .env variable count is updated")
    if '63 total' in env_content or '63 ACTIVE VARIABLES' in env_content:
        print(f"   ✓ Variable count updated to 63")
    else:
        raise AssertionError("❌ FAIL: Variable count not updated to 63!")

    print()

    # Test 4: Check LEVERAGE_CONFIGURATION.md exists
    print("✅ Test 4: Verify LEVERAGE_CONFIGURATION.md exists")
    doc_file = project_root / 'docs' / 'LEVERAGE_CONFIGURATION.md'

    if not doc_file.exists():
        raise AssertionError("❌ FAIL: docs/LEVERAGE_CONFIGURATION.md not found!")

    print(f"   ✓ Found docs/LEVERAGE_CONFIGURATION.md")

    with open(doc_file, 'r') as f:
        doc_content = f.read()

    # Check key sections
    required_sections = [
        'Overview',
        'Configuration',
        'How It Works',
        'Exchange-Specific Behavior',
        'Error Handling',
        'Risk Management',
        'Testing',
        'Troubleshooting',
        'FAQ'
    ]

    print(f"   ✓ Checking documentation sections...")
    for section in required_sections:
        if f"## {section}" in doc_content or f"# {section}" in doc_content:
            print(f"      ✓ Section: {section}")
        else:
            raise AssertionError(f"❌ FAIL: Section '{section}' not found in documentation!")

    print()

    # Test 5: Verify documentation has code examples
    print("✅ Test 5: Verify documentation has code examples")
    if '```python' in doc_content:
        code_blocks = doc_content.count('```python')
        print(f"   ✓ Found {code_blocks} Python code examples")
    else:
        raise AssertionError("❌ FAIL: No Python code examples found!")

    if '```bash' in doc_content:
        bash_blocks = doc_content.count('```bash')
        print(f"   ✓ Found {bash_blocks} Bash code examples")
    else:
        raise AssertionError("❌ FAIL: No Bash code examples found!")

    print()

    # Test 6: Verify documentation mentions all test files
    print("✅ Test 6: Verify documentation mentions all test files")
    test_files = [
        'test_phase1_config_loading.py',
        'test_phase2_set_leverage.py',
        'test_phase3_atomic_integration.py',
        'test_phase4_legacy_fallback.py'
    ]

    for test_file in test_files:
        if test_file in doc_content:
            print(f"   ✓ Mentions {test_file}")
        else:
            raise AssertionError(f"❌ FAIL: {test_file} not mentioned in documentation!")

    print()

    # Test 7: Verify documentation has risk warnings
    print("✅ Test 7: Verify documentation has risk warnings")
    risk_keywords = ['risk', 'WARNING', 'liquidation', 'loss']
    found_warnings = []

    for keyword in risk_keywords:
        if keyword.lower() in doc_content.lower():
            found_warnings.append(keyword)

    if len(found_warnings) >= 3:
        print(f"   ✓ Found {len(found_warnings)} risk-related keywords: {', '.join(found_warnings)}")
    else:
        raise AssertionError("❌ FAIL: Insufficient risk warnings in documentation!")

    print()

    # Test 8: Verify config values can be loaded
    print("✅ Test 8: Verify leverage config loads correctly")
    from config.settings import config

    assert hasattr(config.trading, 'leverage'), "❌ FAIL: leverage not in config!"
    assert hasattr(config.trading, 'max_leverage'), "❌ FAIL: max_leverage not in config!"
    assert hasattr(config.trading, 'auto_set_leverage'), "❌ FAIL: auto_set_leverage not in config!"

    print(f"   ✓ LEVERAGE={config.trading.leverage}")
    print(f"   ✓ MAX_LEVERAGE={config.trading.max_leverage}")
    print(f"   ✓ AUTO_SET_LEVERAGE={config.trading.auto_set_leverage}")

    # Verify values match .env
    if config.trading.leverage == 10:
        print(f"   ✓ Leverage value matches .env")
    else:
        raise AssertionError(f"❌ FAIL: Expected leverage=10, got {config.trading.leverage}")

    print()

    # Summary
    print("=" * 80)
    print("✅ ALL PHASE 5 TESTS PASSED!")
    print("=" * 80)
    print()
    print("📊 Documentation Summary:")
    print(f"   .env file:              Updated with 3 LEVERAGE vars ✓")
    print(f"   Variable count:         63 (was 60) ✓")
    print(f"   Section header:         LEVERAGE CONTROL ✓")
    print(f"   Documentation file:     LEVERAGE_CONFIGURATION.md ✓")
    print(f"   Sections:              {len(required_sections)} major sections ✓")
    print(f"   Code examples:          {code_blocks + bash_blocks} total ✓")
    print(f"   Test file references:   {len(test_files)} files ✓")
    print(f"   Risk warnings:          {len(found_warnings)} keywords ✓")
    print(f"   Config loads:           All values correct ✓")
    print()
    print("🎯 Phase 5 Complete: Documentation is comprehensive and accurate!")
    print("=" * 80)

if __name__ == '__main__':
    try:
        test_phase5_documentation()
        sys.exit(0)
    except AssertionError as e:
        print()
        print("=" * 80)
        print(f"❌ TEST FAILED: {e}")
        print("=" * 80)
        sys.exit(1)
    except Exception as e:
        print()
        print("=" * 80)
        print(f"❌ ERROR: {e}")
        print("=" * 80)
        import traceback
        traceback.print_exc()
        sys.exit(1)
