#!/usr/bin/env python3
"""
Test script to analyze liquid futures pairs on Binance and Bybit.

Filters:
- Open Interest >= $1,000,000
- 24h Volume >= $1,000,000

Usage:
    python tests/manual/test_liquid_pairs_analysis.py
"""
import asyncio
import ccxt.pro as ccxt
from typing import Dict, List
from datetime import datetime


class LiquidPairsAnalyzer:
    """Analyze liquid futures pairs across exchanges."""

    def __init__(self):
        self.exchanges = {}
        self.results = []

    async def initialize_exchanges(self):
        """Initialize exchange connections."""
        print("🔄 Initializing exchanges...")

        # Binance Futures
        self.exchanges['binance'] = ccxt.binance({
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',
            }
        })

        # Bybit Futures
        self.exchanges['bybit'] = ccxt.bybit({
            'enableRateLimit': True,
            'options': {
                'defaultType': 'linear',
            }
        })

        # Load markets
        for name, exchange in self.exchanges.items():
            await exchange.load_markets()
            print(f"✅ {name}: {len(exchange.markets)} markets loaded")

    async def fetch_oi_and_volume(self, exchange_name: str, symbol: str) -> Dict:
        """
        Fetch Open Interest and 24h Volume for a symbol.

        Returns:
            dict with 'oi_usd', 'volume_24h_usd', 'price'
        """
        exchange = self.exchanges[exchange_name]

        try:
            # Fetch ticker for 24h volume and price
            ticker = await exchange.fetch_ticker(symbol)
            price = ticker.get('last', 0)
            volume_24h = ticker.get('quoteVolume', 0)  # Already in USD for USDT pairs

            # Fetch Open Interest
            oi_usd = 0
            try:
                # Try to fetch OI from exchange API
                if exchange_name == 'binance':
                    # Binance: fetch_open_interest returns contracts, need to multiply by price
                    oi_data = await exchange.fetch_open_interest(symbol)
                    oi_contracts = oi_data.get('openInterestAmount', 0)
                    oi_usd = oi_contracts * price if oi_contracts else 0

                elif exchange_name == 'bybit':
                    # Bybit: Use ticker['info']['openInterest'] (in contracts)
                    # fetch_open_interest returns openInterestValue=None, so use ticker instead
                    oi_contracts = float(ticker.get('info', {}).get('openInterest', 0))
                    oi_usd = oi_contracts * price if oi_contracts else 0

            except Exception as oi_error:
                # Some symbols might not have OI data
                pass

            return {
                'oi_usd': float(oi_usd) if oi_usd else 0,
                'volume_24h_usd': float(volume_24h) if volume_24h else 0,
                'price': float(price) if price else 0
            }

        except Exception as e:
            print(f"  ⚠️ Error fetching {symbol} on {exchange_name}: {e}")
            return {
                'oi_usd': 0,
                'volume_24h_usd': 0,
                'price': 0
            }

    async def analyze_exchange(self, exchange_name: str):
        """Analyze all futures pairs on an exchange."""
        exchange = self.exchanges[exchange_name]

        print(f"\n📊 Analyzing {exchange_name.upper()}...")

        # Get all USDT perpetual futures
        futures_symbols = [
            symbol for symbol, market in exchange.markets.items()
            if market.get('type') == 'swap'  # Perpetual futures
            and market.get('quote') == 'USDT'
            and market.get('active', True)
        ]

        print(f"  Found {len(futures_symbols)} USDT perpetual futures")

        # Fetch data for each symbol
        tasks = []
        for symbol in futures_symbols:
            tasks.append(self.fetch_oi_and_volume(exchange_name, symbol))

        print(f"  Fetching OI and volume data...")
        results = await asyncio.gather(*tasks)

        # Filter by thresholds
        min_oi = 1_000_000
        min_volume = 1_000_000

        liquid_pairs = []
        for symbol, data in zip(futures_symbols, results):
            if data['oi_usd'] >= min_oi and data['volume_24h_usd'] >= min_volume:
                liquid_pairs.append({
                    'exchange': exchange_name,
                    'symbol': symbol,
                    'oi_usd': data['oi_usd'],
                    'volume_24h_usd': data['volume_24h_usd'],
                    'price': data['price']
                })

        print(f"  ✅ Found {len(liquid_pairs)} liquid pairs (OI >= ${min_oi:,}, Volume >= ${min_volume:,})")

        return liquid_pairs

    async def run_analysis(self):
        """Run the full analysis."""
        print("=" * 80)
        print("🔍 LIQUID FUTURES PAIRS ANALYSIS")
        print("=" * 80)
        print(f"Filters: OI >= $1,000,000, 24h Volume >= $1,000,000")
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        # Initialize
        await self.initialize_exchanges()

        # Analyze each exchange
        all_results = []
        for exchange_name in ['binance', 'bybit']:
            pairs = await self.analyze_exchange(exchange_name)
            all_results.extend(pairs)

        # Sort by OI descending
        all_results.sort(key=lambda x: x['oi_usd'], reverse=True)

        # Print results table
        print("\n" + "=" * 120)
        print("📋 LIQUID PAIRS SUMMARY")
        print("=" * 120)
        print(f"{'#':<4} {'Exchange':<10} {'Symbol':<25} {'OI (USD)':<20} {'Volume 24h (USD)':<20} {'Price':<15}")
        print("-" * 120)

        for idx, pair in enumerate(all_results, 1):
            print(
                f"{idx:<4} "
                f"{pair['exchange'].upper():<10} "
                f"{pair['symbol']:<25} "
                f"${pair['oi_usd']:>18,.0f} "
                f"${pair['volume_24h_usd']:>18,.0f} "
                f"${pair['price']:>14,.4f}"
            )

        print("-" * 120)
        print(f"Total: {len(all_results)} liquid pairs")
        print()

        # Statistics by exchange
        print("=" * 80)
        print("📊 STATISTICS BY EXCHANGE")
        print("=" * 80)

        for exchange_name in ['binance', 'bybit']:
            exchange_pairs = [p for p in all_results if p['exchange'] == exchange_name]
            total_oi = sum(p['oi_usd'] for p in exchange_pairs)
            total_volume = sum(p['volume_24h_usd'] for p in exchange_pairs)
            avg_oi = total_oi / len(exchange_pairs) if exchange_pairs else 0
            avg_volume = total_volume / len(exchange_pairs) if exchange_pairs else 0

            print(f"\n{exchange_name.upper()}:")
            print(f"  Pairs: {len(exchange_pairs)}")
            print(f"  Total OI: ${total_oi:,.0f}")
            print(f"  Total Volume: ${total_volume:,.0f}")
            print(f"  Avg OI per pair: ${avg_oi:,.0f}")
            print(f"  Avg Volume per pair: ${avg_volume:,.0f}")

        print("\n" + "=" * 80)
        print(f"✅ Analysis complete at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)

        # Cleanup
        for exchange in self.exchanges.values():
            await exchange.close()

    async def close(self):
        """Close all exchange connections."""
        for exchange in self.exchanges.values():
            await exchange.close()


async def main():
    """Main entry point."""
    analyzer = LiquidPairsAnalyzer()
    try:
        await analyzer.run_analysis()
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await analyzer.close()


if __name__ == '__main__':
    asyncio.run(main())
