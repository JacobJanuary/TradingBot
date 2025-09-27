#!/usr/bin/env python3
"""
Проверка, от какого аккаунта ключи - Testnet или Mainnet
"""
import asyncio
import aiohttp
import hmac
import hashlib
import time
import os
from dotenv import load_dotenv

load_dotenv()


async def check_endpoint(api_key, api_secret, endpoint_url, endpoint_name):
    """Проверка одного endpoint"""
    
    timestamp = str(int(time.time() * 1000))
    recv_window = "5000"
    
    # Создаем подпись
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
    
    print(f"\n🔍 Проверяем {endpoint_name}:")
    print(f"   URL: {endpoint_url}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{endpoint_url}/v5/account/info", headers=headers) as response:
                data = await response.json()
                
                if data.get('retCode') == 0:
                    result = data.get('result', {})
                    
                    # Проверяем, есть ли реальные данные
                    if result.get('uid') or result.get('accountType'):
                        print(f"   ✅ РАБОТАЕТ!")
                        print(f"   Account Type: {result.get('accountType', 'N/A')}")
                        print(f"   UID: {result.get('uid', 'N/A')}")
                        print(f"   Status: {result.get('status', 'N/A')}")
                        
                        # Проверяем unified status
                        unified = result.get('unifiedMarginStatus')
                        if unified == 1:
                            print(f"   ✅ UNIFIED Account активен")
                        elif unified == 0:
                            print(f"   ❌ Standard Account (не UNIFIED)")
                        else:
                            print(f"   ⚠️ Unified Status: {unified}")
                        
                        # Пробуем получить баланс
                        balance_url = f"{endpoint_url}/v5/account/wallet-balance?accountType=UNIFIED"
                        async with session.get(balance_url, headers=headers) as bal_response:
                            bal_data = await bal_response.json()
                            if bal_data.get('retCode') == 0:
                                coins = bal_data.get('result', {}).get('list', [])
                                if coins:
                                    for coin_data in coins:
                                        for coin in coin_data.get('coin', []):
                                            if coin['coin'] == 'USDT':
                                                balance = float(coin.get('walletBalance', 0))
                                                print(f"   💰 USDT Balance: {balance:.2f}")
                                                break
                        return True
                    else:
                        print(f"   ⚠️ Ответ получен, но данные пустые")
                        return False
                        
                elif data.get('retCode') == 10003:
                    print(f"   ❌ Неверные ключи для этого endpoint")
                    return False
                elif data.get('retCode') == 10001:
                    print(f"   ❌ Требуется UNIFIED account")
                    return False
                else:
                    print(f"   ❌ Ошибка: {data.get('retMsg')}")
                    return False
                    
    except Exception as e:
        print(f"   ❌ Не удалось подключиться: {e}")
        return False


async def main():
    """Главная функция проверки"""
    
    api_key = os.getenv('BYBIT_API_KEY')
    api_secret = os.getenv('BYBIT_API_SECRET')
    
    print("="*60)
    print("ПРОВЕРКА BYBIT API КЛЮЧЕЙ")
    print("="*60)
    
    if not api_key or not api_secret:
        print("\n❌ API ключи не найдены в .env файле")
        print("\nДобавьте в .env:")
        print("BYBIT_API_KEY=ваш-ключ")
        print("BYBIT_API_SECRET=ваш-секрет")
        return
    
    print(f"\nИспользуем ключи:")
    print(f"API Key: {api_key[:8]}...")
    print(f"API Secret: ***")
    
    # Проверяем оба endpoint
    endpoints = [
        ("https://api-testnet.bybit.com", "TESTNET"),
        ("https://api.bybit.com", "MAINNET (Production)")
    ]
    
    working_endpoint = None
    
    for url, name in endpoints:
        result = await check_endpoint(api_key, api_secret, url, name)
        if result:
            working_endpoint = (url, name)
            break
    
    print("\n" + "="*60)
    print("РЕЗУЛЬТАТЫ")
    print("="*60)
    
    if working_endpoint:
        url, name = working_endpoint
        print(f"\n✅ Ваши ключи работают с {name}")
        
        if "testnet" in url:
            print("\n✅ Всё правильно! Ключи от TESTNET")
            print("\nЕсли бот не работает, проверьте:")
            print("1. Что аккаунт UNIFIED (не Standard)")
            print("2. Что у ключей есть trading permissions")
            
        else:
            print("\n⚠️ ВНИМАНИЕ! Ключи от PRODUCTION (mainnet)")
            print("\nДля тестирования нужны ключи от TESTNET:")
            print("1. Зайдите на https://testnet.bybit.com")
            print("2. Создайте аккаунт (отдельный от mainnet)")
            print("3. Активируйте UNIFIED account")
            print("4. Создайте API ключи")
            print("5. Обновите .env файл")
    else:
        print("\n❌ Ключи не работают ни с одним endpoint")
        print("\nВозможные причины:")
        print("1. Неверные ключи (проверьте копирование)")
        print("2. Ключи удалены или деактивированы")
        print("3. Проблемы с сетью")
        
        print("\nРекомендации:")
        print("1. Зайдите на https://testnet.bybit.com")
        print("2. Проверьте/создайте новые API ключи")
        print("3. Убедитесь, что аккаунт UNIFIED")
        print("4. Обновите .env файл")


if __name__ == "__main__":
    asyncio.run(main())