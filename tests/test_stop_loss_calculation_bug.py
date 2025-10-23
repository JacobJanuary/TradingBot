#!/usr/bin/env python3
"""
Test script to demonstrate the stop loss calculation bug for LONG positions

ROOT CAUSE: position_manager.py passes request.side='BUY' to calculate_stop_loss()
which only recognizes 'long'/'short', causing BUY to be treated as SHORT.
"""
from decimal import Decimal

def calculate_stop_loss(entry_price, side, stop_loss_percent):
    """
    Original function from utils/decimal_utils.py
    """
    sl_distance = entry_price * (stop_loss_percent / Decimal('100'))

    if side.lower() == 'long':
        sl_price = entry_price - sl_distance
    else:  # short
        sl_price = entry_price + sl_distance

    return sl_price


print("=" * 100)
print("STOP LOSS CALCULATION BUG DEMONSTRATION")
print("=" * 100)
print()

# Real data from ATOMUSDT
entry_price = Decimal('3.255')
stop_loss_percent = Decimal('2.0')

print(f"Test Data:")
print(f"  Entry Price: {entry_price}")
print(f"  Stop Loss %: {stop_loss_percent}%")
print()

print("=" * 100)
print("TEST 1: calculate_stop_loss with side='BUY' (CURRENT BUG)")
print("=" * 100)
print()

result_bug = calculate_stop_loss(entry_price, 'BUY', stop_loss_percent)
print(f"Input: side='BUY'")
print(f"Result: {result_bug}")
print(f"Check: {result_bug} > {entry_price}? {result_bug > entry_price}")
print(f"❌ BUG: SL is ABOVE entry for BUY (should be BELOW!)")
print(f"   'BUY'.lower() == 'long' → False")
print(f"   → Falls into else: SHORT formula")
print(f"   → {entry_price} + ({entry_price} * 0.02) = {result_bug}")
print()

print("=" * 100)
print("TEST 2: calculate_stop_loss with side='long' (CORRECT)")
print("=" * 100)
print()

result_correct = calculate_stop_loss(entry_price, 'long', stop_loss_percent)
print(f"Input: side='long'")
print(f"Result: {result_correct}")
print(f"Check: {result_correct} < {entry_price}? {result_correct < entry_price}")
print(f"✅ CORRECT: SL is BELOW entry for LONG")
print(f"   'long'.lower() == 'long' → True")
print(f"   → {entry_price} - ({entry_price} * 0.02) = {result_correct}")
print()

print("=" * 100)
print("REAL WORLD EVIDENCE FROM LOGS")
print("=" * 100)
print()

print("ATOMUSDT (signal_id=5242841) on 2025-10-21 06:05:")
print()
print("Position Manager:")
print(f"  request.side = 'BUY'")
print(f"  request.entry_price = 3.255")
print()
print("Atomic Position Manager:")
print(f"  🛡️ Placing stop-loss for ATOMUSDT at 3.3201")
print()
print("Protection Manager:")
print(f"  📊 Creating SL for ATOMUSDT: stop=3.248, current=3.255, side=sell")
print(f"  ✅ SL placed: 3.248 (CORRECT - BELOW entry)")
print()
print("Trailing Stop Manager:")
print(f"  Created trailing stop for ATOMUSDT long: entry=3.257, initial_stop=3.3201")
print(f"  ❌ Failed to place stop order: binance -2021 'Order would immediately trigger'")
print()

print("ANALYSIS:")
print(f"  Protection Manager SL: 3.248 < 3.255 ✅ CORRECT")
print(f"  TS initial_stop: 3.3201 > 3.255 ❌ WRONG")
print(f"  Calculation: 3.255 * 1.02 = 3.3201")
print(f"  → Used SHORT formula for LONG position!")
print()

print("=" * 100)
print("ROOT CAUSE IDENTIFIED")
print("=" * 100)
print()

print("File: core/position_manager.py")
print()
print("LINE 948-950 (WRONG ORDER):")
print("```python")
print("stop_loss_price = calculate_stop_loss(")
print("    to_decimal(request.entry_price),")
print("    request.side,  # ← 'BUY' passed here!")
print("    to_decimal(stop_loss_percent)")
print(")")
print("```")
print()
print("LINE 958-964 (CONVERSION HAPPENS LATER):")
print("```python")
print("# Convert side: long -> buy, short -> sell for Binance")
print("if request.side.lower() == 'long':")
print("    order_side = 'buy'")
print("elif request.side.lower() == 'short':")
print("    order_side = 'sell'")
print("else:")
print("    order_side = request.side.lower()  # ← 'BUY' stays as 'buy'")
print("```")
print()

print("=" * 100)
print("SOLUTION")
print("=" * 100)
print()

print("Convert request.side to position_side BEFORE calling calculate_stop_loss:")
print()
print("```python")
print("# Convert order side (BUY/SELL) to position side (long/short)")
print("if request.side.lower() in ['buy', 'long']:")
print("    position_side = 'long'")
print("elif request.side.lower() in ['sell', 'short']:")
print("    position_side = 'short'")
print("else:")
print("    raise ValueError(f\"Invalid side: {request.side}\")")
print()
print("# Calculate stop-loss with correct position side")
print("stop_loss_price = calculate_stop_loss(")
print("    to_decimal(request.entry_price),")
print("    position_side,  # ← 'long' or 'short'")
print("    to_decimal(stop_loss_percent)")
print(")")
print("```")
print()

print("=" * 100)
print("VALIDATION")
print("=" * 100)
print()

# Test the fix
def test_fix(request_side, entry, percent):
    # Fixed logic
    if request_side.lower() in ['buy', 'long']:
        position_side = 'long'
    elif request_side.lower() in ['sell', 'short']:
        position_side = 'short'
    else:
        raise ValueError(f"Invalid side: {request_side}")

    result = calculate_stop_loss(entry, position_side, percent)
    return position_side, result

pos_side, fixed_result = test_fix('BUY', entry_price, stop_loss_percent)
print(f"Test with request.side='BUY':")
print(f"  Converted to position_side='{pos_side}'")
print(f"  Stop Loss: {fixed_result}")
print(f"  Check: {fixed_result} < {entry_price}? {fixed_result < entry_price}")
print(f"  ✅ FIXED: SL is now BELOW entry!")
print()

print("=" * 100)
print("IMPACT ANALYSIS")
print("=" * 100)
print()

print("Affected:")
print("  - ALL LONG positions (BUY signals)")
print("  - Initial SL placed ABOVE entry instead of BELOW")
print("  - Binance rejects with -2021 'Order would immediately trigger'")
print("  - Position created but WITHOUT stop loss protection!")
print()

print("NOT Affected:")
print("  - SHORT positions (SELL signals) - calculation accidentally correct")
print("  - Protection Manager SL (uses different path)")
print()

print("Severity: 🔴 CRITICAL (P0)")
print("Priority: IMMEDIATE FIX REQUIRED")
print()

print("=" * 100)
