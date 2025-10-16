#!/usr/bin/env python3
"""
Тестовое создание позиции для проверки логирования orders/trades
ВНИМАНИЕ: Создаст РЕАЛЬНУЮ позицию на бирже с минимальным размером!
"""
import asyncio
import sys
from config.settings import Config
from database.repository import Repository
from core.exchange_manager import ExchangeManager
from core.stop_loss_manager import StopLossManager
from core.atomic_position_manager import AtomicPositionManager

async def create_test_position():
    """Создать тестовую позицию для проверки логирования"""
    print("🧪 Creating test position to verify orders/trades logging...\n")

    # Initialize components
    cfg = Config()

    # Database
    db_config = {
        'host': cfg.database.host,
        'port': cfg.database.port,
        'database': cfg.database.database,
        'user': cfg.database.user,
        'password': cfg.database.password,
        'pool_size': cfg.database.pool_size,
        'max_overflow': cfg.database.max_overflow
    }
    repository = Repository(db_config)
    await repository.initialize()
    print("✅ Database connected")

    # Exchange Manager
    exchange_manager = ExchangeManager(cfg.exchanges)
    await exchange_manager.initialize()
    print("✅ Exchange Manager initialized")

    # Stop Loss Manager
    stop_loss_manager = StopLossManager(exchange_manager, repository)
    print("✅ Stop Loss Manager initialized")

    # Atomic Position Manager
    atomic_manager = AtomicPositionManager(repository, exchange_manager, stop_loss_manager)
    print("✅ Atomic Position Manager initialized\n")

    # Test position parameters (MINIMAL size to minimize cost)
    test_params = {
        'signal_id': 999999,  # Test signal ID
        'symbol': 'BTCUSDT',  # Liquid symbol
        'exchange': 'binance',  # Or 'bybit'
        'side': 'buy',
        'quantity': 0.001,  # MINIMAL BTC amount (~$90)
        'entry_price': 0.0,  # Market price
        'stop_loss_price': 0.0  # Will be calculated
    }

    # Get current price
    exchange = exchange_manager.get_exchange(test_params['exchange'])
    ticker = await exchange.fetch_ticker(test_params['symbol'])
    current_price = ticker['last']

    test_params['entry_price'] = current_price
    test_params['stop_loss_price'] = current_price * 0.98  # 2% SL

    print(f"📊 Test Position Parameters:")
    print(f"   Symbol: {test_params['symbol']}")
    print(f"   Exchange: {test_params['exchange']}")
    print(f"   Side: {test_params['side']}")
    print(f"   Quantity: {test_params['quantity']}")
    print(f"   Entry Price: {test_params['entry_price']}")
    print(f"   Stop Loss: {test_params['stop_loss_price']}")
    print(f"   Estimated Cost: ${current_price * test_params['quantity']:.2f}\n")

    # Ask for confirmation
    confirm = input("⚠️  This will create a REAL position on the exchange. Continue? (yes/no): ")
    if confirm.lower() != 'yes':
        print("❌ Cancelled by user")
        await repository.pool.close()
        await exchange_manager.close()
        return False

    try:
        print("\n🚀 Creating position...")
        result = await atomic_manager.open_position_atomic(
            signal_id=test_params['signal_id'],
            symbol=test_params['symbol'],
            exchange=test_params['exchange'],
            side=test_params['side'],
            quantity=test_params['quantity'],
            entry_price=test_params['entry_price'],
            stop_loss_price=test_params['stop_loss_price']
        )

        if result:
            position_id = result.get('position_id')
            print(f"\n✅ Position created successfully!")
            print(f"   Position ID: {position_id}")

            # Check database
            print(f"\n🔍 Checking database records...")

            # Check orders
            async with repository.pool.acquire() as conn:
                orders = await conn.fetch(
                    "SELECT id, type, side, status FROM monitoring.orders WHERE position_id = $1",
                    str(position_id)
                )
                print(f"\n📋 Orders table ({len(orders)} records):")
                for order in orders:
                    print(f"   - ID:{order['id']}, Type:{order['type']}, Side:{order['side']}, Status:{order['status']}")

                # Check trades
                trades = await conn.fetch(
                    "SELECT id, side, order_type, status FROM monitoring.trades WHERE order_id IN (SELECT order_id FROM monitoring.orders WHERE position_id = $1)",
                    str(position_id)
                )
                print(f"\n📋 Trades table ({len(trades)} records):")
                for trade in trades:
                    print(f"   - ID:{trade['id']}, Side:{trade['side']}, Type:{trade['order_type']}, Status:{trade['status']}")

            if len(orders) > 0 and len(trades) > 0:
                print("\n✅✅✅ SUCCESS! Orders and Trades logging works! ✅✅✅")
                return True
            else:
                print("\n❌ FAILED: No orders/trades logged!")
                return False
        else:
            print("\n❌ Position creation failed")
            return False

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await repository.pool.close()
        await exchange_manager.close()
        print("\n🔌 Connections closed")

if __name__ == "__main__":
    result = asyncio.run(create_test_position())
    sys.exit(0 if result else 1)
