#!/usr/bin/env python3
"""Test order response format after CCXT upgrade"""
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from config.settings import Config
from core.exchange_manager import ExchangeManager
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_order_response():
    """Test order response structure"""
    print("=" * 100)
    print("TEST: Order Response Format After CCXT 4.5.12")
    print("=" * 100)
    print()

    config = Config()
    bybit_config_obj = config.get_exchange_config('bybit')

    if not bybit_config_obj:
        print("❌ Bybit config not found")
        return

    bybit_config = {
        'api_key': bybit_config_obj.api_key,
        'api_secret': bybit_config_obj.api_secret,
        'testnet': bybit_config_obj.testnet,
        'rate_limit': True
    }

    exchange_mgr = ExchangeManager(
        exchange_name='bybit',
        config=bybit_config,
        repository=None
    )

    try:
        # Fetch recent order to see response structure
        print("Fetching recent closed orders...")

        orders = await exchange_mgr.exchange.fetch_closed_orders(
            limit=1,
            params={'category': 'linear'}
        )

        if orders:
            order = orders[0]
            print(f"\nOrder response structure:")
            print(f"  Symbol: {order.get('symbol')}")
            print(f"  Side: {order.get('side')}")
            print(f"  Amount: {order.get('amount')}")
            print(f"  Filled: {order.get('filled')}")

            # Check fee field
            fee = order.get('fee')
            if fee:
                print(f"  Fee: {fee}")
                print(f"    Type: {type(fee)}")
                if isinstance(fee, dict):
                    print(f"    Keys: {fee.keys()}")
                    print(f"    ✅ Fee is dict (expected)")
                else:
                    print(f"    ⚠️ Fee is {type(fee)}, not dict!")
            else:
                print(f"  Fee: None")

            # Check info
            info = order.get('info', {})
            print(f"\n  info fields:")
            for key in ['cumExecQty', 'cumExecValue', 'cumExecFee', 'avgPrice']:
                val = info.get(key, 'NOT FOUND')
                print(f"    {key}: {val}")

            print(f"\n✅ Order response structure verified")
        else:
            print("ℹ️  No closed orders found")

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        raise

    finally:
        await exchange_mgr.close()


if __name__ == '__main__':
    asyncio.run(test_order_response())
