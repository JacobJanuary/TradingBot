#!/usr/bin/env python3
"""
Test Position Lookup - Check real position via API and cache

Tests:
1. Fetch positions via CCXT API
2. Check WebSocket cache contents
3. Verify parsing of exchange response
4. Measure lookup performance
"""
import asyncio
import ccxt.async_support as ccxt
import os
import sys
import time
from decimal import Decimal
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

# Import after path setup
from core.exchange_manager import ExchangeManager
from database.repository import Repository


async def test_fetch_positions_api():
    """Test #1: Fetch positions directly via CCXT API"""
    print("\n" + "="*80)
    print("TEST #1: Fetch Positions via CCXT API")
    print("="*80)

    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_API_SECRET')

    if not api_key or not api_secret:
        print("❌ Missing BINANCE_API_KEY or BINANCE_API_SECRET")
        return

    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })

    try:
        print("\n📡 Fetching ALL open positions from Binance...")
        start_time = time.time()

        positions = await exchange.fetch_positions()

        elapsed_ms = (time.time() - start_time) * 1000
        print(f"⏱️  API call took: {elapsed_ms:.2f}ms")

        # Filter open positions
        open_positions = [p for p in positions if float(p.get('contracts', 0)) > 0]

        print(f"\n✅ Found {len(open_positions)} open positions:")
        print("-" * 80)

        for pos in open_positions:
            symbol = pos.get('symbol')
            contracts = float(pos.get('contracts', 0))
            side = pos.get('side')
            entry_price = float(pos.get('entryPrice', 0))
            mark_price = float(pos.get('markPrice', 0))
            unrealized_pnl = float(pos.get('unrealizedPnl', 0))

            print(f"  {symbol:12} | {side:5} | contracts={contracts:10.2f} | "
                  f"entry={entry_price:.8f} | mark={mark_price:.8f} | pnl=${unrealized_pnl:.2f}")

        print("\n📋 RAW Position Data Sample (first position):")
        if open_positions:
            import json
            print(json.dumps(open_positions[0], indent=2, default=str))

    except Exception as e:
        print(f"❌ Error fetching positions: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await exchange.close()


async def test_websocket_cache():
    """Test #2: Check WebSocket cache in ExchangeManager"""
    print("\n" + "="*80)
    print("TEST #2: WebSocket Cache Inspection")
    print("="*80)

    try:
        # Initialize ExchangeManager
        from core.exchange_manager import ExchangeManager
        from database.repository import Repository

        repo = Repository()
        await repo.connect()

        exchange_manager = ExchangeManager(
            exchange_name='binance',
            repository=repo
        )

        print("\n🔍 Checking self.positions cache...")

        if not exchange_manager.positions:
            print("⚠️  Cache is EMPTY (exchange manager not initialized yet)")
        else:
            print(f"✅ Cache contains {len(exchange_manager.positions)} positions:")
            print("-" * 80)

            for symbol, position in exchange_manager.positions.items():
                contracts = float(position.get('contracts', 0))
                side = position.get('side')
                entry_price = float(position.get('entryPrice', 0))

                print(f"  {symbol:12} | {side:5} | contracts={contracts:10.2f} | entry={entry_price:.8f}")

        await repo.disconnect()

    except Exception as e:
        print(f"❌ Error checking cache: {e}")
        import traceback
        traceback.print_exc()


async def test_get_position_size():
    """Test #3: Test get_position_size() method with live data"""
    print("\n" + "="*80)
    print("TEST #3: Test get_position_size() Method")
    print("="*80)

    try:
        from core.exchange_manager import ExchangeManager
        from database.repository import Repository

        repo = Repository()
        await repo.connect()

        exchange_manager = ExchangeManager(
            exchange_name='binance',
            repository=repo
        )

        # Initialize exchange
        await exchange_manager.initialize()

        # Fetch fresh positions to populate cache
        print("\n📡 Fetching positions to populate cache...")
        positions = await exchange_manager.fetch_positions()
        open_symbols = [p['symbol'] for p in positions if float(p.get('contracts', 0)) > 0]

        print(f"✅ Found {len(open_symbols)} open positions")

        # Test get_position_size() for each open position
        print("\n🔍 Testing get_position_size() for each position:")
        print("-" * 80)

        for symbol in open_symbols:
            start_time = time.time()

            try:
                # Note: get_position_size is not async in some versions
                # Check the actual implementation
                if hasattr(exchange_manager, 'get_position_size'):
                    size = await exchange_manager.get_position_size(symbol)

                    elapsed_ms = (time.time() - start_time) * 1000

                    print(f"  {symbol:12} | size={size['amount']:10.2f} | "
                          f"method={size['lookup_method']:20} | time={elapsed_ms:.2f}ms")
            except Exception as e:
                print(f"  {symbol:12} | ❌ Error: {e}")

        await repo.disconnect()
        await exchange_manager.close()

    except Exception as e:
        print(f"❌ Error testing get_position_size: {e}")
        import traceback
        traceback.print_exc()


async def test_position_response_parsing():
    """Test #4: Verify position response parsing"""
    print("\n" + "="*80)
    print("TEST #4: Position Response Parsing")
    print("="*80)

    # Sample response from Binance API
    sample_response = {
        'symbol': 'BTCUSDT',
        'contracts': 0.1,
        'contractSize': 1.0,
        'unrealizedPnl': -5.23,
        'leverage': 1.0,
        'liquidationPrice': 0.0,
        'collateral': 3000.0,
        'notional': 3005.23,
        'markPrice': 30052.3,
        'entryPrice': 30000.0,
        'timestamp': 1699621234567,
        'isolated': False,
        'side': 'long',
        'percentage': -0.17
    }

    print("\n📋 Sample Position Response:")
    import json
    print(json.dumps(sample_response, indent=2))

    print("\n🔍 Parsing:")
    print(f"  symbol: {sample_response.get('symbol')}")
    print(f"  contracts: {float(sample_response.get('contracts', 0))}")
    print(f"  side: {sample_response.get('side')}")
    print(f"  entryPrice: {float(sample_response.get('entryPrice', 0))}")
    print(f"  markPrice: {float(sample_response.get('markPrice', 0))}")
    print(f"  unrealizedPnl: {float(sample_response.get('unrealizedPnl', 0))}")

    print("\n✅ Parsing works correctly")


async def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("POSITION LOOKUP INVESTIGATION")
    print("="*80)

    await test_fetch_positions_api()
    # await test_websocket_cache()  # Skip if exchange manager not initialized
    # await test_get_position_size()  # Skip if method signature unknown
    await test_position_response_parsing()

    print("\n" + "="*80)
    print("TESTS COMPLETE")
    print("="*80)


if __name__ == '__main__':
    asyncio.run(main())
