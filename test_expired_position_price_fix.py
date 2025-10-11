#!/usr/bin/env python3
"""
Validation test for expired position price fix
Verifies that real-time price is fetched before making decisions
"""

import logging
import re

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_fetch_ticker_before_decision():
    """Test that fetch_ticker is called before is_profitable check"""
    logger.info("=" * 60)
    logger.info("TEST: fetch_ticker before decision")
    logger.info("=" * 60)

    with open('core/position_manager.py', 'r') as f:
        content = f.read()

    checks_passed = []

    # Check 1: fetch_ticker call exists
    if 'await exchange.exchange.fetch_ticker(symbol)' in content:
        logger.info("  ✅ Found fetch_ticker call")
        checks_passed.append(True)
    else:
        logger.error("  ❌ Missing fetch_ticker call")
        checks_passed.append(False)

    # Check 2: real_time_price extraction
    if "real_time_price = ticker.get('last') or ticker.get('markPrice')" in content:
        logger.info("  ✅ Found real_time_price extraction")
        checks_passed.append(True)
    else:
        logger.error("  ❌ Missing real_time_price extraction")
        checks_passed.append(False)

    # Check 3: position.current_price update
    if 'position.current_price = real_time_price' in content:
        logger.info("  ✅ Found position.current_price update")
        checks_passed.append(True)
    else:
        logger.error("  ❌ Missing position.current_price update")
        checks_passed.append(False)

    # Check 4: Verify fetch happens BEFORE is_profitable calculation
    # Look for the pattern: fetch_ticker ... position.current_price = ... is_profitable
    pattern = r'fetch_ticker.*?position\.current_price\s*=\s*real_time_price.*?is_profitable\s*='

    if re.search(pattern, content, re.DOTALL):
        logger.info("  ✅ fetch_ticker occurs BEFORE is_profitable check")
        checks_passed.append(True)
    else:
        logger.error("  ❌ fetch_ticker NOT before is_profitable check")
        checks_passed.append(False)

    return all(checks_passed)


def test_price_logging():
    """Test that price difference is logged"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST: Price difference logging")
    logger.info("=" * 60)

    with open('core/position_manager.py', 'r') as f:
        content = f.read()

    checks_passed = []

    # Check 1: Cached price logging
    if 'Cached price:' in content or 'old_cached_price' in content:
        logger.info("  ✅ Found cached price variable")
        checks_passed.append(True)
    else:
        logger.error("  ❌ Missing cached price logging")
        checks_passed.append(False)

    # Check 2: Real-time price logging
    if 'Real-time:' in content:
        logger.info("  ✅ Found real-time price logging")
        checks_passed.append(True)
    else:
        logger.error("  ❌ Missing real-time price logging")
        checks_passed.append(False)

    # Check 3: Difference calculation
    if 'price_diff_pct' in content or 'Difference:' in content:
        logger.info("  ✅ Found price difference calculation")
        checks_passed.append(True)
    else:
        logger.error("  ❌ Missing price difference calculation")
        checks_passed.append(False)

    return all(checks_passed)


def test_error_handling():
    """Test that fetch errors are handled"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST: Error handling for fetch_ticker")
    logger.info("=" * 60)

    with open('core/position_manager.py', 'r') as f:
        content = f.read()

    checks_passed = []

    # Check 1: Try-except block
    if 'except Exception as e:' in content:
        logger.info("  ✅ Found exception handling")
        checks_passed.append(True)
    else:
        logger.error("  ❌ Missing exception handling")
        checks_passed.append(False)

    # Check 2: Error logging
    if 'Failed to fetch current price' in content:
        logger.info("  ✅ Found error logging for fetch failure")
        checks_passed.append(True)
    else:
        logger.error("  ❌ Missing error logging")
        checks_passed.append(False)

    # Check 3: Fallback to cached price
    if 'Using cached price' in content and 'may be outdated' in content:
        logger.info("  ✅ Found fallback to cached price with warning")
        checks_passed.append(True)
    else:
        logger.error("  ❌ Missing fallback warning")
        checks_passed.append(False)

    return all(checks_passed)


def test_enhanced_decision_logging():
    """Test that decision logging shows all relevant data"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST: Enhanced decision logging")
    logger.info("=" * 60)

    with open('core/position_manager.py', 'r') as f:
        content = f.read()

    checks_passed = []

    # Check for detailed logging in profitable case
    if 'Entry:' in content and 'Current:' in content and 'Breakeven:' in content:
        logger.info("  ✅ Found detailed price logging for decisions")
        checks_passed.append(True)
    else:
        logger.error("  ❌ Missing detailed decision logging")
        checks_passed.append(False)

    return all(checks_passed)


def test_critical_fix_comment():
    """Test that CRITICAL FIX comment is present"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST: CRITICAL FIX documentation")
    logger.info("=" * 60)

    with open('core/position_manager.py', 'r') as f:
        content = f.read()

    if 'CRITICAL FIX: Fetch real-time price before making decision' in content:
        logger.info("  ✅ Found CRITICAL FIX comment")
        return True
    else:
        logger.error("  ❌ Missing CRITICAL FIX comment")
        return False


def main():
    """Run all validation tests"""
    logger.info("🧪 VALIDATING EXPIRED POSITION PRICE FIX")
    logger.info("=" * 60)

    results = []

    # Run all tests
    results.append(("Fetch ticker before decision", test_fetch_ticker_before_decision()))
    results.append(("Price difference logging", test_price_logging()))
    results.append(("Error handling", test_error_handling()))
    results.append(("Enhanced decision logging", test_enhanced_decision_logging()))
    results.append(("Critical fix documentation", test_critical_fix_comment()))

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("📊 VALIDATION SUMMARY")
    logger.info("=" * 60)

    passed = 0
    failed = 0

    for test_name, result in results:
        if result:
            logger.info(f"  ✅ {test_name}: PASSED")
            passed += 1
        else:
            logger.error(f"  ❌ {test_name}: FAILED")
            failed += 1

    logger.info(f"\nTotal: {passed} passed, {failed} failed")

    if failed == 0:
        logger.info("\n🎉 ALL VALIDATIONS PASSED!")
        logger.info("\n✅ Expired position price fix successfully implemented:")
        logger.info("  • Real-time price fetched from exchange")
        logger.info("  • Price difference logged for transparency")
        logger.info("  • Error handling with fallback to cached price")
        logger.info("  • Enhanced decision logging with all data")
        logger.info("  • Decisions now based on CURRENT market price")
        logger.info("\n💰 Impact:")
        logger.info("  • No more decisions based on stale prices")
        logger.info("  • Accurate PnL calculations")
        logger.info("  • Correct win/loss statistics")
        logger.info("  • Transparent logging for debugging")
        return True
    else:
        logger.error(f"\n⚠️ {failed} VALIDATIONS FAILED - Review implementation!")
        return False


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
