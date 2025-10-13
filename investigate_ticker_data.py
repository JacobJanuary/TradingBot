#!/usr/bin/env python3
"""
CRITICAL INVESTIGATION: HNTUSDT Price Mismatch
==============================================
Bot used price 3.31 when marked price on exchange is 1.61
This is a 2x difference - CRITICAL ERROR!

This script will:
1. Fetch ticker data for HNTUSDT from Bybit testnet
2. Show ALL price fields returned by fetch_ticker
3. Compare 'last' vs 'mark' prices
4. Identify which price should be used for SL calculation
"""

import asyncio
import ccxt.async_support as ccxt
from decimal import Decimal
import json
from datetime import datetime


async def investigate_ticker_prices():
    """Fetch and analyze ticker data from Bybit testnet"""

    # Initialize Bybit testnet connection (same as bot uses)
    exchange = ccxt.bybit({
        'apiKey': 'JicrzNxY1jRPeSb5p9',
        'secret': 'DgvCFnkfTisRtAhRudMkbk8mIzEzDn66NKNd',
        'options': {
            'defaultType': 'swap',  # Perpetual futures
        }
    })

    # Set testnet
    exchange.set_sandbox_mode(True)

    try:
        print("="*80)
        print("INVESTIGATION: HNTUSDT Price Mismatch")
        print("="*80)
        print(f"Timestamp: {datetime.now()}")
        print()

        symbol = 'HNTUSDT'

        print(f"Fetching ticker for {symbol}...")
        ticker = await exchange.fetch_ticker(symbol)

        print()
        print("="*80)
        print("FULL TICKER DATA:")
        print("="*80)
        print(json.dumps(ticker, indent=2, default=str))
        print()

        # Extract key prices
        last_price = ticker.get('last')
        mark_price = ticker.get('mark')
        bid = ticker.get('bid')
        ask = ticker.get('ask')
        index_price = ticker.get('info', {}).get('indexPrice')

        print("="*80)
        print("KEY PRICES ANALYSIS:")
        print("="*80)
        print(f"ticker['last']:           {last_price}")
        print(f"ticker['mark']:           {mark_price}")
        print(f"ticker['bid']:            {bid}")
        print(f"ticker['ask']:            {ask}")
        print(f"ticker['info']['indexPrice']: {index_price}")
        print()

        # Show what bot's code does
        print("="*80)
        print("WHAT BOT'S CODE DOES:")
        print("="*80)
        print("Code: current_price = float(ticker.get('last') or ticker.get('mark') or 0)")
        print()

        bot_price = float(ticker.get('last') or ticker.get('mark') or 0)
        print(f"Result: bot_price = {bot_price}")
        print()

        # Compare to marked price
        if mark_price and last_price:
            diff_pct = abs((last_price - mark_price) / mark_price) * 100
            print(f"DIFFERENCE: last vs mark = {diff_pct:.2f}%")
            print()

            if diff_pct > 10:
                print("⚠️ WARNING: LARGE DISCREPANCY DETECTED!")
                print(f"   last price ({last_price}) differs from mark price ({mark_price}) by {diff_pct:.2f}%")
                print()

        # Analysis
        print("="*80)
        print("ANALYSIS:")
        print("="*80)
        print("'last':  Last traded price (can be old/stale in low liquidity)")
        print("'mark':  Fair price calculated by exchange (used for liquidations)")
        print()
        print("For perpetual futures, 'mark' price is MORE ACCURATE because:")
        print("  - It's continuously calculated by exchange")
        print("  - It's used for liquidations and unrealized PnL")
        print("  - It's less susceptible to manipulation")
        print("  - 'last' can be stale if no recent trades")
        print()

        # Recommendation
        print("="*80)
        print("RECOMMENDATION:")
        print("="*80)
        if mark_price:
            print(f"✅ USE MARK PRICE: {mark_price}")
            print("   This is the fair price used by exchange for liquidations")
        else:
            print(f"⚠️ FALLBACK TO LAST PRICE: {last_price}")
            print("   Mark price not available")
        print()

        # Check position data too
        print("="*80)
        print("CHECKING POSITION DATA FROM EXCHANGE:")
        print("="*80)

        try:
            positions = await exchange.fetch_positions([symbol])
            if positions:
                for pos in positions:
                    if pos['contracts'] and float(pos['contracts']) > 0:
                        print(f"Position found for {symbol}:")
                        print(f"  Entry Price:     {pos.get('entryPrice')}")
                        print(f"  Mark Price:      {pos.get('markPrice')}")
                        print(f"  Liquidation:     {pos.get('liquidationPrice')}")
                        print(f"  Unrealized PnL:  {pos.get('unrealizedPnl')}")
                        print()
            else:
                print("No open positions found")
        except Exception as e:
            print(f"Could not fetch position data: {e}")

        print("="*80)

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await exchange.close()


if __name__ == "__main__":
    asyncio.run(investigate_ticker_prices())
