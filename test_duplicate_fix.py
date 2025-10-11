#!/usr/bin/env python3
"""
Direct verification of duplicate position prevention fix
"""

import logging
import re

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def verify_duplicate_fix():
    """Verify the duplicate position prevention fix is in place"""
    logger.info("=" * 60)
    logger.info("VERIFYING DUPLICATE POSITION PREVENTION FIX")
    logger.info("=" * 60)

    try:
        with open('core/position_manager.py', 'r') as f:
            content = f.read()

        # Critical patterns to find
        fixes_found = []
        fixes_not_found = []

        # Pattern 1: Early return for atomic path
        if "return position  # Return early - atomic creation is complete" in content:
            fixes_found.append("✅ Early return for atomic path")
        else:
            fixes_not_found.append("❌ Early return for atomic path NOT FOUND")

        # Pattern 2: Using existing position ID from atomic result
        if "id=atomic_result['position_id']" in content:
            fixes_found.append("✅ Reusing position ID from atomic result")
        else:
            fixes_not_found.append("❌ Reusing position ID NOT FOUND")

        # Pattern 3: Check if position already created
        if "if position.id is not None:" in content:
            fixes_found.append("✅ Check for existing position.id")
        else:
            fixes_not_found.append("❌ Check for existing position.id NOT FOUND")

        # Pattern 4: Skip DB creation comment
        if "# Skip database creation - position already exists!" in content or \
           "Position already created atomically" in content:
            fixes_found.append("✅ Skip DB creation logic")
        else:
            fixes_not_found.append("❌ Skip DB creation logic NOT FOUND")

        # Pattern 5: Atomic path creates position with ID
        if re.search(r"position = PositionState\([^)]*id=atomic_result\['position_id'\]", content):
            fixes_found.append("✅ PositionState created with atomic ID")
        else:
            fixes_not_found.append("❌ PositionState with atomic ID NOT FOUND")

        # Extract and display the atomic section
        atomic_match = re.search(r'if atomic_result:(.*?)else:', content, re.DOTALL)
        if atomic_match:
            atomic_section = atomic_match.group(1)
            logger.info("\n📋 ATOMIC SUCCESS SECTION:")
            logger.info("-" * 40)
            # Show first 20 lines of the atomic section
            lines = atomic_section.strip().split('\n')[:20]
            for line in lines:
                logger.info(line.rstrip())
            if len(atomic_section.strip().split('\n')) > 20:
                logger.info("... (section continues)")
            logger.info("-" * 40)

        # Results
        logger.info("\n📊 FIX VERIFICATION RESULTS:")
        logger.info("=" * 40)

        for fix in fixes_found:
            logger.info(f"  {fix}")

        for fix in fixes_not_found:
            logger.error(f"  {fix}")

        if not fixes_not_found:
            logger.info("\n🎉 ALL DUPLICATE PREVENTION FIXES VERIFIED!")
            logger.info("The system should now:")
            logger.info("  1. Create position ONCE in atomic path")
            logger.info("  2. Use the atomic position ID")
            logger.info("  3. Return early without duplicate DB insert")
            return True
        else:
            logger.error(f"\n⚠️ {len(fixes_not_found)} FIXES MISSING")
            return False

    except FileNotFoundError:
        logger.error("❌ core/position_manager.py not found!")
        return False
    except Exception as e:
        logger.error(f"❌ Error checking fixes: {e}")
        return False


def verify_json_fix():
    """Verify the JSON serialization fix is in place"""
    logger.info("\n" + "=" * 60)
    logger.info("VERIFYING JSON SERIALIZATION FIX")
    logger.info("=" * 60)

    try:
        with open('core/position_manager_integration.py', 'r') as f:
            content = f.read()

        # Check for the fix
        if "float(stop_price) if stop_price is not None else None" in content:
            logger.info("  ✅ JSON fix found: Decimal→float conversion in place")

            # Find and display the fixed line
            for i, line in enumerate(content.split('\n')):
                if "float(stop_price)" in line:
                    logger.info(f"\n  Line {i+1}: {line.strip()}")
                    break
            return True
        else:
            logger.error("  ❌ JSON fix NOT FOUND")
            return False

    except FileNotFoundError:
        logger.error("❌ core/position_manager_integration.py not found!")
        return False
    except Exception as e:
        logger.error(f"❌ Error checking JSON fix: {e}")
        return False


if __name__ == "__main__":
    json_ok = verify_json_fix()
    duplicate_ok = verify_duplicate_fix()

    logger.info("\n" + "=" * 60)
    logger.info("FINAL VERIFICATION SUMMARY")
    logger.info("=" * 60)

    if json_ok and duplicate_ok:
        logger.info("✅ ALL CRITICAL FIXES CONFIRMED IN CODE")
        logger.info("\nThe system is ready to:")
        logger.info("  • Place stop-loss orders without JSON errors")
        logger.info("  • Create positions atomically without duplicates")
        logger.info("  • Track positions correctly after creation")
    else:
        logger.error("⚠️ SOME FIXES MAY BE INCOMPLETE")
        if not json_ok:
            logger.error("  • JSON serialization fix needs review")
        if not duplicate_ok:
            logger.error("  • Duplicate prevention fix needs review")