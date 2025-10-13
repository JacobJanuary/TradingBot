#!/usr/bin/env python3
"""Test manual quantity update"""

import asyncio
import asyncpg
from dotenv import load_dotenv
import os
from database.repository import Repository

async def test_manual_update():
    load_dotenv()

    # DB config
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', '5433')),
        'database': os.getenv('DB_NAME', 'fox_crypto_test'),
        'user': os.getenv('DB_USER', 'elcrypto'),
        'password': os.getenv('DB_PASSWORD')
    }

    # Create repository and initialize
    repo = Repository(db_config)
    await repo.initialize()

    pool = repo.pool

    try:
        # Find any active position
        async with pool.acquire() as conn:
            position = await conn.fetchrow("""
                SELECT id, symbol, quantity, entry_price, current_price, unrealized_pnl
                FROM monitoring.positions
                WHERE status = 'active'
                LIMIT 1
            """)

        if not position:
            print("❌ No active positions found for testing")
            return

        print("="*80)
        print("TESTING MANUAL QUANTITY UPDATE")
        print("="*80)

        pos_id = position['id']
        old_qty = float(position['quantity'])
        old_entry_price = float(position['entry_price'] or 0)
        old_price = float(position['current_price'] or 0)
        old_pnl = float(position['unrealized_pnl'] or 0)

        print(f"\n📊 Position BEFORE update:")
        print(f"  ID: {pos_id}")
        print(f"  Symbol: {position['symbol']}")
        print(f"  Quantity: {old_qty}")
        print(f"  Entry Price: {old_entry_price}")
        print(f"  Current Price: {old_price}")
        print(f"  Unrealized PnL: {old_pnl}")

        # Test update with new values
        new_qty = old_qty + 1.0  # Increase by 1 for testing
        new_price = old_price + 0.01  # Increase price slightly
        new_pnl = old_pnl + 0.5  # Increase PnL slightly

        print(f"\n🔄 Updating position...")
        print(f"  New Quantity: {new_qty}")
        print(f"  New Current Price: {new_price}")
        print(f"  New Unrealized PnL: {new_pnl}")

        result = await repo.update_position(
            position_id=pos_id,
            quantity=new_qty,
            current_price=new_price,
            unrealized_pnl=new_pnl
        )

        print(f"  Update result: {result}")

        # Verify update
        async with pool.acquire() as conn:
            updated = await conn.fetchrow("""
                SELECT quantity, entry_price, current_price, unrealized_pnl
                FROM monitoring.positions
                WHERE id = $1
            """, pos_id)

        print(f"\n📊 Position AFTER update:")
        print(f"  Quantity: {float(updated['quantity'])}")
        print(f"  Entry Price: {float(updated['entry_price'] or 0)}")
        print(f"  Current Price: {float(updated['current_price'] or 0)}")
        print(f"  Unrealized PnL: {float(updated['unrealized_pnl'] or 0)}")

        # Verify values
        print(f"\n🧪 Verification:")
        success = True

        # Check quantity updated
        if abs(float(updated['quantity']) - new_qty) > 0.001:
            print(f"  ❌ FAIL: Quantity not updated correctly")
            print(f"     Expected: {new_qty}, Got: {float(updated['quantity'])}")
            success = False
        else:
            print(f"  ✅ Quantity updated correctly")

        # Check entry_price NOT changed (immutability test)
        if abs(float(updated['entry_price'] or 0) - old_entry_price) > 0.001:
            print(f"  ❌ CRITICAL FAIL: Entry price changed (should be immutable)!")
            print(f"     Expected: {old_entry_price}, Got: {float(updated['entry_price'] or 0)}")
            success = False
        else:
            print(f"  ✅ Entry price unchanged (immutability preserved)")

        # Check current_price updated
        if abs(float(updated['current_price'] or 0) - new_price) > 0.001:
            print(f"  ❌ FAIL: Current price not updated correctly")
            print(f"     Expected: {new_price}, Got: {float(updated['current_price'] or 0)}")
            success = False
        else:
            print(f"  ✅ Current price updated correctly")

        # Check unrealized_pnl updated
        if abs(float(updated['unrealized_pnl'] or 0) - new_pnl) > 0.001:
            print(f"  ❌ FAIL: Unrealized PnL not updated correctly")
            print(f"     Expected: {new_pnl}, Got: {float(updated['unrealized_pnl'] or 0)}")
            success = False
        else:
            print(f"  ✅ Unrealized PnL updated correctly")

        if success:
            print(f"\n✅ SUCCESS: All tests passed!")
        else:
            print(f"\n❌ FAILURE: Some tests failed")

        # Restore original values
        print(f"\n♻️  Restoring original values...")
        await repo.update_position(
            position_id=pos_id,
            quantity=old_qty,
            current_price=old_price,
            unrealized_pnl=old_pnl
        )
        print(f"  ✅ Restored")

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await pool.close()

if __name__ == '__main__':
    asyncio.run(test_manual_update())
