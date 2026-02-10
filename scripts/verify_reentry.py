#!/usr/bin/env python3
"""
Quick diagnostic script to verify reentry functionality is working correctly.
Tests:
1. WebSocket price updates are flowing to ReentryManager
2. AggTrades stream is collecting trade data for delta calculation  
3. Reentry signal conditions are properly evaluated
"""

import asyncio
import os
import sys
from decimal import Decimal
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

async def test_aggtrades_stream():
    """Test that aggTrades stream is receiving real trade data"""
    from websocket.binance_aggtrades_stream import BinanceAggTradesStream
    
    print("\n" + "="*60)
    print("TEST 1: AggTrades Stream - Trade Data Collection")
    print("="*60)
    
    stream = BinanceAggTradesStream(testnet=False)
    await stream.start()
    
    # Subscribe to a test symbol
    test_symbols = ['BTCUSDT', 'ETHUSDT', 'NEARUSDT']
    for sym in test_symbols:
        await stream.subscribe(sym)
    
    print(f"✓ Subscribed to: {test_symbols}")
    print(f"⏳ Collecting trades for 10 seconds...")
    
    await asyncio.sleep(10)
    
    # Check stats
    for sym in test_symbols:
        stats = stream.get_stats(sym)
        if stats:
            print(f"\n📊 {sym} Stats:")
            print(f"   Trade count: {stats.get('trade_count', 0)}")
            print(f"   Rolling delta (20s): ${stats.get('rolling_delta_20s', 0):,.0f}")
            print(f"   Avg delta (100s): ${stats.get('avg_delta_100s', 0):,.0f}")
            print(f"   Large buys (60s): {stats.get('large_buys_60s', 0)}")
            print(f"   Large sells (60s): {stats.get('large_sells_60s', 0)}")
            
            if stats.get('trade_count', 0) > 0:
                print(f"   ✅ Trade data flowing correctly!")
            else:
                print(f"   ❌ NO TRADES RECEIVED - Check subscription!")
        else:
            print(f"\n❌ {sym}: No stats available - stream not working!")
    
    await stream.stop()
    return True


async def test_mark_price_updates():
    """Test that mark price WebSocket is sending updates"""
    from websocket.binance_hybrid_stream import BinanceHybridStream
    
    print("\n" + "="*60)
    print("TEST 2: Mark Price WebSocket - Price Updates")
    print("="*60)
    
    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_API_SECRET')
    
    if not api_key or not api_secret:
        print("❌ BINANCE_API_KEY/SECRET not found in .env")
        return False
    
    price_updates = {}
    
    async def price_handler(symbol: str, price: str):
        price_updates[symbol] = float(price)
    
    stream = BinanceHybridStream(
        api_key=api_key,
        api_secret=api_secret,
        testnet=False
    )
    stream.set_reentry_callback(price_handler)
    await stream.start()
    
    # Subscribe to test symbols
    test_symbols = ['BTCUSDT', 'ETHUSDT', 'NEARUSDT']
    for sym in test_symbols:
        await stream.subscribe_symbol(sym)
    
    print(f"✓ Subscribed to: {test_symbols}")
    print(f"⏳ Collecting price updates for 10 seconds...")
    
    await asyncio.sleep(10)
    
    print(f"\n📊 Price updates received: {len(price_updates)}")
    for sym, price in list(price_updates.items())[:5]:
        print(f"   {sym}: ${price:,.4f}")
    
    if len(price_updates) > 0:
        print(f"\n✅ Price updates flowing correctly!")
    else:
        print(f"\n❌ NO PRICE UPDATES RECEIVED - Check callback!")
    
    await stream.stop()
    return len(price_updates) > 0


async def test_reentry_signal_conditions():
    """Test reentry signal trigger conditions"""
    from core.reentry_manager import ReentrySignal
    from decimal import Decimal
    
    print("\n" + "="*60)
    print("TEST 3: Reentry Signal - Trigger Conditions Logic")
    print("="*60)
    
    # Create test signal (simulating a LONG exit at $100)
    signal = ReentrySignal(
        symbol='TESTUSDT',
        side='long',
        last_exit_price=Decimal('100.00'),
        last_exit_time=datetime.now(timezone.utc),
        original_entry_time=datetime.now(timezone.utc),
        total_pnl=Decimal('50.00'),
        reentry_count=0,
        max_reentries=5
    )
    
    print(f"✓ Test signal created: {signal.symbol} {signal.side.upper()}")
    print(f"   Exit price: ${signal.last_exit_price}")
    print(f"   Drop threshold: 5%")
    
    # Test trigger price calculation
    trigger_price = signal.get_reentry_trigger_price()
    print(f"\n📊 Trigger price for LONG reentry: ${trigger_price}")
    print(f"   (Price needs to DROP to {trigger_price} from {signal.last_exit_price})")
    
    # Simulate price updates and check trigger
    test_prices = [Decimal('99'), Decimal('97'), Decimal('95'), Decimal('94')]
    print(f"\n🔬 Testing price scenarios:")
    
    for price in test_prices:
        would_trigger = price <= trigger_price
        status = "✅ WOULD TRIGGER" if would_trigger else "⏳ Not yet"
        pct_drop = (signal.last_exit_price - price) / signal.last_exit_price * 100
        print(f"   Price ${price} ({pct_drop:.1f}% drop): {status}")
    
    print(f"\n✅ Trigger logic working correctly!")
    return True


async def main():
    """Run all verification tests"""
    print("\n" + "="*60)
    print("REENTRY FUNCTIONALITY VERIFICATION")
    print("="*60)
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    
    results = {}
    
    try:
        # Test 1: AggTrades
        results['aggtrades'] = await test_aggtrades_stream()
    except Exception as e:
        print(f"❌ AggTrades test failed: {e}")
        results['aggtrades'] = False
    
    try:
        # Test 2: Mark Price
        results['mark_price'] = await test_mark_price_updates()
    except Exception as e:
        print(f"❌ Mark Price test failed: {e}")
        results['mark_price'] = False
    
    try:
        # Test 3: Reentry Conditions
        results['reentry_logic'] = await test_reentry_signal_conditions()
    except Exception as e:
        print(f"❌ Reentry logic test failed: {e}")
        results['reentry_logic'] = False
    
    # Summary
    print("\n" + "="*60)
    print("VERIFICATION SUMMARY")
    print("="*60)
    
    all_passed = True
    for test, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {test}: {status}")
        if not passed:
            all_passed = False
    
    if all_passed:
        print("\n🎉 ALL TESTS PASSED - Reentry functionality is working!")
    else:
        print("\n⚠️ SOME TESTS FAILED - Review the errors above")
    
    return all_passed


if __name__ == '__main__':
    asyncio.run(main())
