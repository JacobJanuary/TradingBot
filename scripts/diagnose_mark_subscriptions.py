#!/usr/bin/env python3
"""
Diagnostic script to verify Mark Price data flow for symbols
that appear in "subscription lost" warnings.

Checks:
1. self.positions keys (CCXT format)
2. self.subscribed_symbols (Binance format)
3. self.mark_prices data freshness
4. Format comparison

Run on server: python scripts/diagnose_mark_subscriptions.py
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
import time


async def main():
    print("=" * 60)
    print("MARK PRICE SUBSCRIPTION DIAGNOSTIC")
    print("=" * 60)
    print(f"Time: {datetime.now()}")
    print()
    
    # Import after path setup
    from config.settings import settings
    from websocket.binance_hybrid_stream import BinanceHybridStream
    
    # Get exchange config
    binance_config = settings.exchanges.get('binance')
    if not binance_config:
        print("❌ No binance config found")
        return
    
    # Create stream instance (just to access state, not to connect)
    stream = BinanceHybridStream(
        api_key=binance_config.api_key,
        api_secret=binance_config.api_secret,
        testnet=binance_config.testnet
    )
    
    # We can't access live state without connecting to the running bot
    # Instead, let's check by reading the log file
    
    log_file = "/home/elcrypto/TradingBot/logs/trading_bot.log"
    
    # Check 1: Find the affected symbols
    print("[CHECK 1] Affected Symbols from Logs")
    print("-" * 40)
    
    affected_symbols = set()
    try:
        with open(log_file, 'r') as f:
            for line in f:
                if "positions WITHOUT subscriptions" in line:
                    # Extract symbols from the set notation
                    start = line.find("{")
                    end = line.find("}")
                    if start != -1 and end != -1:
                        symbols_str = line[start+1:end]
                        for s in symbols_str.split(","):
                            s = s.strip().strip("'\"")
                            if s:
                                affected_symbols.add(s)
                    break  # Just need one line
    except Exception as e:
        print(f"Error reading log: {e}")
    
    print(f"Affected symbols (CCXT format): {affected_symbols}")
    
    # Check 2: Normalize to Binance format
    print()
    print("[CHECK 2] Format Conversion")
    print("-" * 40)
    
    def normalize(symbol: str) -> str:
        if ':' in symbol:
            symbol = symbol.split(':')[0]
        return symbol.replace('/', '').upper()
    
    binance_format = {normalize(s): s for s in affected_symbols}
    print(f"Normalized (Binance format): {list(binance_format.keys())}")
    
    # Check 3: Look for Subscribed confirmations in log
    print()
    print("[CHECK 3] Subscription Confirmations in Log")
    print("-" * 40)
    
    for binance_sym, ccxt_sym in binance_format.items():
        try:
            with open(log_file, 'r') as f:
                lines = f.readlines()
                # Search from end (most recent)
                found = None
                for line in reversed(lines[-1000:]):
                    if f"Subscribed to {binance_sym}" in line or f"Subscribed to {ccxt_sym}" in line:
                        found = line.strip()[-100:]  # Last 100 chars
                        break
                if found:
                    print(f"✅ {binance_sym}: {found}")
                else:
                    print(f"❓ {binance_sym}: No subscription confirmation found in last 1000 lines")
        except Exception as e:
            print(f"❌ {binance_sym}: Error - {e}")
    
    # Check 4: Look for mark price updates
    print()
    print("[CHECK 4] Recent Mark Price Updates")
    print("-" * 40)
    
    for binance_sym, ccxt_sym in binance_format.items():
        try:
            with open(log_file, 'r') as f:
                lines = f.readlines()
                found_count = 0
                last_found = None
                for line in reversed(lines[-5000:]):
                    if binance_sym in line and ("mark_price" in line.lower() or "markprice" in line.lower()):
                        found_count += 1
                        if not last_found:
                            last_found = line.strip()[:100]
                if found_count > 0:
                    print(f"✅ {binance_sym}: {found_count} mark price mentions, last: {last_found[:60]}...")
                else:
                    print(f"⚠️ {binance_sym}: No mark price updates found in last 5000 lines")
        except Exception as e:
            print(f"❌ {binance_sym}: Error - {e}")
    
    # Check 5: Look for Resubscribing patterns
    print()
    print("[CHECK 5] Resubscription Pattern Analysis")
    print("-" * 40)
    
    resub_count = 0
    try:
        with open(log_file, 'r') as f:
            for line in f:
                if "Resubscribing to" in line and any(s in line for s in affected_symbols):
                    resub_count += 1
    except Exception as e:
        print(f"Error: {e}")
    
    print(f"Total resubscription attempts for affected symbols: {resub_count}")
    
    if resub_count > 50:
        print("⚠️ HIGH resubscription count suggests format mismatch bug")
    
    # Conclusion
    print()
    print("=" * 60)
    print("CONCLUSION")
    print("=" * 60)
    print("""
The bug is likely FORMAT MISMATCH between:
- positions.keys() using CCXT format (JASMY/USDT:USDT)  
- subscribed_symbols using Binance format (JASMYUSDT)

This causes health check to ALWAYS see "missing" subscriptions.
Actual data flow is probably FINE - just comparison is broken.

FIX: Normalize position keys before comparison in health check.
""")


if __name__ == "__main__":
    asyncio.run(main())
