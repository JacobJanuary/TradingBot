#!/usr/bin/env python3
"""
VERIFICATION: Проверка текущего состояния кода

Цель: Убедиться что мы правильно понимаем текущую реализацию
"""

import re
import sys

def verify_rollback_implementation():
    """
    Проверяем текущую реализацию _rollback_position
    """
    print("=" * 80)
    print("🔍 VERIFICATION: Current _rollback_position implementation")
    print("=" * 80)
    print()

    file_path = 'core/atomic_position_manager.py'

    try:
        with open(file_path, 'r') as f:
            content = f.read()
            lines = content.split('\n')

    except FileNotFoundError:
        print(f"❌ File not found: {file_path}")
        return False

    # Find _rollback_position method
    method_start = None
    for i, line in enumerate(lines):
        if 'async def _rollback_position' in line:
            method_start = i
            break

    if method_start is None:
        print("❌ Method _rollback_position not found!")
        return False

    print(f"✅ Found _rollback_position at line {method_start + 1}")
    print()

    # Extract method signature
    print("📋 Method signature:")
    print()
    signature_lines = []
    i = method_start
    while i < len(lines) and not lines[i].strip().endswith('):'):
        signature_lines.append(lines[i])
        i += 1
    if i < len(lines):
        signature_lines.append(lines[i])

    for line in signature_lines:
        print(f"  {line}")
    print()

    # Check if quantity parameter exists
    has_quantity_param = any('quantity' in line for line in signature_lines)
    if has_quantity_param:
        print("✅ quantity parameter EXISTS in signature")
    else:
        print("❌ quantity parameter NOT FOUND in signature")
        return False

    print()

    # Find the problematic line with create_market_order
    print("🔍 Searching for create_market_order call in rollback...")
    print()

    found_issue = False
    issue_line_num = None

    # Look within the method (next ~200 lines from start)
    method_end = min(method_start + 200, len(lines))

    for i in range(method_start, method_end):
        line = lines[i]

        if 'create_market_order' in line and 'await' in line:
            # Found a create_market_order call
            print(f"  Found at line {i + 1}:")
            print(f"    {lines[i].strip()}")

            # Check next few lines for continuation
            j = i + 1
            while j < len(lines) and j < i + 5:
                if ')' in lines[j]:
                    print(f"    {lines[j].strip()}")
                    break
                else:
                    print(f"    {lines[j].strip()}")
                j += 1

            # Check if it uses entry_order.filled
            context = '\n'.join(lines[i:j+1])
            if 'entry_order.filled' in context:
                print()
                print("  ⚠️  BUG CONFIRMED: Uses entry_order.filled!")
                found_issue = True
                issue_line_num = i + 1
            elif 'quantity' in context and 'entry_order' not in context:
                print()
                print("  ✅ GOOD: Uses quantity parameter")
            else:
                print()
                print("  ⚠️  UNCLEAR: Check manually")

            print()

    if not found_issue:
        print("✅ No obvious bug found (maybe already fixed?)")
        return True
    else:
        print("🎯 BUG LOCATION:")
        print(f"  File: {file_path}")
        print(f"  Line: {issue_line_num}")
        print(f"  Problem: Uses entry_order.filled instead of quantity")
        print()
        return False


def verify_fix_location():
    """
    Показываем точное местоположение фикса
    """
    print("=" * 80)
    print("🎯 FIX LOCATION")
    print("=" * 80)
    print()

    file_path = 'core/atomic_position_manager.py'

    try:
        with open(file_path, 'r') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"❌ File not found: {file_path}")
        return

    # Find the problematic line
    for i, line in enumerate(lines):
        if 'create_market_order' in line and 'entry_order.filled' in line:
            print(f"📍 CURRENT CODE (line {i + 1}):")
            print()
            # Show context: 3 lines before, the line, 3 lines after
            start = max(0, i - 3)
            end = min(len(lines), i + 4)

            for j in range(start, end):
                marker = "👉" if j == i else "  "
                print(f"  {marker} {j + 1:4d} | {lines[j].rstrip()}")

            print()
            print("🔧 SHOULD BE CHANGED TO:")
            print()
            print(f"  {i + 1:4d} | {lines[i].replace('entry_order.filled', 'quantity  # Use original quantity, not filled').rstrip()}")
            print()
            return

    print("⚠️  Could not find exact line with entry_order.filled")


def main():
    print()
    print("🔬 VERIFICATION: Current code state")
    print()

    # Verify current implementation
    has_bug = not verify_rollback_implementation()

    print()

    # Show exact location if bug exists
    if has_bug:
        verify_fix_location()

    # Summary
    print("=" * 80)
    print("📊 VERIFICATION SUMMARY")
    print("=" * 80)
    print()

    if has_bug:
        print("❌ BUG CONFIRMED:")
        print("  - File: core/atomic_position_manager.py")
        print("  - Problem: Uses entry_order.filled=0 instead of quantity")
        print("  - Impact: Rollback fails with Amount 0.0 error")
        print()
        print("🔧 FIX NEEDED:")
        print("  - Change entry_order.filled → quantity")
        print("  - 1 line change")
        print()
        return 1
    else:
        print("✅ CODE LOOKS GOOD:")
        print("  - Either bug already fixed")
        print("  - Or uses quantity parameter correctly")
        print()
        return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
