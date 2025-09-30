import asyncio
import sys
sys.path.append('/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot')

from core.exchange_manager import ExchangeManager
from config.settings import settings
import os
from dotenv import load_dotenv

load_dotenv()

async def check_bybit_positions():
    # Инициализируем Bybit
    bybit = ExchangeManager('bybit')
    await bybit.initialize()

    print('=== ПРОВЕРКА ПОЗИЦИЙ НА BYBIT ===\n')

    # Получаем позиции
    positions = await bybit.fetch_positions()

    open_positions = [p for p in positions if p.quantity > 0]

    print(f'Найдено открытых позиций: {len(open_positions)}')
    print(f'Позиций без stop loss: {len([p for p in open_positions if not hasattr(p, "stop_loss") or p.stop_loss is None])}\n')

    if open_positions:
        print('Детали позиций на Bybit:')
        print('-' * 80)
        for i, pos in enumerate(open_positions[:15], 1):
            sl_status = '❌ НЕТ' if not hasattr(pos, 'stop_loss') or pos.stop_loss is None else f'✅ {pos.stop_loss}'
            print(f'{i:2}. {pos.symbol:15} | {pos.side.upper():5} | Вход: ${pos.entry_price:.4f} | Кол-во: {pos.quantity:.2f}')
            print(f'    Stop Loss: {sl_status}')

        # Установим stop loss для позиций без защиты
        print('\n' + '='*80)
        print('УСТАНОВКА STOP LOSS ДЛЯ НЕЗАЩИЩЕННЫХ ПОЗИЦИЙ:')
        print('='*80)

        for pos in open_positions:
            if not hasattr(pos, 'stop_loss') or pos.stop_loss is None:
                try:
                    # Рассчитываем stop loss (2% от входа)
                    if pos.side == 'long':
                        stop_price = pos.entry_price * 0.98
                    else:
                        stop_price = pos.entry_price * 1.02

                    print(f'\nУстанавливаю stop loss для {pos.symbol}:')
                    print(f'  Позиция: {pos.side} {pos.quantity} @ {pos.entry_price}')
                    print(f'  Stop price: ${stop_price:.4f}')

                    # Создаем stop loss ордер
                    order_side = 'sell' if pos.side == 'long' else 'buy'
                    order = await bybit.create_stop_loss_order(
                        symbol=pos.symbol,
                        side=order_side,
                        amount=pos.quantity,
                        stop_price=stop_price
                    )

                    if order:
                        print(f'  ✅ Stop loss установлен!')
                    else:
                        print(f'  ❌ Не удалось установить stop loss')

                except Exception as e:
                    print(f'  ❌ Ошибка: {e}')

    await bybit.close()

if __name__ == '__main__':
    asyncio.run(check_bybit_positions())