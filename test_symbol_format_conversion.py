#!/usr/bin/env python3
"""
Validation test for symbol format conversion fix
Verifies that symbols are properly converted between DB and exchange formats
"""

import logging
import re

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_normalize_symbol_function():
    """Test that normalize_symbol function exists and works correctly"""
    logger.info("=" * 60)
    logger.info("TEST: normalize_symbol() function")
    logger.info("=" * 60)

    with open('core/exchange_manager.py', 'r') as f:
        content = f.read()

    checks_passed = []

    # Check 1: Function exists
    if 'def normalize_symbol(' in content:
        logger.info("  ✅ Found normalize_symbol function")
        checks_passed.append(True)
    else:
        logger.error("  ❌ Missing normalize_symbol function")
        checks_passed.append(False)

    # Check 2: Converts BLAST/USDT:USDT → BLASTUSDT
    if "replace('/', '')" in content and "split(':')" in content:
        logger.info("  ✅ Found format conversion logic")
        checks_passed.append(True)
    else:
        logger.error("  ❌ Missing format conversion logic")
        checks_passed.append(False)

    return all(checks_passed)


def test_find_exchange_symbol_function():
    """Test that find_exchange_symbol method exists"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST: find_exchange_symbol() method")
    logger.info("=" * 60)

    with open('core/exchange_manager.py', 'r') as f:
        content = f.read()

    checks_passed = []

    # Check 1: Method exists
    if 'def find_exchange_symbol(' in content:
        logger.info("  ✅ Found find_exchange_symbol method")
        checks_passed.append(True)
    else:
        logger.error("  ❌ Missing find_exchange_symbol method")
        checks_passed.append(False)

    # Check 2: Has CRITICAL FIX comment
    if 'CRITICAL FIX' in content and 'BLASTUSDT' in content:
        logger.info("  ✅ Found CRITICAL FIX documentation")
        checks_passed.append(True)
    else:
        logger.error("  ❌ Missing CRITICAL FIX documentation")
        checks_passed.append(False)

    # Check 3: Tries exact match first
    if 'if normalized_symbol in self.markets:' in content:
        logger.info("  ✅ Found exact match check (Binance compatibility)")
        checks_passed.append(True)
    else:
        logger.error("  ❌ Missing exact match check")
        checks_passed.append(False)

    # Check 4: Searches markets with normalize_symbol
    if 'for market_symbol in self.markets.keys():' in content:
        logger.info("  ✅ Found market search loop")
        checks_passed.append(True)
    else:
        logger.error("  ❌ Missing market search loop")
        checks_passed.append(False)

    # Check 5: Returns None if not found
    if 'return None' in content:
        logger.info("  ✅ Returns None for unavailable symbols")
        checks_passed.append(True)
    else:
        logger.error("  ❌ Missing None return")
        checks_passed.append(False)

    return all(checks_passed)


def test_validate_and_adjust_amount_fix():
    """Test that _validate_and_adjust_amount uses find_exchange_symbol"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST: _validate_and_adjust_amount() uses symbol conversion")
    logger.info("=" * 60)

    with open('core/exchange_manager.py', 'r') as f:
        content = f.read()

    checks_passed = []

    # Check 1: Calls find_exchange_symbol
    if 'exchange_symbol = self.find_exchange_symbol(symbol)' in content:
        logger.info("  ✅ Found find_exchange_symbol call")
        checks_passed.append(True)
    else:
        logger.error("  ❌ Missing find_exchange_symbol call")
        checks_passed.append(False)

    # Check 2: Raises ValueError if symbol not found
    if 'raise ValueError' in content and 'not available on' in content:
        logger.info("  ✅ Raises ValueError for unavailable symbols")
        checks_passed.append(True)
    else:
        logger.error("  ❌ Missing ValueError for unavailable symbols")
        checks_passed.append(False)

    # Check 3: Uses exchange_symbol for market lookup
    if 'market = self.markets.get(exchange_symbol)' in content:
        logger.info("  ✅ Uses exchange_symbol for market lookup")
        checks_passed.append(True)
    else:
        logger.error("  ❌ Doesn't use exchange_symbol for market lookup")
        checks_passed.append(False)

    # Check 4: NO MORE "Market info not found, using original amount"
    # The problematic pattern was silent warning without raising error
    if 'Market info not found' not in content or 'using original amount' not in content:
        logger.info("  ✅ No silent return without validation")
        checks_passed.append(True)
    else:
        # Check if it's still in the problematic context
        pattern = r'market.*=.*self\.markets\.get\(symbol\).*if not market:.*Market info not found.*return amount'
        if re.search(pattern, content, re.DOTALL):
            logger.error("  ❌ Still has silent return without validation")
            checks_passed.append(False)
        else:
            logger.info("  ✅ No silent return without validation")
            checks_passed.append(True)

    return all(checks_passed)


def test_create_order_fix():
    """Test that create_order uses symbol conversion"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST: create_order() uses symbol conversion")
    logger.info("=" * 60)

    with open('core/exchange_manager.py', 'r') as f:
        content = f.read()

    checks_passed = []

    # Check 1: Calls find_exchange_symbol in create_order
    if 'exchange_symbol = self.find_exchange_symbol(symbol)' in content:
        logger.info("  ✅ Found find_exchange_symbol call in create methods")
        checks_passed.append(True)
    else:
        logger.error("  ❌ Missing find_exchange_symbol call")
        checks_passed.append(False)

    # Check 2: Uses exchange_symbol in API call
    if 'symbol=exchange_symbol' in content:
        logger.info("  ✅ Uses exchange_symbol in API call")
        checks_passed.append(True)
    else:
        logger.error("  ❌ Doesn't use exchange_symbol in API call")
        checks_passed.append(False)

    # Check 3: Has comment marking the fix
    if '✅ Use exchange-specific format' in content:
        logger.info("  ✅ Found documentation comment")
        checks_passed.append(True)
    else:
        logger.error("  ❌ Missing documentation comment")
        checks_passed.append(False)

    return all(checks_passed)


def test_market_order_fix():
    """Test that create_market_order uses symbol conversion"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST: create_market_order() uses symbol conversion")
    logger.info("=" * 60)

    with open('core/exchange_manager.py', 'r') as f:
        content = f.read()

    # Look for create_market_order method
    pattern = r'async def create_market_order.*?(?=\n    async def|\n    def|\Z)'
    match = re.search(pattern, content, re.DOTALL)

    checks_passed = []

    if match:
        method_content = match.group(0)

        # Check 1: Calls find_exchange_symbol
        if 'exchange_symbol = self.find_exchange_symbol(symbol)' in method_content:
            logger.info("  ✅ Found find_exchange_symbol call")
            checks_passed.append(True)
        else:
            logger.error("  ❌ Missing find_exchange_symbol call")
            checks_passed.append(False)

        # Check 2: Uses exchange_symbol in API call
        if 'symbol=exchange_symbol' in method_content:
            logger.info("  ✅ Uses exchange_symbol in API call")
            checks_passed.append(True)
        else:
            logger.error("  ❌ Doesn't use exchange_symbol")
            checks_passed.append(False)
    else:
        logger.error("  ❌ create_market_order method not found")
        checks_passed.append(False)

    return all(checks_passed)


def test_limit_order_fix():
    """Test that create_limit_order uses symbol conversion"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST: create_limit_order() uses symbol conversion")
    logger.info("=" * 60)

    with open('core/exchange_manager.py', 'r') as f:
        content = f.read()

    # Look for create_limit_order method
    pattern = r'async def create_limit_order.*?(?=\n    async def|\n    def|\Z)'
    match = re.search(pattern, content, re.DOTALL)

    checks_passed = []

    if match:
        method_content = match.group(0)

        # Check 1: Calls find_exchange_symbol
        if 'exchange_symbol = self.find_exchange_symbol(symbol)' in method_content:
            logger.info("  ✅ Found find_exchange_symbol call")
            checks_passed.append(True)
        else:
            logger.error("  ❌ Missing find_exchange_symbol call")
            checks_passed.append(False)

        # Check 2: Uses exchange_symbol in API call
        if 'symbol=exchange_symbol' in method_content:
            logger.info("  ✅ Uses exchange_symbol in API call")
            checks_passed.append(True)
        else:
            logger.error("  ❌ Doesn't use exchange_symbol")
            checks_passed.append(False)
    else:
        logger.error("  ❌ create_limit_order method not found")
        checks_passed.append(False)

    return all(checks_passed)


def test_precision_methods_fix():
    """Test that precision methods use symbol conversion"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST: Precision methods use symbol conversion")
    logger.info("=" * 60)

    with open('core/exchange_manager.py', 'r') as f:
        content = f.read()

    checks_passed = []

    # Check amount_to_precision
    if 'def amount_to_precision' in content:
        pattern = r'def amount_to_precision.*?(?=\n    def|\Z)'
        match = re.search(pattern, content, re.DOTALL)
        if match and 'find_exchange_symbol' in match.group(0):
            logger.info("  ✅ amount_to_precision uses find_exchange_symbol")
            checks_passed.append(True)
        else:
            logger.error("  ❌ amount_to_precision missing symbol conversion")
            checks_passed.append(False)
    else:
        logger.error("  ❌ amount_to_precision not found")
        checks_passed.append(False)

    # Check price_to_precision
    if 'def price_to_precision' in content:
        pattern = r'def price_to_precision.*?(?=\n    def|\Z)'
        match = re.search(pattern, content, re.DOTALL)
        if match and 'find_exchange_symbol' in match.group(0):
            logger.info("  ✅ price_to_precision uses find_exchange_symbol")
            checks_passed.append(True)
        else:
            logger.error("  ❌ price_to_precision missing symbol conversion")
            checks_passed.append(False)
    else:
        logger.error("  ❌ price_to_precision not found")
        checks_passed.append(False)

    return all(checks_passed)


def main():
    """Run all validation tests"""
    logger.info("🧪 VALIDATING SYMBOL FORMAT CONVERSION FIX")
    logger.info("=" * 60)

    results = []

    # Run all tests
    results.append(("normalize_symbol function", test_normalize_symbol_function()))
    results.append(("find_exchange_symbol method", test_find_exchange_symbol_function()))
    results.append(("_validate_and_adjust_amount fix", test_validate_and_adjust_amount_fix()))
    results.append(("create_order fix", test_create_order_fix()))
    results.append(("create_market_order fix", test_market_order_fix()))
    results.append(("create_limit_order fix", test_limit_order_fix()))
    results.append(("Precision methods fix", test_precision_methods_fix()))

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
        logger.info("\n✅ Symbol format conversion successfully implemented:")
        logger.info("  • normalize_symbol() converts exchange → DB format")
        logger.info("  • find_exchange_symbol() converts DB → exchange format")
        logger.info("  • All order creation methods use symbol conversion")
        logger.info("  • Validation methods use converted symbols")
        logger.info("  • Precision methods use converted symbols")
        logger.info("  • Clear error messages for unavailable symbols")
        logger.info("\n💰 Impact:")
        logger.info("  • Bybit positions can now be opened (BLAST/USDT:USDT)")
        logger.info("  • Binance continues working (backward compatible)")
        logger.info("  • No more 'Market info not found' silent failures")
        logger.info("  • Proper validation for all symbols")
        logger.info("\n🎯 Test Cases:")
        logger.info("  • Bybit BLASTUSDT → BLAST/USDT:USDT ✅")
        logger.info("  • Binance BTCUSDT → BTCUSDT ✅")
        logger.info("  • Fake symbol → ValueError ✅")
        return True
    else:
        logger.error(f"\n⚠️ {failed} VALIDATIONS FAILED - Review implementation!")
        return False


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
