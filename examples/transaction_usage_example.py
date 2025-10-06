"""
Example: Using Database Transactions in Position Management

This example demonstrates how to use transactions to ensure atomicity
of database operations when opening a position.

WITHOUT TRANSACTIONS (риск inconsistency):
    1. create_trade() ✅ успех
    2. create_position() ❌ падает
    → Result: Trade записан, но Position НЕТ → INCONSISTENT STATE

WITH TRANSACTIONS (atomic):
    1. BEGIN TRANSACTION
    2. create_trade() ✅ успех  
    3. create_position() ❌ падает
    4. ROLLBACK
    → Result: Оба отменены → CONSISTENT STATE
"""
import asyncio
from database.repository import Repository
from decimal import Decimal


async def example_without_transaction():
    """
    BAD PRACTICE: Without transaction (can lead to inconsistent state)
    """
    repo = Repository({
        'host': 'localhost',
        'port': 5433,
        'database': 'fox_crypto',
        'user': 'elcrypto',
        'password': 'password'
    })
    
    await repo.initialize()
    
    try:
        # Step 1: Create trade
        trade_id = await repo.create_trade({
            'symbol': 'BTC/USDT',
            'exchange': 'binance',
            'side': 'buy',
            'quantity': 0.001,
            'price': 50000.0,
            'order_id': '12345',
            'status': 'FILLED'
        })
        print(f"✅ Trade created: {trade_id}")
        
        # Step 2: Create position
        # ❌ If this fails, we have a trade without a position!
        position_id = await repo.create_position({
            'symbol': 'BTC/USDT',
            'exchange': 'binance',
            'side': 'long',
            'quantity': 0.001,
            'entry_price': 50000.0
        })
        print(f"✅ Position created: {position_id}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print("⚠️  Trade might be created but position is NOT - INCONSISTENT!")
    finally:
        await repo.close()


async def example_with_transaction():
    """
    GOOD PRACTICE: With transaction (atomic operation)
    """
    repo = Repository({
        'host': 'localhost',
        'port': 5433,
        'database': 'fox_crypto',
        'user': 'elcrypto',
        'password': 'password'
    })
    
    await repo.initialize()
    
    try:
        # Use transaction context manager
        async with repo.transaction() as conn:
            # Step 1: Create trade (with connection)
            trade_id = await repo.create_trade({
                'symbol': 'BTC/USDT',
                'exchange': 'binance',
                'side': 'buy',
                'quantity': 0.001,
                'price': 50000.0,
                'order_id': '12345',
                'status': 'FILLED'
            }, conn=conn)  # ← Pass connection
            print(f"✅ Trade created: {trade_id}")
            
            # Step 2: Create position (with same connection)
            position_id = await repo.create_position({
                'symbol': 'BTC/USDT',
                'exchange': 'binance',
                'side': 'long',
                'quantity': 0.001,
                'entry_price': 50000.0
            }, conn=conn)  # ← Pass same connection
            print(f"✅ Position created: {position_id}")
            
            # Step 3: Update position with stop loss (optional)
            await repo.update_position_stop_loss(
                position_id,
                stop_price=48000.0,
                order_id='sl_12345',
                conn=conn  # ← Pass same connection
            )
            print(f"✅ Stop loss updated")
            
            # If ANY of these fails, ALL are rolled back!
            # Transaction commits automatically at end of 'with' block
            
    except Exception as e:
        print(f"❌ Error: {e}")
        print("✅ All operations rolled back - DATABASE IS CONSISTENT!")
    finally:
        await repo.close()


async def example_position_manager_integration():
    """
    Example: How to integrate transactions into PositionManager.open_position()
    
    This is how you would modify core/position_manager.py:open_position()
    to use transactions for atomicity.
    """
    print("\n" + "="*70)
    print("RECOMMENDED IMPLEMENTATION IN PositionManager:")
    print("="*70)
    print("""
async def open_position(self, request: PositionRequest):
    '''
    Open new position with transaction support for atomicity.
    '''
    symbol = request.symbol
    exchange_name = request.exchange.lower()
    db_lock_acquired = False
    
    # ... (lock acquisition code) ...
    
    try:
        # ... (validation, order execution) ...
        
        # ✅ ATOMIC DATABASE OPERATIONS
        async with self.repository.transaction() as conn:
            # Step 1: Create trade record
            trade_id = await self.repository.create_trade({
                'symbol': symbol,
                'exchange': exchange_name,
                'side': order_side,
                'quantity': order.amount,
                'price': order.price,
                'executed_qty': order.filled,
                'order_id': order.id,
                'status': 'FILLED'
            }, conn=conn)  # ← Transaction mode
            
            # Step 2: Create position record
            position_id = await self.repository.create_position({
                'trade_id': trade_id,
                'symbol': symbol,
                'exchange': exchange_name,
                'side': position.side,
                'quantity': position.quantity,
                'entry_price': position.entry_price
            }, conn=conn)  # ← Same transaction
            
            position.id = position_id
            
            # Step 3: Set stop loss in DB
            if stop_loss_order_id:
                await self.repository.update_position_stop_loss(
                    position_id, 
                    stop_loss_price, 
                    stop_loss_order_id,
                    conn=conn  # ← Same transaction
                )
            
            # If ANY of these fail → ALL are rolled back automatically!
            # If all succeed → Transaction commits automatically
        
        # Transaction committed - continue with in-memory updates
        self.positions[symbol] = position
        logger.info(f"✅ Position opened with atomic DB operations")
        
        return position
        
    except Exception as e:
        logger.error(f"Error opening position: {e}")
        # Transaction already rolled back automatically
        return None
    finally:
        # ... (lock release) ...
""")


if __name__ == '__main__':
    print("="*70)
    print("DATABASE TRANSACTION EXAMPLES")
    print("="*70)
    
    # Uncomment to run examples:
    # asyncio.run(example_without_transaction())
    # asyncio.run(example_with_transaction())
    
    asyncio.run(example_position_manager_integration())

