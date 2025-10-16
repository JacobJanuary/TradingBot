#!/usr/bin/env python3
"""
Проверка реального состояния ордеров и позиций через API
Сравнение с тем, что показывает веб-интерфейс
"""

import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv
from datetime import datetime
from collections import defaultdict
import json

load_dotenv()


async def check_binance():
    """Проверка Binance Futures"""
    print("\n" + "="*80)
    print("📊 BINANCE FUTURES - REAL STATE")
    print("="*80)

    exchange = ccxt.binanceusdm({
        'apiKey': os.getenv('BINANCE_API_KEY'),
        'secret': os.getenv('BINANCE_API_SECRET'),
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
            'adjustForTimeDifference': True,
            'warnOnFetchOpenOrdersWithoutSymbol': False,
        }
    })

    # Определяем testnet или mainnet
    if os.getenv('BINANCE_TESTNET', 'false').lower() == 'true':
        exchange.set_sandbox_mode(True)
        print("🔧 Mode: TESTNET")
    else:
        print("🔧 Mode: MAINNET")

    try:
        # 1. Получить все позиции
        print("\n📈 POSITIONS:")
        positions = await exchange.fetch_positions()

        active_positions = []
        for pos in positions:
            contracts = float(pos.get('contracts', 0) or 0)
            if contracts != 0:  # Любая ненулевая позиция (включая отрицательные)
                active_positions.append(pos)

                print(f"\n  Symbol: {pos['symbol']}")
                print(f"    Side: {pos.get('side', 'N/A')}")
                print(f"    Contracts: {contracts}")
                print(f"    Entry Price: {pos.get('entryPrice', 0)}")
                print(f"    Mark Price: {pos.get('markPrice', 0)}")
                print(f"    Unrealized PnL: {pos.get('unrealizedPnl', 0)}")
                print(f"    Leverage: {pos.get('leverage', 1)}")

        print(f"\n  Total active positions: {len(active_positions)}")

        # 2. Получить ВСЕ открытые ордера
        print("\n📋 OPEN ORDERS:")
        all_orders = await exchange.fetch_open_orders()

        print(f"\n  Total open orders: {len(all_orders)}")

        # Группировка по типам
        orders_by_type = defaultdict(list)
        orders_by_symbol = defaultdict(list)

        for order in all_orders:
            order_type = order.get('type', 'UNKNOWN')
            symbol = order.get('symbol', 'UNKNOWN')

            orders_by_type[order_type].append(order)
            orders_by_symbol[symbol].append(order)

        # Статистика по типам
        print("\n  📊 Orders by type:")
        for order_type, orders in sorted(orders_by_type.items()):
            print(f"    {order_type}: {len(orders)}")

        # Статистика по символам
        print("\n  📊 Orders by symbol:")
        for symbol, orders in sorted(orders_by_symbol.items(), key=lambda x: len(x[1]), reverse=True):
            # Проверить есть ли позиция
            has_position = any(
                p['symbol'] == symbol and float(p.get('contracts', 0)) != 0
                for p in positions
            )

            position_marker = "✅ HAS POSITION" if has_position else "❌ NO POSITION"
            print(f"    {symbol}: {len(orders)} orders - {position_marker}")

            # Детали ордеров для этого символа
            for order in orders:
                order_id = order.get('id', 'N/A')
                order_type = order.get('type', 'N/A')
                side = order.get('side', 'N/A')
                status = order.get('status', 'N/A')
                amount = order.get('amount', 0)
                price = order.get('price', 0)

                # Проверить reduceOnly
                reduce_only = order.get('reduceOnly', False)
                reduce_marker = "🔻 REDUCE_ONLY" if reduce_only else ""

                # Проверить возраст
                timestamp = order.get('timestamp', 0)
                if timestamp:
                    age_hours = (datetime.now().timestamp() * 1000 - timestamp) / (1000 * 3600)
                    age_str = f"{age_hours:.1f}h old"
                else:
                    age_str = "unknown age"

                print(f"      • ID: {order_id[:12]}... {order_type} {side} "
                      f"@{price} amt={amount} [{status}] {age_str} {reduce_marker}")

        # 3. АНАЛИЗ: Зомби-ордера?
        print("\n" + "="*80)
        print("🧟 ZOMBIE ANALYSIS:")
        print("="*80)

        active_symbols = {p['symbol'] for p in active_positions}

        potential_zombies = []
        for symbol, orders in orders_by_symbol.items():
            if symbol not in active_symbols:
                # Нет позиции, но есть ордера
                for order in orders:
                    potential_zombies.append({
                        'symbol': symbol,
                        'order_id': order.get('id'),
                        'type': order.get('type'),
                        'side': order.get('side'),
                        'reduceOnly': order.get('reduceOnly', False),
                        'age_hours': (datetime.now().timestamp() * 1000 - order.get('timestamp', 0)) / (1000 * 3600) if order.get('timestamp') else 0
                    })

        if potential_zombies:
            print(f"\n⚠️  Found {len(potential_zombies)} potential zombie orders:")
            for zombie in potential_zombies:
                print(f"\n  Symbol: {zombie['symbol']}")
                print(f"    Order ID: {zombie['order_id']}")
                print(f"    Type: {zombie['type']}")
                print(f"    Side: {zombie['side']}")
                print(f"    ReduceOnly: {zombie['reduceOnly']}")
                print(f"    Age: {zombie['age_hours']:.1f} hours")

                # Определить: это действительно зомби или нет?
                is_protective = any(keyword in zombie['type'].upper()
                                   for keyword in ['STOP', 'TAKE_PROFIT', 'TRAILING'])

                if is_protective and zombie['reduceOnly']:
                    print(f"    ⚠️  This is a PROTECTIVE order without position - ZOMBIE!")
                elif is_protective:
                    print(f"    🟡 Protective order but not reduceOnly - check manually")
                else:
                    print(f"    🟢 Regular order without position - legitimate zombie")
        else:
            print("\n✅ No zombie orders found - all orders have corresponding positions")

        # 4. Сохранить детальные данные
        report_data = {
            'exchange': 'binance',
            'timestamp': datetime.now().isoformat(),
            'positions_count': len(active_positions),
            'orders_count': len(all_orders),
            'positions': [
                {
                    'symbol': p['symbol'],
                    'side': p.get('side'),
                    'contracts': float(p.get('contracts', 0)),
                    'entry_price': p.get('entryPrice'),
                    'unrealized_pnl': p.get('unrealizedPnl')
                }
                for p in active_positions
            ],
            'orders': [
                {
                    'order_id': o.get('id'),
                    'symbol': o.get('symbol'),
                    'type': o.get('type'),
                    'side': o.get('side'),
                    'status': o.get('status'),
                    'amount': o.get('amount'),
                    'price': o.get('price'),
                    'reduceOnly': o.get('reduceOnly', False),
                    'timestamp': o.get('timestamp')
                }
                for o in all_orders
            ],
            'potential_zombies': potential_zombies
        }

        filename = f"binance_real_state_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(report_data, f, indent=2)

        print(f"\n💾 Detailed data saved to: {filename}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await exchange.close()


async def check_bybit():
    """Проверка Bybit"""
    print("\n" + "="*80)
    print("📊 BYBIT - REAL STATE")
    print("="*80)

    exchange = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'enableRateLimit': True,
        'options': {
            'defaultType': 'swap',
        }
    })

    if os.getenv('BYBIT_TESTNET', 'false').lower() == 'true':
        exchange.set_sandbox_mode(True)
        print("🔧 Mode: TESTNET")
    else:
        print("🔧 Mode: MAINNET")

    try:
        # 1. Позиции
        print("\n📈 POSITIONS:")
        positions = await exchange.fetch_positions()

        active_positions = []
        for pos in positions:
            contracts = float(pos.get('contracts', 0) or pos.get('size', 0) or 0)
            if contracts != 0:
                active_positions.append(pos)

                pos_info = pos.get('info', {})
                position_idx = pos_info.get('positionIdx', 0)

                print(f"\n  Symbol: {pos['symbol']}")
                print(f"    Side: {pos.get('side', 'N/A')}")
                print(f"    Contracts: {contracts}")
                print(f"    Position Idx: {position_idx}")
                print(f"    Entry Price: {pos.get('entryPrice', 0)}")
                print(f"    Mark Price: {pos.get('markPrice', 0)}")
                print(f"    Unrealized PnL: {pos.get('unrealizedPnl', 0)}")

        print(f"\n  Total active positions: {len(active_positions)}")

        # 2. Ордера
        print("\n📋 OPEN ORDERS:")
        all_orders = await exchange.fetch_open_orders()

        print(f"\n  Total open orders: {len(all_orders)}")

        orders_by_type = defaultdict(list)
        orders_by_symbol = defaultdict(list)

        for order in all_orders:
            order_type = order.get('type', 'UNKNOWN')
            symbol = order.get('symbol', 'UNKNOWN')

            orders_by_type[order_type].append(order)
            orders_by_symbol[symbol].append(order)

        print("\n  📊 Orders by type:")
        for order_type, orders in sorted(orders_by_type.items()):
            print(f"    {order_type}: {len(orders)}")

        print("\n  📊 Orders by symbol:")
        for symbol, orders in sorted(orders_by_symbol.items(), key=lambda x: len(x[1]), reverse=True):
            has_position = any(
                p['symbol'] == symbol and float(p.get('contracts', 0) or p.get('size', 0) or 0) != 0
                for p in positions
            )

            position_marker = "✅ HAS POSITION" if has_position else "❌ NO POSITION"
            print(f"    {symbol}: {len(orders)} orders - {position_marker}")

            for order in orders:
                order_info = order.get('info', {})
                order_id = order.get('id', 'N/A')
                order_type = order.get('type', 'N/A')
                side = order.get('side', 'N/A')
                status = order.get('status', 'N/A')

                reduce_only = order_info.get('reduceOnly', False)
                position_idx = order_info.get('positionIdx', 0)
                stop_order_type = order_info.get('stopOrderType', '')

                reduce_marker = "🔻 REDUCE" if reduce_only else ""
                stop_marker = f"🛑 {stop_order_type}" if stop_order_type else ""

                timestamp = order.get('timestamp', 0)
                if timestamp:
                    age_hours = (datetime.now().timestamp() * 1000 - timestamp) / (1000 * 3600)
                    age_str = f"{age_hours:.1f}h"
                else:
                    age_str = "?"

                print(f"      • ID: {order_id[:12]}... {order_type} {side} "
                      f"idx={position_idx} [{status}] {age_str} {reduce_marker} {stop_marker}")

        # 3. Анализ зомби
        print("\n" + "="*80)
        print("🧟 ZOMBIE ANALYSIS:")
        print("="*80)

        # Создать карту активных позиций с positionIdx
        active_position_keys = set()
        for p in active_positions:
            symbol = p['symbol']
            pos_info = p.get('info', {})
            position_idx = int(pos_info.get('positionIdx', 0))
            active_position_keys.add((symbol, position_idx))

        potential_zombies = []
        for order in all_orders:
            symbol = order.get('symbol')
            order_info = order.get('info', {})
            position_idx = int(order_info.get('positionIdx', 0))

            order_key = (symbol, position_idx)

            if order_key not in active_position_keys:
                # Нет соответствующей позиции
                potential_zombies.append({
                    'symbol': symbol,
                    'order_id': order.get('id'),
                    'type': order.get('type'),
                    'side': order.get('side'),
                    'position_idx': position_idx,
                    'reduceOnly': order_info.get('reduceOnly', False),
                    'stopOrderType': order_info.get('stopOrderType', ''),
                    'status': order.get('status', ''),
                    'age_hours': (datetime.now().timestamp() * 1000 - order.get('timestamp', 0)) / (1000 * 3600) if order.get('timestamp') else 0
                })

        if potential_zombies:
            print(f"\n⚠️  Found {len(potential_zombies)} potential zombie orders:")
            for zombie in potential_zombies:
                print(f"\n  Symbol: {zombie['symbol']} (positionIdx={zombie['position_idx']})")
                print(f"    Order ID: {zombie['order_id']}")
                print(f"    Type: {zombie['type']}")
                print(f"    Side: {zombie['side']}")
                print(f"    Status: {zombie['status']}")
                print(f"    ReduceOnly: {zombie['reduceOnly']}")
                print(f"    StopOrderType: {zombie['stopOrderType']}")
                print(f"    Age: {zombie['age_hours']:.1f} hours")

                if zombie['stopOrderType']:
                    print(f"    ⚠️  This is a TP/SL order without position - ZOMBIE!")
                elif zombie['reduceOnly']:
                    print(f"    ⚠️  ReduceOnly order without position - ZOMBIE!")
                else:
                    print(f"    🟢 Regular order without position")
        else:
            print("\n✅ No zombie orders found")

        # Сохранить данные
        report_data = {
            'exchange': 'bybit',
            'timestamp': datetime.now().isoformat(),
            'positions_count': len(active_positions),
            'orders_count': len(all_orders),
            'positions': [
                {
                    'symbol': p['symbol'],
                    'side': p.get('side'),
                    'contracts': float(p.get('contracts', 0) or p.get('size', 0) or 0),
                    'position_idx': p.get('info', {}).get('positionIdx', 0),
                    'entry_price': p.get('entryPrice'),
                    'unrealized_pnl': p.get('unrealizedPnl')
                }
                for p in active_positions
            ],
            'orders': [
                {
                    'order_id': o.get('id'),
                    'symbol': o.get('symbol'),
                    'type': o.get('type'),
                    'side': o.get('side'),
                    'status': o.get('status'),
                    'position_idx': o.get('info', {}).get('positionIdx', 0),
                    'reduceOnly': o.get('info', {}).get('reduceOnly', False),
                    'stopOrderType': o.get('info', {}).get('stopOrderType', ''),
                    'timestamp': o.get('timestamp')
                }
                for o in all_orders
            ],
            'potential_zombies': potential_zombies
        }

        filename = f"bybit_real_state_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(report_data, f, indent=2)

        print(f"\n💾 Detailed data saved to: {filename}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await exchange.close()


async def main():
    print("="*80)
    print("🔍 REAL EXCHANGE STATE CHECK")
    print("="*80)
    print(f"Time: {datetime.now().isoformat()}")
    print("\nThis script checks the REAL state of orders and positions via API")
    print("and identifies potential zombie orders.\n")

    # Проверить обе биржи
    await check_binance()
    await check_bybit()

    print("\n" + "="*80)
    print("✅ CHECK COMPLETE")
    print("="*80)
    print("\nFiles created:")
    print("  - binance_real_state_YYYYMMDD_HHMMSS.json")
    print("  - bybit_real_state_YYYYMMDD_HHMMSS.json")
    print("\nReview the zombie analysis above to see if cleanup is needed.")


if __name__ == '__main__':
    asyncio.run(main())
