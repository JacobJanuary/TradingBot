#!/usr/bin/env python3
"""
Check Stop-Loss on Exchange - Verify actual SL on Binance/Bybit

Purpose: Проверить что Stop-Loss реально установлен на бирже
         для позиции которая не отображается в веб-интерфейсе

Usage:
    python3 check_stop_loss_on_exchange.py --symbol 1000WHYUSDT --exchange binance
    python3 check_stop_loss_on_exchange.py --position-id 5
"""
import asyncio
import sys
import argparse
from datetime import datetime
from pprint import pprint

sys.path.insert(0, '/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot')

from config import config
from core.exchange_manager import ExchangeManager
from database.repository import Repository


async def check_stop_loss_orders(exchange_manager: ExchangeManager, symbol: str):
    """
    Check all stop-loss orders for a symbol
    """
    print(f"\n{'='*80}")
    print(f"🔍 CHECKING STOP-LOSS ORDERS FOR {symbol} on {exchange_manager.name.upper()}")
    print(f"{'='*80}\n")

    try:
        # Method 1: Fetch open orders (includes conditional/stop orders)
        print("📋 Method 1: Fetching open orders (fetch_open_orders)")
        print("-" * 80)

        open_orders = await exchange_manager.exchange.fetch_open_orders(symbol)

        print(f"Found {len(open_orders)} open orders\n")

        stop_orders = []
        for order in open_orders:
            order_type = order.get('type', '').lower()
            is_stop = ('stop' in order_type or
                      order_type in ['stop_market', 'stop_loss', 'stop_loss_limit'])

            if is_stop:
                stop_orders.append(order)
                print(f"✅ STOP ORDER FOUND:")
                print(f"   ID: {order['id']}")
                print(f"   Type: {order['type']}")
                print(f"   Side: {order['side']}")
                print(f"   Amount: {order['amount']}")
                print(f"   Stop Price: {order.get('stopPrice', 'N/A')}")
                print(f"   Price: {order.get('price', 'N/A')}")
                print(f"   Status: {order['status']}")
                print(f"   Info: {order.get('info', {})}")
                print()

        if not stop_orders:
            print("❌ No stop orders found in open orders\n")

    except Exception as e:
        print(f"❌ Error fetching open orders: {e}\n")

    # Method 2: Fetch positions (for position-attached SL on Bybit/Binance)
    if exchange_manager.name.lower() in ['bybit', 'binance']:
        try:
            print("📋 Method 2: Fetching positions (fetch_positions)")
            print("-" * 80)

            if exchange_manager.name.lower() == 'bybit':
                positions = await exchange_manager.exchange.fetch_positions(
                    params={'category': 'linear'}
                )
            else:
                positions = await exchange_manager.exchange.fetch_positions()

            print(f"Found {len(positions)} positions\n")

            for pos in positions:
                if pos['symbol'] == symbol and float(pos.get('contracts', 0)) > 0:
                    print(f"✅ POSITION FOUND:")
                    print(f"   Symbol: {pos['symbol']}")
                    print(f"   Side: {pos['side']}")
                    print(f"   Contracts: {pos['contracts']}")
                    print(f"   Entry Price: {pos.get('entryPrice', 'N/A')}")
                    print(f"   Mark Price: {pos.get('markPrice', 'N/A')}")
                    print(f"   Unrealized PnL: {pos.get('unrealizedPnl', 'N/A')}")
                    print()

                    # Check position-attached SL (in info)
                    info = pos.get('info', {})
                    stop_loss = info.get('stopLoss') or info.get('stopLossPrice')

                    if stop_loss and stop_loss != '0':
                        print(f"   ✅ STOP LOSS (position-attached): {stop_loss}")
                    else:
                        print(f"   ❌ No position-attached stop loss")

                    print()

                    # Show full info for debugging
                    print(f"   Raw position info:")
                    pprint(info, indent=6)
                    print()

        except Exception as e:
            print(f"❌ Error fetching positions: {e}\n")

    # Method 3: Fetch conditional orders (Binance specific)
    if exchange_manager.name.lower() == 'binance':
        try:
            print("📋 Method 3: Fetching conditional orders (Binance specific)")
            print("-" * 80)

            # Binance futures conditional orders
            conditional_orders = await exchange_manager.exchange.fetch_open_orders(
                symbol,
                params={'type': 'STOP_MARKET'}
            )

            print(f"Found {len(conditional_orders)} conditional orders\n")

            for order in conditional_orders:
                print(f"✅ CONDITIONAL ORDER:")
                print(f"   ID: {order['id']}")
                print(f"   Type: {order['type']}")
                print(f"   Side: {order['side']}")
                print(f"   Amount: {order['amount']}")
                print(f"   Stop Price: {order.get('stopPrice', 'N/A')}")
                print(f"   Status: {order['status']}")
                print()

        except Exception as e:
            print(f"❌ Error fetching conditional orders: {e}\n")

    print(f"{'='*80}")
    print("✅ Check completed")
    print(f"{'='*80}\n")


async def check_position_from_db(repository: Repository, position_id: int):
    """
    Get position details from database
    """
    print(f"\n{'='*80}")
    print(f"🔍 CHECKING POSITION #{position_id} IN DATABASE")
    print(f"{'='*80}\n")

    try:
        position = await repository.get_position(position_id)

        if not position:
            print(f"❌ Position #{position_id} not found in database\n")
            return None, None, None

        print(f"✅ POSITION FOUND IN DATABASE:")
        print(f"   ID: {position['id']}")
        print(f"   Symbol: {position['symbol']}")
        print(f"   Exchange: {position['exchange']}")
        print(f"   Side: {position['side']}")
        print(f"   Quantity: {position['quantity']}")
        print(f"   Entry Price: {position.get('entry_price', 'N/A')}")
        print(f"   Stop Loss Price: {position.get('stop_loss_price', 'N/A')}")
        print(f"   Status: {position.get('status', 'N/A')}")
        print(f"   Created: {position.get('created_at', 'N/A')}")
        print()

        return position['symbol'], position['exchange'], position.get('stop_loss_price')

    except Exception as e:
        print(f"❌ Error fetching position from DB: {e}\n")
        return None, None, None


async def main():
    parser = argparse.ArgumentParser(description='Check Stop-Loss orders on exchange')
    parser.add_argument('--symbol', type=str, help='Trading symbol (e.g., 1000WHYUSDT)')
    parser.add_argument('--exchange', type=str, choices=['binance', 'bybit'],
                       help='Exchange name')
    parser.add_argument('--position-id', type=int, help='Position ID from database')

    args = parser.parse_args()

    print()
    print("🔬 STOP-LOSS VERIFICATION TOOL")
    print("=" * 80)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Initialize repository
    repository = Repository()
    await repository.initialize()

    symbol = args.symbol
    exchange_name = args.exchange
    expected_sl_price = None

    # If position ID provided, get details from DB
    if args.position_id:
        symbol, exchange_name, expected_sl_price = await check_position_from_db(
            repository, args.position_id
        )
        if not symbol:
            print("❌ Cannot proceed without valid position")
            return

    # Validate inputs
    if not symbol or not exchange_name:
        print("❌ Error: Must provide either --position-id OR (--symbol AND --exchange)")
        parser.print_help()
        return

    print(f"Target Symbol: {symbol}")
    print(f"Target Exchange: {exchange_name}")
    if expected_sl_price:
        print(f"Expected SL Price (from DB): {expected_sl_price}")
    print()

    # Initialize exchange
    exchange_config = {
        'api_key': config.exchanges[exchange_name].api_key,
        'api_secret': config.exchanges[exchange_name].api_secret,
        'testnet': config.exchanges[exchange_name].testnet
    }

    exchange_manager = ExchangeManager(exchange_name, exchange_config)

    try:
        # Check stop-loss orders
        await check_stop_loss_orders(exchange_manager, symbol)

        # Summary
        print()
        print("=" * 80)
        print("📊 SUMMARY")
        print("=" * 80)
        print()
        print(f"Symbol: {symbol}")
        print(f"Exchange: {exchange_name}")
        if expected_sl_price:
            print(f"Expected SL (DB): {expected_sl_price}")
        print()
        print("✅ Check the output above to verify if stop-loss exists on exchange")
        print()
        print("🔍 If SL not visible in web UI but found here:")
        print("   → SL exists but may be hidden in conditional orders tab")
        print("   → Or position-attached SL (check position details)")
        print()
        print("❌ If SL not found anywhere:")
        print("   → CRITICAL: Position has no protection!")
        print("   → Manually set SL immediately")
        print()

    finally:
        await exchange_manager.close()
        await repository.close()


if __name__ == "__main__":
    asyncio.run(main())
