#!/usr/bin/env python3
"""
DIAGNOSTIC: Bybit Order Status Investigation

Проверяет что именно возвращает Bybit API при создании market order
"""
import asyncio
import ccxt.async_support as ccxt
import json
from decimal import Decimal


async def test_bybit_market_order():
    """
    Test Bybit market order creation and inspect response
    """
    print()
    print("=" * 80)
    print("🔍 DIAGNOSTIC: Bybit Market Order Response")
    print("=" * 80)
    print()

    # Initialize Bybit exchange
    exchange = ccxt.bybit({
        'apiKey': 'YOUR_API_KEY',  # Replace with real key for testing
        'secret': 'YOUR_SECRET',
        'enableRateLimit': True,
        'options': {
            'defaultType': 'linear',  # USDT perpetual
        }
    })

    # Test symbols from the logs
    test_symbols = [
        '1000000CHEEMSUSDT',
        'VRUSDT',
        'ALUUSDT'
    ]

    try:
        # Load markets first
        await exchange.load_markets()
        print(f"✅ Markets loaded: {len(exchange.markets)} symbols")
        print()

        for symbol in test_symbols:
            print(f"Testing {symbol}...")
            print("-" * 80)

            # Check if symbol exists
            if symbol not in exchange.markets:
                print(f"❌ {symbol} not found in markets")
                print()
                continue

            market = exchange.markets[symbol]
            print(f"Symbol: {symbol}")
            print(f"Type: {market.get('type')}")
            print(f"Linear: {market.get('linear')}")
            print(f"Active: {market.get('active')}")
            print(f"Precision: {market.get('precision')}")
            print(f"Limits: {market.get('limits')}")
            print()

            # Get current price
            ticker = await exchange.fetch_ticker(symbol)
            last_price = ticker['last']
            print(f"Current price: {last_price}")
            print()

            # Calculate minimum order size
            min_amount = market['limits']['amount']['min']
            min_cost = market['limits']['cost']['min']

            # Calculate quantity for $5 order (minimal test)
            test_quantity = max(min_amount, 5 / last_price)
            test_quantity = exchange.amount_to_precision(symbol, test_quantity)

            print(f"Test order parameters:")
            print(f"  Quantity: {test_quantity}")
            print(f"  Est. cost: ${float(test_quantity) * last_price:.2f}")
            print(f"  Min amount: {min_amount}")
            print(f"  Min cost: ${min_cost}")
            print()

            # DRY RUN - Do not actually create order
            print("⚠️ DRY RUN - Not creating actual order")
            print("To test for real, uncomment the create_market_order call below")
            print()

            # UNCOMMENT TO TEST FOR REAL:
            # try:
            #     order = await exchange.create_market_order(
            #         symbol=symbol,
            #         side='buy',  # or 'sell'
            #         amount=test_quantity
            #     )
            #
            #     print("RAW ORDER RESPONSE:")
            #     print(json.dumps(order, indent=2, default=str))
            #     print()
            #
            #     print("KEY FIELDS:")
            #     print(f"  id: {order.get('id')}")
            #     print(f"  status: {order.get('status')}")
            #     print(f"  type: {order.get('type')}")
            #     print(f"  side: {order.get('side')}")
            #     print(f"  amount: {order.get('amount')}")
            #     print(f"  filled: {order.get('filled')}")
            #     print(f"  price: {order.get('price')}")
            #     print(f"  average: {order.get('average')}")
            #     print()
            #
            #     if 'info' in order:
            #         print("INFO SECTION:")
            #         print(json.dumps(order['info'], indent=2, default=str))
            #         print()
            #
            #         print("INFO KEY FIELDS:")
            #         print(f"  orderStatus: {order['info'].get('orderStatus')}")
            #         print(f"  retCode: {order['info'].get('retCode')}")
            #         print(f"  retMsg: {order['info'].get('retMsg')}")
            #
            # except Exception as e:
            #     print(f"❌ Order creation failed: {e}")
            #     print(f"Error type: {type(e).__name__}")
            #     if hasattr(e, 'response'):
            #         print(f"Response: {e.response}")

            print()

    finally:
        await exchange.close()


async def analyze_order_response_format():
    """
    Analyze different possible order response formats
    """
    print()
    print("=" * 80)
    print("📊 ANALYSIS: Possible Order Response Formats")
    print("=" * 80)
    print()

    scenarios = [
        {
            "name": "Instant Fill (empty status)",
            "response": {
                "id": "order123",
                "type": "market",
                "status": "",  # Empty!
                "info": {
                    "orderStatus": "",  # Also empty
                    "retCode": "0",
                    "retMsg": "OK"
                }
            }
        },
        {
            "name": "Filled (lowercase CCXT)",
            "response": {
                "id": "order123",
                "type": "market",
                "status": "closed",  # CCXT normalized
                "info": {
                    "orderStatus": "Filled",  # Bybit format
                    "retCode": "0",
                    "retMsg": "OK"
                }
            }
        },
        {
            "name": "Unknown Status",
            "response": {
                "id": "order123",
                "type": "market",
                "status": "unknown",  # Problem!
                "info": {
                    "orderStatus": "SomethingNew",
                    "retCode": "0",
                    "retMsg": "OK"
                }
            }
        },
        {
            "name": "Missing Status",
            "response": {
                "id": "order123",
                "type": "market",
                # No status field at all
                "info": {
                    # No orderStatus either
                    "retCode": "0",
                    "retMsg": "OK"
                }
            }
        }
    ]

    for scenario in scenarios:
        print(f"Scenario: {scenario['name']}")
        print("-" * 80)

        response = scenario['response']

        # Simulate normalization logic
        info = response.get('info', {})
        raw_status = info.get('orderStatus') or response.get('status', '')

        status_map = {
            'Filled': 'closed',
            'PartiallyFilled': 'open',
            'New': 'open',
            'Cancelled': 'canceled',
            'Rejected': 'canceled',
            'closed': 'closed',
            'open': 'open',
            'canceled': 'canceled',
        }

        # Check empty status special case
        if not raw_status and response.get('type') == 'market':
            final_status = 'closed'
            print(f"  Empty status + market order → 'closed' ✅")
        else:
            final_status = status_map.get(raw_status) or response.get('status') or 'unknown'
            print(f"  raw_status: {raw_status!r}")
            print(f"  mapped: {status_map.get(raw_status)}")
            print(f"  response.status: {response.get('status')}")
            print(f"  final_status: {final_status}")

            if final_status == 'unknown':
                print(f"  ❌ Would cause 'Entry order failed: unknown'")
            elif final_status == 'closed':
                print(f"  ✅ Order would be accepted")
            else:
                print(f"  ⚠️ Status: {final_status}")

        print()


async def main():
    print()
    print("🔬 BYBIT ORDER STATUS DIAGNOSTIC")
    print("=" * 80)
    print()

    # Analyze possible formats
    await analyze_order_response_format()

    # Test real orders (commented out for safety)
    print()
    print("⚠️ REAL ORDER TESTING DISABLED")
    print("=" * 80)
    print()
    print("To test with real orders:")
    print("1. Add your Bybit API credentials")
    print("2. Uncomment the create_market_order call")
    print("3. Run: python3 diagnose_bybit_order_status.py")
    print()
    print("IMPORTANT: Test with SMALL amounts ($5-10) to minimize risk!")
    print()

    # Uncomment to test for real:
    # await test_bybit_market_order()


if __name__ == "__main__":
    asyncio.run(main())
