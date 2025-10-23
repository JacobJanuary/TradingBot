#!/usr/bin/env python3
"""
CASE #1: Reproduce HNTUSDT Symbol Mismatch Issue

Test Hypothesis:
    fetch_ticker("HNTUSDT") returns wrong price data
    Should use "HNT/USDT:USDT" for Bybit perpetuals

Expected Results:
    - HNTUSDT format: Wrong price or error
    - HNT/USDT:USDT format: Correct price ~$1.62

Evidence from Logs:
    - DB stores: HNTUSDT
    - WebSocket receives: HNT/USDT:USDT with price 1.616
    - fetch_ticker(HNTUSDT) returned: 3.310 (WRONG!)
    - This led to invalid SL calculation

Author: Forensic Analysis - CASE #1
Date: 2025-10-22
"""

import asyncio
import ccxt.async_support as ccxt
from datetime import datetime
import os
import sys
from decimal import Decimal

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


class Case01SymbolMismatchTest:
    """Test suite for CASE #1: Symbol mismatch investigation"""

    def __init__(self, use_testnet=True):
        self.use_testnet = use_testnet
        self.results = {
            'bug_confirmed': False,
            'wrong_price': None,
            'correct_price': None,
            'evidence': []
        }

    async def setup_exchange(self):
        """Initialize Bybit exchange connection"""
        config = {
            'options': {
                'defaultType': 'swap',  # USDT perpetual futures
            },
            'enableRateLimit': True
        }

        if self.use_testnet:
            config['options']['testnet'] = True
            print("🔧 Using Bybit TESTNET")
        else:
            print("⚠️ Using Bybit PRODUCTION")

        # NOTE: Update with actual credentials for testnet testing
        # For this forensic test, we can use public endpoints (no auth needed for ticker data)

        exchange = ccxt.bybit(config)
        return exchange

    async def test_1_list_hnt_symbols(self, exchange):
        """List all HNT-related trading pairs"""
        print("\n" + "="*70)
        print("TEST 1: List Available HNT Symbols")
        print("="*70)

        await exchange.load_markets()

        hnt_symbols = [s for s in exchange.symbols if 'HNT' in s.upper()]

        if hnt_symbols:
            print(f"\n✓ Found {len(hnt_symbols)} HNT symbol(s):")
            for sym in hnt_symbols:
                market = exchange.market(sym)
                print(f"   - {sym}")
                print(f"     Type: {market.get('type')}")
                print(f"     Base: {market.get('base')}, Quote: {market.get('quote')}")
        else:
            print("❌ No HNT symbols found!")
            self.results['evidence'].append("No HNT symbols found in market")

        return hnt_symbols

    async def test_2_fetch_with_db_symbol(self, exchange):
        """Test fetching ticker with database symbol format (HNTUSDT)"""
        print("\n" + "="*70)
        print("TEST 2: Fetch Ticker with DB Symbol 'HNTUSDT'")
        print("="*70)

        db_symbol = "HNTUSDT"

        try:
            print(f"\n📡 Calling: exchange.fetch_ticker('{db_symbol}')")
            ticker = await exchange.fetch_ticker(db_symbol)

            # Extract price data
            last_price = ticker.get('last')
            mark_price = ticker.get('info', {}).get('markPrice')
            symbol_returned = ticker.get('symbol')

            print(f"\n✓ Success! Response received:")
            print(f"   Symbol returned:  {symbol_returned}")
            print(f"   Last price:       {last_price}")
            print(f"   Mark price:       {mark_price}")
            print(f"   Timestamp:        {ticker.get('timestamp')}")

            # What the bot code does
            current_price = float(mark_price or last_price or 0)
            print(f"\n📊 Bot logic: current_price = float(mark_price or last or 0)")
            print(f"   Result: {current_price}")

            self.results['wrong_price'] = current_price
            self.results['db_symbol_works'] = True
            self.results['evidence'].append(f"HNTUSDT → price={current_price}")

            return ticker, current_price

        except Exception as e:
            print(f"\n❌ Error: {type(e).__name__}: {e}")
            self.results['db_symbol_works'] = False
            self.results['evidence'].append(f"HNTUSDT → Error: {e}")
            return None, None

    async def test_3_fetch_with_ccxt_symbol(self, exchange):
        """Test fetching ticker with CCXT unified symbol (HNT/USDT:USDT)"""
        print("\n" + "="*70)
        print("TEST 3: Fetch Ticker with CCXT Symbol 'HNT/USDT:USDT'")
        print("="*70)

        ccxt_symbol = "HNT/USDT:USDT"

        try:
            print(f"\n📡 Calling: exchange.fetch_ticker('{ccxt_symbol}')")
            ticker = await exchange.fetch_ticker(ccxt_symbol)

            # Extract price data
            last_price = ticker.get('last')
            mark_price = ticker.get('info', {}).get('markPrice')
            symbol_returned = ticker.get('symbol')

            print(f"\n✓ Success! Response received:")
            print(f"   Symbol returned:  {symbol_returned}")
            print(f"   Last price:       {last_price}")
            print(f"   Mark price:       {mark_price}")
            print(f"   Timestamp:        {ticker.get('timestamp')}")

            # What the bot code does
            current_price = float(mark_price or last_price or 0)
            print(f"\n📊 Bot logic: current_price = float(mark_price or last or 0)")
            print(f"   Result: {current_price}")

            self.results['correct_price'] = current_price
            self.results['ccxt_symbol_works'] = True
            self.results['evidence'].append(f"HNT/USDT:USDT → price={current_price}")

            return ticker, current_price

        except Exception as e:
            print(f"\n❌ Error: {type(e).__name__}: {e}")
            self.results['ccxt_symbol_works'] = False
            self.results['evidence'].append(f"HNT/USDT:USDT → Error: {e}")
            return None, None

    async def test_4_compare_prices(self, price_from_db_symbol, price_from_ccxt_symbol):
        """Compare prices from both symbol formats"""
        print("\n" + "="*70)
        print("TEST 4: Price Comparison")
        print("="*70)

        if price_from_db_symbol is None or price_from_ccxt_symbol is None:
            print("\n⚠️ Cannot compare: One or both prices unavailable")
            return

        print(f"\nDB Symbol (HNTUSDT):       ${price_from_db_symbol:.6f}")
        print(f"CCXT Symbol (HNT/USDT:USDT): ${price_from_ccxt_symbol:.6f}")

        diff = abs(price_from_db_symbol - price_from_ccxt_symbol)
        diff_pct = (diff / price_from_ccxt_symbol) * 100 if price_from_ccxt_symbol > 0 else 0

        print(f"\nDifference:  ${diff:.6f} ({diff_pct:.2f}%)")

        # Bug detection
        if diff_pct > 5:  # More than 5% difference
            print(f"\n🚨 BUG CONFIRMED! Price difference: {diff_pct:.2f}%")
            print("   The two symbol formats return DIFFERENT prices!")
            print("   This explains the invalid SL calculation in production.")
            self.results['bug_confirmed'] = True
            self.results['evidence'].append(f"Price diff: {diff_pct:.2f}% - BUG CONFIRMED")
        elif diff_pct > 0.1:
            print(f"\n⚠️ Minor difference: {diff_pct:.2f}%")
            print("   Could be timing or spread, but warrants investigation")
            self.results['evidence'].append(f"Price diff: {diff_pct:.2f}% - Minor variance")
        else:
            print(f"\n✅ Prices match (diff: {diff_pct:.4f}%)")
            print("   Both symbol formats return same data")
            print("   Bug not reproduced (may be production-specific issue)")
            self.results['evidence'].append(f"Price diff: {diff_pct:.4f}% - No issue")

    async def test_5_reproduce_bot_logic(self, exchange):
        """Reproduce the exact bot logic from logs"""
        print("\n" + "="*70)
        print("TEST 5: Reproduce Bot's Exact Logic")
        print("="*70)

        # From production logs
        entry_price = 1.75154900
        position_symbol = "HNTUSDT"  # Symbol from database
        stop_loss_percent = 2.0

        print(f"\nPosition Details (from production):")
        print(f"   Symbol:       {position_symbol}")
        print(f"   Entry Price:  ${entry_price}")
        print(f"   SL Percent:   {stop_loss_percent}%")

        # Reproduce bot code (position_manager.py:2689-2691)
        print(f"\n📝 Executing bot's code:")
        print(f"   ticker = await exchange.fetch_ticker('{position_symbol}')")

        try:
            ticker = await exchange.fetch_ticker(position_symbol)
            mark_price = ticker.get('info', {}).get('markPrice')
            current_price = float(mark_price or ticker.get('last') or 0)

            print(f"   mark_price = ticker.get('info', {{}}).get('markPrice')")
            print(f"   current_price = float(mark_price or ticker.get('last') or 0)")
            print(f"\n   Result: current_price = {current_price}")

            # Calculate drift (position_manager.py:2703)
            price_drift_pct = abs((current_price - entry_price) / entry_price) * 100

            print(f"\n📊 Drift Calculation:")
            print(f"   Entry:   ${entry_price}")
            print(f"   Current: ${current_price}")
            print(f"   Drift:   {price_drift_pct:.2f}%")

            # Check drift threshold (position_manager.py:2711)
            threshold = stop_loss_percent * 100  # 200%
            print(f"\n🔍 Drift Check:")
            print(f"   Threshold: {threshold:.2f}%")

            if price_drift_pct > stop_loss_percent:
                print(f"   ⚠️ DRIFT EXCEEDED! Using current price for SL base")
                base_price = current_price
                use_current = True
            else:
                print(f"   ✅ Drift within threshold. Using entry for SL base")
                base_price = entry_price
                use_current = False

            # Calculate SL
            sl_price = base_price * (1 - stop_loss_percent / 100)

            print(f"\n💰 SL Calculation:")
            print(f"   Base Price: ${base_price:.6f} ({'current' if use_current else 'entry'})")
            print(f"   SL Price:   ${sl_price:.6f} (base * 0.{100 - int(stop_loss_percent)})")

            # Check if this matches production error
            if current_price > 3.0 and entry_price < 2.0:
                print(f"\n🚨 BUG REPRODUCED!")
                print(f"   Fetched price ({current_price:.2f}) is far from entry ({entry_price:.2f})")
                print(f"   This matches production logs: 'Using current price 3.310000'")
                self.results['bug_confirmed'] = True
                self.results['evidence'].append("Bot logic reproduced with wrong price")

            # Bybit validation check
            print(f"\n🏦 Bybit Validation:")
            print(f"   For LONG: SL must be < current market price")
            if sl_price >= current_price:
                print(f"   ❌ INVALID! SL ({sl_price:.4f}) >= Current ({current_price:.4f})")
                print(f"   Bybit will reject this order")
                self.results['evidence'].append(f"SL validation fail: {sl_price:.4f} >= {current_price:.4f}")
            else:
                print(f"   ✅ Valid: SL ({sl_price:.4f}) < Current ({current_price:.4f})")

        except Exception as e:
            print(f"\n❌ Error reproducing logic: {e}")
            self.results['evidence'].append(f"Bot logic error: {e}")

    def generate_report(self):
        """Generate final test report"""
        print("\n" + "="*70)
        print("FINAL REPORT: CASE #1 Symbol Mismatch Test")
        print("="*70)

        print(f"\n📋 Test Results:")
        print(f"   Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        if self.results.get('db_symbol_works'):
            print(f"   ✓ DB symbol 'HNTUSDT' works")
        else:
            print(f"   ✗ DB symbol 'HNTUSDT' failed")

        if self.results.get('ccxt_symbol_works'):
            print(f"   ✓ CCXT symbol 'HNT/USDT:USDT' works")
        else:
            print(f"   ✗ CCXT symbol 'HNT/USDT:USDT' failed")

        if self.results['bug_confirmed']:
            print(f"\n🚨 BUG STATUS: CONFIRMED")
            print(f"   The symbol mismatch causes wrong price to be fetched")
            print(f"   This leads to invalid SL calculation")
        else:
            print(f"\n✅ BUG STATUS: NOT REPRODUCED")
            print(f"   Both symbols return similar prices")
            print(f"   Issue may be production-specific or transient")

        print(f"\n📊 Prices:")
        if self.results.get('wrong_price'):
            print(f"   HNTUSDT:       ${self.results['wrong_price']:.6f}")
        if self.results.get('correct_price'):
            print(f"   HNT/USDT:USDT: ${self.results['correct_price']:.6f}")

        print(f"\n📝 Evidence Trail:")
        for i, evidence in enumerate(self.results['evidence'], 1):
            print(f"   {i}. {evidence}")

        print("\n" + "="*70)

        # Return status code
        return 0 if self.results['bug_confirmed'] else 1


async def main():
    """Run all tests"""
    print("="*70)
    print("CASE #1: HNTUSDT Symbol Mismatch Forensic Test")
    print("="*70)
    print("\nObjective: Determine if symbol format affects price data")
    print("Hypothesis: fetch_ticker('HNTUSDT') returns wrong price")
    print("Expected: Should use 'HNT/USDT:USDT' for Bybit perpetuals")

    # Initialize test suite
    test = Case01SymbolMismatchTest(use_testnet=False)  # Use production for accurate test

    exchange = await test.setup_exchange()

    try:
        # Run test sequence
        await test.test_1_list_hnt_symbols(exchange)

        _, price_db = await test.test_2_fetch_with_db_symbol(exchange)
        _, price_ccxt = await test.test_3_fetch_with_ccxt_symbol(exchange)

        await test.test_4_compare_prices(price_db, price_ccxt)

        await test.test_5_reproduce_bot_logic(exchange)

    finally:
        await exchange.close()

    # Generate final report
    exit_code = test.generate_report()

    return exit_code


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️ Test interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
