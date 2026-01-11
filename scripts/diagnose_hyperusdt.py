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
    
import glob
import os

def main():
    log_dir = "/home/elcrypto/TradingBot/logs"
    log_files = glob.glob(f"{log_dir}/trading_bot.log*")
    # Sort logs: trading_bot.log is newest, .1 is older, etc.
    # Usually log rotation renames current to .1. So we want to check all.
    # But simple ascii sort might put .10 before .2.
    # Let's just process all of them.
    
    target_times = ["05:01", "05:02", "05:03"] # 3 minute window
    target_symbol = "HYPERUSDT"
    
    print(f"Analyzing {len(log_files)} log files in {log_dir}...")
    print(f"Target Time Window: {target_times}")
    
    found_events = []
    error_events = []
    
    min_time_seen = "9999"
    max_time_seen = "0000"
    
    total_lines = 0
    
    for log_file in log_files:
        try:
            with open(log_file, 'r') as f:
                # Read line by line to avoid memory issues if massive
                for line in f:
                    total_lines += 1
                    # Extract roughly time
                    # Format: 2026-01-11 08:34:44,...
                    if len(line) > 20:
                        timestamp = line[11:16] # "08:34"
                        if timestamp < min_time_seen: min_time_seen = timestamp
                        if timestamp > max_time_seen: max_time_seen = timestamp
                        
                        # Check target window
                        if any(t in line for t in target_times):
                            if target_symbol in line:
                                found_events.append(f"[{os.path.basename(log_file)}] {line.strip()}")
                            
                            if "error" in line.lower() or "failed" in line.lower() or "retry" in line.lower() or "exception" in line.lower():
                                error_events.append(f"[{os.path.basename(log_file)}] {line.strip()}")
                                
        except Exception as e:
            print(f"Error reading {log_file}: {e}")

    print(f"Scanned {total_lines} lines.")
    print(f"Log Coverage (Approx): {min_time_seen} to {max_time_seen}")

    if found_events:
        print(f"\n✅ Found {len(found_events)} {target_symbol} events in window:")
        for e in sorted(found_events): # Sort might not be perfect time-wise but helps
            print(e)
    else:
        print(f"\n❌ No {target_symbol} events found in 05:01-05:03 window.")

    if error_events:
        print(f"\n❌ Found {len(error_events)} FAILURES in window:")
        for e in sorted(error_events):
            print(e)
    else:
        print("\n✅ No errors found in 05:01-05:03 window.")
            
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
