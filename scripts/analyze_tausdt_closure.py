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
    
    # Scan specifically around the event time (00:09:46)
    # 50k lines covers about 1 hour usually, should be enough
    for line in lines[-50000:]:
        # Filter for TAUSDT or relevant generic events if close to our timestamp
        if symbol in line or "ORDER_TRADE_UPDATE" in line:
            if any(p in line for p in closure_patterns):
                events.append(line.strip())
                
    print(f"Found {len(events)} relevant events. Showing last 40:")
    for line in events[-40:]:
        print(line)

if __name__ == "__main__":
    main()
