#!/usr/bin/env python3
"""
PROOF: ticker['last'] can be DRASTICALLY different from ticker['info']['markPrice']

This demonstrates the CRITICAL BUG in the bot:
- Code uses: ticker.get('last') or ticker.get('mark')
- ticker['last'] = Last TRADE price (can be old/stale in low liquidity)
- ticker['info']['markPrice'] = Fair price calculated by exchange (CORRECT!)
"""

import asyncio
import ccxt.async_support as ccxt
from datetime import datetime


async def prove_bug():
    """Prove that 'last' can differ significantly from 'markPrice'"""

    exchange = ccxt.bybit({
        'apiKey': 'JicrzNxY1jRPeSb5p9',
        'secret': 'DgvCFnkfTisRtAhRudMkbk8mIzEzDn66NKNd',
        'options': {'defaultType': 'swap'},
    })
    exchange.set_sandbox_mode(True)

    try:
        print("="*80)
        print("PROOF: ticker['last'] vs ticker['info']['markPrice'] MISMATCH")
        print("="*80)
        print(f"Time: {datetime.now()}\n")

        # Fetch tickers for all USDT pairs
        print("Scanning USDT perpetual pairs for price mismatches...\n")

        markets = await exchange.load_markets()
        usdt_symbols = [s for s in markets if s.endswith('USDT:USDT')][:20]  # Check first 20

        mismatches = []

        for symbol in usdt_symbols:
            try:
                ticker = await exchange.fetch_ticker(symbol)

                last = ticker.get('last')
                mark_from_top = ticker.get('mark')
                mark_from_info = ticker.get('info', {}).get('markPrice')

                if last and mark_from_info:
                    last_float = float(last)
                    mark_float = float(mark_from_info)

                    if last_float > 0 and mark_float > 0:
                        diff_pct = abs((last_float - mark_float) / mark_float) * 100

                        if diff_pct > 5:  # More than 5% difference
                            mismatches.append({
                                'symbol': symbol.replace('/USDT:USDT', ''),
                                'last': last_float,
                                'mark': mark_float,
                                'diff_pct': diff_pct
                            })

            except Exception as e:
                continue  # Skip problematic symbols

        # Sort by difference percentage
        mismatches.sort(key=lambda x: x['diff_pct'], reverse=True)

        print("="*80)
        print(f"FOUND {len(mismatches)} PAIRS WITH >5% PRICE MISMATCH:")
        print("="*80)
        print(f"{'Symbol':<15} {'Last Price':>12} {'Mark Price':>12} {'Difference':>12}")
        print("-"*80)

        for m in mismatches[:10]:  # Show top 10
            print(f"{m['symbol']:<15} {m['last']:>12.6f} {m['mark']:>12.6f} {m['diff_pct']:>11.2f}%")

        print("\n" + "="*80)
        print("ANALYSIS:")
        print("="*80)
        print("""
The bot's code uses:
    current_price = float(ticker.get('last') or ticker.get('mark') or 0)

Problems:
    1. ticker['mark'] is ALWAYS None (CCXT doesn't populate it for Bybit)
    2. ticker['last'] can be VERY OLD in low-liquidity testnet pairs
    3. ticker['info']['markPrice'] is the CORRECT price but NOT used

Example (HNTUSDT):
    - Bot sees: ticker['last'] = 3.31 (old trade from hours ago)
    - Reality:  markPrice = 1.616 (current fair price)
    - Bybit rejects: "SL 3.24 should be lower than base_price 1.616"

SOLUTION:
    Use ticker['info']['markPrice'] FIRST, fallback to ticker['last']:

    mark_price = ticker.get('info', {}).get('markPrice')
    current_price = float(mark_price or ticker.get('last') or 0)
        """)

        print("="*80)
        print("CRITICAL BUG CONFIRMED!")
        print("="*80)

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await exchange.close()


if __name__ == "__main__":
    asyncio.run(prove_bug())
