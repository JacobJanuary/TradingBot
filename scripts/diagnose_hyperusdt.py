#!/usr/bin/env python3
"""
Diagnose HYPERUSDT creation issues (~Jan 5) and check subscription health.
"""
import re
from datetime import datetime

def main():
    log_file = "/home/elcrypto/TradingBot/logs/trading_bot.log"
    target_symbol = "HYPERUSDT"
    target_time = "05:02"
    
    print(f"Analyzing logs for {target_symbol} around time {target_time}...")
    
    try:
        with open(log_file, 'r') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading log file: {e}")
        return

    # 1. Analyze HYPERUSDT events
    hyper_events = []
    error_events_at_time = []
    
    for line in lines[-50000:]: # Last 50k lines
        if target_symbol in line:
            hyper_events.append(line.strip())
        
        if target_time in line and ("error" in line.lower() or "failed" in line.lower() or "retry" in line.lower() or "exception" in line.lower()):
            error_events_at_time.append(line.strip())
            
    print(f"\nFound {len(hyper_events)} events for {target_symbol} total.")
    
    # Filter for 05:02 specifically details
    specific_events = [e for e in hyper_events if target_time in e]
    
    if specific_events:
        print(f"\nEVENTS AT {target_time} for {target_symbol}:")
        for e in specific_events:
            print(e)
    else:
        print(f"No {target_symbol} events found specifically at {target_time}.")

    if error_events_at_time:
         print(f"\n❌ ALL ERRORS/FAILURES AT {target_time}:")
         for e in error_events_at_time:
             print(e)
    else:
         print(f"No errors found at {target_time} generic search.")
         
    # Show nearby context if possible
    # ...
            
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
