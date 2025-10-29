#!/usr/bin/env python3
"""
Test different methods to fetch Bybit Open Interest.

Tests:
1. CCXT fetch_ticker (check if openInterest field exists)
2. CCXT fetch_open_interest (check if it works)
3. Direct Bybit API v5 call

Usage:
    python tests/manual/test_bybit_oi_methods.py
"""
import asyncio
import ccxt.pro as ccxt
import requests
from typing import Dict


class BybitOITester:
    """Test different methods to get Bybit Open Interest."""

    def __init__(self):
        self.exchange = None
        self.test_symbols = [
            'BTC/USDT:USDT',
            'ETH/USDT:USDT',
            'SOL/USDT:USDT'
        ]

    async def initialize(self):
        """Initialize Bybit exchange."""
        print("=" * 80)
        print("🔧 INITIALIZING BYBIT EXCHANGE")
        print("=" * 80)

        self.exchange = ccxt.bybit({
            'enableRateLimit': True,
            'options': {
                'defaultType': 'linear',
            }
        })

        await self.exchange.load_markets()
        print(f"✅ Loaded {len(self.exchange.markets)} markets\n")

    async def test_method_1_fetch_ticker(self, symbol: str) -> Dict:
        """
        Method 1: CCXT fetch_ticker

        Check if ticker contains openInterest field.
        """
        print("-" * 80)
        print(f"🧪 METHOD 1: CCXT fetch_ticker - {symbol}")
        print("-" * 80)

        try:
            ticker = await self.exchange.fetch_ticker(symbol)

            print(f"✅ Ticker fetched successfully")
            print(f"   Last Price: ${ticker.get('last', 0):,.2f}")
            print(f"   24h Volume (quote): ${ticker.get('quoteVolume', 0):,.2f}")

            # Check for openInterest field
            oi = ticker.get('info', {}).get('openInterest', None)

            if oi is not None:
                oi_float = float(oi)
                price = ticker.get('last', 0)
                oi_usd = oi_float * price

                print(f"   Open Interest (contracts): {oi_float:,.2f}")
                print(f"   Open Interest (USD): ${oi_usd:,.2f}")
                print(f"   ✅ SUCCESS: openInterest found in ticker['info']")

                return {
                    'success': True,
                    'oi_contracts': oi_float,
                    'oi_usd': oi_usd,
                    'price': price,
                    'method': 'fetch_ticker -> info.openInterest'
                }
            else:
                print(f"   ❌ FAILED: openInterest NOT found in ticker['info']")
                print(f"   Available fields in ticker['info']: {list(ticker.get('info', {}).keys())[:10]}...")

                return {
                    'success': False,
                    'error': 'openInterest field not found',
                    'method': 'fetch_ticker'
                }

        except Exception as e:
            print(f"   ❌ ERROR: {e}")
            return {
                'success': False,
                'error': str(e),
                'method': 'fetch_ticker'
            }

    async def test_method_2_fetch_open_interest(self, symbol: str) -> Dict:
        """
        Method 2: CCXT fetch_open_interest

        Direct method for OI (if implemented by CCXT).
        """
        print("-" * 80)
        print(f"🧪 METHOD 2: CCXT fetch_open_interest - {symbol}")
        print("-" * 80)

        try:
            oi_data = await self.exchange.fetch_open_interest(symbol)

            print(f"✅ OI data fetched successfully")
            print(f"   Response: {oi_data}")

            oi_value = oi_data.get('openInterestValue', 0)
            oi_amount = oi_data.get('openInterestAmount', 0)

            print(f"   openInterestValue: {oi_value}")
            print(f"   openInterestAmount: {oi_amount}")

            if oi_value > 0:
                print(f"   ✅ SUCCESS: openInterestValue = ${oi_value:,.2f}")
                return {
                    'success': True,
                    'oi_usd': oi_value,
                    'method': 'fetch_open_interest'
                }
            elif oi_amount > 0:
                # Need to multiply by price
                ticker = await self.exchange.fetch_ticker(symbol)
                price = ticker.get('last', 0)
                oi_usd = oi_amount * price

                print(f"   ✅ SUCCESS: openInterestAmount * price = ${oi_usd:,.2f}")
                return {
                    'success': True,
                    'oi_usd': oi_usd,
                    'oi_contracts': oi_amount,
                    'price': price,
                    'method': 'fetch_open_interest'
                }
            else:
                print(f"   ❌ FAILED: Both values are 0")
                return {
                    'success': False,
                    'error': 'All OI values are 0',
                    'method': 'fetch_open_interest'
                }

        except Exception as e:
            print(f"   ❌ ERROR: {e}")
            return {
                'success': False,
                'error': str(e),
                'method': 'fetch_open_interest'
            }

    def test_method_3_direct_api(self, symbol: str) -> Dict:
        """
        Method 3: Direct Bybit API v5 call

        Bypass CCXT and call Bybit API directly.
        """
        print("-" * 80)
        print(f"🧪 METHOD 3: Direct Bybit API v5 - {symbol}")
        print("-" * 80)

        try:
            # Convert CCXT symbol to Bybit format
            # 'BTC/USDT:USDT' -> 'BTCUSDT'
            bybit_symbol = symbol.split('/')[0] + symbol.split('/')[1].split(':')[0]

            url = "https://api.bybit.com/v5/market/tickers"
            params = {
                'category': 'linear',
                'symbol': bybit_symbol
            }

            print(f"   URL: {url}")
            print(f"   Params: {params}")

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            if data.get('retCode') != 0:
                print(f"   ❌ API ERROR: {data.get('retMsg', 'Unknown error')}")
                return {
                    'success': False,
                    'error': data.get('retMsg', 'Unknown error'),
                    'method': 'direct_api'
                }

            result = data.get('result', {})
            ticker_list = result.get('list', [])

            if not ticker_list:
                print(f"   ❌ FAILED: No ticker data returned")
                return {
                    'success': False,
                    'error': 'No ticker data',
                    'method': 'direct_api'
                }

            ticker = ticker_list[0]

            oi_contracts = float(ticker.get('openInterest', 0))
            last_price = float(ticker.get('lastPrice', 0))
            volume_24h = float(ticker.get('turnover24h', 0))

            oi_usd = oi_contracts * last_price

            print(f"✅ API call successful")
            print(f"   Symbol: {ticker.get('symbol')}")
            print(f"   Last Price: ${last_price:,.2f}")
            print(f"   Open Interest (contracts): {oi_contracts:,.2f}")
            print(f"   Open Interest (USD): ${oi_usd:,.2f}")
            print(f"   24h Volume (USD): ${volume_24h:,.2f}")

            if oi_usd > 0:
                print(f"   ✅ SUCCESS: OI = ${oi_usd:,.2f}")
                return {
                    'success': True,
                    'oi_contracts': oi_contracts,
                    'oi_usd': oi_usd,
                    'price': last_price,
                    'volume_24h_usd': volume_24h,
                    'method': 'direct_api'
                }
            else:
                print(f"   ❌ FAILED: OI is 0")
                return {
                    'success': False,
                    'error': 'OI is 0',
                    'method': 'direct_api'
                }

        except Exception as e:
            print(f"   ❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e),
                'method': 'direct_api'
            }

    async def run_tests(self):
        """Run all tests for all symbols."""
        print("=" * 80)
        print("🧪 BYBIT OPEN INTEREST METHODS TEST")
        print("=" * 80)
        print(f"Testing {len(self.test_symbols)} symbols with 3 methods")
        print()

        await self.initialize()

        results = {}

        for symbol in self.test_symbols:
            print("\n" + "=" * 80)
            print(f"📊 TESTING SYMBOL: {symbol}")
            print("=" * 80)
            print()

            results[symbol] = {}

            # Test Method 1: fetch_ticker
            results[symbol]['method1'] = await self.test_method_1_fetch_ticker(symbol)
            print()

            # Test Method 2: fetch_open_interest
            results[symbol]['method2'] = await self.test_method_2_fetch_open_interest(symbol)
            print()

            # Test Method 3: direct API
            results[symbol]['method3'] = self.test_method_3_direct_api(symbol)
            print()

        # Print summary
        print("\n" + "=" * 80)
        print("📋 SUMMARY OF RESULTS")
        print("=" * 80)
        print()

        for symbol, methods in results.items():
            print(f"\n{symbol}:")
            for method_name, result in methods.items():
                status = "✅ SUCCESS" if result.get('success') else "❌ FAILED"
                method_desc = result.get('method', method_name)

                if result.get('success'):
                    oi_usd = result.get('oi_usd', 0)
                    print(f"  {method_name}: {status} - {method_desc} - OI: ${oi_usd:,.2f}")
                else:
                    error = result.get('error', 'Unknown error')
                    print(f"  {method_name}: {status} - {method_desc} - Error: {error}")

        # Determine winning method
        print("\n" + "=" * 80)
        print("🏆 RECOMMENDED METHOD")
        print("=" * 80)
        print()

        # Count successes for each method
        method1_success = sum(1 for r in results.values() if r['method1'].get('success'))
        method2_success = sum(1 for r in results.values() if r['method2'].get('success'))
        method3_success = sum(1 for r in results.values() if r['method3'].get('success'))

        print(f"Method 1 (fetch_ticker): {method1_success}/{len(self.test_symbols)} successful")
        print(f"Method 2 (fetch_open_interest): {method2_success}/{len(self.test_symbols)} successful")
        print(f"Method 3 (direct API): {method3_success}/{len(self.test_symbols)} successful")
        print()

        if method3_success == len(self.test_symbols):
            print("✅ WINNER: Method 3 (Direct Bybit API v5)")
            print("   Recommendation: Use direct API call to /v5/market/tickers")
        elif method1_success == len(self.test_symbols):
            print("✅ WINNER: Method 1 (CCXT fetch_ticker)")
            print("   Recommendation: Use ticker['info']['openInterest']")
        elif method2_success == len(self.test_symbols):
            print("✅ WINNER: Method 2 (CCXT fetch_open_interest)")
            print("   Recommendation: Use fetch_open_interest()")
        else:
            print("⚠️ WARNING: No method is 100% successful")
            print(f"   Best method: Method {[method1_success, method2_success, method3_success].index(max([method1_success, method2_success, method3_success])) + 1}")

        # Cleanup
        await self.exchange.close()


async def main():
    """Main entry point."""
    tester = BybitOITester()
    try:
        await tester.run_tests()
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted by user")
    except Exception as e:
        print(f"\n❌ Fatal Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if tester.exchange:
            await tester.exchange.close()


if __name__ == '__main__':
    asyncio.run(main())
