#!/usr/bin/env python3
"""
Патч для CCXT чтобы заработал Bybit UNIFIED на testnet
"""
import ccxt
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

# Патчим метод fetch_balance для Bybit
original_fetch_balance = ccxt.bybit.fetch_balance

async def patched_fetch_balance(self, params={}):
    """Патч для fetch_balance чтобы работал с UNIFIED testnet"""
    # Форсируем правильные параметры
    params['accountType'] = 'UNIFIED'
    
    # Пробуем сначала стандартный метод
    try:
        return await original_fetch_balance(self, params)
    except Exception as e:
        if "accountType only support UNIFIED" in str(e):
            # Если ошибка UNIFIED, используем прямой API вызов
            response = await self.privateGetV5AccountWalletBalance(params)
            
            if response['retCode'] == 0:
                result = {}
                accounts = response['result']['list']
                
                for account in accounts:
                    for coin in account.get('coin', []):
                        currency = coin['coin']
                        result[currency] = {
                            'free': float(coin.get('availableToWithdraw') or 0),
                            'used': float(coin.get('walletBalance') or 0) - float(coin.get('availableToWithdraw') or 0),
                            'total': float(coin.get('walletBalance') or 0)
                        }
                
                result['info'] = response
                return result
        raise

# Применяем патч
ccxt.bybit.fetch_balance = patched_fetch_balance


async def test_patched():
    """Тест с патчем"""
    
    print("="*60)
    print("ТЕСТ CCXT С ПАТЧЕМ ДЛЯ BYBIT UNIFIED")
    print("="*60)
    
    exchange = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'testnet': True,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
            'accountType': 'UNIFIED'
        }
    })
    
    exchange.set_sandbox_mode(True)
    
    try:
        print("\n1️⃣ Загрузка рынков...")
        markets = await exchange.load_markets()
        print(f"   ✅ Загружено {len(markets)} рынков")
        
        print("\n2️⃣ Баланс (с патчем)...")
        balance = await exchange.fetch_balance()
        usdt = balance.get('USDT', {})
        print(f"   ✅ USDT: {usdt.get('total', 0):.2f}")
        
        print("\n3️⃣ Тикер...")
        ticker = await exchange.fetch_ticker('BTC/USDT:USDT')
        print(f"   ✅ BTC/USDT: ${ticker['last']:,.2f}")
        
        print("\n✅ Патч работает! CCXT теперь совместим с Bybit UNIFIED testnet")
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
    finally:
        await exchange.close()


if __name__ == "__main__":
    asyncio.run(test_patched())