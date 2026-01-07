#!/usr/bin/env python3
"""
Verification Script: Check subscription flow after fix deployment

Checks:
1. Position cache populated for new positions
2. Subscription confirmation log messages
3. Mark price updates flowing
4. TS monitoring active

Run on server: python scripts/verify_subscription_fix.py
"""

import sys
import os
from datetime import datetime, timedelta
from collections import Counter

def main():
    print("=" * 70)
    print("SUBSCRIPTION FIX VERIFICATION")
    print("=" * 70)
    print(f"Time: {datetime.now()}")
    print()
    
    log_file = "/home/elcrypto/TradingBot/logs/trading_bot.log"
    
    # Read log file
    try:
        with open(log_file, 'r') as f:
            lines = f.readlines()
        print(f"Log file loaded: {len(lines)} lines")
    except Exception as e:
        print(f"Error reading log: {e}")
        return
    
    # Get recent lines (last 30 minutes ~ 18000 lines)
    recent_lines = lines[-18000:]
    
    # CHECK 1: Position cache populated (NEW FIX)
    print()
    print("[CHECK 1] Position Cache Population (CRITICAL FIX)")
    print("-" * 50)
    
    cache_populated = [l for l in recent_lines if "Position cache populated" in l]
    if cache_populated:
        print(f"✅ FOUND {len(cache_populated)} cache population events:")
        for line in cache_populated[-5:]:
            print(f"   {line.strip()[:100]}...")
    else:
        print("⚠️ No cache population events found in recent logs")
        print("   This is expected if no new positions were opened after the fix.")
    
    # CHECK 2: Subscription confirmations
    print()
    print("[CHECK 2] Subscription Confirmations")
    print("-" * 50)
    
    subscribed = [l for l in recent_lines if "[MARK] Subscribed to" in l]
    print(f"Subscription confirmations: {len(subscribed)}")
    for line in subscribed[-5:]:
        print(f"   {line.strip()[:80]}...")
    
    # CHECK 3: Position updates flowing
    print()
    print("[CHECK 3] Position Updates")
    print("-" * 50)
    
    position_updates = [l for l in recent_lines if "Position update:" in l]
    print(f"Position update events: {len(position_updates)}")
    
    # Count unique symbols
    symbols = Counter()
    for line in position_updates:
        # Extract symbol from log
        if "update:" in line:
            parts = line.split("update:")
            if len(parts) > 1:
                sym = parts[1].strip().split()[0]
                symbols[sym] += 1
    
    print("Updates per symbol (top 5):")
    for sym, count in symbols.most_common(5):
        print(f"   {sym}: {count}")
    
    # CHECK 4: TS monitoring
    print()
    print("[CHECK 4] Trailing Stop Monitoring")
    print("-" * 50)
    
    ts_debug = [l for l in recent_lines if "[TS_DEBUG]" in l or "trailing" in l.lower()]
    print(f"TS-related log entries: {len(ts_debug)}")
    
    # CHECK 5: Any errors related to subscriptions
    print()
    print("[CHECK 5] Subscription Errors")
    print("-" * 50)
    
    sub_errors = [l for l in recent_lines if "error" in l.lower() and ("subscri" in l.lower() or "mark" in l.lower())]
    if sub_errors:
        print(f"⚠️ Found {len(sub_errors)} potential subscription errors:")
        for line in sub_errors[-5:]:
            print(f"   {line.strip()[:100]}...")
    else:
        print("✅ No subscription errors found")
    
    # CHECK 6: Missing subscriptions warnings (should be ZERO after fix)
    print()
    print("[CHECK 6] Missing Subscription Warnings (should be 0 after fix)")
    print("-" * 50)
    
    missing_subs = [l for l in recent_lines if "positions WITHOUT subscriptions" in l]
    if missing_subs:
        print(f"⚠️ Found {len(missing_subs)} 'missing subscriptions' warnings")
        print("   This indicates either:")
        print("   1. Format mismatch bug (should be fixed)")
        print("   2. New issue to investigate")
        for line in missing_subs[-3:]:
            print(f"   {line.strip()[:100]}...")
    else:
        print("✅ No 'missing subscriptions' warnings found!")
    
    # SUMMARY
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    all_good = True
    
    if not cache_populated:
        print("⚠️ No cache population events — open a test position to verify fix")
        all_good = False
    else:
        print("✅ Cache population working (CRITICAL FIX confirmed)")
    
    if len(position_updates) > 0:
        print("✅ Position updates flowing")
    else:
        print("⚠️ No position updates — may indicate issue")
        all_good = False
    
    if not missing_subs:
        print("✅ No 'missing subscriptions' warnings")
    else:
        print("⚠️ Some 'missing subscriptions' warnings found")
        all_good = False
    
    if all_good:
        print()
        print("🎉 ALL CHECKS PASSED: Subscription fix appears to be working!")
    else:
        print()
        print("⚠️ Some checks need attention — see details above")


if __name__ == "__main__":
    main()
