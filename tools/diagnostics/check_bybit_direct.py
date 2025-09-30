import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv

load_dotenv()

async def check_and_protect_bybit():
    # Инициализация Bybit testnet
    exchange = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'enableRateLimit': True,
        'options': {
            'defaultType': 'linear',  # USDT perpetual
            'recvWindow': 10000
        }
    })

    # Включаем testnet
    exchange.set_sandbox_mode(True)

    print('=== ПРОВЕРКА ПОЗИЦИЙ НА BYBIT TESTNET ===\n')

    try:
        # Получаем баланс
        balance = await exchange.fetch_balance()
        usdt_balance = balance['USDT']['free'] if 'USDT' in balance else 0
        print(f'Баланс USDT: ${usdt_balance:.2f}\n')

        # Получаем все позиции
        positions = await exchange.fetch_positions()

        # Фильтруем открытые позиции
        open_positions = [p for p in positions if p['contracts'] > 0]

        print(f'Найдено открытых позиций: {len(open_positions)}')

        if open_positions:
            print('\nДетали позиций:')
            print('-' * 100)
            print(f'{"№":3} {"Символ":15} {"Сторона":7} {"Кол-во":12} {"Вход":10} {"Текущая":10} {"P&L %":8} {"Stop Loss":15}')
            print('-' * 100)

            positions_without_sl = []

            for i, pos in enumerate(open_positions, 1):
                symbol = pos['symbol']
                side = pos['side'].upper() if pos['side'] else 'UNKNOWN'
                contracts = pos['contracts']
                entry_price = pos['info'].get('avgPrice', 0) if pos['info'] else 0
                mark_price = pos['info'].get('markPrice', 0) if pos['info'] else 0
                pnl_pct = pos['percentage'] if pos['percentage'] else 0

                # Проверяем наличие stop loss
                has_sl = False
                sl_price = 'НЕТ ❌'

                # Получаем открытые ордера для символа
                try:
                    orders = await exchange.fetch_open_orders(symbol)
                    for order in orders:
                        if order['type'] in ['stop', 'stop_market', 'stop_loss']:
                            has_sl = True
                            sl_price = f"${order['stopPrice']:.4f} ✅"
                            break
                except:
                    pass

                if not has_sl:
                    positions_without_sl.append(pos)

                print(f'{i:3} {symbol:15} {side:7} {contracts:12.4f} ${float(entry_price):9.4f} ${float(mark_price):9.4f} {pnl_pct:7.2f}% {sl_price:15}')

            print('-' * 100)
            print(f'\nПозиций без stop loss: {len(positions_without_sl)}')

            if positions_without_sl:
                print('\n' + '='*80)
                print('УСТАНОВКА STOP LOSS ДЛЯ НЕЗАЩИЩЕННЫХ ПОЗИЦИЙ')
                print('='*80)

                for pos in positions_without_sl[:3]:  # Устанавливаем для первых 3 позиций
                    symbol = pos['symbol']
                    side = pos['side']
                    contracts = pos['contracts']
                    entry_price = float(pos['info'].get('avgPrice', 0)) if pos['info'] else 0

                    if entry_price > 0:
                        # Рассчитываем stop loss (2% от входа)
                        if side == 'long':
                            stop_price = entry_price * 0.98
                            order_side = 'sell'
                        else:  # short
                            stop_price = entry_price * 1.02
                            order_side = 'buy'

                        print(f'\n{symbol}:')
                        print(f'  Позиция: {side.upper()} {contracts:.4f} @ ${entry_price:.4f}')
                        print(f'  Устанавливаю stop loss: ${stop_price:.4f}')

                        try:
                            # Создаем stop loss ордер для Bybit
                            order = await exchange.create_order(
                                symbol=symbol,
                                type='market',
                                side=order_side,
                                amount=contracts,
                                params={
                                    'stopLoss': stop_price,
                                    'reduceOnly': True
                                }
                            )
                            print(f'  ✅ Stop loss установлен! Order ID: {order["id"]}')
                        except Exception as e:
                            # Альтернативный способ для Bybit
                            try:
                                order = await exchange.private_post_private_linear_stop_order_create({
                                    'symbol': symbol.replace('/USDT:USDT', 'USDT').replace('/', ''),
                                    'side': 'Buy' if order_side == 'buy' else 'Sell',
                                    'order_type': 'Market',
                                    'qty': str(contracts),
                                    'stop_px': str(stop_price),
                                    'time_in_force': 'GoodTillCancel',
                                    'reduce_only': True,
                                    'close_on_trigger': True
                                })
                                print(f'  ✅ Stop loss установлен через API! Order ID: {order["result"]["order_id"]}')
                            except Exception as e2:
                                print(f'  ❌ Ошибка установки stop loss: {e}')

        else:
            print('\nНет открытых позиций на Bybit testnet')

    except Exception as e:
        print(f'Ошибка при получении данных: {e}')

    finally:
        await exchange.close()

if __name__ == '__main__':
    asyncio.run(check_and_protect_bybit())