#!/usr/bin/env python3
"""
Исправление авторизации Bybit с правильной подписью для V5 API
"""
import asyncio
import aiohttp
import hmac
import hashlib
import time
import json
import os
from urllib.parse import urlencode
from dotenv import load_dotenv

load_dotenv()


class BybitV5Auth:
    """Правильная авторизация для Bybit V5 API"""
    
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        
    def generate_signature(self, timestamp, recv_window, query_string=""):
        """Генерация подписи для V5 API"""
        # Формат для GET запросов: timestamp + api_key + recv_window + query_string
        param_str = f"{timestamp}{self.api_key}{recv_window}{query_string}"
        
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            param_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature
    
    async def test_connection(self, base_url):
        """Тест подключения к Bybit"""
        
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"
        
        # Для account/info нет query parameters
        signature = self.generate_signature(timestamp, recv_window, "")
        
        headers = {
            'X-BAPI-API-KEY': self.api_key,
            'X-BAPI-SIGN': signature,
            'X-BAPI-TIMESTAMP': timestamp,
            'X-BAPI-RECV-WINDOW': recv_window,
            'Content-Type': 'application/json'
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                # 1. Проверяем account info
                url = f"{base_url}/v5/account/info"
                async with session.get(url, headers=headers) as response:
                    data = await response.json()
                    return data
                    
            except Exception as e:
                return {"error": str(e)}
    
    async def get_wallet_balance(self, base_url):
        """Получить баланс кошелька"""
        
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"
        
        # Query parameters для wallet balance
        params = {
            'accountType': 'UNIFIED'
        }
        query_string = urlencode(sorted(params.items()))
        
        signature = self.generate_signature(timestamp, recv_window, query_string)
        
        headers = {
            'X-BAPI-API-KEY': self.api_key,
            'X-BAPI-SIGN': signature,
            'X-BAPI-TIMESTAMP': timestamp,
            'X-BAPI-RECV-WINDOW': recv_window
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                url = f"{base_url}/v5/account/wallet-balance"
                async with session.get(url, headers=headers, params=params) as response:
                    data = await response.json()
                    return data
                    
            except Exception as e:
                return {"error": str(e)}


async def main():
    """Главная функция"""
    
    api_key = os.getenv('BYBIT_API_KEY')
    api_secret = os.getenv('BYBIT_API_SECRET')
    
    print("="*60)
    print("BYBIT V5 API - ИСПРАВЛЕНИЕ АВТОРИЗАЦИИ")
    print("="*60)
    
    if not api_key or not api_secret:
        print("\n❌ API ключи не найдены")
        return
    
    print(f"\n📋 Используемые ключи:")
    print(f"   API Key: {api_key[:10]}...")
    print(f"   Secret: ***")
    
    auth = BybitV5Auth(api_key, api_secret)
    
    # Тестируем оба endpoint
    endpoints = [
        ("https://api-testnet.bybit.com", "TESTNET"),
        ("https://api.bybit.com", "MAINNET")
    ]
    
    for base_url, name in endpoints:
        print(f"\n🔍 Проверяем {name}:")
        print(f"   URL: {base_url}")
        
        # Тест 1: Account Info
        result = await auth.test_connection(base_url)
        
        if result.get('retCode') == 0:
            print(f"   ✅ Подключение успешно!")
            
            data = result.get('result', {})
            if data:
                print(f"   Account UID: {data.get('uid', 'N/A')}")
                print(f"   Account Type: {data.get('accountType', 'N/A')}")
                
                # Для старых аккаунтов
                unified_status = data.get('unifiedMarginStatus')
                if unified_status is not None:
                    if unified_status == 1:
                        print(f"   ✅ UNIFIED Account")
                    elif unified_status == 0:
                        print(f"   ❌ Standard Account (нужно переключить на UNIFIED)")
                    else:
                        print(f"   Status Code: {unified_status}")
                
                # Для новых аккаунтов
                uta = data.get('uta')
                if uta is not None:
                    if uta == 1:
                        print(f"   ✅ UTA (Unified Trading Account) активен")
                    else:
                        print(f"   ❌ UTA не активен")
                
                # Тест 2: Баланс
                balance_result = await auth.get_wallet_balance(base_url)
                
                if balance_result.get('retCode') == 0:
                    print(f"   ✅ Баланс получен")
                    
                    accounts = balance_result.get('result', {}).get('list', [])
                    for account in accounts:
                        account_type = account.get('accountType')
                        print(f"\n   💼 Account Type: {account_type}")
                        
                        coins = account.get('coin', [])
                        for coin in coins:
                            if coin['coin'] == 'USDT':
                                wallet_balance = float(coin.get('walletBalance') or 0)
                                available = float(coin.get('availableToWithdraw') or 0)
                                print(f"   💰 USDT Balance: {wallet_balance:.2f}")
                                print(f"   💵 Available: {available:.2f}")
                                break
                                
                elif balance_result.get('retCode') == 10001:
                    print(f"   ❌ Ошибка: accountType only support UNIFIED")
                    print(f"   📋 Нужно активировать UNIFIED account на {base_url.replace('api', 'www').replace('-testnet', '')}")
                else:
                    print(f"   ⚠️ Не удалось получить баланс: {balance_result.get('retMsg')}")
                
                print(f"\n   🎉 КЛЮЧИ РАБОТАЮТ С {name}!")
                
                if 'testnet' in base_url:
                    print("\n✅ Отлично! Ключи от TESTNET")
                    
                    # Создаем рабочую конфигурацию
                    print("\n📝 Добавьте в config/config.yaml:")
                    print("```yaml")
                    print("exchanges:")
                    print("  bybit:")
                    print("    enabled: true")
                    print("    testnet: true")
                    print("    api_key: ${BYBIT_API_KEY}")
                    print("    api_secret: ${BYBIT_API_SECRET}")
                    print("    options:")
                    print("      defaultType: 'future'")
                    print("      accountType: 'UNIFIED'")
                    print("```")
                else:
                    print("\n⚠️ ВНИМАНИЕ! Это PRODUCTION ключи")
                    print("Для тестирования создайте ключи на testnet.bybit.com")
                
                break
                
        elif result.get('retCode') == 10003:
            print(f"   ❌ Неверная подпись или ключи")
            
        elif result.get('retCode') == 10001:
            print(f"   ❌ Account не UNIFIED")
            
        else:
            print(f"   ❌ Ошибка: {result.get('retMsg', 'Unknown error')}")
            
    print("\n" + "="*60)


if __name__ == "__main__":
    asyncio.run(main())