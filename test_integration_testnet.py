"""
Integration test for Trailing Stop SL update methods on testnet
Tests with REAL positions on Bybit and Binance testnet
"""
import asyncio
import os
import sys
from decimal import Decimal
import ccxt.async_support as ccxt
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import config
from core.exchange_manager import ExchangeManager
from utils.rate_limiter import RateLimiter, RateLimitConfig

async def check_bybit_testnet():
    """Check Bybit testnet balance and positions"""
    print("\n" + "="*80)
    print("BYBIT TESTNET - Status Check")
    print("="*80)

    # Get credentials (same as production but testnet=true)
    api_key = os.getenv('BYBIT_API_KEY')
    api_secret = os.getenv('BYBIT_API_SECRET')

    if not api_key or not api_secret:
        print("❌ Bybit credentials not found in .env")
        return None

    # Create exchange
    exchange = ccxt.bybit({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'swap',
            'testnet': True
        }
    })

    try:
        # Check balance
        balance = await exchange.fetch_balance()
        usdt_balance = balance.get('USDT', {})
        total = usdt_balance.get('total', 0) or usdt_balance.get('free', 0)

        print(f"💰 Balance: {total} USDT")

        # Check positions
        positions = await exchange.fetch_positions()
        open_positions = [p for p in positions if float(p.get('contracts', 0)) > 0]

        print(f"📊 Open positions: {len(open_positions)}")

        if open_positions:
            print("\n📋 Positions:")
            for pos in open_positions[:5]:  # Show first 5
                symbol = pos['symbol']
                side = pos['side']
                size = pos['contracts']
                entry = pos['entryPrice']
                current = pos['markPrice']

                print(f"   {symbol}: {side} {size} @ {entry} (current: {current})")

        await exchange.close()
        return {
            'balance': total,
            'positions': open_positions
        }

    except Exception as e:
        print(f"❌ Error: {e}")
        await exchange.close()
        return None

async def check_binance_testnet():
    """Check Binance testnet balance and positions"""
    print("\n" + "="*80)
    print("BINANCE TESTNET - Status Check")
    print("="*80)

    # Get credentials (same as production but testnet=true)
    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_API_SECRET')

    if not api_key or not api_secret:
        print("❌ Binance credentials not found in .env")
        return None

    # Create exchange
    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
            'testnet': True
        }
    })

    try:
        # Check balance
        balance = await exchange.fetch_balance()
        usdt_balance = balance.get('USDT', {})
        total = usdt_balance.get('total', 0) or usdt_balance.get('free', 0)

        print(f"💰 Balance: {total} USDT")

        # Check positions
        positions = await exchange.fetch_positions()
        open_positions = [p for p in positions if float(p.get('contracts', 0)) > 0]

        print(f"📊 Open positions: {len(open_positions)}")

        if open_positions:
            print("\n📋 Positions:")
            for pos in open_positions[:5]:  # Show first 5
                symbol = pos['symbol']
                side = pos['side']
                size = pos['contracts']
                entry = pos['entryPrice']
                current = pos['markPrice']

                print(f"   {symbol}: {side} {size} @ {entry} (current: {current})")

        await exchange.close()
        return {
            'balance': total,
            'positions': open_positions
        }

    except Exception as e:
        print(f"❌ Error: {e}")
        await exchange.close()
        return None

async def test_bybit_atomic_update():
    """Test Bybit atomic SL update with real position"""
    print("\n" + "="*80)
    print("TEST: Bybit Atomic SL Update")
    print("="*80)

    # Check if we have positions
    bybit_status = await check_bybit_testnet()
    if not bybit_status or not bybit_status['positions']:
        print("❌ No open positions on Bybit testnet")
        print("💡 Suggestion: Open a small position manually for testing")
        return False

    # Select first position
    position = bybit_status['positions'][0]
    symbol = position['symbol']
    current_price = float(position['markPrice'])
    entry_price = float(position['entryPrice'])
    side = position['side']

    print(f"\n📊 Testing with position:")
    print(f"   Symbol: {symbol}")
    print(f"   Side: {side}")
    print(f"   Entry: {entry_price}")
    print(f"   Current: {current_price}")

    # Create ExchangeManager
    exchange_config = {
        'api_key': os.getenv('BYBIT_API_KEY'),
        'api_secret': os.getenv('BYBIT_API_SECRET'),
        'testnet': True
    }

    exchange_manager = ExchangeManager(
        exchange_name='bybit',
        config=exchange_config
    )

    await exchange_manager.initialize()

    try:
        # Calculate new SL price (5% below current for long, 5% above for short)
        if side.lower() == 'long':
            new_sl_price = current_price * 0.95
        else:
            new_sl_price = current_price * 1.05

        print(f"\n🔄 Updating SL to {new_sl_price:.4f} (5% from current)")

        # Call atomic update
        start_time = datetime.now()
        result = await exchange_manager.update_stop_loss_atomic(
            symbol=symbol,
            new_sl_price=new_sl_price,
            position_side=side.lower()
        )
        execution_time = (datetime.now() - start_time).total_seconds() * 1000

        print(f"\n✅ Result:")
        print(f"   Success: {result['success']}")
        print(f"   Method: {result['method']}")
        print(f"   Execution time: {result['execution_time_ms']:.2f}ms (measured: {execution_time:.2f}ms)")
        print(f"   Unprotected window: {result.get('unprotected_window_ms', 0):.2f}ms")

        if result['success']:
            print("\n✅ PASSED: Bybit atomic update works!")
            await exchange_manager.close()
            return True
        else:
            print(f"\n❌ FAILED: {result.get('error')}")
            await exchange_manager.close()
            return False

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        await exchange_manager.close()
        return False

async def test_binance_optimized_update():
    """Test Binance optimized cancel+create with real position"""
    print("\n" + "="*80)
    print("TEST: Binance Optimized Cancel+Create")
    print("="*80)

    # Check if we have positions
    binance_status = await check_binance_testnet()
    if not binance_status or not binance_status['positions']:
        print("❌ No open positions on Binance testnet")
        print("💡 Suggestion: Open a small position manually for testing")
        return False

    # Select first position
    position = binance_status['positions'][0]
    symbol = position['symbol']
    current_price = float(position['markPrice'])
    entry_price = float(position['entryPrice'])
    side = position['side']

    print(f"\n📊 Testing with position:")
    print(f"   Symbol: {symbol}")
    print(f"   Side: {side}")
    print(f"   Entry: {entry_price}")
    print(f"   Current: {current_price}")

    # Create ExchangeManager
    exchange_config = {
        'api_key': os.getenv('BINANCE_API_KEY'),
        'api_secret': os.getenv('BINANCE_API_SECRET'),
        'testnet': True
    }

    exchange_manager = ExchangeManager(
        exchange_name='binance',
        config=exchange_config
    )

    await exchange_manager.initialize()

    try:
        # Calculate new SL price (5% below current for long, 5% above for short)
        if side.lower() == 'long':
            new_sl_price = current_price * 0.95
        else:
            new_sl_price = current_price * 1.05

        print(f"\n🔄 Updating SL to {new_sl_price:.4f} (5% from current)")

        # Call optimized update
        start_time = datetime.now()
        result = await exchange_manager.update_stop_loss_atomic(
            symbol=symbol,
            new_sl_price=new_sl_price,
            position_side=side.lower()
        )
        execution_time = (datetime.now() - start_time).total_seconds() * 1000

        print(f"\n✅ Result:")
        print(f"   Success: {result['success']}")
        print(f"   Method: {result['method']}")
        print(f"   Execution time: {result['execution_time_ms']:.2f}ms (measured: {execution_time:.2f}ms)")
        print(f"   Unprotected window: {result.get('unprotected_window_ms', 0):.2f}ms")

        if result['success']:
            print("\n✅ PASSED: Binance optimized update works!")
            await exchange_manager.close()
            return True
        else:
            print(f"\n❌ FAILED: {result.get('error')}")
            await exchange_manager.close()
            return False

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        await exchange_manager.close()
        return False

async def main():
    """Run integration tests"""
    print("\n" + "🧪"*40)
    print("INTEGRATION TESTS - TESTNET")
    print("🧪"*40)

    results = {}

    # Check testnet status
    print("\n📊 Checking testnet accounts...")
    bybit_status = await check_bybit_testnet()
    binance_status = await check_binance_testnet()

    # Run tests if positions available
    if bybit_status and bybit_status['positions']:
        results['Bybit Atomic Update'] = await test_bybit_atomic_update()
    else:
        print("\n⏭️  Skipping Bybit test - no positions")
        results['Bybit Atomic Update'] = None

    if binance_status and binance_status['positions']:
        results['Binance Optimized Update'] = await test_binance_optimized_update()
    else:
        print("\n⏭️  Skipping Binance test - no positions")
        results['Binance Optimized Update'] = None

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

    for test_name, result in results.items():
        if result is None:
            status = "⏭️  SKIPPED"
        elif result:
            status = "✅ PASSED"
        else:
            status = "❌ FAILED"
        print(f"{status}: {test_name}")

    passed = sum(1 for v in results.values() if v is True)
    total = sum(1 for v in results.values() if v is not None)

    if total == 0:
        print("\n⚠️  No tests run - need open positions on testnet")
        print("💡 Open small positions manually and run again")
        return 2

    print(f"\n🎯 Total: {passed}/{total} tests passed")

    if passed == total:
        print("✅ ALL TESTS PASSED!")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        return 1

if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
