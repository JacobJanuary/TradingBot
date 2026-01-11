#!/usr/bin/env python3
"""
Diagnose HYPERUSDT creation issues (~Jan 5) and check subscription health.
"""
import re
from datetime import datetime

def main():
    log_file = "/home/elcrypto/TradingBot/logs/trading_bot.log"
    target_symbol = "HYPERUSDT"
    target_date_patterns = ["2026-01-05", "2026-01-04", "2026-01-06"]  # Range around Jan 5
    
    print(f"Analyzing logs for {target_symbol} around Jan 5...")
    
    try:
        with open(log_file, 'r') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading log file: {e}")
        return

    # 1. Analyze HYPERUSDT events
    hyper_events = []
    
    for line in lines:
        if target_symbol in line:
            if any(d in line for d in target_date_patterns):
                hyper_events.append(line.strip())
    
    print(f"\nFound {len(hyper_events)} events for {target_symbol} around Jan 5.")
    if len(hyper_events) > 0:
        print("Last 20 events:")
        for e in hyper_events[-20:]:
            print(e)
            
    # 2. Check RETRY logic generic errors
    print("\n--- RETRY MODULE CHECK ---")
    retry_patterns = ["Retrying", "retry attempt", "Max retries exceeded"]
    retry_events = []
    for line in lines[-50000:]: # Last 50k lines for recent retry health
         if any(p in line for p in retry_patterns):
             retry_events.append(line.strip())
             
    print(f"Found {len(retry_events)} retry events in last 50k lines.")
    for e in retry_events[-10:]:
        print(e)

    # 3. Check Subscription Health Warnings
    print("\n--- SUBSCRIPTION HEALTH ---")
    sub_warns = []
    for line in lines[-20000:]: # Last 20k lines
        if "positions WITHOUT subscriptions" in line or "Subscription gap" in line:
            sub_warns.append(line.strip())
            
    if sub_warns:
        print(f"⚠️ Found {len(sub_warns)} subscription warnings!")
        for w in sub_warns[-5:]:
            print(w)
    else:
        print("✅ No active subscription warnings found in recent logs.")

if __name__ == "__main__":
    main()
