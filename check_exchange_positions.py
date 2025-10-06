import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv

load_dotenv()

async def check_positions():
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("🔍 ПРОВЕРКА РЕАЛЬНЫХ ПОЗИЦИЙ НА БИРЖАХ")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    
    # Binance
    binance = ccxt.binance({
        'apiKey': os.getenv('BINANCE_API_KEY'),
        'secret': os.getenv('BINANCE_API_SECRET'),
        'options': {'defaultType': 'future'}
    })
    binance.urls['api']['fapiPublic'] = 'https://testnet.binancefuture.com/fapi/v1'
    binance.urls['api']['fapiPrivate'] = 'https://testnet.binancefuture.com/fapi/v1'
    binance.hostname = 'testnet.binancefuture.com'
    
    # Bybit
    bybit = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'options': {
            'defaultType': 'future',
            'accountType': 'UNIFIED'
        }
    })
    bybit.urls['api'] = {
        'public': 'https://api-testnet.bybit.com',
        'private': 'https://api-testnet.bybit.com'
    }
    
    try:
        # Binance positions
        print("📊 BINANCE FUTURES TESTNET:")
        print("-" * 80)
        binance_positions = await binance.fetch_positions()
        active_binance = [p for p in binance_positions if float(p.get('contracts', 0)) != 0]
        
        if active_binance:
            for i, pos in enumerate(active_binance, 1):
                symbol = pos['symbol']
                side = pos['side']
                contracts = float(pos.get('contracts', 0))
                entry = float(pos.get('entryPrice', 0))
                notional = float(pos.get('notional', 0))
                leverage = float(pos.get('leverage', 0))
                pnl = float(pos.get('unrealizedPnl', 0))
                
                print(f"{i}. {symbol}")
                print(f"   Side: {side}")
                print(f"   Contracts: {contracts}")
                print(f"   Entry: ${entry:.6f}")
                print(f"   Notional: ${abs(notional):.2f}")
                print(f"   Leverage: {leverage}x")
                print(f"   PnL: ${pnl:.2f}")
                print()
        else:
            print("   ✅ Нет открытых позиций")
        
        print()
        print("📊 BYBIT TESTNET:")
        print("-" * 80)
        bybit_positions = await bybit.fetch_positions()
        active_bybit = [p for p in bybit_positions if float(p.get('contracts', 0)) != 0]
        
        if active_bybit:
            for i, pos in enumerate(active_bybit, 1):
                symbol = pos['symbol']
                side = pos['side']
                contracts = float(pos.get('contracts', 0))
                entry = float(pos.get('entryPrice', 0))
                notional = float(pos.get('notional', 0))
                leverage = float(pos.get('leverage', 0))
                pnl = float(pos.get('unrealizedPnl', 0))
                
                print(f"{i}. {symbol}")
                print(f"   Side: {side}")
                print(f"   Contracts: {contracts}")
                print(f"   Entry: ${entry:.6f}")
                print(f"   Notional: ${abs(notional):.2f}")
                print(f"   Leverage: {leverage}x")
                print(f"   PnL: ${pnl:.2f}")
                print()
        else:
            print("   ✅ Нет открытых позиций")
        
        print()
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"📈 ИТОГО: {len(active_binance)} Binance + {len(active_bybit)} Bybit = {len(active_binance) + len(active_bybit)} позиций")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        
        # Check stop loss orders
        print()
        print("🛡️ STOP LOSS ОРДЕРА:")
        print("-" * 80)
        
        # Binance orders
        print("Binance:")
        binance_orders = await binance.fetch_open_orders()
        sl_orders_binance = [o for o in binance_orders if o.get('type') == 'STOP_MARKET' or o.get('stopPrice')]
        if sl_orders_binance:
            for order in sl_orders_binance:
                print(f"  ✅ {order['symbol']}: Stop @ ${order.get('stopPrice', 0)}")
        else:
            print("  ❌ НЕТ SL ордеров!")
        
        print()
        print("Bybit:")
        bybit_orders = await bybit.fetch_open_orders()
        sl_orders_bybit = [o for o in bybit_orders if 'stop' in o.get('type', '').lower()]
        if sl_orders_bybit:
            for order in sl_orders_bybit:
                print(f"  ✅ {order['symbol']}: Stop @ ${order.get('stopPrice', 0)}")
        else:
            print("  ❌ НЕТ SL ордеров!")
        
    finally:
        await binance.close()
        await bybit.close()

if __name__ == "__main__":
    asyncio.run(check_positions())
