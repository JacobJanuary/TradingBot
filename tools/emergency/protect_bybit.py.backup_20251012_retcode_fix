import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv

load_dotenv()

async def protect_bybit_positions():
    # Инициализация Bybit testnet
    exchange = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'enableRateLimit': True,
        'options': {
            'defaultType': 'linear',
            'recvWindow': 10000
        }
    })

    exchange.set_sandbox_mode(True)

    print('=== ЗАЩИТА ПОЗИЦИЙ НА BYBIT TESTNET ===\n')

    try:
        # Получаем позиции
        positions = await exchange.fetch_positions()
        open_positions = [p for p in positions if p['contracts'] > 0]

        print(f'Найдено {len(open_positions)} открытых позиций\n')

        protected = 0
        failed = 0

        for pos in open_positions:
            symbol = pos['symbol']
            side = pos['side']
            contracts = pos['contracts']
            entry_price = float(pos['info'].get('avgPrice', 0))

            if entry_price > 0:
                # Рассчитываем stop loss (2% от входа)
                if side == 'long':
                    stop_price = round(entry_price * 0.98, 4)
                    order_side = 'sell'
                else:  # short
                    stop_price = round(entry_price * 1.02, 4)
                    order_side = 'buy'

                print(f'{symbol}:')
                print(f'  {side.upper()} {contracts:.2f} @ ${entry_price:.4f}')
                print(f'  Stop loss: ${stop_price:.4f}', end=' ')

                try:
                    # Используем createStopLossOrder если доступен
                    if hasattr(exchange, 'create_stop_loss_order'):
                        order = await exchange.create_stop_loss_order(
                            symbol=symbol,
                            type='market',
                            side=order_side,
                            amount=contracts,
                            stopLossPrice=stop_price,
                            params={'reduceOnly': True}
                        )
                    else:
                        # Используем стандартный stop market order
                        order = await exchange.create_order(
                            symbol=symbol,
                            type='stop',
                            side=order_side,
                            amount=contracts,
                            price=None,
                            params={
                                'stopPx': stop_price,
                                'reduceOnly': True,
                                'triggerPrice': stop_price
                            }
                        )

                    print('✅ Установлен')
                    protected += 1

                except Exception as e:
                    # Последняя попытка через прямой API
                    try:
                        # Форматируем символ для Bybit API
                        bybit_symbol = symbol.replace('/USDT:USDT', 'USDT').replace('/', '')

                        # Создаем stop order через нативный API
                        result = await exchange.privatePostContractV3PrivateStopOrderCreate({
                            'symbol': bybit_symbol,
                            'side': 'Buy' if order_side == 'buy' else 'Sell',
                            'orderType': 'Market',
                            'qty': str(contracts),
                            'triggerPrice': str(stop_price),
                            'triggerDirection': 1 if side == 'long' else 2,  # 1=rise for long, 2=fall for short
                            'timeInForce': 'GTC',
                            'reduceOnly': True,
                            'closeOnTrigger': True,
                            'positionIdx': 0  # One-way mode
                        })

                        if result.get('retCode') == 0:
                            print('✅ Установлен через API')
                            protected += 1
                        else:
                            print(f'❌ Ошибка API: {result.get("retMsg", "Unknown")}')
                            failed += 1

                    except Exception as e2:
                        print(f'❌ Ошибка: {str(e)[:50]}')
                        failed += 1

        print(f'\n' + '='*50)
        print(f'РЕЗУЛЬТАТ:')
        print(f'✅ Защищено позиций: {protected}')
        print(f'❌ Не удалось защитить: {failed}')
        print(f'Всего позиций: {len(open_positions)}')

    except Exception as e:
        print(f'Критическая ошибка: {e}')

    finally:
        await exchange.close()

if __name__ == '__main__':
    asyncio.run(protect_bybit_positions())