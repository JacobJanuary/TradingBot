import asyncio
import sys
sys.path.insert(0, '/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot')

from core.exchange_manager import ExchangeManager
from config.settings import config

async def cleanup():
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("🧹 ОЧИСТКА TESTNET ПОЗИЦИЙ")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    
    exchanges = {}
    for name, ex_config in config.exchanges.items():
        exchanges[name] = ExchangeManager(name, {
            'api_key': ex_config.api_key,
            'api_secret': ex_config.api_secret,
            'testnet': ex_config.testnet,
            'rate_limit': True
        })
        await exchanges[name].initialize()
    
    total_closed = 0
    
    try:
        for name, exchange in exchanges.items():
            print(f"📊 {name.upper()} {'TESTNET' if config.exchanges[name].testnet else 'PRODUCTION'}:")
            print("-" * 80)
            
            # Получить все позиции
            positions = await exchange.fetch_positions()
            active = [p for p in positions if float(p.get('contracts', 0)) != 0]
            
            if not active:
                print(f"   ✅ Нет открытых позиций")
                print()
                continue
                
            print(f"   Найдено {len(active)} открытых позиций")
            
            # Закрыть каждую позицию
            for pos in active:
                symbol = pos['symbol']
                side = pos['side']
                contracts = float(pos.get('contracts', 0))
                
                try:
                    # Определить сторону закрытия (противоположную открытию)
                    close_side = 'sell' if side == 'long' else 'buy'
                    
                    # Закрыть позицию market ордером
                    order = await exchange.create_market_order(
                        symbol, 
                        close_side, 
                        abs(contracts)
                    )
                    
                    print(f"   ✅ Закрыта: {symbol} {side} {contracts}")
                    total_closed += 1
                    
                except Exception as e:
                    print(f"   ❌ Ошибка закрытия {symbol}: {e}")
            
            print()
        
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"✅ ОЧИСТКА ЗАВЕРШЕНА: {total_closed} позиций закрыто")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        
    finally:
        for exchange in exchanges.values():
            await exchange.close()

if __name__ == "__main__":
    asyncio.run(cleanup())
