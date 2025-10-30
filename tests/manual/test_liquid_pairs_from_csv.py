#!/usr/bin/env python3
"""
Test script to fetch OI and Volume for pairs from CSV and save to trading_pairs_temp.

Usage:
    python tests/manual/test_liquid_pairs_from_csv.py data-1761789887608.csv
"""
import asyncio
import ccxt.pro as ccxt
import csv
import sys
from typing import Dict, List
from datetime import datetime
import asyncpg


class PairDataFetcher:
    """Fetch OI and Volume data for pairs from CSV."""

    def __init__(self, csv_file: str):
        self.csv_file = csv_file
        self.exchanges = {}
        self.db_pool = None
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

    async def initialize_database(self):
        """Initialize database connection."""
        print("🔄 Connecting to database...")
        try:
            self.db_pool = await asyncpg.create_pool(
                host='localhost',
                port=5432,
                user='evgeniyyanvarskiy',
                database='fox_crypto',
                min_size=1,
                max_size=5
            )
            print("✅ Database connected")
        except Exception as e:
            print(f"⚠️ Database connection failed: {e}")
            print("  Continuing without database save...")

    async def insert_pairs_to_database(self, pairs: List[Dict]):
        """Insert all pairs from CSV into database."""
        if not self.db_pool:
            return

        print("🔄 Inserting pairs into database...")
        inserted = 0

        try:
            async with self.db_pool.acquire() as conn:
                for pair in pairs:
                    try:
                        await conn.execute("""
                            INSERT INTO public.trading_pairs_temp
                                (id, token_id, exchange_id, pair_symbol, contract_type_id, is_active, last_24h_volume)
                            VALUES ($1, $2, $3, $4, $5, $6, $7)
                            ON CONFLICT (id) DO NOTHING
                        """,
                            pair['id'],
                            pair['token_id'],
                            pair['exchange_id'],
                            pair['pair_symbol'],
                            pair['contract_type_id'],
                            pair['is_active'],
                            pair['last_24h_volume']
                        )
                        inserted += 1
                    except Exception as e:
                        print(f"  ⚠️ Failed to insert pair {pair['pair_symbol']}: {e}")

            print(f"✅ Inserted {inserted}/{len(pairs)} pairs into database")
        except Exception as e:
            print(f"⚠️ Batch insert failed: {e}")

    def load_pairs_from_csv(self) -> List[Dict]:
        """Load trading pairs from CSV file."""
        print(f"\n📂 Loading pairs from {self.csv_file}...")

        pairs = []
        with open(self.csv_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Extract exchange name from exchange_id
                exchange_id = int(row['exchange_id'])
                exchange_name = 'binance' if exchange_id == 1 else 'bybit'

                pairs.append({
                    'id': int(row['id']),
                    'token_id': int(row['token_id']),
                    'exchange_id': exchange_id,
                    'exchange_name': exchange_name,
                    'pair_symbol': row['pair_symbol'],
                    'contract_type_id': int(row['contract_type_id']),
                    'is_active': row['is_active'] == 'True',
                    'last_24h_volume': float(row['last_24h_volume'])
                })

        print(f"  Loaded {len(pairs)} pairs")
        print(f"  Binance: {len([p for p in pairs if p['exchange_name'] == 'binance'])} pairs")
        print(f"  Bybit: {len([p for p in pairs if p['exchange_name'] == 'bybit'])} pairs")

        return pairs

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
                if exchange_name == 'binance':
                    # Binance: fetch_open_interest returns contracts, multiply by price
                    oi_data = await exchange.fetch_open_interest(symbol)
                    oi_contracts = oi_data.get('openInterestAmount', 0)
                    oi_usd = oi_contracts * price if oi_contracts else 0

                elif exchange_name == 'bybit':
                    # Bybit: Use openInterestValue (already in USDT)
                    # Fallback to openInterest * price if openInterestValue not available
                    oi_value = ticker.get('info', {}).get('openInterestValue', 0)
                    if oi_value:
                        oi_usd = float(oi_value)
                    else:
                        # Fallback: calculate from contracts
                        oi_contracts = float(ticker.get('info', {}).get('openInterest', 0))
                        oi_usd = oi_contracts * price if oi_contracts else 0

            except Exception:
                # Some symbols might not have OI data
                pass

            return {
                'oi_usd': float(oi_usd) if oi_usd else 0,
                'volume_24h_usd': float(volume_24h) if volume_24h else 0,
                'price': float(price) if price else 0,
                'success': True
            }

        except Exception as e:
            return {
                'oi_usd': 0,
                'volume_24h_usd': 0,
                'price': 0,
                'success': False,
                'error': str(e)
            }

    async def save_to_database(self, pair_id: int, oi_usd: float, volume_24h_usd: float):
        """Save OI and Volume data to database."""
        if not self.db_pool:
            return False

        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    UPDATE public.trading_pairs_temp
                    SET oi = $1,
                        volume24h = $2,
                        updated_at = NOW()
                    WHERE id = $3
                """, oi_usd, volume_24h_usd, pair_id)
            return True
        except Exception as e:
            print(f"    ⚠️ DB save failed for pair {pair_id}: {e}")
            return False

    async def process_pairs(self):
        """Process all pairs from CSV."""
        print("\n" + "=" * 80)
        print("🔍 FETCHING OI AND VOLUME FOR PAIRS FROM CSV")
        print("=" * 80)
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        # Initialize
        await self.initialize_exchanges()
        await self.initialize_database()

        # Load pairs from CSV
        pairs = self.load_pairs_from_csv()

        # Insert pairs into database first
        await self.insert_pairs_to_database(pairs)

        # Process each exchange separately to manage rate limits
        for exchange_name in ['binance', 'bybit']:
            exchange_pairs = [p for p in pairs if p['exchange_name'] == exchange_name]

            if not exchange_pairs:
                continue

            print(f"\n📊 Processing {exchange_name.upper()} ({len(exchange_pairs)} pairs)...")

            successful = 0
            failed = 0
            saved_to_db = 0

            for idx, pair in enumerate(exchange_pairs, 1):
                symbol = pair['pair_symbol']
                pair_id = pair['id']

                # Progress indicator
                if idx % 50 == 0:
                    print(f"  Progress: {idx}/{len(exchange_pairs)} pairs processed...")

                # Fetch data
                data = await self.fetch_oi_and_volume(exchange_name, symbol)

                if data['success']:
                    successful += 1

                    # Save to database if available
                    if self.db_pool:
                        saved = await self.save_to_database(
                            pair_id,
                            data['oi_usd'],
                            data['volume_24h_usd']
                        )
                        if saved:
                            saved_to_db += 1

                    # Store result
                    self.results.append({
                        'id': pair_id,
                        'exchange': exchange_name,
                        'symbol': symbol,
                        'oi_usd': data['oi_usd'],
                        'volume_24h_usd': data['volume_24h_usd'],
                        'price': data['price']
                    })
                else:
                    failed += 1
                    if idx % 50 == 0 or failed < 5:  # Show first few errors
                        print(f"    ⚠️ Failed: {symbol} - {data.get('error', 'Unknown error')}")

                # Small delay to respect rate limits
                await asyncio.sleep(0.1)

            print(f"  ✅ {exchange_name.upper()} complete:")
            print(f"    Success: {successful}/{len(exchange_pairs)}")
            print(f"    Failed: {failed}/{len(exchange_pairs)}")
            if self.db_pool:
                print(f"    Saved to DB: {saved_to_db}/{successful}")

    def print_summary(self):
        """Print summary of results."""
        print("\n" + "=" * 120)
        print("📊 SUMMARY")
        print("=" * 120)

        # Top 20 by OI
        top_by_oi = sorted(self.results, key=lambda x: x['oi_usd'], reverse=True)[:20]

        print("\n🏆 TOP 20 BY OPEN INTEREST:")
        print("-" * 120)
        print(f"{'#':<4} {'Exchange':<10} {'Symbol':<25} {'OI (USD)':<20} {'Volume 24h (USD)':<20} {'Price':<15}")
        print("-" * 120)

        for idx, pair in enumerate(top_by_oi, 1):
            print(
                f"{idx:<4} "
                f"{pair['exchange'].upper():<10} "
                f"{pair['symbol']:<25} "
                f"${pair['oi_usd']:>18,.0f} "
                f"${pair['volume_24h_usd']:>18,.0f} "
                f"${pair['price']:>14,.4f}"
            )

        # Statistics
        print("\n" + "=" * 80)
        print("📈 STATISTICS")
        print("=" * 80)

        total_pairs = len(self.results)
        total_oi = sum(p['oi_usd'] for p in self.results)
        total_volume = sum(p['volume_24h_usd'] for p in self.results)

        # Liquid pairs (OI >= $1M AND Volume >= $1M)
        liquid_pairs = [
            p for p in self.results
            if p['oi_usd'] >= 1_000_000 and p['volume_24h_usd'] >= 1_000_000
        ]

        print(f"\nTotal pairs processed: {total_pairs}")
        print(f"Total OI: ${total_oi:,.0f}")
        print(f"Total Volume: ${total_volume:,.0f}")
        print(f"Avg OI per pair: ${total_oi / total_pairs:,.0f}" if total_pairs > 0 else "N/A")
        print(f"Avg Volume per pair: ${total_volume / total_pairs:,.0f}" if total_pairs > 0 else "N/A")
        print(f"\n🌊 Liquid pairs (OI >= $1M AND Volume >= $1M): {len(liquid_pairs)}")

        # By exchange
        for exchange_name in ['binance', 'bybit']:
            exchange_pairs = [p for p in self.results if p['exchange'] == exchange_name]
            exchange_liquid = [p for p in liquid_pairs if p['exchange'] == exchange_name]

            if exchange_pairs:
                total_oi_ex = sum(p['oi_usd'] for p in exchange_pairs)
                total_vol_ex = sum(p['volume_24h_usd'] for p in exchange_pairs)

                print(f"\n{exchange_name.upper()}:")
                print(f"  Total pairs: {len(exchange_pairs)}")
                print(f"  Liquid pairs: {len(exchange_liquid)}")
                print(f"  Total OI: ${total_oi_ex:,.0f}")
                print(f"  Total Volume: ${total_vol_ex:,.0f}")

        print("\n" + "=" * 80)
        print(f"✅ Complete at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)

    async def cleanup(self):
        """Cleanup resources."""
        print("\n🔄 Cleaning up...")

        # Close exchanges
        for exchange in self.exchanges.values():
            await exchange.close()

        # Close database
        if self.db_pool:
            await self.db_pool.close()

        print("✅ Cleanup complete")

    async def run(self):
        """Main execution flow."""
        try:
            await self.process_pairs()
            self.print_summary()
        except KeyboardInterrupt:
            print("\n⚠️ Interrupted by user")
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await self.cleanup()


async def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python test_liquid_pairs_from_csv.py <csv_file>")
        print("Example: python test_liquid_pairs_from_csv.py data-1761789887608.csv")
        sys.exit(1)

    csv_file = sys.argv[1]
    fetcher = PairDataFetcher(csv_file)
    await fetcher.run()


if __name__ == '__main__':
    asyncio.run(main())
