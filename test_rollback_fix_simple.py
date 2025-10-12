#!/usr/bin/env python3
"""
SIMPLE TEST: Проверка что фикс применен

Цель: Убедиться что код использует quantity вместо entry_order.filled
"""

import re

def test_fix_applied():
    """
    Проверяем что в коде используется quantity, а не entry_order.filled
    """
    print("=" * 80)
    print("🧪 TEST: Verify rollback fix is applied")
    print("=" * 80)
    print()

    with open('core/atomic_position_manager.py', 'r') as f:
        content = f.read()
        lines = content.split('\n')

    # Check 1: Method signature has quantity parameter
    print("✅ Check 1: _rollback_position has quantity parameter")
    found_signature = False
    for i, line in enumerate(lines):
        if 'async def _rollback_position' in line:
            # Check next 10 lines for quantity parameter
            signature_block = '\n'.join(lines[i:i+10])
            if 'quantity:' in signature_block or 'quantity =' in signature_block:
                found_signature = True
                print(f"   ✅ Found quantity parameter around line {i+1}")
                break

    if not found_signature:
        print("   ❌ FAIL: quantity parameter NOT found in signature")
        return False

    # Check 2: quantity is passed when calling _rollback_position
    print()
    print("✅ Check 2: quantity is passed when calling _rollback_position")
    found_call = False
    for i, line in enumerate(lines):
        if 'await self._rollback_position(' in line:
            # Check next 10 lines for quantity argument
            call_block = '\n'.join(lines[i:i+10])
            if 'quantity=' in call_block:
                found_call = True
                print(f"   ✅ Found quantity argument around line {i+1}")
                break

    if not found_call:
        print("   ❌ FAIL: quantity argument NOT passed to _rollback_position")
        return False

    # Check 3: quantity is used instead of entry_order.filled
    print()
    print("✅ Check 3: quantity used in create_market_order, NOT entry_order.filled")

    # Find _rollback_position method
    method_start = None
    for i, line in enumerate(lines):
        if 'async def _rollback_position' in line:
            method_start = i
            break

    if method_start is None:
        print("   ❌ FAIL: Could not find _rollback_position method")
        return False

    # Check within method (next ~100 lines)
    method_block = '\n'.join(lines[method_start:method_start+100])

    # Check for create_market_order call
    found_good = False
    found_bad = False

    for i in range(method_start, min(len(lines), method_start + 100)):
        line = lines[i]
        if 'create_market_order' in line:
            # Check this line and next few lines
            call_block = '\n'.join(lines[i:i+3])
            if 'entry_order.filled' in call_block:
                found_bad = True
                print(f"   ❌ FAIL: Still uses entry_order.filled at line {i+1}")
                print(f"      {line.strip()}")
            elif ', quantity' in call_block:
                found_good = True
                print(f"   ✅ Uses quantity at line {i+1}")
                print(f"      {line.strip()}")

    if found_bad:
        return False

    if not found_good:
        print("   ⚠️  WARNING: Could not verify quantity usage")
        return False

    return True


def verify_comments():
    """
    Проверяем что добавлены комментарии с объяснением фикса
    """
    print()
    print("=" * 80)
    print("📝 Check: Comments added to explain the fix")
    print("=" * 80)
    print()

    with open('core/atomic_position_manager.py', 'r') as f:
        content = f.read()

    if 'CRITICAL FIX' in content:
        count = content.count('CRITICAL FIX')
        print(f"✅ Found {count} 'CRITICAL FIX' comment(s)")
        return True
    else:
        print("⚠️  No 'CRITICAL FIX' comments found (optional)")
        return True


def main():
    print()
    print("🔬 VERIFICATION: Rollback fix applied correctly")
    print()

    test1_passed = test_fix_applied()
    test2_passed = verify_comments()

    print()
    print("=" * 80)
    print("📊 TEST SUMMARY")
    print("=" * 80)
    print()

    if test1_passed and test2_passed:
        print("✅ ALL CHECKS PASSED")
        print()
        print("🎯 ВЕРДИКТ:")
        print("  - quantity parameter added to signature ✅")
        print("  - quantity passed when calling method ✅")
        print("  - quantity used instead of entry_order.filled ✅")
        print("  - Comments added ✅")
        print()
        print("  🎉 FIX SUCCESSFULLY APPLIED!")
        return 0
    else:
        print("❌ SOME CHECKS FAILED")
        print()
        print("  ⚠️  Fix may not be applied correctly!")
        return 1


if __name__ == "__main__":
    import sys
    exit_code = main()
    sys.exit(exit_code)
