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

    # Look for closure events
    closure_patterns = [
        "closed", "selling", "Selling", "CLOSE", "closing", 
        "Max age", "aged", "monitor", "zombie"
    ]
    
    events = []
    
    for line in lines[-50000:]:  # Scan last 50k lines
        if symbol in line:
            # Check for interesting keywords
            if any(p in line for p in closure_patterns):
                events.append(line.strip())
            # Check for age calculations logs
            if "Calculated age=" in line or "age=" in line:
                events.append(line.strip())
                
    print(f"Found {len(events)} relevant events. Showing last 30:")
    for line in events[-30:]:
        print(line)

if __name__ == "__main__":
    main()
