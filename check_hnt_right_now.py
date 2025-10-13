#!/usr/bin/env python3
"""Check HNT position RIGHT NOW with timestamp"""

import asyncio
from dotenv import load_dotenv
import os
import ccxt.async_support as ccxt
from datetime import datetime
import time

async def check_now():
    load_dotenv()

    bybit = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
            'accountType': 'UNIFIED'
        }
    })

    bybit.set_sandbox_mode(True)

    try:
        current_time = datetime.now()
        timestamp_ms = int(time.time() * 1000)

        print("="*80)
        print(f"CHECKING HNTUSDT RIGHT NOW")
        print(f"Local time: {current_time}")
        print(f"Timestamp: {timestamp_ms}")
        print("="*80)

        # Direct API call with current timestamp
        result = await bybit.private_get_v5_position_list({
            'category': 'linear',
            'symbol': 'HNTUSDT',
            'timestamp': timestamp_ms
        })

        if result.get('result'):
            positions = result['result'].get('list', [])

            if positions:
                pos = positions[0]

                size = pos.get('size', '0')
                side = pos.get('side', '')
                avg_price = pos.get('avgPrice', '0')
                mark_price = pos.get('markPrice', '0')
                stop_loss = pos.get('stopLoss', '')
                unrealised_pnl = pos.get('unrealisedPnl', '')

                print(f"\nPosition data:")
                print(f"  size: {size}")
                print(f"  side: '{side}'")
                print(f"  avgPrice: {avg_price}")
                print(f"  markPrice: {mark_price}")
                print(f"  stopLoss: {stop_loss}")
                print(f"  unrealisedPnl: {unrealised_pnl}")

                size_float = float(size) if size else 0

                print(f"\nAnalysis:")
                if size_float > 0:
                    print(f"  ✅ POSITION IS OPEN with {size_float} contracts")
                    print(f"  Side: {side}")
                    print(f"  Avg entry: {avg_price}")

                    if stop_loss and float(stop_loss) > 0:
                        print(f"  ✅ Stop Loss SET at {stop_loss}")
                    else:
                        print(f"  ⚠️ NO Stop Loss")

                elif size_float == 0:
                    print(f"  ⭕ POSITION IS CLOSED (size = 0)")

                    if stop_loss and float(stop_loss) > 0:
                        print(f"  ⚠️ But stopLoss field shows: {stop_loss}")
                        print(f"     This is stale data from when position was open")

        # Also check with fetch_positions
        print(f"\n{'='*80}")
        print(f"Cross-checking with fetch_positions:")
        print(f"{'='*80}")

        positions = await bybit.fetch_positions(['HNT/USDT:USDT'])

        if positions and len(positions) > 0:
            pos = positions[0]
            contracts = pos.get('contracts')
            side = pos.get('side')
            entry = pos.get('entryPrice')

            print(f"\nfetch_positions result:")
            print(f"  contracts: {contracts}")
            print(f"  side: {side}")
            print(f"  entryPrice: {entry}")

            if contracts and float(contracts) > 0:
                print(f"\n  ✅ CCXT sees position with {contracts} contracts")
            else:
                print(f"\n  ⭕ CCXT shows contracts = 0 or None")

        print(f"\n{'='*80}")
        print(f"ВАЖНО:")
        print(f"{'='*80}")
        print(f"\nЕсли ты СЕЙЧАС видишь 59.88 в веб-UI:")
        print(f"  - Проверь timestamp обновления в веб-UI")
        print(f"  - Сверь с нашим timestamp: {timestamp_ms}")
        print(f"  - Разница покажет задержку данных")
        print(f"\nЕсли API показывает size=0 но ты видишь 59.88:")
        print(f"  - Либо веб-UI показывает кеш")
        print(f"  - Либо API возвращает stale data")
        print(f"  - Либо это разные режимы (positionIdx)")

        await bybit.close()

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(check_now())
