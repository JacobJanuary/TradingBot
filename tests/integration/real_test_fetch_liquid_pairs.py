"""
Real Integration Test - Fetch Most Liquid Trading Pairs
========================================================
Fetches the most liquid trading pairs from Binance and Bybit using CCXT.

Usage:
    python tests/integration/real_test_fetch_liquid_pairs.py

Output:
    - Top 30 most liquid pairs from Binance
    - Top 30 most liquid pairs from Bybit
    - JSON file with pair details (60 pairs total)
    
Note: 60 pairs provide sufficient diversity for multi-hour tests with duplicate detection.
"""
import asyncio
import json
from typing import List, Dict, Any
from datetime import datetime
import ccxt.async_support as ccxt
from decimal import Decimal


class LiquidPairsFetcher:
    """Fetches most liquid trading pairs from exchanges"""
    
    def __init__(self):
        self.binance = None
        self.bybit = None
        self.results = []
    
    async def initialize(self):
        """Initialize exchange connections"""
        print("🔌 Connecting to exchanges...")
        
        # Initialize Binance
        self.binance = ccxt.binance({
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',  # USDT-M Futures
            }
        })
        
        # Initialize Bybit
        self.bybit = ccxt.bybit({
            'enableRateLimit': True,
            'options': {
                'defaultType': 'linear',  # USDT Perpetual
            }
        })
        
        print("✅ Connected to Binance and Bybit")
    
    async def fetch_binance_liquid_pairs(self, top_n: int = 5) -> List[Dict[str, Any]]:
        """
        Fetch top N most liquid pairs from Binance Futures
        
        Criteria:
        - USDT perpetual futures
        - Highest 24h quote volume
        - Active trading
        """
        print("\n📊 Fetching Binance Futures tickers...")
        
        try:
            # Fetch all tickers
            tickers = await self.binance.fetch_tickers()
            
            # Filter USDT perpetual futures
            usdt_pairs = []
            for symbol, ticker in tickers.items():
                if '/USDT' in symbol and ':USDT' in symbol:  # Perpetual format: BTC/USDT:USDT
                    # Extract relevant data
                    pair_data = {
                        'symbol': symbol.split(':')[0],  # BTC/USDT
                        'full_symbol': symbol,
                        'exchange': 'binance',
                        'volume_24h_usd': ticker.get('quoteVolume', 0) or 0,
                        'volume_24h_base': ticker.get('baseVolume', 0) or 0,
                        'last_price': ticker.get('last', 0) or 0,
                        'bid': ticker.get('bid', 0) or 0,
                        'ask': ticker.get('ask', 0) or 0,
                        'spread_pct': self._calculate_spread_pct(
                            ticker.get('bid'), 
                            ticker.get('ask')
                        ),
                        'change_24h_pct': ticker.get('percentage', 0) or 0,
                        'timestamp': ticker.get('timestamp'),
                    }
                    usdt_pairs.append(pair_data)
            
            # Sort by 24h quote volume (liquidity)
            usdt_pairs.sort(key=lambda x: x['volume_24h_usd'], reverse=True)
            
            # Take top N
            top_pairs = usdt_pairs[:top_n]
            
            print(f"✅ Found {len(usdt_pairs)} USDT pairs, selected top {len(top_pairs)}")
            
            for i, pair in enumerate(top_pairs, 1):
                print(f"   {i}. {pair['symbol']} - Volume: ${pair['volume_24h_usd']:,.0f}")
            
            return top_pairs
            
        except Exception as e:
            print(f"❌ Error fetching Binance pairs: {e}")
            return []
    
    async def fetch_bybit_liquid_pairs(self, top_n: int = 5) -> List[Dict[str, Any]]:
        """
        Fetch top N most liquid pairs from Bybit Linear (USDT Perpetual)
        
        Criteria:
        - USDT perpetual futures
        - Highest 24h quote volume
        - Active trading
        """
        print("\n📊 Fetching Bybit Linear tickers...")
        
        try:
            # Fetch all tickers
            tickers = await self.bybit.fetch_tickers()
            
            # Filter USDT perpetual futures
            usdt_pairs = []
            for symbol, ticker in tickers.items():
                if '/USDT:USDT' in symbol:  # Bybit perpetual format
                    # Extract relevant data
                    pair_data = {
                        'symbol': symbol.split(':')[0],  # BTC/USDT
                        'full_symbol': symbol,
                        'exchange': 'bybit',
                        'volume_24h_usd': ticker.get('quoteVolume', 0) or 0,
                        'volume_24h_base': ticker.get('baseVolume', 0) or 0,
                        'last_price': ticker.get('last', 0) or 0,
                        'bid': ticker.get('bid', 0) or 0,
                        'ask': ticker.get('ask', 0) or 0,
                        'spread_pct': self._calculate_spread_pct(
                            ticker.get('bid'), 
                            ticker.get('ask')
                        ),
                        'change_24h_pct': ticker.get('percentage', 0) or 0,
                        'timestamp': ticker.get('timestamp'),
                    }
                    usdt_pairs.append(pair_data)
            
            # Sort by 24h quote volume (liquidity)
            usdt_pairs.sort(key=lambda x: x['volume_24h_usd'], reverse=True)
            
            # Take top N
            top_pairs = usdt_pairs[:top_n]
            
            print(f"✅ Found {len(usdt_pairs)} USDT pairs, selected top {len(top_pairs)}")
            
            for i, pair in enumerate(top_pairs, 1):
                print(f"   {i}. {pair['symbol']} - Volume: ${pair['volume_24h_usd']:,.0f}")
            
            return top_pairs
            
        except Exception as e:
            print(f"❌ Error fetching Bybit pairs: {e}")
            return []
    
    def _calculate_spread_pct(self, bid: float, ask: float) -> float:
        """Calculate bid-ask spread percentage"""
        if bid and ask and bid > 0:
            return ((ask - bid) / bid) * 100
        return 0.0
    
    async def fetch_all(self, top_n_per_exchange: int = 5) -> List[Dict[str, Any]]:
        """Fetch liquid pairs from all exchanges"""
        print("\n" + "="*70)
        print("🚀 Fetching Most Liquid Trading Pairs")
        print("="*70)
        
        # Fetch from both exchanges concurrently
        binance_pairs, bybit_pairs = await asyncio.gather(
            self.fetch_binance_liquid_pairs(top_n_per_exchange),
            self.fetch_bybit_liquid_pairs(top_n_per_exchange)
        )
        
        # Combine results
        all_pairs = binance_pairs + bybit_pairs
        self.results = all_pairs
        
        print("\n" + "="*70)
        print(f"✅ Total pairs selected: {len(all_pairs)}")
        print("="*70)
        
        return all_pairs
    
    async def save_to_file(self, filename: str = "liquid_pairs.json"):
        """Save results to JSON file"""
        output = {
            'timestamp': datetime.utcnow().isoformat(),
            'total_pairs': len(self.results),
            'binance_pairs': [p for p in self.results if p['exchange'] == 'binance'],
            'bybit_pairs': [p for p in self.results if p['exchange'] == 'bybit'],
            'all_pairs': self.results
        }
        
        with open(filename, 'w') as f:
            json.dump(output, f, indent=2, default=str)
        
        print(f"\n💾 Results saved to: {filename}")
    
    async def close(self):
        """Close exchange connections"""
        if self.binance:
            await self.binance.close()
        if self.bybit:
            await self.bybit.close()
        print("🔌 Connections closed")


async def main():
    """Main execution"""
    fetcher = LiquidPairsFetcher()
    
    try:
        # Initialize
        await fetcher.initialize()
        
        # Fetch liquid pairs (30 per exchange for longer tests)
        pairs = await fetcher.fetch_all(top_n_per_exchange=30)
        
        # Save to file
        output_file = "tests/integration/liquid_pairs.json"
        await fetcher.save_to_file(output_file)
        
        # Display summary
        print("\n" + "━"*70)
        print("📋 SUMMARY")
        print("━"*70)
        
        binance_count = len([p for p in pairs if p['exchange'] == 'binance'])
        bybit_count = len([p for p in pairs if p['exchange'] == 'bybit'])
        
        print(f"Binance pairs: {binance_count}")
        print(f"Bybit pairs:   {bybit_count}")
        print(f"Total pairs:   {len(pairs)}")
        
        print("\n🎯 Selected Pairs:")
        for pair in pairs:
            print(f"  • {pair['symbol']:15} ({pair['exchange']:8}) "
                  f"- Vol: ${pair['volume_24h_usd']:>15,.0f}")
        
        print("━"*70)
        print("✅ Done!")
        print("━"*70)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await fetcher.close()


if __name__ == "__main__":
    asyncio.run(main())

