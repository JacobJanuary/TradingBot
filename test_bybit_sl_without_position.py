#!/usr/bin/env python3
"""
TEST: Что происходит при установке SL без позиции?

Проверяет:
1. Можно ли установить SL если позиции нет?
2. Какую ошибку возвращает Bybit?
3. Требует ли SL дополнительный margin?
4. Является ли SL reduce-only?
"""
import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv

load_dotenv()


async def test_sl_without_position():
    """
    Test setting SL when position doesn't exist
    """
    print()
    print("="*80)
    print("🔬 TEST: Setting SL without position")
    print("="*80)
    print()

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

    try:
        await exchange.load_markets()

        # Use a symbol we DON'T have position in
        symbol = 'ETH/USDT:USDT'
        bybit_symbol = 'ETHUSDT'

        print(f"Test symbol: {symbol}")
        print()

        # Get current positions
        positions = await exchange.fetch_positions(params={'category': 'linear'})
        has_position = False

        for pos in positions:
            if pos['symbol'] == symbol and float(pos.get('contracts', 0)) > 0:
                has_position = True
                print(f"⚠️  WARNING: Position exists! {pos['side']} {pos['contracts']}")
                break

        if not has_position:
            print(f"✅ Confirmed: No position in {symbol}")
        print()

        # Try to set SL without position
        print("="*80)
        print("TEST: Setting SL for non-existent position")
        print("="*80)
        print()

        sl_price = 2000  # Arbitrary price

        params = {
            'category': 'linear',
            'symbol': bybit_symbol,
            'stopLoss': str(sl_price),
            'positionIdx': 0,
            'slTriggerBy': 'LastPrice',
            'tpslMode': 'Full'
        }

        print(f"Params: {params}")
        print()

        try:
            result = await exchange.private_post_v5_position_trading_stop(params)

            ret_code = int(result.get('retCode', 1))
            ret_msg = result.get('retMsg', 'Unknown')

            print(f"Response:")
            print(f"  retCode: {ret_code}")
            print(f"  retMsg: {ret_msg}")
            print()

            if ret_code == 0:
                print("⚠️  UNEXPECTED: SL was set without position!")
                print("     This means SL might NOT be position-attached!")
            else:
                print(f"✅ EXPECTED: API rejected SL (no position)")
                print(f"   Error code: {ret_code}")

        except Exception as e:
            print(f"✅ EXPECTED: Exception raised")
            print(f"   Error: {e}")

        print()
        print("="*80)
        print("ANALYSIS")
        print("="*80)
        print()
        print("If retCode != 0:")
        print("  → SL is position-attached ✅")
        print("  → Cannot set SL without position ✅")
        print("  → No margin consumed ✅")
        print()
        print("If retCode == 0:")
        print("  → SL might be standalone order ⚠️")
        print("  → Could consume margin/USDT ⚠️")
        print("  → Need further investigation ⚠️")

    finally:
        await exchange.close()


async def test_sl_with_position():
    """
    Test setting SL WITH position
    Check margin before and after
    """
    print()
    print()
    print("="*80)
    print("🔬 TEST: Setting SL with position + margin check")
    print("="*80)
    print()

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

    try:
        await exchange.load_markets()

        symbol = 'BTC/USDT:USDT'
        bybit_symbol = 'BTCUSDT'

        # Get initial balance
        balance_before = await exchange.fetch_balance()
        free_before = balance_before['USDT']['free']
        used_before = balance_before['USDT']['used']

        print(f"Balance BEFORE position:")
        print(f"  Free: ${free_before:.2f}")
        print(f"  Used: ${used_before:.2f}")
        print()

        # Create small position
        ticker = await exchange.fetch_ticker(symbol)
        price = ticker['last']

        market = exchange.markets[symbol]
        min_amount = market['limits']['amount']['min']
        quantity = exchange.amount_to_precision(symbol, min_amount)

        print(f"Creating position: {symbol}")
        print(f"  Quantity: {quantity}")
        print(f"  Price: ~${price}")
        print()

        order = await exchange.create_market_order(
            symbol=symbol,
            side='buy',
            amount=quantity
        )

        print(f"✅ Position opened: {order.get('id')}")
        print()

        # Wait for position to be visible
        await asyncio.sleep(2)

        # Get balance after position
        balance_after_position = await exchange.fetch_balance()
        free_after_position = balance_after_position['USDT']['free']
        used_after_position = balance_after_position['USDT']['used']

        print(f"Balance AFTER position:")
        print(f"  Free: ${free_after_position:.2f} (Δ {free_after_position - free_before:+.2f})")
        print(f"  Used: ${used_after_position:.2f} (Δ {used_after_position - used_before:+.2f})")
        print()

        # Set SL
        sl_price = price * 0.98
        sl_price = exchange.price_to_precision(symbol, sl_price)

        params = {
            'category': 'linear',
            'symbol': bybit_symbol,
            'stopLoss': str(sl_price),
            'positionIdx': 0,
            'slTriggerBy': 'LastPrice',
            'tpslMode': 'Full'
        }

        print(f"Setting SL at ${sl_price}")
        result = await exchange.private_post_v5_position_trading_stop(params)

        ret_code = int(result.get('retCode', 1))
        if ret_code == 0:
            print(f"✅ SL set successfully")
        else:
            print(f"❌ SL failed: {result.get('retMsg')}")

        print()

        # Get balance after SL
        balance_after_sl = await exchange.fetch_balance()
        free_after_sl = balance_after_sl['USDT']['free']
        used_after_sl = balance_after_sl['USDT']['used']

        print(f"Balance AFTER SL:")
        print(f"  Free: ${free_after_sl:.2f} (Δ {free_after_sl - free_after_position:+.2f})")
        print(f"  Used: ${used_after_sl:.2f} (Δ {used_after_sl - used_after_position:+.2f})")
        print()

        print("="*80)
        print("MARGIN ANALYSIS")
        print("="*80)
        print()

        if abs(free_after_sl - free_after_position) < 0.01:
            print("✅ FREE balance unchanged after SL")
            print("   → SL does NOT consume free USDT ✅")
        else:
            print(f"⚠️  FREE balance changed: {free_after_sl - free_after_position:+.2f}")
            print("   → SL might consume free USDT ⚠️")

        print()

        if abs(used_after_sl - used_after_position) < 0.01:
            print("✅ USED balance unchanged after SL")
            print("   → SL does NOT require additional margin ✅")
        else:
            print(f"⚠️  USED balance changed: {used_after_sl - used_after_position:+.2f}")
            print("   → SL might require additional margin ⚠️")

        # Cleanup
        print()
        print("="*80)
        print("CLEANUP")
        print("="*80)

        close_order = await exchange.create_market_order(
            symbol=symbol,
            side='sell',
            amount=quantity
        )
        print(f"✅ Position closed: {close_order.get('id')}")

    finally:
        await exchange.close()


if __name__ == "__main__":
    asyncio.run(test_sl_without_position())
    asyncio.run(test_sl_with_position())
