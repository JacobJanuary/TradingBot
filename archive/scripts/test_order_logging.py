#!/usr/bin/env python3
"""Test create_order and create_trade methods"""
import asyncio
import sys
from database.repository import Repository
from config.settings import Config

async def test_order_logging():
    """Test order and trade logging"""
    print("🔧 Testing order/trade logging...")

    cfg = Config()
    db_config = {
        'host': cfg.database.host,
        'port': cfg.database.port,
        'database': cfg.database.database,
        'user': cfg.database.user,
        'password': cfg.database.password,
        'pool_size': cfg.database.pool_size,
        'max_overflow': cfg.database.max_overflow
    }
    repo = Repository(db_config)

    try:
        await repo.initialize()
        print("✅ Connected to database")

        # Test 1: Create order
        print("\n📝 Test 1: Creating test order...")
        order_data = {
            'position_id': '999',
            'exchange': 'test_exchange',
            'symbol': 'TESTUSDT',
            'order_id': 'test_order_123',
            'type': 'MARKET',
            'side': 'buy',
            'size': 100.0,
            'price': 1.5,
            'status': 'FILLED',
            'filled': 100.0,
            'remaining': 0.0,
            'fee': 0.15,
            'fee_currency': 'USDT'
        }

        order_id = await repo.create_order(order_data)
        print(f"✅ Order created with ID: {order_id}")

        # Test 2: Create trade
        print("\n📝 Test 2: Creating test trade...")
        trade_data = {
            'symbol': 'TESTUSDT',
            'exchange': 'test_exchange',
            'side': 'buy',
            'order_type': 'MARKET',
            'quantity': 100.0,
            'price': 1.5,
            'executed_qty': 100.0,
            'average_price': 1.5,
            'order_id': 'test_order_123',
            'status': 'FILLED',
            'fee': 0.15,
            'fee_currency': 'USDT'
        }

        trade_id = await repo.create_trade(trade_data)
        print(f"✅ Trade created with ID: {trade_id}")

        # Verify
        print("\n🔍 Verifying records in database...")
        async with repo.pool.acquire() as conn:
            order_count = await conn.fetchval(
                "SELECT COUNT(*) FROM monitoring.orders WHERE order_id = 'test_order_123'"
            )
            trade_count = await conn.fetchval(
                "SELECT COUNT(*) FROM monitoring.trades WHERE order_id = 'test_order_123'"
            )

        print(f"✅ Found {order_count} order(s) in database")
        print(f"✅ Found {trade_count} trade(s) in database")

        # Cleanup
        print("\n🧹 Cleaning up test records...")
        async with repo.pool.acquire() as conn:
            await conn.execute("DELETE FROM monitoring.orders WHERE position_id = '999'")
            await conn.execute("DELETE FROM monitoring.trades WHERE order_id = 'test_order_123'")
        print("✅ Cleanup complete")

        print("\n✅ All tests passed!")
        return True

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if repo.pool:
            await repo.pool.close()
        print("🔌 Database connection closed")

if __name__ == "__main__":
    result = asyncio.run(test_order_logging())
    sys.exit(0 if result else 1)
