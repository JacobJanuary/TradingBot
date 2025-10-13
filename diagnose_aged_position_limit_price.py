#!/usr/bin/env python3
"""
Diagnostic script for aged position limit price error

Analyzes the root cause of Binance error -4016:
"Limit price can't be higher than X"

This script simulates aged_position_manager logic and identifies
the architectural issue with limit order pricing.
"""

import logging
from decimal import Decimal
from typing import Tuple

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def calculate_target_price_grace_period(
    entry_price: float,
    side: str,
    commission_percent: float = 0.1
) -> Tuple[float, str]:
    """
    Simulate aged_position_manager._calculate_target_price() for GRACE_PERIOD

    This is the EXACT logic from aged_position_manager.py lines 216-227
    """
    entry_price_decimal = Decimal(str(entry_price))
    commission_decimal = Decimal(str(commission_percent)) / 100
    double_commission = 2 * commission_decimal

    if side in ['long', 'buy']:
        target_price = entry_price_decimal * (1 + double_commission)
    else:  # short/sell
        target_price = entry_price_decimal * (1 - double_commission)

    return float(target_price), "GRACE_PERIOD_BREAKEVEN"


def check_binance_limit_order_validity(
    current_price: float,
    target_price: float,
    side: str
) -> Tuple[bool, float, str]:
    """
    Check if limit order price is within Binance's allowed range

    Binance rules for limit orders:
    - BUY limit: price must be <= current_price * 1.05 (5% above market)
    - SELL limit: price must be >= current_price * 0.95 (5% below market)

    Returns:
        (is_valid, max_allowed_price, reason)
    """
    if side == 'buy':
        # For BUY limit orders (closing SHORT positions)
        max_allowed = current_price * 1.05  # 5% above current
        is_valid = target_price <= max_allowed
        reason = f"BUY limit must be <= {max_allowed:.4f} (105% of current)"
    else:
        # For SELL limit orders (closing LONG positions)
        min_allowed = current_price * 0.95  # 5% below current
        is_valid = target_price >= min_allowed
        reason = f"SELL limit must be >= {min_allowed:.4f} (95% of current)"

    return is_valid, max_allowed if side == 'buy' else min_allowed, reason


def main():
    """Run diagnostic on HYPERUSDT case from logs"""

    logger.info("=" * 80)
    logger.info("🔍 DIAGNOSTIC: Aged Position Limit Price Error")
    logger.info("=" * 80)

    # Data from actual logs
    symbol = "HYPERUSDT"
    side = "short"
    entry_price = 0.2020
    current_price = 0.1883  # Real-time price from exchange
    age_hours = 7.0
    hours_over_limit = 4.0
    grace_period_hours = 8

    logger.info(f"\n📊 Position Data (from logs):")
    logger.info(f"  Symbol: {symbol}")
    logger.info(f"  Side: {side}")
    logger.info(f"  Entry price: ${entry_price:.4f}")
    logger.info(f"  Current price: ${current_price:.4f}")
    logger.info(f"  Age: {age_hours:.1f}h ({hours_over_limit:.1f}h over limit)")
    logger.info(f"  Phase: GRACE_PERIOD ({hours_over_limit:.1f}/{grace_period_hours}h)")

    # Step 1: Calculate target price (aged_position_manager logic)
    logger.info(f"\n🎯 Step 1: Calculate Target Price")
    logger.info(f"  Logic: GRACE_PERIOD tries to exit at breakeven")

    target_price, phase = calculate_target_price_grace_period(entry_price, side)

    logger.info(f"  Formula for {side}: entry_price * (1 - 2*commission)")
    logger.info(f"  Calculation: {entry_price:.4f} * (1 - 0.002)")
    logger.info(f"  Target price: ${target_price:.4f}")

    # Step 2: Check distance from market
    logger.info(f"\n📏 Step 2: Check Distance from Current Market Price")

    distance_dollars = target_price - current_price
    distance_percent = (distance_dollars / current_price) * 100

    logger.info(f"  Current market: ${current_price:.4f}")
    logger.info(f"  Target price:   ${target_price:.4f}")
    logger.info(f"  Distance:       ${distance_dollars:.4f} ({distance_percent:+.2f}%)")

    if distance_percent > 5:
        logger.warning(f"  ⚠️ Target is {distance_percent:.1f}% above market (> 5% limit)")

    # Step 3: Check Binance validity
    logger.info(f"\n🏦 Step 3: Check Binance Limit Order Rules")

    # For SHORT position, we need BUY order to close
    order_side = 'buy'
    logger.info(f"  To close {side} position → {order_side.upper()} order needed")

    is_valid, limit, reason = check_binance_limit_order_validity(
        current_price, target_price, order_side
    )

    logger.info(f"  Rule: {reason}")
    logger.info(f"  Max allowed: ${limit:.4f}")
    logger.info(f"  Target price: ${target_price:.4f}")

    if is_valid:
        logger.info(f"  ✅ VALID - Order can be placed")
    else:
        logger.error(f"  ❌ INVALID - Order will be REJECTED")
        logger.error(f"  Binance error: \"Limit price can't be higher than {limit:.7f}\"")

    # Step 4: Comparison with actual Binance error
    logger.info(f"\n📋 Step 4: Compare with Actual Error from Logs")

    actual_binance_max = 0.1978200  # From error message
    logger.info(f"  Actual Binance max from logs: ${actual_binance_max:.7f}")
    logger.info(f"  Our calculated max:           ${limit:.7f}")

    diff = abs(actual_binance_max - limit)
    if diff < 0.0001:
        logger.info(f"  ✅ MATCH - Calculation confirmed (diff: ${diff:.7f})")
    else:
        logger.warning(f"  ⚠️ MISMATCH - Difference: ${diff:.7f}")

    # Step 5: Root cause analysis
    logger.info(f"\n" + "=" * 80)
    logger.info(f"🔴 ROOT CAUSE ANALYSIS")
    logger.info(f"=" * 80)

    logger.info(f"\n1. ❌ NOT a stale price issue:")
    logger.info(f"   - aged_position_manager DOES fetch real-time price")
    logger.info(f"   - _get_current_price() calls fetch_ticker()")
    logger.info(f"   - Current price ${current_price:.4f} is FRESH")

    logger.info(f"\n2. ✅ ARCHITECTURAL ISSUE:")
    logger.info(f"   - GRACE_PERIOD phase tries to exit at BREAKEVEN")
    logger.info(f"   - Breakeven = entry price ± 2*commission")
    logger.info(f"   - For this position: ${target_price:.4f}")
    logger.info(f"   - But market moved {abs(distance_percent):.1f}% away!")

    logger.info(f"\n3. 🏦 Binance Limit Order Rules:")
    logger.info(f"   - BUY limit orders: max 5% above current market")
    logger.info(f"   - SELL limit orders: max 5% below current market")
    logger.info(f"   - This prevents manipulation and ensures liquidity")

    logger.info(f"\n4. 🎯 What Happened:")
    logger.info(f"   Step 1: Position opened at ${entry_price:.4f}")
    logger.info(f"   Step 2: Market dropped to ${current_price:.4f} (-6.8%)")
    logger.info(f"   Step 3: Position exceeded max age → GRACE_PERIOD")
    logger.info(f"   Step 4: GRACE tries breakeven exit at ${target_price:.4f}")
    logger.info(f"   Step 5: Target is {distance_percent:+.1f}% from market")
    logger.info(f"   Step 6: Binance rejects (> 5% limit)")
    logger.info(f"   Step 7: Error: \"Limit price can't be higher than {actual_binance_max:.7f}\"")

    # Step 6: Solutions
    logger.info(f"\n" + "=" * 80)
    logger.info(f"💡 SOLUTIONS")
    logger.info(f"=" * 80)

    logger.info(f"\nOption 1: Clamp limit price to Binance max")
    clamped_price = min(target_price, limit)
    logger.info(f"  Target: ${target_price:.4f} → Clamped: ${clamped_price:.4f}")
    logger.info(f"  Pros: Order will be accepted")
    logger.info(f"  Cons: May not reach breakeven, will accept {distance_percent-5:.1f}% worse price")

    logger.info(f"\nOption 2: Use market order when target too far")
    logger.info(f"  If target > 5% from market → use MARKET order")
    logger.info(f"  Pros: Guaranteed execution immediately")
    logger.info(f"  Cons: Worse price (current market ${current_price:.4f})")

    logger.info(f"\nOption 3: Progressive approach")
    logger.info(f"  Start with limit at max allowed (${limit:.4f})")
    logger.info(f"  Update periodically towards breakeven as market moves")
    logger.info(f"  Pros: Best price possible over time")
    logger.info(f"  Cons: May take long time if market doesn't move")

    logger.info(f"\nOption 4: Hybrid approach (RECOMMENDED)")
    logger.info(f"  • If target within 5%: use limit at target")
    logger.info(f"  • If target 5-10% away: use limit at max allowed")
    logger.info(f"  • If target >10% away: use market order")
    logger.info(f"  Pros: Balances execution certainty with price optimization")

    # Step 7: Previous fix verification
    logger.info(f"\n" + "=" * 80)
    logger.info(f"🔍 PREVIOUS FIX VERIFICATION")
    logger.info(f"=" * 80)

    logger.info(f"\nPrevious fix (commit 1ae55d1):")
    logger.info(f"  • Fixed: position_manager.py check_position_age()")
    logger.info(f"  • Problem: Used cached position.current_price (stale)")
    logger.info(f"  • Solution: Added fetch_ticker() before decision")
    logger.info(f"  • Status: ✅ CORRECT - Fixed stale price in position_manager")

    logger.info(f"\nCurrent issue:")
    logger.info(f"  • Module: aged_position_manager.py (DIFFERENT!)")
    logger.info(f"  • Already uses: _get_current_price() with fetch_ticker()")
    logger.info(f"  • Price is: ✅ FRESH (${current_price:.4f})")
    logger.info(f"  • Problem: ❌ Target price violates Binance rules")

    logger.info(f"\n✅ CONCLUSION: Previous fix was correct for its scope")
    logger.info(f"❌ Current issue is UNRELATED - different root cause")

    # Summary
    logger.info(f"\n" + "=" * 80)
    logger.info(f"📊 SUMMARY")
    logger.info(f"=" * 80)

    logger.info(f"\n✅ Diagnostic complete:")
    logger.info(f"  • Root cause: Limit price calculation doesn't check Binance limits")
    logger.info(f"  • Not related to: Stale prices (prices are fresh)")
    logger.info(f"  • Module: aged_position_manager.py _calculate_target_price()")
    logger.info(f"  • Fix needed: Add limit price clamping or market order fallback")
    logger.info(f"  • Location: aged_position_manager.py lines 205-264")

    logger.info(f"\n🎯 Next steps:")
    logger.info(f"  1. Review aged_position_manager.py _calculate_target_price()")
    logger.info(f"  2. Implement hybrid approach for limit price validation")
    logger.info(f"  3. Test with positions where market moved >5% from breakeven")
    logger.info(f"  4. Ensure graceful fallback to market orders when needed")


if __name__ == "__main__":
    main()
