#!/usr/bin/env python3
"""
Script to analyze TAUSDT closure in logs.
Scans for TAUSDT checks, closure events, and age calculations.
"""

import sys
import re
from datetime import datetime

def main():
    log_file = "/home/elcrypto/TradingBot/logs/trading_bot.log"
    symbol = "TAUSDT"
    
    print(f"Analyzing {log_file} for {symbol} events...")
    
    try:
        with open(log_file, 'r') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading log file: {e}")
        return

    # Look for detailed closure reason (sync, order update, etc)
    closure_patterns = [
        "sync_cleanup", "ORDER_TRADE_UPDATE", "execution", "FILLED",
        "Stop Loss triggered", "Trailing Stop triggered",
        "reconciliation", "Closed on exchange", "discrepancy"
    ]
    
    events = []
    
    # Look for ANY trade updates around the closure time 00:09:46
    target_time_snippets = ["00:09:4", "00:09:5"]
    
    events = []
    
    for line in lines[-50000:]:
        # If it's around the target time (00:09:4x or 00:09:5x)
        if any(t in line for t in target_time_snippets):
            # Capture relevant events
            if "ORDER_TRADE_UPDATE" in line or "execution" in line or "TAUSDT" in line:
                events.append(line.strip())
                
    print(f"Found {len(events)} events around 00:09:46. Showing ALL:")
    for line in events:
        print(line)

if __name__ == "__main__":
    main()
