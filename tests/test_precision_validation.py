#!/usr/bin/env python3
"""
Comprehensive Test Script for Precision Validation (AAVE Edge Case)

Tests 10+ scenarios to verify correct handling of:
- LOT_SIZE filter validation (minQty, stepSize)
- amount_to_precision rounding/truncation
- Re-validation after precision formatting
- Edge cases where precision rounding falls below minimum

Based on research:
- Binance LOT_SIZE: (quantity - minQty) % stepSize == 0
- CCXT amount_to_precision uses truncation mode
- Must re-validate after precision formatting
"""

import asyncio
import sys
from decimal import Decimal
from typing import Dict, Optional
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.exchange_manager import ExchangeManager
from utils.decimal_utils import to_decimal


class PrecisionValidator:
    """Test implementation of precision validation logic"""

    @staticmethod
    def validate_lot_size(quantity: float, min_qty: float, step_size: float) -> bool:
        """
        Validate quantity against LOT_SIZE filter

        Binance Rule: (quantity - minQty) % stepSize == 0
        """
        if quantity < min_qty:
            return False

        # Check stepSize alignment
        diff = Decimal(str(quantity)) - Decimal(str(min_qty))
        step = Decimal(str(step_size))

        if step == 0:
            return True

        remainder = diff % step
        # Allow tiny floating point errors
        return abs(remainder) < Decimal('0.00000001') or abs(remainder - step) < Decimal('0.00000001')

    @staticmethod
    def calculate_position_size_v1_current(
        price: float,
        size_usd: float,
        min_amount: float,
        exchange_amount_to_precision
    ) -> Optional[float]:
        """
        CURRENT implementation (has bug)

        Problem: No re-validation after amount_to_precision
        """
        quantity = Decimal(str(size_usd)) / Decimal(str(price))

        # Check minimum BEFORE precision
        if quantity < Decimal(str(min_amount)):
            min_cost = min_amount * price
            if min_cost <= size_usd * 1.1:
                quantity = Decimal(str(min_amount))
            else:
                return None

        # Apply precision
        formatted_qty = exchange_amount_to_precision(float(quantity))

        # ⚠️ BUG: No re-check that formatted_qty >= min_amount!
        return formatted_qty

    @staticmethod
    def calculate_position_size_v2_fixed(
        price: float,
        size_usd: float,
        min_amount: float,
        step_size: float,
        exchange_amount_to_precision
    ) -> Optional[float]:
        """
        FIXED implementation

        Solution: Re-validate after amount_to_precision and adjust if needed
        """
        quantity = Decimal(str(size_usd)) / Decimal(str(price))

        # Check minimum BEFORE precision
        if quantity < Decimal(str(min_amount)):
            min_cost = min_amount * price
            if min_cost <= size_usd * 1.1:
                quantity = Decimal(str(min_amount))
            else:
                return None

        # Apply precision (may round down)
        formatted_qty = exchange_amount_to_precision(float(quantity))

        # ✅ FIX: Re-validate after precision
        if formatted_qty < min_amount:
            # Round UP to next valid step that meets minimum
            steps_needed = ((min_amount - formatted_qty) / step_size) + 1
            adjusted_qty = formatted_qty + (int(steps_needed) * step_size)

            # Re-apply precision to ensure alignment
            formatted_qty = exchange_amount_to_precision(adjusted_qty)

            # Final check: if still below minimum, we can't trade this
            if formatted_qty < min_amount:
                return None

        return formatted_qty


class TestCase:
    """Test case definition"""

    def __init__(self, name: str, symbol: str, price: float, size_usd: float,
                 min_qty: float, step_size: float, expected_pass: bool,
                 expected_qty: Optional[float] = None, description: str = ""):
        self.name = name
        self.symbol = symbol
        self.price = price
        self.size_usd = size_usd
        self.min_qty = min_qty
        self.step_size = step_size
        self.expected_pass = expected_pass
        self.expected_qty = expected_qty
        self.description = description


async def run_tests():
    """Run all test cases"""

    print("=" * 80)
    print("🧪 COMPREHENSIVE PRECISION VALIDATION TEST SUITE")
    print("=" * 80)
    print()

    # Mock exchange for precision testing (no real API calls needed)
    class MockExchange:
        """Mock exchange for testing precision logic without API calls"""

        def __init__(self):
            self.markets = {}
            self._step_sizes = {}  # Store step sizes per symbol

        def set_step_size(self, symbol: str, step_size: float):
            """Set step size for a symbol (for testing)"""
            self._step_sizes[symbol] = step_size

        def amount_to_precision(self, symbol: str, amount: float) -> float:
            """
            Simulate CCXT amount_to_precision behavior

            CCXT uses TRUNCATE mode by default for amount precision
            This matches real Binance behavior
            """
            import math

            # Get step size for this symbol
            step_size = self._step_sizes.get(symbol, 0.01)

            if step_size == 0:
                return amount

            # TRUNCATE mode (not ROUND) - this is critical!
            # amount_to_precision TRUNCATES, which can round DOWN below minimum
            steps = int(amount / step_size)
            return steps * step_size

    exchange = MockExchange()

    # Define test cases based on real market data
    test_cases = [
        # Test 1: AAVE - The original bug case
        TestCase(
            name="Test 1: AAVE Original Bug",
            symbol="AAVE/USDT:USDT",
            price=350.0,
            size_usd=200.0,
            min_qty=0.1,
            step_size=0.1,
            expected_pass=True,
            expected_qty=0.5,  # $200 / $350 = 0.571 → rounds to 0.5 (should pass)
            description="Real AAVE case: $200 position should create 0.5 AAVE"
        ),

        # Test 2: Edge case - rounds DOWN to exactly minimum
        TestCase(
            name="Test 2: Rounds to Minimum",
            symbol="TEST1/USDT:USDT",
            price=100.0,
            size_usd=21.0,
            min_qty=0.2,
            step_size=0.1,
            expected_pass=True,
            expected_qty=0.2,  # $21 / $100 = 0.21 → rounds to 0.2 (exactly minimum)
            description="Edge case: rounds down to exactly minimum quantity"
        ),

        # Test 3: Edge case - rounds DOWN below minimum (SHOULD FAIL or ADJUST)
        TestCase(
            name="Test 3: Rounds Below Minimum",
            symbol="TEST2/USDT:USDT",
            price=100.0,
            size_usd=14.0,
            min_qty=0.2,
            step_size=0.1,
            expected_pass=False,  # V1 will fail LOT_SIZE, V2 should handle
            expected_qty=None,  # $14 / $100 = 0.14 → rounds to 0.1 < 0.2 minimum
            description="Critical bug case: precision rounds below minimum"
        ),

        # Test 4: Well above minimum
        TestCase(
            name="Test 4: Well Above Minimum",
            symbol="BTC/USDT:USDT",
            price=50000.0,
            size_usd=200.0,
            min_qty=0.001,
            step_size=0.001,
            expected_pass=True,
            expected_qty=0.004,  # $200 / $50000 = 0.004 (well above 0.001)
            description="Normal case: well above minimum"
        ),

        # Test 5: Expensive asset with large stepSize
        TestCase(
            name="Test 5: Expensive Asset",
            symbol="TEST3/USDT:USDT",
            price=5000.0,
            size_usd=200.0,
            min_qty=0.01,
            step_size=0.01,
            expected_pass=True,
            expected_qty=0.04,  # $200 / $5000 = 0.04
            description="Expensive asset: small quantity but meets minimum"
        ),

        # Test 6: stepSize alignment issue
        TestCase(
            name="Test 6: StepSize Alignment",
            symbol="TEST4/USDT:USDT",
            price=3.33,
            size_usd=10.0,
            min_qty=1.0,
            step_size=0.5,
            expected_pass=True,
            expected_qty=3.0,  # $10 / $3.33 = 3.003 → rounds to 3.0 (aligned with 0.5 step)
            description="StepSize alignment: must align with 0.5 increments"
        ),

        # Test 7: Tiny stepSize (high precision)
        TestCase(
            name="Test 7: High Precision",
            symbol="TEST5/USDT:USDT",
            price=0.01,
            size_usd=200.0,
            min_qty=100.0,
            step_size=0.01,
            expected_pass=True,
            expected_qty=20000.0,  # $200 / $0.01 = 20000
            description="High precision: tiny stepSize with large quantities"
        ),

        # Test 8: Cannot afford minimum
        TestCase(
            name="Test 8: Cannot Afford Minimum",
            symbol="TEST6/USDT:USDT",
            price=1000.0,
            size_usd=200.0,
            min_qty=1.0,
            step_size=0.1,
            expected_pass=False,
            expected_qty=None,  # $200 / $1000 = 0.2 < 1.0 minimum, and $1000 > $200 * 1.1
            description="Cannot afford: minimum costs more than budget allows"
        ),

        # Test 9: Borderline affordable minimum
        TestCase(
            name="Test 9: Borderline Affordable",
            symbol="TEST7/USDT:USDT",
            price=1.05,
            size_usd=1.0,
            min_qty=1.0,
            step_size=0.1,
            expected_pass=True,
            expected_qty=1.0,  # $1 / $1.05 = 0.95 < 1.0, but $1.05 <= $1 * 1.1 → use minimum
            description="Borderline: can afford minimum with 10% tolerance"
        ),

        # Test 10: Large stepSize (e.g., whole numbers only)
        TestCase(
            name="Test 10: Whole Numbers Only",
            symbol="TEST8/USDT:USDT",
            price=5.0,
            size_usd=200.0,
            min_qty=10.0,
            step_size=1.0,
            expected_pass=True,
            expected_qty=40.0,  # $200 / $5 = 40.0 (exactly 40 whole units)
            description="Integer stepSize: must be whole numbers"
        ),

        # Test 11: AAVE at different price (higher)
        TestCase(
            name="Test 11: AAVE Higher Price",
            symbol="AAVE/USDT:USDT",
            price=400.0,
            size_usd=200.0,
            min_qty=0.1,
            step_size=0.1,
            expected_pass=True,
            expected_qty=0.5,  # $200 / $400 = 0.5 (exactly)
            description="AAVE at $400: should still work"
        ),

        # Test 12: Critical - rounds to 0.09 with min 0.1
        TestCase(
            name="Test 12: Critical Rounding Bug",
            symbol="TEST9/USDT:USDT",
            price=100.0,
            size_usd=9.5,
            min_qty=0.1,
            step_size=0.01,
            expected_pass=False,  # V1 will create 0.09 < 0.1 → FAIL
            expected_qty=None,  # $9.5 / $100 = 0.095 → rounds to 0.09 < 0.1
            description="Critical bug: precision creates quantity below minimum"
        ),

        # Test 13: Real AAVE bug - price moves higher
        TestCase(
            name="Test 13: AAVE at $500 (real edge case)",
            symbol="AAVE/USDT:USDT",
            price=500.0,
            size_usd=200.0,
            min_qty=0.1,
            step_size=0.1,
            expected_pass=True,
            expected_qty=0.4,  # $200 / $500 = 0.4 (exactly on step)
            description="AAVE at higher price: still valid"
        ),

        # Test 14: The EXACT bug case - truncates to below minimum
        TestCase(
            name="Test 14: Truncation Below Minimum (CRITICAL)",
            symbol="TEST10/USDT:USDT",
            price=10.0,
            size_usd=1.85,
            min_qty=0.2,
            step_size=0.1,
            expected_pass=False,  # This is the bug!
            expected_qty=None,  # $1.85 / $10 = 0.185 → TRUNCATES to 0.1 < 0.2 minimum
            description="CRITICAL: amount_to_precision TRUNCATES 0.185 to 0.1, below 0.2 minimum"
        ),

        # Test 15: Verify V2 adjusts up correctly
        TestCase(
            name="Test 15: V2 Adjustment Test",
            symbol="TEST11/USDT:USDT",
            price=10.0,
            size_usd=1.95,
            min_qty=0.2,
            step_size=0.1,
            expected_pass=True,  # V2 should adjust 0.1 → 0.2
            expected_qty=0.2,  # $1.95 / $10 = 0.195 → truncates to 0.1, V2 adjusts to 0.2
            description="V2 should detect 0.1 < 0.2 and adjust UP to 0.2"
        ),
    ]

    print(f"Running {len(test_cases)} test cases...\n")

    results = {
        'passed': 0,
        'failed': 0,
        'details': []
    }

    validator = PrecisionValidator()

    for i, tc in enumerate(test_cases, 1):
        print(f"\n{'=' * 80}")
        print(f"🧪 {tc.name}")
        print(f"{'=' * 80}")
        print(f"Symbol: {tc.symbol}")
        print(f"Price: ${tc.price}")
        print(f"Position Size: ${tc.size_usd}")
        print(f"Min Qty: {tc.min_qty}")
        print(f"Step Size: {tc.step_size}")
        print(f"Description: {tc.description}")
        print()

        # Set step size for this symbol
        exchange.set_step_size(tc.symbol, tc.step_size)

        # Calculate raw quantity
        raw_qty = tc.size_usd / tc.price
        print(f"📊 Raw Quantity: {raw_qty:.10f}")

        # Test V1 (current implementation)
        try:
            qty_v1 = validator.calculate_position_size_v1_current(
                tc.price,
                tc.size_usd,
                tc.min_qty,
                lambda q: float(exchange.amount_to_precision(tc.symbol, q))
            )

            if qty_v1 is not None:
                lot_size_valid_v1 = validator.validate_lot_size(qty_v1, tc.min_qty, tc.step_size)
                print(f"V1 (Current): {qty_v1:.10f} - LOT_SIZE: {'✅ PASS' if lot_size_valid_v1 else '❌ FAIL'}")
            else:
                lot_size_valid_v1 = False
                print(f"V1 (Current): None (cannot calculate)")
        except Exception as e:
            qty_v1 = None
            lot_size_valid_v1 = False
            print(f"V1 (Current): ❌ ERROR - {str(e)}")

        # Test V2 (fixed implementation)
        try:
            qty_v2 = validator.calculate_position_size_v2_fixed(
                tc.price,
                tc.size_usd,
                tc.min_qty,
                tc.step_size,
                lambda q: float(exchange.amount_to_precision(tc.symbol, q))
            )

            if qty_v2 is not None:
                lot_size_valid_v2 = validator.validate_lot_size(qty_v2, tc.min_qty, tc.step_size)
                print(f"V2 (Fixed):   {qty_v2:.10f} - LOT_SIZE: {'✅ PASS' if lot_size_valid_v2 else '❌ FAIL'}")
            else:
                lot_size_valid_v2 = True if not tc.expected_pass else False
                print(f"V2 (Fixed):   None (correctly rejected)")
        except Exception as e:
            qty_v2 = None
            lot_size_valid_v2 = False
            print(f"V2 (Fixed):   ❌ ERROR - {str(e)}")

        # Evaluate test result
        if tc.expected_pass:
            # Should create valid quantity
            test_passed = lot_size_valid_v2 and qty_v2 is not None
            if tc.expected_qty:
                test_passed = test_passed and abs(qty_v2 - tc.expected_qty) < 0.0001
        else:
            # Should reject (return None) OR create valid quantity
            test_passed = (qty_v2 is None) or (qty_v2 is not None and lot_size_valid_v2)

        # Show result
        print()
        print(f"Expected: {'Create valid quantity' if tc.expected_pass else 'Reject or handle gracefully'}")
        print(f"Result: {'✅ PASS' if test_passed else '❌ FAIL'}")

        if test_passed:
            results['passed'] += 1
        else:
            results['failed'] += 1

        results['details'].append({
            'name': tc.name,
            'passed': test_passed,
            'qty_v1': qty_v1,
            'qty_v2': qty_v2,
            'lot_size_v1': lot_size_valid_v1 if qty_v1 else False,
            'lot_size_v2': lot_size_valid_v2 if qty_v2 else True
        })

    # Print summary
    print(f"\n{'=' * 80}")
    print("📊 TEST SUMMARY")
    print(f"{'=' * 80}")
    print(f"Total Tests: {len(test_cases)}")
    print(f"✅ Passed: {results['passed']}")
    print(f"❌ Failed: {results['failed']}")
    print(f"Success Rate: {results['passed'] / len(test_cases) * 100:.1f}%")
    print()

    # Show V1 vs V2 comparison
    print(f"{'=' * 80}")
    print("🔍 V1 (Current) vs V2 (Fixed) COMPARISON")
    print(f"{'=' * 80}")

    v1_failures = sum(1 for d in results['details'] if not d['lot_size_v1'])
    v2_failures = sum(1 for d in results['details'] if not d['lot_size_v2'])

    print(f"V1 LOT_SIZE Failures: {v1_failures}")
    print(f"V2 LOT_SIZE Failures: {v2_failures}")
    print()

    if results['passed'] == len(test_cases):
        print("✅ ALL TESTS PASSED! Solution is ready for implementation.")
        return 0
    else:
        print("❌ SOME TESTS FAILED. Solution needs refinement.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_tests())
    sys.exit(exit_code)
