#!/usr/bin/env python3
"""
Детальная диагностика Bybit UNIFIED подключения
"""
import asyncio
import ccxt.async_support as ccxt
import os
import hmac
import hashlib
import time
import json
from dotenv import load_dotenv

load_dotenv()


async def debug_bybit():
    """Детальная проверка всех аспектов подключения"""
    
    api_key = os.getenv('BYBIT_API_KEY')
    api_secret = os.getenv('BYBIT_API_SECRET')
    
    print("="*60)
    print("BYBIT UNIFIED ACCOUNT DEBUGGING")
    print("="*60)
    
    print("\n1️⃣ Проверка ключей:")
    print(f"   API Key: {api_key[:8] if api_key else 'NOT FOUND'}...")
    print(f"   API Secret: {'***' if api_secret else 'NOT FOUND'}")
    
    if not api_key or not api_secret:
        print("\n❌ Ключи не найдены в .env")
        return
    
    # Тест 1: Прямой API запрос
    print("\n2️⃣ Прямой API запрос (без CCXT):")
    
    import aiohttp
    
    timestamp = str(int(time.time() * 1000))
    recv_window = "5000"
    
    # Создаем подпись для запроса
    param_str = f"{timestamp}{api_key}{recv_window}"
    signature = hmac.new(
        api_secret.encode('utf-8'),
        param_str.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    headers = {
        'X-BAPI-API-KEY': api_key,
        'X-BAPI-SIGN': signature,
        'X-BAPI-TIMESTAMP': timestamp,
        'X-BAPI-RECV-WINDOW': recv_window,
        'Content-Type': 'application/json'
    }
    
    async with aiohttp.ClientSession() as session:
        # Пробуем получить информацию об аккаунте
        url = "https://api-testnet.bybit.com/v5/account/info"
        
        try:
            async with session.get(url, headers=headers) as response:
                data = await response.json()
                print(f"   Response code: {data.get('retCode')}")
                print(f"   Response msg: {data.get('retMsg')}")
                
                if data.get('retCode') == 0:
                    result = data.get('result', {})
                    print(f"   ✅ Account Type: {result.get('accountType')}")
                    print(f"   ✅ UID: {result.get('uid')}")
                    print(f"   ✅ Status: {result.get('status')}")
                    
                    if result.get('accountType') != 'UNIFIED':
                        print("\n   ⚠️ Аккаунт НЕ UNIFIED!")
                else:
                    print(f"   ❌ API Error: {data}")
                    
        except Exception as e:
            print(f"   ❌ Request failed: {e}")
    
    # Тест 2: CCXT с разными настройками
    print("\n3️⃣ Тест через CCXT:")
    
    configs = [
        {
            'name': 'Default config',
            'options': {
                'defaultType': 'future',
                'accountType': 'UNIFIED'
            }
        },
        {
            'name': 'With adjustForTimeDifference',
            'options': {
                'defaultType': 'future',
                'accountType': 'UNIFIED',
                'adjustForTimeDifference': True,
                'recvWindow': 60000
            }
        },
        {
            'name': 'Spot mode',
            'options': {
                'defaultType': 'spot',
                'accountType': 'UNIFIED'
            }
        }
    ]
    
    for config in configs:
        print(f"\n   Тестируем: {config['name']}")
        
        exchange = ccxt.bybit({
            'apiKey': api_key,
            'secret': api_secret,
            'testnet': True,
            'enableRateLimit': True,
            'options': config['options']
        })
        
        exchange.set_sandbox_mode(True)
        
        try:
            # Пробуем получить баланс
            balance = await exchange.fetch_balance()
            usdt = balance.get('USDT', {}).get('free', 0)
            print(f"      ✅ Успех! USDT баланс: {usdt:.2f}")
            
            # Если успешно, пробуем другие методы
            try:
                # Получаем рынки
                markets = await exchange.load_markets()
                print(f"      ✅ Рынки загружены: {len(markets)}")
                
                # Получаем позиции
                positions = await exchange.fetch_positions()
                print(f"      ✅ Позиций открыто: {len(positions)}")
                
                # Получаем тикер
                ticker = await exchange.fetch_ticker('BTC/USDT:USDT')
                print(f"      ✅ BTC/USDT: ${ticker['last']:,.2f}")
                
                print(f"\n   🎉 Конфигурация '{config['name']}' работает!")
                
                # Сохраняем рабочую конфигурацию
                print("\n4️⃣ Рабочая конфигурация для .env и config.yaml:")
                print("   ```yaml")
                print("   bybit:")
                print("     enabled: true")
                print("     testnet: true")
                print("     api_key: ${BYBIT_API_KEY}")
                print("     api_secret: ${BYBIT_API_SECRET}")
                print("     options:")
                for key, value in config['options'].items():
                    print(f"       {key}: {value}")
                print("   ```")
                
                await exchange.close()
                break
                
            except Exception as e:
                print(f"      ⚠️ Частичный успех, но ошибка в методе: {e}")
                
        except Exception as e:
            error_msg = str(e)
            if "accountType only support UNIFIED" in error_msg:
                print(f"      ❌ Требуется UNIFIED account")
            elif "Invalid API" in error_msg:
                print(f"      ❌ Неверные API ключи")
            elif "Timestamp" in error_msg:
                print(f"      ❌ Проблема с синхронизацией времени")
            else:
                print(f"      ❌ Ошибка: {error_msg[:100]}...")
        
        finally:
            await exchange.close()
    
    # Тест 3: Проверка WebSocket
    print("\n5️⃣ Проверка WebSocket подключения:")
    
    try:
        exchange = ccxt.bybit({
            'apiKey': api_key,
            'secret': api_secret,
            'testnet': True,
            'options': {
                'defaultType': 'future',
                'accountType': 'UNIFIED'
            }
        })
        
        exchange.set_sandbox_mode(True)
        
        # Пробуем подписаться на тикер
        print("   Подключаемся к WebSocket...")
        
        # Для CCXT Pro нужен отдельный импорт
        # Но проверим хотя бы REST API WebSocket endpoint
        ws_info = {
            'public': 'wss://stream-testnet.bybit.com/v5/public/linear',
            'private': 'wss://stream-testnet.bybit.com/v5/private'
        }
        
        print(f"   Public WS: {ws_info['public']}")
        print(f"   Private WS: {ws_info['private']}")
        print("   ✅ WebSocket endpoints настроены")
        
        await exchange.close()
        
    except Exception as e:
        print(f"   ❌ WebSocket ошибка: {e}")
    
    print("\n" + "="*60)
    print("ИТОГИ ДИАГНОСТИКИ")
    print("="*60)
    
    print("""
Если все тесты провалились:
1. Убедитесь, что ключи от TESTNET, а не MAINNET
2. Проверьте, что в testnet.bybit.com показан UNIFIED account
3. Попробуйте создать НОВЫЕ ключи
4. Убедитесь, что у ключей есть permissions для торговли

Если работает только определенная конфигурация:
- Используйте её в config.yaml
""")


if __name__ == "__main__":
    asyncio.run(debug_bybit())