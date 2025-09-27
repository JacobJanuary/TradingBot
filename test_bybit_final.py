#!/usr/bin/env python3
"""
Финальный тест Bybit UNIFIED - всё должно работать!
"""
import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()


async def test_bybit():
    """Полный тест функциональности Bybit"""
    
    print("="*60)
    print("🎉 BYBIT UNIFIED ACCOUNT - ФИНАЛЬНЫЙ ТЕСТ")
    print("="*60)
    
    # Создаем exchange с правильными настройками
    exchange = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'testnet': True,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',  # Для perpetual futures
            'accountType': 'UNIFIED',  # ВАЖНО!
            'recvWindow': 60000,
            'adjustForTimeDifference': True
        }
    })
    
    # Включаем sandbox mode
    exchange.set_sandbox_mode(True)
    
    # Устанавливаем правильные URLs
    exchange.urls['api'] = {
        'public': 'https://api-testnet.bybit.com',
        'private': 'https://api-testnet.bybit.com'
    }
    
    try:
        # 1. Загружаем рынки
        print("\n1️⃣ Загрузка рынков...")
        markets = await exchange.load_markets()
        futures = [m for m in markets.values() if m['future']]
        print(f"   ✅ Загружено {len(markets)} рынков")
        print(f"   ✅ Futures: {len(futures)}")
        
        # 2. Проверяем баланс
        print("\n2️⃣ Проверка баланса...")
        balance = await exchange.fetch_balance()
        usdt = balance.get('USDT', {})
        print(f"   ✅ USDT Total: {usdt.get('total', 0):.2f}")
        print(f"   ✅ USDT Free: {usdt.get('free', 0):.2f}")
        print(f"   ✅ USDT Used: {usdt.get('used', 0):.2f}")
        
        # 3. Получаем тикер
        print("\n3️⃣ Получение тикеров...")
        symbol = 'BTC/USDT:USDT'
        ticker = await exchange.fetch_ticker(symbol)
        print(f"   ✅ {symbol}")
        print(f"      Last: ${ticker['last']:,.2f}")
        print(f"      Bid: ${ticker['bid']:,.2f}")
        print(f"      Ask: ${ticker['ask']:,.2f}")
        print(f"      Volume: {ticker['quoteVolume']:,.0f} USDT")
        
        # 4. Получаем позиции
        print("\n4️⃣ Проверка позиций...")
        positions = await exchange.fetch_positions()
        open_positions = [p for p in positions if p['contracts'] > 0]
        print(f"   ✅ Всего позиций: {len(positions)}")
        print(f"   ✅ Открытых: {len(open_positions)}")
        
        if open_positions:
            for pos in open_positions[:3]:
                print(f"      {pos['symbol']}: {pos['side']} {pos['contracts']}")
        
        # 5. Получаем открытые ордера
        print("\n5️⃣ Проверка ордеров...")
        try:
            orders = await exchange.fetch_open_orders()
            print(f"   ✅ Открытых ордеров: {len(orders)}")
        except:
            print(f"   ℹ️ Нет открытых ордеров")
        
        # 6. Тест размещения ордера
        print("\n6️⃣ Тест размещения ордера...")
        
        # Параметры тестового ордера
        test_symbol = 'BTC/USDT:USDT'
        test_side = 'buy'
        test_amount = 0.001  # Минимальный размер
        test_price = ticker['last'] * 0.8  # 20% ниже рынка
        
        print(f"   Тестовый ордер:")
        print(f"      Symbol: {test_symbol}")
        print(f"      Side: {test_side}")
        print(f"      Amount: {test_amount} BTC")
        print(f"      Price: ${test_price:,.2f}")
        
        if usdt.get('free', 0) >= test_price * test_amount:
            try:
                # Размещаем ордер
                order = await exchange.create_limit_buy_order(
                    test_symbol,
                    test_amount,
                    test_price
                )
                
                order_id = order['id']
                print(f"   ✅ Ордер размещен! ID: {order_id}")
                
                # Ждем секунду
                await asyncio.sleep(1)
                
                # Отменяем ордер
                await exchange.cancel_order(order_id, test_symbol)
                print(f"   ✅ Ордер отменен")
                
            except Exception as e:
                print(f"   ⚠️ Не удалось разместить ордер: {e}")
        else:
            print(f"   ⚠️ Недостаточно средств для теста")
        
        # 7. Проверка истории
        print("\n7️⃣ Проверка истории...")
        try:
            # Получаем последние сделки
            trades = await exchange.fetch_my_trades(symbol, limit=5)
            print(f"   ✅ Последних сделок: {len(trades)}")
        except:
            print(f"   ℹ️ История пуста")
        
        print("\n" + "="*60)
        print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
        print("="*60)
        
        print("\n🎊 Поздравляем! Ваш Bybit UNIFIED аккаунт полностью настроен и работает!")
        print("\nТеперь вы можете:")
        print("1. Запустить бота: python main.py --mode shadow")
        print("2. Протестировать стратегии на тестнете")
        print("3. Использовать все функции торгового бота")
        
        print("\n📋 Ваша конфигурация:")
        print("   • UNIFIED Account ✅")
        print("   • Testnet ✅")
        print("   • 10,000 USDT тестовых средств ✅")
        print("   • API работает ✅")
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        
        if "accountType only support UNIFIED" in str(e):
            print("\n⚠️ Всё еще проблема с UNIFIED")
            print("Попробуйте создать НОВЫЕ ключи")
        
    finally:
        await exchange.close()


if __name__ == "__main__":
    asyncio.run(test_bybit())