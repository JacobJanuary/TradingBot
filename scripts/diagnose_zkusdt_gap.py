#!/usr/bin/env python3
"""
Deeper diagnostic for ZKUSDT/STORJUSDT data gap.

Checks:
1. Look for any mention of these symbols in log (subscriptions, errors, etc.)
2. Check if positions dict might have format mismatch too
3. Look for combined events

Run on server: python scripts/diagnose_zkusdt_gap.py
"""

import sys
import os
from datetime import datetime
from collections import Counter

def main():
    print("=" * 60)
    print("ZKUSDT / STORJUSDT DATA GAP DIAGNOSTIC")
    print("=" * 60)
    print(f"Time: {datetime.now()}")
    print()
    
    log_file = "/home/elcrypto/TradingBot/logs/trading_bot.log"
    target_symbols = ["ZKUSDT", "STORJUSDT", "ZK/USDT:USDT", "STORJ/USDT:USDT"]
    
    # Read entire log file
    try:
        with open(log_file, 'r') as f:
            lines = f.readlines()
        print(f"Log file loaded: {len(lines)} lines")
    except Exception as e:
        print(f"Error reading log: {e}")
        return
    
    # CHECK 1: Count all mentions of target symbols
    print()
    print("[CHECK 1] Symbol Mentions Count (any context)")
    print("-" * 40)
    
    for target in target_symbols:
        count = sum(1 for line in lines if target in line)
        print(f"  {target}: {count} mentions")
    
    # CHECK 2: Find what contexts these symbols appear in
    print()
    print("[CHECK 2] Context Analysis (last 30 mentions for each symbol)")
    print("-" * 40)
    
    for target in ["ZKUSDT", "STORJUSDT"]:
        mentions = [line.strip() for line in lines if target in line][-30:]
        contexts = Counter()
        
        for line in mentions:
            if "Subscribed" in line:
                contexts["Subscribed"] += 1
            elif "Resubscribing" in line:
                contexts["Resubscribing"] += 1
            elif "positions" in line.lower():
                contexts["positions"] += 1
            elif "mark" in line.lower():
                contexts["mark_price"] += 1
            elif "error" in line.lower():
                contexts["ERROR"] += 1
            elif "position.update" in line:
                contexts["position.update"] += 1
            else:
                contexts["other"] += 1
        
        print(f"\n  {target}:")
        for ctx, cnt in contexts.most_common():
            print(f"    {ctx}: {cnt}")
    
    # CHECK 3: Look for self.positions mentions with these symbols
    print()
    print("[CHECK 3] Position Update Events")
    print("-" * 40)
    
    for target in ["ZKUSDT", "STORJUSDT"]:
        position_updates = [line.strip()[-100:] for line in lines 
                           if target in line and ("position.update" in line or "ACCOUNT_UPDATE" in line)]
        print(f"\n  {target} position events: {len(position_updates)}")
        for event in position_updates[-3:]:
            print(f"    ...{event}")
    
    # CHECK 4: Check for format-related issues
    print()
    print("[CHECK 4] Format Comparison")
    print("-" * 40)
    
    # Count CCXT format vs Binance format mentions
    for base in ["ZK", "STORJ"]:
        ccxt_format = f"{base}/USDT:USDT"
        binance_format = f"{base}USDT"
        
        ccxt_count = sum(1 for line in lines if ccxt_format in line)
        binance_count = sum(1 for line in lines if binance_format in line)
        
        print(f"  {base}:")
        print(f"    CCXT format ({ccxt_format}): {ccxt_count}")
        print(f"    Binance format ({binance_format}): {binance_count}")
    
    # CHECK 5: Recent subscription confirmations
    print()
    print("[CHECK 5] Recent Activity (last 1000 lines)")
    print("-" * 40)
    
    recent_lines = lines[-1000:]
    for target in ["ZKUSDT", "STORJUSDT"]:
        recent = [line.strip() for line in recent_lines if target in line]
        print(f"\n  {target}: {len(recent)} mentions in last 1000 lines")
        for r in recent[-3:]:
            print(f"    {r[:100]}...")
    
    # CONCLUSION
    print()
    print("=" * 60)
    print("ANALYSIS")
    print("=" * 60)
    print("""
If symbols appear in Subscribed/Resubscribing but NOT in mark_price or position.update:
  → Data is NOT being linked to positions (likely format mismatch in self.positions)

If symbols appear mostly in "other":
  → Need to check what specific log messages appear

The format mismatch fix we just applied should help — after restart, check again.
""")


if __name__ == "__main__":
    main()
