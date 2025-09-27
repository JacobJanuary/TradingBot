#!/usr/bin/env python3
"""Quick test of trading functionality"""

import asyncio
import ccxt.async_support as ccxt
from dotenv import load_dotenv
import os
import random
from datetime import datetime

load_dotenv()

async def quick_test():
    print("\n=== QUICK TRADING BOT TEST ===\n")
    
    # Initialize exchange
    exchange = ccxt.binance({
        'apiKey': os.getenv('BINANCE_API_KEY'),
        'secret': os.getenv('BINANCE_API_SECRET'),
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
            'fetchPositions': 'positionRisk',
        }
    })
    exchange.set_sandbox_mode(True)
    
    try:
        # Load markets
        print("1. Loading markets...")
        await exchange.load_markets()
        print(f"   ✅ Loaded {len(exchange.markets)} markets")
        
        # Get account balance
        print("\n2. Checking account balance...")
        balance = await exchange.fetch_balance()
        usdt_balance = balance.get('USDT', {}).get('free', 0)
        print(f"   ✅ USDT Balance: ${usdt_balance:.2f}")
        
        # Get top 30 liquid pairs
        print("\n3. Fetching top 30 liquid pairs...")
        tickers = await exchange.fetch_tickers()
        
        usdt_pairs = []
        for symbol, ticker in tickers.items():
            if symbol.endswith('/USDT:USDT') and ticker.get('quoteVolume'):
                usdt_pairs.append({
                    'symbol': symbol,
                    'volume': ticker['quoteVolume'],
                    'price': ticker['last']
                })
        
        usdt_pairs.sort(key=lambda x: x['volume'], reverse=True)
        top_30 = usdt_pairs[:30]
        
        print("   Top 30 pairs by 24h volume:")
        for i, pair in enumerate(top_30[:10], 1):  # Show first 10
            volume_m = pair['volume'] / 1_000_000
            print(f"   {i:2}. {pair['symbol']:20} | Price: ${pair['price']:10.2f} | Volume: ${volume_m:8.1f}M")
        print(f"   ... and {len(top_30)-10} more pairs")
        
        # Simulate 5 random signals
        print("\n4. Simulating 5 random trading signals...")
        for i in range(5):
            pair = random.choice(top_30)
            action = random.choice(['BUY', 'SELL'])
            score = random.randint(70, 95)
            
            print(f"   Signal #{i+1}: {action:4} {pair['symbol']:20} | Score: {score}% | Price: ${pair['price']:.2f}")
            await asyncio.sleep(0.5)  # Small delay
        
        # Check positions (should be empty or minimal in testnet)
        print("\n5. Checking open positions...")
        try:
            positions = await exchange.fetch_positions()
            open_positions = [p for p in positions if p['contracts'] > 0]
            print(f"   ✅ Open positions: {len(open_positions)}")
            if open_positions:
                for pos in open_positions[:3]:  # Show first 3
                    print(f"      - {pos['symbol']}: {pos['contracts']} contracts, PnL: ${pos.get('unrealizedPnl', 0):.2f}")
        except Exception as e:
            print(f"   ⚠️  Could not fetch positions: {e}")
        
        print("\n=== TEST COMPLETED SUCCESSFULLY ===\n")
        
        # Save top 30 pairs to file
        with open('top_30_pairs.txt', 'w') as f:
            f.write("TOP 30 LIQUID PAIRS ON BINANCE FUTURES\n")
            f.write("=" * 60 + "\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n\n")
            
            for i, pair in enumerate(top_30, 1):
                volume_m = pair['volume'] / 1_000_000
                f.write(f"{i:2}. {pair['symbol']:25} | Price: ${pair['price']:12.4f} | 24h Volume: ${volume_m:10.2f}M\n")
        
        print("📄 Top 30 pairs saved to top_30_pairs.txt")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(quick_test())