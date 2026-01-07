#!/usr/bin/env python3
"""
CRITICAL BUG Investigation: Position Created Without Subscription

Analyzes logs around ANIMEUSDT position creation to find why subscription failed.

Run on server: python scripts/diagnose_anime_subscription.py
"""

import sys
import os
from datetime import datetime
from collections import Counter

def main():
    print("=" * 70)
    print("CRITICAL BUG INVESTIGATION: ANIMEUSDT SUBSCRIPTION FAILURE")
    print("=" * 70)
    print(f"Analysis Time: {datetime.now()}")
    print()
    
    log_file = "/home/elcrypto/TradingBot/logs/trading_bot.log"
    target_symbol = "ANIMEUSDT"
    
    # Read log file
    try:
        with open(log_file, 'r') as f:
            lines = f.readlines()
        print(f"Log file loaded: {len(lines)} lines")
    except Exception as e:
        print(f"Error reading log: {e}")
        return
    
    # Find all ANIMEUSDT mentions
    anime_lines = [(i, line) for i, line in enumerate(lines) if target_symbol in line]
    print(f"\nTotal {target_symbol} mentions: {len(anime_lines)}")
    
    if not anime_lines:
        print(f"\n❌ No mentions of {target_symbol} found in logs!")
        return
    
    # CHECK 1: Find first mention (position creation?)
    print()
    print("[CHECK 1] First ANIMEUSDT Mentions (Position Creation?)")
    print("-" * 60)
    
    for idx, (line_num, line) in enumerate(anime_lines[:10]):
        print(f"[{line_num}] {line.strip()[:120]}...")
    
    # CHECK 2: Look for subscription events
    print()
    print("[CHECK 2] Subscription Events")
    print("-" * 60)
    
    sub_events = [(i, l) for i, l in anime_lines if any(x in l for x in [
        "Subscrib", "subscribe", "SUBSCRIBE", "pending", "queued"
    ])]
    print(f"Subscription-related events: {len(sub_events)}")
    for idx, (line_num, line) in enumerate(sub_events[:10]):
        print(f"  [{line_num}] {line.strip()[:100]}...")
    
    # CHECK 3: Look for errors around position creation
    print()
    print("[CHECK 3] Errors Around First ANIMEUSDT Mention")
    print("-" * 60)
    
    if anime_lines:
        first_line_num = anime_lines[0][0]
        # Get 50 lines before and after
        context_start = max(0, first_line_num - 50)
        context_end = min(len(lines), first_line_num + 50)
        
        context_errors = []
        for i in range(context_start, context_end):
            line = lines[i]
            if any(x in line.lower() for x in ["error", "exception", "failed", "traceback"]):
                context_errors.append((i, line.strip()))
        
        print(f"Errors in context window [{context_start}:{context_end}]: {len(context_errors)}")
        for line_num, line in context_errors[:10]:
            print(f"  [{line_num}] {line[:100]}...")
    
    # CHECK 4: Look for ACCOUNT_UPDATE events
    print()
    print("[CHECK 4] ACCOUNT_UPDATE Events for ANIMEUSDT")
    print("-" * 60)
    
    account_updates = [(i, l) for i, l in anime_lines if "ACCOUNT_UPDATE" in l or "position.update" in l]
    print(f"ACCOUNT_UPDATE events: {len(account_updates)}")
    for idx, (line_num, line) in enumerate(account_updates[:5]):
        print(f"  [{line_num}] {line.strip()[:100]}...")
    
    # CHECK 5: Compare with successful symbol (e.g., most recent successful subscription)
    print()
    print("[CHECK 5] Recent Successful Subscriptions (for comparison)")
    print("-" * 60)
    
    successful_subs = [l for l in lines[-5000:] if "Subscribed to" in l and "pending cleared" in l]
    print(f"Recent successful subscriptions: {len(successful_subs)}")
    for line in successful_subs[-5:]:
        print(f"  {line.strip()[:80]}...")
    
    # CHECK 6: Look for format issues
    print()
    print("[CHECK 6] Format Analysis")
    print("-" * 60)
    
    anime_ccxt = sum(1 for l in lines if "ANIME/USDT:USDT" in l)
    anime_binance = sum(1 for l in lines if "ANIMEUSDT" in l)
    print(f"CCXT format (ANIME/USDT:USDT): {anime_ccxt}")
    print(f"Binance format (ANIMEUSDT): {anime_binance}")
    
    # CHECK 7: Check subscribed_symbols state
    print()
    print("[CHECK 7] Subscription State Logs")
    print("-" * 60)
    
    state_logs = [(i, l) for i, l in anime_lines if any(x in l for x in [
        "subscribed_symbols", "pending_subscriptions", "health check", "health OK"
    ])]
    print(f"Subscription state logs: {len(state_logs)}")
    for idx, (line_num, line) in enumerate(state_logs[:5]):
        print(f"  [{line_num}] {line.strip()[:100]}...")
    
    # CHECK 8: Timeline of ALL ANIMEUSDT events
    print()
    print("[CHECK 8] Full Timeline (last 50 events)")
    print("-" * 60)
    
    for idx, (line_num, line) in enumerate(anime_lines[-50:]):
        # Extract timestamp if present
        timestamp = line[:23] if len(line) > 23 else "?"
        # Categorize event
        if "Subscrib" in line:
            event_type = "📬 SUBSCRIPTION"
        elif "position" in line.lower():
            event_type = "📊 POSITION"
        elif "error" in line.lower():
            event_type = "❌ ERROR"
        elif "ACCOUNT_UPDATE" in line:
            event_type = "🔄 ACC_UPDATE"
        elif "price" in line.lower() or "mark" in line.lower():
            event_type = "💰 PRICE"
        else:
            event_type = "📝 OTHER"
        
        short_content = line[24:].strip()[:60] if len(line) > 24 else line.strip()[:60]
        print(f"{timestamp} {event_type}: {short_content}...")
    
    # CONCLUSION
    print()
    print("=" * 70)
    print("INVESTIGATION SUMMARY")
    print("=" * 70)
    
    has_subscription = any("Subscribed" in l[1] and target_symbol in l[1] for l in anime_lines)
    has_position_update = any("position.update" in l[1] for l in anime_lines)
    has_errors = any("error" in l[1].lower() for l in anime_lines)
    
    print(f"""
Symbol: {target_symbol}
Total Log Entries: {len(anime_lines)}
Subscription Events: {len(sub_events)}
Position Updates: {len(account_updates)}
Has 'Subscribed' confirmation: {'✅ YES' if has_subscription else '❌ NO'}
Has position.update events: {'✅ YES' if has_position_update else '❌ NO'}
Has errors: {'⚠️ YES' if has_errors else '✅ NO'}

NEXT STEPS:
1. Check if subscription was requested but never confirmed
2. Check if there's a queue processing issue
3. Check if format mismatch in positions dict prevents updates
""")


if __name__ == "__main__":
    main()
