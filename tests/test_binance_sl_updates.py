#!/usr/bin/env python3
"""
Integration test: Multiple Binance SL updates to verify orphan order handling
"""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import config as settings
from core.exchange_manager import ExchangeManager

async def test_multiple_sl_updates():
    """
    Test scenario:
    1. Create initial SL order
    2. Update SL 3 times rapidly
    3. Verify no orphan orders remain
    """
    print("=" * 80)
    print("BINANCE SL UPDATE ORPHAN TEST")
    print("=" * 80)
    print()

    # Initialize Binance exchange
    binance_config = settings.exchanges.get('binance')
    if not binance_config:
        print("❌ Binance not configured")
        return False

    exchange = ExchangeManager('binance', {
        'api_key': binance_config.api_key,
        'api_secret': binance_config.api_secret,
        'testnet': binance_config.testnet
    })
    await exchange.initialize()

    test_symbol = 'BTCUSDT'
    position_side = 'long'

    # Test sequence of SL updates
    sl_prices = [50000.0, 50100.0, 50200.0]

    for i, sl_price in enumerate(sl_prices, 1):
        print(f"TEST {i}: Updating SL to {sl_price}...")

        result = await exchange.update_stop_loss_atomic(
            symbol=test_symbol,
            new_sl_price=sl_price,
            position_side=position_side
        )

        if result['success']:
            print(f"✅ SL updated: {result['method']}, {result['execution_time_ms']:.2f}ms")
            if result.get('orders_cancelled'):
                print(f"   Cancelled {result['orders_cancelled']} order(s)")
        else:
            print(f"❌ SL update failed: {result['error']}")

        print()
        await asyncio.sleep(1)  # Small delay between updates

    # Verify: Check if any orphan SL orders remain
    print("VERIFICATION: Checking for orphan SL orders...")
    orders = await exchange.exchange.fetch_open_orders(test_symbol)

    sl_orders = [
        o for o in orders
        if o.get('type', '').upper() == 'STOP_MARKET'
        and o.get('reduceOnly', False)
    ]

    print(f"Found {len(sl_orders)} SL order(s):")
    for order in sl_orders:
        print(f"  - Order {order['id'][:8]}...: stopPrice={order.get('stopPrice')}")

    if len(sl_orders) == 1:
        print("✅ TEST PASSED: Exactly 1 SL order (no orphans)")
        return True
    elif len(sl_orders) > 1:
        print(f"❌ TEST FAILED: {len(sl_orders)} SL orders found (orphans detected!)")
        return False
    else:
        print("⚠️  TEST INCONCLUSIVE: No SL orders found (position may not exist)")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_multiple_sl_updates())
    sys.exit(0 if result else 1)
