#!/usr/bin/env python3
"""
Тест Bybit с обновленным CCXT v4.5.6
"""
import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()


async def test_bybit_complete():
    """Полный тест Bybit UNIFIED с новым CCXT"""
    
    print("="*70)
    print("🚀 BYBIT UNIFIED ACCOUNT TEST - CCXT v4.5.6")
    print("="*70)
    
    api_key = os.getenv('BYBIT_API_KEY')
    api_secret = os.getenv('BYBIT_API_SECRET')
    
    if not api_key or not api_secret:
        print("❌ API keys not found in .env")
        return False
    
    print(f"\n📋 Configuration:")
    print(f"   API Key: {api_key[:10]}...")
    print(f"   CCXT Version: {ccxt.__version__}")
    print(f"   Testnet: Yes")
    
    # Создаем exchange с правильными настройками для UNIFIED
    exchange = ccxt.bybit({
        'apiKey': api_key,
        'secret': api_secret,
        'testnet': True,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',    # Для perpetual futures
            'accountType': 'UNIFIED',   # ВАЖНО для V5 API
            'recvWindow': 60000,
            'adjustForTimeDifference': True
        }
    })
    
    # Включаем sandbox mode
    exchange.set_sandbox_mode(True)
    
    all_tests_passed = True
    results = {}
    
    try:
        # TEST 1: Load Markets
        print("\n1️⃣ Loading Markets...")
        try:
            markets = await exchange.load_markets()
            
            # Подсчитываем типы рынков
            spot_markets = sum(1 for m in markets.values() if m.get('spot'))
            future_markets = sum(1 for m in markets.values() if m.get('future'))
            swap_markets = sum(1 for m in markets.values() if m.get('swap'))
            
            print(f"   ✅ Total markets: {len(markets)}")
            print(f"   📊 Spot: {spot_markets}, Futures: {future_markets}, Swaps: {swap_markets}")
            
            # Проверяем популярные пары
            test_symbols = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT']
            available = []
            for symbol in test_symbols:
                if symbol in exchange.markets:
                    available.append(symbol)
            print(f"   📈 Available pairs: {', '.join(available)}")
            
            results['Markets'] = 'PASSED'
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results['Markets'] = 'FAILED'
            all_tests_passed = False
        
        # TEST 2: Fetch Balance
        print("\n2️⃣ Fetching Balance...")
        try:
            balance = await exchange.fetch_balance()
            
            # Показываем основные валюты
            main_currencies = ['USDT', 'BTC', 'ETH']
            has_balance = False
            
            for currency in main_currencies:
                if currency in balance:
                    total = balance[currency].get('total', 0)
                    free = balance[currency].get('free', 0)
                    used = balance[currency].get('used', 0)
                    
                    if total > 0:
                        has_balance = True
                        print(f"   💰 {currency}:")
                        print(f"      Total: {total:.4f}")
                        print(f"      Free: {free:.4f}")
                        print(f"      Used: {used:.4f}")
            
            if not has_balance:
                print("   ⚠️ No balances (get test funds at testnet.bybit.com)")
            else:
                print("   ✅ Balance fetched successfully")
            
            results['Balance'] = 'PASSED'
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results['Balance'] = 'FAILED'
            all_tests_passed = False
        
        # TEST 3: Fetch Ticker
        print("\n3️⃣ Fetching Tickers...")
        try:
            symbol = 'BTC/USDT:USDT'
            ticker = await exchange.fetch_ticker(symbol)
            
            print(f"   📊 {symbol}:")
            print(f"      Last: ${ticker.get('last', 0):,.2f}")
            print(f"      Bid: ${ticker.get('bid', 0):,.2f}")
            print(f"      Ask: ${ticker.get('ask', 0):,.2f}")
            print(f"      24h Volume: {ticker.get('quoteVolume', 0):,.0f} USDT")
            print(f"      24h Change: {ticker.get('percentage', 0):.2f}%")
            print("   ✅ Ticker fetched successfully")
            
            results['Ticker'] = 'PASSED'
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results['Ticker'] = 'FAILED'
            all_tests_passed = False
        
        # TEST 4: Fetch Order Book
        print("\n4️⃣ Fetching Order Book...")
        try:
            orderbook = await exchange.fetch_order_book('BTC/USDT:USDT', limit=5)
            
            print(f"   📖 BTC/USDT Order Book:")
            print(f"      Bids (top 3):")
            for i, bid in enumerate(orderbook['bids'][:3], 1):
                print(f"         {i}. ${bid[0]:,.2f} x {bid[1]:.4f}")
            print(f"      Asks (top 3):")
            for i, ask in enumerate(orderbook['asks'][:3], 1):
                print(f"         {i}. ${ask[0]:,.2f} x {ask[1]:.4f}")
            print("   ✅ Order book fetched successfully")
            
            results['OrderBook'] = 'PASSED'
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results['OrderBook'] = 'FAILED'
            all_tests_passed = False
        
        # TEST 5: Fetch Positions
        print("\n5️⃣ Fetching Positions...")
        try:
            positions = await exchange.fetch_positions()
            
            open_positions = [p for p in positions if p.get('contracts', 0) > 0]
            
            if open_positions:
                print(f"   📊 Open positions: {len(open_positions)}")
                for pos in open_positions[:3]:
                    print(f"      {pos['symbol']}: {pos['side']} {pos['contracts']} contracts")
                    if pos.get('unrealizedPnl'):
                        print(f"         PnL: ${pos['unrealizedPnl']:.2f}")
            else:
                print("   📊 No open positions")
            
            print("   ✅ Positions fetched successfully")
            results['Positions'] = 'PASSED'
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results['Positions'] = 'FAILED'
            all_tests_passed = False
        
        # TEST 6: Fetch Open Orders
        print("\n6️⃣ Fetching Open Orders...")
        try:
            orders = await exchange.fetch_open_orders()
            
            if orders:
                print(f"   📋 Open orders: {len(orders)}")
                for order in orders[:3]:
                    print(f"      {order['symbol']}: {order['side']} {order['amount']} @ ${order.get('price', 0):.2f}")
            else:
                print("   📋 No open orders")
            
            print("   ✅ Open orders fetched successfully")
            results['OpenOrders'] = 'PASSED'
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results['OpenOrders'] = 'FAILED'
            all_tests_passed = False
        
        # TEST 7: Place Test Order
        print("\n7️⃣ Testing Order Placement...")
        try:
            # Получаем текущую цену
            test_symbol = 'BTC/USDT:USDT'
            ticker = await exchange.fetch_ticker(test_symbol)
            current_price = ticker['last']
            
            # Параметры тестового ордера (далеко от рынка)
            test_price = round(current_price * 0.7, 2)  # 30% ниже рынка
            test_amount = 0.001  # Минимальный размер
            
            print(f"   📝 Test order:")
            print(f"      Symbol: {test_symbol}")
            print(f"      Type: Limit Buy")
            print(f"      Amount: {test_amount} BTC")
            print(f"      Price: ${test_price:,.2f} (30% below market)")
            
            # Проверяем баланс
            if balance.get('USDT', {}).get('free', 0) >= test_price * test_amount:
                # Размещаем ордер
                order = await exchange.create_limit_buy_order(
                    test_symbol,
                    test_amount,
                    test_price
                )
                
                order_id = order['id']
                print(f"   ✅ Order placed! ID: {order_id}")
                
                # Ждем немного
                await asyncio.sleep(1)
                
                # Отменяем ордер
                try:
                    await exchange.cancel_order(order_id, test_symbol)
                    print(f"   ✅ Order cancelled successfully")
                except:
                    print(f"   ⚠️ Could not cancel order (may be already filled)")
                
                results['OrderPlacement'] = 'PASSED'
            else:
                print(f"   ⚠️ Insufficient balance for test order")
                results['OrderPlacement'] = 'SKIPPED'
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results['OrderPlacement'] = 'FAILED'
            all_tests_passed = False
        
        # TEST 8: Fetch Trading Fees
        print("\n8️⃣ Fetching Trading Fees...")
        try:
            fees = await exchange.fetch_trading_fees()
            
            if 'trading' in fees:
                maker = fees['trading'].get('maker', 0)
                taker = fees['trading'].get('taker', 0)
                print(f"   💸 Trading fees:")
                print(f"      Maker: {maker*100:.4f}%")
                print(f"      Taker: {taker*100:.4f}%")
            else:
                print("   ℹ️ Fee structure not available")
            
            print("   ✅ Fees fetched successfully")
            results['Fees'] = 'PASSED'
        except Exception as e:
            print(f"   ⚠️ Warning: {e}")
            results['Fees'] = 'WARNING'
        
    except Exception as e:
        print(f"\n❌ Critical error: {e}")
        all_tests_passed = False
    
    finally:
        await exchange.close()
    
    # Summary
    print("\n" + "="*70)
    print("📊 TEST RESULTS SUMMARY")
    print("="*70)
    
    for test_name, result in results.items():
        if result == 'PASSED':
            emoji = '✅'
        elif result == 'FAILED':
            emoji = '❌'
        elif result == 'SKIPPED':
            emoji = '⏭️'
        else:
            emoji = '⚠️'
        
        print(f"{emoji} {test_name}: {result}")
    
    passed_tests = sum(1 for r in results.values() if r == 'PASSED')
    total_tests = len(results)
    
    print(f"\n📈 Score: {passed_tests}/{total_tests} tests passed")
    
    if all_tests_passed:
        print("\n🎉 SUCCESS! All tests passed!")
        print("Your Bybit UNIFIED account is fully functional with CCXT v4.5.6")
        print("\n✅ You can now:")
        print("   • Run the trading bot")
        print("   • Place and manage orders")
        print("   • Monitor positions")
        print("   • Access market data")
    else:
        failed_tests = [k for k, v in results.items() if v == 'FAILED']
        if failed_tests:
            print(f"\n⚠️ Some tests failed: {', '.join(failed_tests)}")
            print("Please check the errors above")
    
    print("\n" + "="*70)
    
    return all_tests_passed


if __name__ == "__main__":
    result = asyncio.run(test_bybit_complete())
    exit(0 if result else 1)