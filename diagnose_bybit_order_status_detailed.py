#!/usr/bin/env python3
"""
Diagnostic: Bybit Order Status "Unknown" Issue - DETAILED ANALYSIS
==========================================

Purpose: Capture EXACT response from Bybit to understand why status="unknown"

User reports: Position actually created successfully but logs show "unknown"
Previous fix (dbc4da8): Handled empty status for market orders
Current issue: Still getting "unknown" status - need to understand WHY

This script will:
1. Simulate the exact flow: ExchangeManager -> ExchangeResponseAdapter
2. Capture raw CCXT response
3. Show OrderResult after _parse_order
4. Show NormalizedOrder after normalize_order
5. Identify where "unknown" comes from
"""
import asyncio
import sys
import json
from pprint import pprint
from dataclasses import asdict

sys.path.insert(0, '/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot')

from core.exchange_response_adapter import ExchangeResponseAdapter, NormalizedOrder
from core.exchange_manager import ExchangeManager, OrderResult
from config import config


def analyze_order_flow(ccxt_response: dict, exchange_name: str):
    """
    Analyze the complete order flow to find where 'unknown' status originates
    """
    print("=" * 100)
    print("📊 ANALYZING ORDER FLOW")
    print("=" * 100)
    print()

    # Step 1: Raw CCXT response
    print("🔍 STEP 1: Raw CCXT Response from Bybit API")
    print("-" * 100)
    print(json.dumps(ccxt_response, indent=2, default=str))
    print()

    # Step 2: ExchangeManager._parse_order creates OrderResult
    print("🔍 STEP 2: After ExchangeManager._parse_order() → OrderResult dataclass")
    print("-" * 100)

    # Simulate _parse_order logic
    from datetime import datetime, timezone

    if ccxt_response.get('timestamp'):
        timestamp = datetime.fromtimestamp(ccxt_response['timestamp'] / 1000)
    else:
        timestamp = datetime.now(timezone.utc)

    order_result = OrderResult(
        id=ccxt_response['id'],
        symbol=ccxt_response['symbol'],
        side=ccxt_response['side'],
        type=ccxt_response['type'],
        amount=ccxt_response['amount'],
        price=ccxt_response['price'] or 0,
        filled=ccxt_response.get('filled', 0),
        remaining=ccxt_response.get('remaining', ccxt_response['amount']),
        status=ccxt_response['status'],  # ⚠️ KEY: This is raw CCXT status
        timestamp=timestamp,
        info=ccxt_response['info']
    )

    print("OrderResult fields:")
    order_dict = asdict(order_result)
    # Remove timestamp for cleaner output
    order_dict['timestamp'] = str(order_dict['timestamp'])
    for key, value in order_dict.items():
        if key != 'info':
            print(f"  {key}: {value}")
    print(f"  info: {json.dumps(order_result.info, indent=4, default=str)}")
    print()

    # Step 3: Convert OrderResult to dict for ExchangeResponseAdapter
    print("🔍 STEP 3: OrderResult.__dict__ (passed to ExchangeResponseAdapter.normalize_order)")
    print("-" * 100)
    order_as_dict = order_result.__dict__
    print("Dict keys:", list(order_as_dict.keys()))
    print("Dict['status']:", order_as_dict['status'])
    print("Dict['info']:", json.dumps(order_as_dict['info'], indent=2, default=str))
    print()

    # Step 4: ExchangeResponseAdapter.normalize_order
    print("🔍 STEP 4: ExchangeResponseAdapter.normalize_order(order_result, 'bybit')")
    print("-" * 100)

    normalized = ExchangeResponseAdapter.normalize_order(order_result, exchange_name)

    print("NormalizedOrder fields:")
    print(f"  id: {normalized.id}")
    print(f"  status: {normalized.status}")  # ⚠️ KEY: This is where 'unknown' appears
    print(f"  side: {normalized.side}")
    print(f"  amount: {normalized.amount}")
    print(f"  filled: {normalized.filled}")
    print(f"  price: {normalized.price}")
    print(f"  average: {normalized.average}")
    print(f"  symbol: {normalized.symbol}")
    print(f"  type: {normalized.type}")
    print()

    # Step 5: Analyze why status became 'unknown'
    print("🔍 STEP 5: ROOT CAUSE ANALYSIS")
    print("-" * 100)

    info = order_as_dict.get('info', {})
    raw_status_from_info = info.get('orderStatus')
    raw_status_from_data = order_as_dict.get('status', '')
    order_type = order_as_dict.get('type')

    print(f"info.get('orderStatus'): {raw_status_from_info}")
    print(f"data.get('status'): {raw_status_from_data}")
    print(f"data.get('type'): {order_type}")
    print()

    # Simulate _normalize_bybit_order logic
    raw_status = info.get('orderStatus') or order_as_dict.get('status', '')

    print(f"Combined raw_status: '{raw_status}'")
    print()

    # Check the fix condition
    if not raw_status and order_as_dict.get('type') == 'market':
        print("✅ FIX TRIGGERED: Empty status + market order → status='closed'")
        final_status = 'closed'
    else:
        status_map = {
            'Filled': 'closed',
            'PartiallyFilled': 'open',
            'New': 'open',
            'Cancelled': 'canceled',
            'Rejected': 'canceled',
        }
        final_status = status_map.get(raw_status) or order_as_dict.get('status') or 'unknown'
        print(f"❌ FIX NOT TRIGGERED:")
        print(f"   - raw_status not empty: '{raw_status}'")
        print(f"   - Checking status_map for '{raw_status}': {status_map.get(raw_status)}")
        print(f"   - Fallback to data['status']: {order_as_dict.get('status')}")
        print(f"   - Final status: '{final_status}'")

    print()
    print(f"🎯 FINAL STATUS: '{final_status}'")
    print()

    # Step 6: Check is_order_filled
    print("🔍 STEP 6: ExchangeResponseAdapter.is_order_filled(normalized)")
    print("-" * 100)
    is_filled = ExchangeResponseAdapter.is_order_filled(normalized)
    print(f"Result: {is_filled}")
    print()

    if not is_filled:
        print("❌ ORDER REJECTED!")
        print(f"   Reason: is_order_filled() returned False")
        print(f"   Status: {normalized.status}")
        print(f"   Type: {normalized.type}")
        print(f"   Filled: {normalized.filled}/{normalized.amount}")
    else:
        print("✅ ORDER ACCEPTED")

    print()
    print("=" * 100)
    print("📋 SUMMARY")
    print("=" * 100)
    print(f"Raw CCXT status: '{ccxt_response['status']}'")
    print(f"After normalization: '{normalized.status}'")
    print(f"Order filled: {is_filled}")
    print()

    return {
        'ccxt_status': ccxt_response['status'],
        'normalized_status': normalized.status,
        'is_filled': is_filled,
        'raw_status_from_info': raw_status_from_info,
        'order_type': order_type
    }


async def test_real_bybit_order():
    """
    Create a real market order on Bybit testnet and capture response
    """
    print("=" * 100)
    print("🧪 TESTING REAL BYBIT ORDER")
    print("=" * 100)
    print()

    # Initialize exchange
    exchange_config = {
        'api_key': config.exchanges['bybit'].api_key,
        'api_secret': config.exchanges['bybit'].api_secret,
        'testnet': True
    }

    exchange_manager = ExchangeManager('bybit', exchange_config)

    # Test symbol (small amount)
    test_symbol = 'SUNDOGUSDT'  # Use same symbol as previous diagnosis
    test_side = 'sell'
    test_amount = 10  # Very small amount

    print(f"Creating market order: {test_symbol} {test_side.upper()} {test_amount}")
    print()

    try:
        # This will create a real order
        order_result = await exchange_manager.create_market_order(
            test_symbol, test_side, test_amount
        )

        print("✅ Order created successfully!")
        print()

        # Now analyze the flow
        # We need the raw CCXT response - let's get it from order_result.info
        ccxt_response = {
            'id': order_result.id,
            'symbol': order_result.symbol,
            'side': order_result.side,
            'type': order_result.type,
            'amount': order_result.amount,
            'price': order_result.price,
            'filled': order_result.filled,
            'remaining': order_result.remaining,
            'status': order_result.status,  # ⚠️ This is the key field
            'timestamp': int(order_result.timestamp.timestamp() * 1000),
            'info': order_result.info
        }

        analysis = analyze_order_flow(ccxt_response, 'bybit')

        return analysis

    except Exception as e:
        print(f"❌ Error creating order: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        await exchange_manager.close()


async def main():
    print()
    print("🔬 BYBIT ORDER STATUS DIAGNOSIS - DETAILED FLOW ANALYSIS")
    print("=" * 100)
    print()
    print("This script will:")
    print("1. Create a real market order on Bybit testnet")
    print("2. Capture the raw CCXT response")
    print("3. Show how OrderResult is created")
    print("4. Show how NormalizedOrder is created")
    print("5. Identify where 'unknown' status comes from")
    print()
    print("⚠️  WARNING: This will create a REAL order on testnet!")
    print()

    analysis = await test_real_bybit_order()

    if analysis:
        print()
        print("=" * 100)
        print("🎯 ROOT CAUSE IDENTIFIED")
        print("=" * 100)
        print()

        if analysis['normalized_status'] == 'unknown':
            print("❌ PROBLEM CONFIRMED:")
            print(f"   CCXT returns status: '{analysis['ccxt_status']}'")
            print(f"   But normalized to: '{analysis['normalized_status']}'")
            print()
            print("🔍 Possible causes:")
            print("   1. CCXT returns a status not in status_map")
            print("   2. Status is passed through but not recognized")
            print("   3. Empty status fix doesn't trigger (raw_status not empty)")
            print()
            print(f"   info.orderStatus: '{analysis['raw_status_from_info']}'")
            print(f"   order type: '{analysis['order_type']}'")
        else:
            print("✅ Order normalized correctly!")
            print(f"   Final status: '{analysis['normalized_status']}'")

    print()
    print("=" * 100)
    print("📝 NEXT STEPS")
    print("=" * 100)
    print("1. Check what status CCXT actually returns")
    print("2. Update status_map if needed")
    print("3. Update empty status fix condition if needed")
    print()


if __name__ == "__main__":
    asyncio.run(main())
