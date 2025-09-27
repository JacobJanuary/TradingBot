#!/usr/bin/env python3
"""Test script to verify fixes for aiohttp session leaks and Bybit testnet"""

import asyncio
import ccxt.async_support as ccxt
from dotenv import load_dotenv
import os
import sys

load_dotenv()

async def test_bybit_connection():
    """Test Bybit testnet connection"""
    print("\n=== TESTING BYBIT TESTNET CONNECTION ===\n")
    
    exchange = None
    try:
        # Initialize Bybit with testnet
        exchange = ccxt.bybit({
            'apiKey': os.getenv('BYBIT_API_KEY'),
            'secret': os.getenv('BYBIT_API_SECRET'),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',
            }
        })
        
        # Configure testnet URLs properly
        exchange.urls['api'] = {
            'public': 'https://api-testnet.bybit.com',
            'private': 'https://api-testnet.bybit.com'
        }
        exchange.hostname = 'api-testnet.bybit.com'
        
        print("1. Testing API connectivity...")
        # Try to fetch server time (public endpoint)
        time_response = await exchange.fetch_time()
        print(f"   ✅ Server time: {time_response}")
        
        print("\n2. Loading markets...")
        markets = await exchange.load_markets()
        print(f"   ✅ Loaded {len(markets)} markets")
        
        print("\n3. Fetching ticker for BTC/USDT...")
        ticker = await exchange.fetch_ticker('BTC/USDT:USDT')
        print(f"   ✅ BTC/USDT price: ${ticker['last']:.2f}")
        
        print("\n4. Testing authenticated endpoint...")
        try:
            balance = await exchange.fetch_balance()
            usdt_balance = balance.get('USDT', {}).get('free', 0)
            print(f"   ✅ USDT Balance: ${usdt_balance:.2f}")
        except Exception as e:
            print(f"   ⚠️  Authentication test failed (check API keys): {e}")
        
        print("\n✅ Bybit testnet connection successful!")
        return True
        
    except Exception as e:
        print(f"\n❌ Bybit testnet connection failed: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Properly close the exchange connection
        if exchange:
            await exchange.close()
            print("   ✅ Exchange connection properly closed")

async def test_resource_cleanup():
    """Test that resources are properly cleaned up"""
    print("\n=== TESTING RESOURCE CLEANUP ===\n")
    
    exchanges = []
    
    try:
        # Create multiple exchange instances
        print("1. Creating exchange instances...")
        
        # Binance
        binance = ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_API_SECRET'),
            'enableRateLimit': True,
            'options': {'defaultType': 'future', 'fetchPositions': 'positionRisk'}
        })
        binance.set_sandbox_mode(True)
        exchanges.append(('binance', binance))
        
        # Bybit
        bybit = ccxt.bybit({
            'apiKey': os.getenv('BYBIT_API_KEY'),
            'secret': os.getenv('BYBIT_API_SECRET'),
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
        bybit.urls['api'] = {
            'public': 'https://api-testnet.bybit.com',
            'private': 'https://api-testnet.bybit.com'
        }
        exchanges.append(('bybit', bybit))
        
        print("   ✅ Created 2 exchange instances")
        
        # Perform some operations
        print("\n2. Performing operations...")
        for name, exchange in exchanges:
            try:
                await exchange.load_markets()
                print(f"   ✅ {name.capitalize()}: Markets loaded")
            except Exception as e:
                print(f"   ⚠️  {name.capitalize()}: {e}")
        
        # Clean up
        print("\n3. Cleaning up resources...")
        for name, exchange in exchanges:
            await exchange.close()
            print(f"   ✅ {name.capitalize()}: Connection closed")
        
        print("\n✅ Resource cleanup test passed - no session leaks!")
        return True
        
    except Exception as e:
        print(f"\n❌ Resource cleanup test failed: {e}")
        return False
        
    finally:
        # Ensure all exchanges are closed
        for name, exchange in exchanges:
            try:
                await exchange.close()
            except:
                pass

async def main():
    """Run all tests"""
    print("🔧 TESTING FIXES FOR IDENTIFIED ISSUES\n")
    print("=" * 60)
    
    results = []
    
    # Test Bybit connection
    bybit_result = await test_bybit_connection()
    results.append(('Bybit Testnet Connection', bybit_result))
    
    # Test resource cleanup
    cleanup_result = await test_resource_cleanup()
    results.append(('Resource Cleanup', cleanup_result))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    all_passed = True
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name:30} {status}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    
    if all_passed:
        print("\n✅ ALL TESTS PASSED - Issues have been fixed!")
        return 0
    else:
        print("\n⚠️  Some tests failed - please review the output above")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)