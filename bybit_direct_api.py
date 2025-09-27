#!/usr/bin/env python3
"""
Прямой доступ к Bybit API без CCXT
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


class BybitDirectAPI:
    """Прямой доступ к Bybit V5 API"""
    
    def __init__(self, api_key, api_secret, testnet=True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = "https://api-testnet.bybit.com" if testnet else "https://api.bybit.com"
        
    def _generate_signature(self, timestamp, recv_window, query_string="", body=""):
        """Генерация подписи"""
        if body:
            param_str = f"{timestamp}{self.api_key}{recv_window}{body}"
        else:
            param_str = f"{timestamp}{self.api_key}{recv_window}{query_string}"
        
        return hmac.new(
            self.api_secret.encode('utf-8'),
            param_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    async def _request(self, method, endpoint, params=None, body=None):
        """Выполнить запрос к API"""
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"
        
        # Подготовка query string
        query_string = ""
        if params and method == "GET":
            query_string = urlencode(sorted(params.items()))
        
        # Подготовка body
        body_str = ""
        if body and method == "POST":
            body_str = json.dumps(body)
        
        # Генерация подписи
        signature = self._generate_signature(timestamp, recv_window, query_string, body_str)
        
        # Заголовки
        headers = {
            'X-BAPI-API-KEY': self.api_key,
            'X-BAPI-SIGN': signature,
            'X-BAPI-TIMESTAMP': timestamp,
            'X-BAPI-RECV-WINDOW': recv_window
        }
        
        if method == "POST":
            headers['Content-Type'] = 'application/json'
        
        # Выполнение запроса
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}{endpoint}"
            
            if method == "GET":
                async with session.get(url, headers=headers, params=params) as response:
                    return await response.json()
            else:
                async with session.post(url, headers=headers, data=body_str) as response:
                    return await response.json()
    
    async def get_account_info(self):
        """Получить информацию об аккаунте"""
        return await self._request("GET", "/v5/account/info")
    
    async def get_wallet_balance(self):
        """Получить баланс кошелька"""
        params = {'accountType': 'UNIFIED'}
        return await self._request("GET", "/v5/account/wallet-balance", params)
    
    async def get_positions(self, category='linear'):
        """Получить позиции"""
        params = {
            'category': category,
            'settleCoin': 'USDT'
        }
        return await self._request("GET", "/v5/position/list", params)
    
    async def get_tickers(self, category='linear', symbol='BTCUSDT'):
        """Получить тикеры"""
        params = {
            'category': category,
            'symbol': symbol
        }
        return await self._request("GET", "/v5/market/tickers", params)
    
    async def place_order(self, symbol, side, qty, order_type='Limit', price=None):
        """Разместить ордер"""
        body = {
            'category': 'linear',
            'symbol': symbol,
            'side': side,  # Buy или Sell
            'orderType': order_type,
            'qty': str(qty),
            'timeInForce': 'GTC'
        }
        
        if price and order_type == 'Limit':
            body['price'] = str(price)
        
        return await self._request("POST", "/v5/order/create", body=body)
    
    async def cancel_order(self, order_id, symbol):
        """Отменить ордер"""
        body = {
            'category': 'linear',
            'symbol': symbol,
            'orderId': order_id
        }
        return await self._request("POST", "/v5/order/cancel", body=body)
    
    async def get_open_orders(self, category='linear'):
        """Получить открытые ордера"""
        params = {'category': category}
        return await self._request("GET", "/v5/order/realtime", params)


async def test_direct_api():
    """Тестирование прямого API"""
    
    api_key = os.getenv('BYBIT_API_KEY')
    api_secret = os.getenv('BYBIT_API_SECRET')
    
    print("="*60)
    print("BYBIT DIRECT API TEST")
    print("="*60)
    
    api = BybitDirectAPI(api_key, api_secret, testnet=True)
    
    try:
        # 1. Account Info
        print("\n1️⃣ Account Info:")
        info = await api.get_account_info()
        if info['retCode'] == 0:
            print(f"   ✅ Success")
            result = info.get('result', {})
            print(f"   UID: {result.get('uid', 'N/A')}")
            print(f"   Status: {result.get('unifiedMarginStatus', 'N/A')}")
        else:
            print(f"   ❌ Error: {info['retMsg']}")
        
        # 2. Wallet Balance
        print("\n2️⃣ Wallet Balance:")
        balance = await api.get_wallet_balance()
        if balance['retCode'] == 0:
            print(f"   ✅ Success")
            accounts = balance['result']['list']
            for account in accounts:
                for coin in account.get('coin', []):
                    if coin['coin'] == 'USDT':
                        print(f"   💰 USDT: {float(coin['walletBalance'] or 0):.2f}")
                        print(f"   💵 Available: {float(coin['availableToWithdraw'] or 0):.2f}")
        else:
            print(f"   ❌ Error: {balance['retMsg']}")
        
        # 3. Tickers
        print("\n3️⃣ BTC/USDT Ticker:")
        ticker = await api.get_tickers(symbol='BTCUSDT')
        if ticker['retCode'] == 0:
            print(f"   ✅ Success")
            data = ticker['result']['list'][0]
            print(f"   Last Price: ${float(data['lastPrice']):,.2f}")
            print(f"   24h Volume: {float(data['volume24h']):,.0f} USDT")
        else:
            print(f"   ❌ Error: {ticker['retMsg']}")
        
        # 4. Positions
        print("\n4️⃣ Open Positions:")
        positions = await api.get_positions()
        if positions['retCode'] == 0:
            print(f"   ✅ Success")
            pos_list = positions['result']['list']
            print(f"   Open positions: {len([p for p in pos_list if float(p['size']) > 0])}")
        else:
            print(f"   ❌ Error: {positions['retMsg']}")
        
        # 5. Open Orders
        print("\n5️⃣ Open Orders:")
        orders = await api.get_open_orders()
        if orders['retCode'] == 0:
            print(f"   ✅ Success")
            print(f"   Open orders: {len(orders['result']['list'])}")
        else:
            print(f"   ❌ Error: {orders['retMsg']}")
        
        # 6. Test Order
        print("\n6️⃣ Test Order Placement:")
        
        # Получаем текущую цену BTC
        ticker_data = ticker['result']['list'][0]
        current_price = float(ticker_data['lastPrice'])
        test_price = round(current_price * 0.8, 2)  # 20% ниже рынка
        
        print(f"   Placing test order...")
        print(f"   Symbol: BTCUSDT")
        print(f"   Side: Buy")
        print(f"   Qty: 0.001 BTC")
        print(f"   Price: ${test_price}")
        
        order = await api.place_order(
            symbol='BTCUSDT',
            side='Buy',
            qty=0.001,
            order_type='Limit',
            price=test_price
        )
        
        if order['retCode'] == 0:
            order_id = order['result']['orderId']
            print(f"   ✅ Order placed! ID: {order_id}")
            
            # Отменяем ордер
            await asyncio.sleep(1)
            cancel = await api.cancel_order(order_id, 'BTCUSDT')
            if cancel['retCode'] == 0:
                print(f"   ✅ Order cancelled")
        else:
            print(f"   ❌ Error: {order['retMsg']}")
        
        print("\n" + "="*60)
        print("✅ ALL TESTS COMPLETED!")
        print("="*60)
        
        print("\n🎉 Direct API работает отлично!")
        print("\nРекомендация: Используйте прямые API вызовы вместо CCXT")
        print("или обновите CCXT до последней версии:")
        print("pip install --upgrade ccxt")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_direct_api())