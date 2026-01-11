#!/usr/bin/env python3
"""
Diagnose HYPERUSDT creation issues (~Jan 5) and check subscription health.
"""
import re
from datetime import datetime

def main():
    log_file = "/home/elcrypto/TradingBot/logs/trading_bot.log"
    target_symbol = "HYPERUSDT"
    target_time = "05:05"
    
    print(f"Analyzing logs for {target_symbol} around time {target_time}...")
    
    try:
        with open(log_file, 'r') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading log file: {e}")
        return

    # 1. Analyze HYPERUSDT events
    hyper_events = []
    
    for line in lines[-50000:]: # Last 50k lines
        if target_symbol in line:
            # Capture ALL HYPERUSDT events to see context
            hyper_events.append(line.strip())
            
    print(f"\nFound {len(hyper_events)} events for {target_symbol} (showing context around 05:05 if exists).")
    
    # Filter for 05:05 specifically
    specific_events = [e for e in hyper_events if target_time in e]
    
    if specific_events:
        print(f"EVENTS AT {target_time}:")
        for e in specific_events:
            print(e)
    else:
        print(f"No events found specifically at {target_time}. Showing last 20 general events for symbol:")
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

    # 3. Check Subscription Health Warnings (Expanded)
    print("\n--- SUBSCRIPTION HEALTH ---")
    sub_warns = []
    # Expanded patterns to catch stale data warnings AND connection issues
    warn_patterns = [
        "positions WITHOUT subscriptions", 
        "Subscription gap",
        "SILENT FAILS",
        "STALE POSITIONS",
        "STALE SUBSCRIPTION",
        "Connection lost",
        "Reconnecting",
        "Connection closed",
        "Restoring"
    ]
    
    for line in lines[-20000:]: # Last 20k lines
        if any(p in line for p in warn_patterns):
            sub_warns.append(line.strip())
            
    if sub_warns:
        print(f"⚠️ Found {len(sub_warns)} subscription warnings!")
        for w in sub_warns[-10:]: # Show last 10
            print(w)
    else:
        print("✅ No active subscription warnings found in recent logs.")

if __name__ == "__main__":
    main()
