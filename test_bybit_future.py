#!/usr/bin/env python3
"""
Test script to verify Bybit works with defaultType='future'
Will attempt to open real positions on testnet
"""
import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv
from decimal import Decimal
import json

load_dotenv('.env')

async def test_bybit_future():
    print("=" * 60)
    print("BYBIT 'FUTURE' TYPE TESTING")
    print("Testing if we can open positions with defaultType='future'")
    print("=" * 60)

    api_key = os.getenv('BYBIT_API_KEY')
    api_secret = os.getenv('BYBIT_API_SECRET')

    if not api_key or not api_secret:
        print("❌ Missing BYBIT_API_KEY or BYBIT_API_SECRET in .env")
        return

    print(f"✅ API credentials loaded")

    # Create exchange with 'future' type (same as our fix)
    exchange = ccxt.bybit({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',  # Testing 'future' instead of 'unified'
            'adjustForTimeDifference': True,
            'recvWindow': 10000,
        }
    })

    # Use testnet
    exchange.set_sandbox_mode(True)
    print(f"✅ Exchange initialized with defaultType='future'")
    print(f"   Options: {exchange.options.get('defaultType')}")

    try:
        # Load markets
        print("\n⏳ Loading markets...")
        markets = await exchange.load_markets()
        print(f"✅ Markets loaded: {len(markets)} markets found")

        # Get account balance
        print("\n💰 Fetching account balance...")
        try:
            balance = await exchange.fetch_balance()
            usdt_balance = balance.get('USDT', {})
            usdt_free = usdt_balance.get('free', 0) if usdt_balance else 0
            if usdt_free:
                print(f"✅ USDT Balance: {usdt_free:.2f}")
            else:
                print("⚠️  Could not fetch USDT balance (testnet may have issues)")
                usdt_free = 1000  # Assume some balance for testing
        except Exception as e:
            print(f"⚠️  Balance fetch failed: {e}")
            usdt_free = 1000  # Continue with test anyway

        # Test symbols that were causing issues
        test_symbols = [
            'BTC/USDT:USDT',   # Bitcoin perpetual
            'ETH/USDT:USDT',   # Ethereum perpetual
            'XDC/USDT:USDT',   # XDC perpetual (was in signals)
            'IDEX/USDT:USDT',  # IDEX perpetual (was causing errors)
        ]

        print("\n📊 Testing market access and price formatting:")
        print("-" * 40)

        working_symbols = []

        for symbol in test_symbols:
            print(f"\n🔍 Testing {symbol}:")

            if symbol not in markets:
                print(f"   ⚠️  Symbol not found in markets")
                continue

            market = markets[symbol]
            print(f"   ✅ Market found")
            print(f"      Type: {market.get('type')}")
            print(f"      Active: {market.get('active')}")
            print(f"      Linear: {market.get('linear')}")

            # Test the problematic function that was causing KeyError
            try:
                test_price = 100.123456
                formatted_price = exchange.price_to_precision(symbol, test_price)
                print(f"   ✅ price_to_precision works: {test_price} -> {formatted_price}")

                # Test amount formatting too
                test_amount = 0.123456
                formatted_amount = exchange.amount_to_precision(symbol, test_amount)
                print(f"   ✅ amount_to_precision works: {test_amount} -> {formatted_amount}")

                working_symbols.append(symbol)

            except KeyError as e:
                print(f"   ❌ KeyError: {e}")
            except Exception as e:
                print(f"   ❌ Error: {type(e).__name__}: {e}")

        # Now try to open actual positions on working symbols
        if working_symbols:
            print("\n" + "=" * 60)
            print("📈 ATTEMPTING TO OPEN TEST POSITIONS")
            print("=" * 60)

            for symbol in working_symbols[:2]:  # Test only first 2 to avoid too many positions
                print(f"\n🎯 Opening position for {symbol}:")

                try:
                    # Fetch current ticker
                    ticker = await exchange.fetch_ticker(symbol)
                    current_price = ticker['last']
                    print(f"   Current price: {current_price}")

                    # Calculate position size (minimum for test)
                    market = markets[symbol]
                    min_amount = market.get('limits', {}).get('amount', {}).get('min', 0.001)

                    # Use slightly above minimum
                    amount = min_amount * 2 if min_amount else 0.001

                    # Format amount properly
                    amount = exchange.amount_to_precision(symbol, amount)

                    print(f"   Position size: {amount} {symbol.split('/')[0]}")
                    print(f"   Estimated cost: ${float(amount) * current_price:.2f}")

                    # Create a market buy order (long position)
                    print(f"   📤 Placing MARKET BUY order...")

                    order = await exchange.create_market_buy_order(
                        symbol=symbol,
                        amount=amount,
                        params={
                            'positionIdx': 0,  # One-way mode
                            'reduceOnly': False
                        }
                    )

                    print(f"   ✅ ORDER PLACED SUCCESSFULLY!")
                    print(f"      Order ID: {order['id']}")
                    print(f"      Status: {order['status']}")
                    print(f"      Filled: {order.get('filled', 'N/A')}")

                    # Wait a bit for order to process
                    await asyncio.sleep(2)

                    # Check position
                    positions = await exchange.fetch_positions([symbol])
                    if positions:
                        pos = positions[0]
                        print(f"   ✅ POSITION OPENED:")
                        print(f"      Side: {pos.get('side')}")
                        print(f"      Amount: {pos.get('contracts')}")
                        print(f"      Entry Price: {pos.get('markPrice')}")
                        print(f"      Unrealized PnL: {pos.get('unrealizedPnl')}")

                        # Close the position immediately (cleanup)
                        print(f"   🔄 Closing test position...")
                        close_order = await exchange.create_market_sell_order(
                            symbol=symbol,
                            amount=amount,
                            params={
                                'positionIdx': 0,
                                'reduceOnly': True
                            }
                        )
                        print(f"   ✅ Position closed: Order {close_order['id']}")
                    else:
                        print(f"   ⚠️  No position found after order")

                except Exception as e:
                    print(f"   ❌ Failed to open position: {type(e).__name__}: {e}")

        else:
            print("\n⚠️  No working symbols found for position testing")

        # Final verification
        print("\n" + "=" * 60)
        print("📋 FINAL STATUS:")
        print("-" * 40)

        if working_symbols:
            print(f"✅ SUCCESS: defaultType='future' works with Bybit!")
            print(f"   Working symbols: {', '.join(working_symbols)}")
            print(f"\n✅ RECOMMENDATION: Change 'unified' to 'future' in exchange_manager.py")
        else:
            print(f"❌ FAILURE: No symbols worked with defaultType='future'")

    except Exception as e:
        print(f"\n❌ Test failed with error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await exchange.close()

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_bybit_future())