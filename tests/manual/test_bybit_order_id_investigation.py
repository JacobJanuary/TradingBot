#!/usr/bin/env python3
"""
BYBIT ORDER ID INVESTIGATION TEST SCRIPT
=======================================

Purpose: Investigate GIGAUSDT "missing 'side' field" root cause
Date: 2025-10-29
Issue: Client Order ID vs Exchange Order ID mismatch

This script tests 3 DIFFERENT ways to verify:
1. What order_id format does create_market_order return?
2. Can we fetch_order with that ID?
3. What's in the raw response?

CRITICAL: This is INVESTIGATION ONLY - NO CODE CHANGES!

Per user requirements:
- Test 3 times with different methods
- NO simplifications
- Check EVERY API call
- Study EVERY response
- Verify EVERY parameter
- ONLY facts, NO assumptions
"""

import asyncio
import json
import os
import sys
from decimal import Decimal
from datetime import datetime
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

# Load environment
load_dotenv()

# Import after path setup
import ccxt.async_support as ccxt


class BybitOrderIDInvestigator:
    """Ultra-detailed investigation of Bybit order ID behavior"""

    def __init__(self):
        self.bybit_api_key = os.getenv('BYBIT_API_KEY')
        self.bybit_api_secret = os.getenv('BYBIT_API_SECRET')
        self.testnet = os.getenv('BYBIT_TESTNET', 'false').lower() == 'true'

        if not self.bybit_api_key or not self.bybit_api_secret:
            raise ValueError("BYBIT_API_KEY and BYBIT_API_SECRET must be set in .env")

        self.exchange = None
        self.test_symbol = 'GIGAUSDT'  # Same symbol as the failure
        self.auto_confirm = False  # Set by main() if --auto-confirm flag
        self.test_results = {
            'method1_raw_ccxt': {},
            'method2_exchange_manager': {},
            'method3_minimal_order': {},
            'summary': {}
        }

    async def setup(self):
        """Initialize Bybit exchange connection"""
        print("=" * 80)
        print("BYBIT ORDER ID INVESTIGATION - SETUP")
        print("=" * 80)
        print(f"Testnet: {self.testnet}")
        print(f"Symbol: {self.test_symbol}")
        print()

        self.exchange = ccxt.bybit({
            'apiKey': self.bybit_api_key,
            'secret': self.bybit_api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'linear',  # USDT perpetual
                'recvWindow': 10000,
            }
        })

        if self.testnet:
            self.exchange.set_sandbox_mode(True)

        # Load markets
        await self.exchange.load_markets()
        print("✅ Exchange initialized and markets loaded")
        print()

    async def cleanup(self):
        """Close exchange connection"""
        if self.exchange:
            await self.exchange.close()
            print("✅ Exchange connection closed")

    async def method1_raw_ccxt_order(self):
        """
        METHOD 1: Direct CCXT API Call
        ================================

        Test: Create market order using CCXT directly
        Goal: See EXACTLY what Bybit returns in raw response

        This mimics what our code does at:
        core/exchange_manager.py line 417-425
        """
        print("=" * 80)
        print("METHOD 1: RAW CCXT API CALL")
        print("=" * 80)
        print()

        # Check if we have open position first
        print("STEP 1.1: Checking current positions...")
        positions = await self.exchange.fetch_positions([self.test_symbol])

        has_position = False
        for pos in positions:
            size = float(pos.get('contracts', 0))
            if pos['symbol'] == self.test_symbol and size != 0:
                print(f"⚠️  WARNING: Already have position in {self.test_symbol}:")
                print(f"   Size: {size}")
                print(f"   Side: {pos.get('side')}")
                print(f"   Entry Price: {pos.get('entryPrice')}")
                has_position = True

        if not has_position:
            print(f"✅ No open position in {self.test_symbol}")
        print()

        # Check balance
        print("STEP 1.2: Checking USDT balance...")
        balance = await self.exchange.fetch_balance()
        usdt_free = float(balance['USDT']['free'])
        print(f"✅ USDT Free: ${usdt_free:.2f}")

        if usdt_free < 10:
            print("❌ ERROR: Insufficient balance for test (need at least $10)")
            self.test_results['method1_raw_ccxt']['error'] = "Insufficient balance"
            return
        print()

        # Get market info
        print("STEP 1.3: Getting market info...")
        ticker = await self.exchange.fetch_ticker(self.test_symbol)
        current_price = float(ticker['last'])
        print(f"✅ Current price: ${current_price:.8f}")

        # Calculate minimum order size
        market = self.exchange.market(self.test_symbol)
        min_amount = market['limits']['amount']['min']
        min_cost = market['limits']['cost']['min']

        print(f"✅ Min amount: {min_amount}")
        print(f"✅ Min cost: ${min_cost}")

        # Calculate order size ($6 like production)
        order_value_usd = 6.0
        quantity = order_value_usd / current_price

        # Round to appropriate precision
        amount_precision = market['precision']['amount']
        if amount_precision:
            quantity = round(quantity, int(-1 * abs(amount_precision)) if amount_precision < 1 else int(amount_precision))

        print(f"✅ Calculated quantity: {quantity} {self.test_symbol.replace('USDT', '')}")
        print(f"✅ Order value: ~${quantity * current_price:.2f}")
        print()

        # CRITICAL: Check params that will be sent
        print("STEP 1.4: Preparing order parameters...")
        params = {
            'positionIdx': 0,  # One-way mode (same as production)
        }

        print(f"✅ Params: {json.dumps(params, indent=2)}")
        print()

        # Ask for confirmation (unless auto-confirm mode)
        print("⚠️  IMPORTANT: This will create a REAL market order!")
        print(f"   Symbol: {self.test_symbol}")
        print(f"   Side: SELL (short)")
        print(f"   Quantity: {quantity}")
        print(f"   Estimated cost: ~${quantity * current_price:.2f}")
        print()

        if self.auto_confirm:
            print("🤖 AUTO-CONFIRM: Proceeding automatically...")
        else:
            response = input("Continue? (yes/no): ")
            if response.lower() != 'yes':
                print("❌ Test cancelled by user")
                self.test_results['method1_raw_ccxt']['status'] = 'cancelled'
                return
        print()

        # CREATE ORDER
        print("STEP 1.5: Creating market order...")
        print(f"CALL: exchange.create_market_order('{self.test_symbol}', 'sell', {quantity}, params={params})")
        print()

        try:
            order = await self.exchange.create_market_order(
                self.test_symbol,
                'sell',
                quantity,
                params=params
            )

            print("✅ ORDER CREATED!")
            print()

            # ANALYZE RESPONSE
            print("=" * 80)
            print("RESPONSE ANALYSIS")
            print("=" * 80)
            print()

            print("FULL RESPONSE (JSON):")
            print(json.dumps(order, indent=2, default=str))
            print()

            # Extract key fields
            order_id = order.get('id')
            order_id_type = 'UUID' if '-' in str(order_id) else 'NUMERIC'

            print("KEY FIELDS:")
            print(f"  id: {order_id} ({order_id_type})")
            print(f"  symbol: {order.get('symbol')}")
            print(f"  side: {order.get('side')}")
            print(f"  type: {order.get('type')}")
            print(f"  status: {order.get('status')}")
            print(f"  filled: {order.get('filled')}")
            print(f"  amount: {order.get('amount')}")
            print(f"  price: {order.get('price')}")
            print(f"  timestamp: {order.get('timestamp')}")
            print()

            # Check info field (raw response from Bybit)
            info = order.get('info', {})
            print("INFO FIELD (Raw Bybit Response):")
            print(json.dumps(info, indent=2, default=str))
            print()

            # Check for orderId in info
            if 'orderId' in info:
                bybit_order_id = info['orderId']
                print(f"🎯 FOUND: info['orderId'] = {bybit_order_id}")
                print(f"   Type: {'UUID' if '-' in str(bybit_order_id) else 'NUMERIC'}")
            else:
                print("⚠️  WARNING: No 'orderId' in info field!")
            print()

            # Check for orderLinkId (client order ID)
            if 'orderLinkId' in info:
                client_order_id = info['orderLinkId']
                print(f"🎯 FOUND: info['orderLinkId'] = {client_order_id}")
                print(f"   Type: {'UUID' if '-' in str(client_order_id) else 'NUMERIC/STRING'}")
            else:
                print("ℹ️  INFO: No 'orderLinkId' in info field (not set by us)")
            print()

            # Store results
            self.test_results['method1_raw_ccxt'] = {
                'status': 'success',
                'order_id_from_ccxt': order_id,
                'order_id_type': order_id_type,
                'has_side_field': order.get('side') is not None,
                'side_value': order.get('side'),
                'raw_info': info,
                'bybit_order_id': info.get('orderId'),
                'client_order_id': info.get('orderLinkId'),
                'full_response': order
            }

            # NOW TEST fetch_order with CCXT ID
            print("=" * 80)
            print("STEP 1.6: Testing fetch_order with CCXT ID")
            print("=" * 80)
            print()

            print(f"CALL: exchange.fetch_order('{order_id}', '{self.test_symbol}')")
            print()

            try:
                fetched = await self.exchange.fetch_order(order_id, self.test_symbol)
                print("✅ fetch_order SUCCEEDED!")
                print()
                print("FETCHED ORDER:")
                print(json.dumps(fetched, indent=2, default=str))

                self.test_results['method1_raw_ccxt']['fetch_order_with_ccxt_id'] = {
                    'status': 'success',
                    'response': fetched
                }
            except Exception as e:
                print(f"❌ fetch_order FAILED: {type(e).__name__}: {e}")
                self.test_results['method1_raw_ccxt']['fetch_order_with_ccxt_id'] = {
                    'status': 'failed',
                    'error_type': type(e).__name__,
                    'error_message': str(e)
                }
            print()

            # If we found bybit order ID, test with that
            if 'orderId' in info:
                bybit_order_id = info['orderId']

                print("=" * 80)
                print("STEP 1.7: Testing fetch_order with Bybit Order ID")
                print("=" * 80)
                print()

                print(f"CALL: exchange.fetch_order('{bybit_order_id}', '{self.test_symbol}')")
                print()

                try:
                    fetched = await self.exchange.fetch_order(bybit_order_id, self.test_symbol)
                    print("✅ fetch_order SUCCEEDED!")
                    print()
                    print("FETCHED ORDER:")
                    print(json.dumps(fetched, indent=2, default=str))

                    self.test_results['method1_raw_ccxt']['fetch_order_with_bybit_id'] = {
                        'status': 'success',
                        'response': fetched
                    }
                except Exception as e:
                    print(f"❌ fetch_order FAILED: {type(e).__name__}: {e}")
                    self.test_results['method1_raw_ccxt']['fetch_order_with_bybit_id'] = {
                        'status': 'failed',
                        'error_type': type(e).__name__,
                        'error_message': str(e)
                    }
                print()

        except Exception as e:
            print(f"❌ ORDER CREATION FAILED: {type(e).__name__}: {e}")
            self.test_results['method1_raw_ccxt'] = {
                'status': 'failed',
                'error_type': type(e).__name__,
                'error_message': str(e)
            }
            import traceback
            traceback.print_exc()

        print()

    async def method2_check_existing_positions(self):
        """
        METHOD 2: Check for Existing Positions
        ========================================

        Test: Use fetch_positions to see what we created
        Goal: Verify position exists and can be queried
        """
        print("=" * 80)
        print("METHOD 2: CHECK EXISTING POSITIONS")
        print("=" * 80)
        print()

        print("CALL: exchange.fetch_positions(['{self.test_symbol}'])")
        print()

        try:
            positions = await self.exchange.fetch_positions([self.test_symbol])

            print(f"✅ Got {len(positions)} position(s)")
            print()

            for pos in positions:
                size = float(pos.get('contracts', 0))
                if size != 0:
                    print("POSITION FOUND:")
                    print(json.dumps(pos, indent=2, default=str))
                    print()

                    self.test_results['method2_exchange_manager']['position'] = pos

            if not any(float(p.get('contracts', 0)) != 0 for p in positions):
                print("ℹ️  No open positions found")
                self.test_results['method2_exchange_manager']['status'] = 'no_positions'

        except Exception as e:
            print(f"❌ FAILED: {type(e).__name__}: {e}")
            self.test_results['method2_exchange_manager'] = {
                'status': 'failed',
                'error_type': type(e).__name__,
                'error_message': str(e)
            }

        print()

    async def method3_query_recent_orders(self):
        """
        METHOD 3: Query Recent Orders
        ===============================

        Test: Use fetch_orders to see recent orders
        Goal: Check if our order appears in recent orders list
        """
        print("=" * 80)
        print("METHOD 3: QUERY RECENT ORDERS")
        print("=" * 80)
        print()

        print(f"CALL: exchange.fetch_orders('{self.test_symbol}', limit=10)")
        print()

        try:
            orders = await self.exchange.fetch_orders(self.test_symbol, limit=10)

            print(f"✅ Got {len(orders)} recent order(s)")
            print()

            for i, order in enumerate(orders, 1):
                print(f"ORDER #{i}:")
                print(f"  id: {order.get('id')}")
                print(f"  symbol: {order.get('symbol')}")
                print(f"  side: {order.get('side')}")
                print(f"  status: {order.get('status')}")
                print(f"  filled: {order.get('filled')}")
                print(f"  timestamp: {datetime.fromtimestamp(order.get('timestamp', 0) / 1000)}")
                print()

            self.test_results['method3_minimal_order'] = {
                'status': 'success',
                'orders_count': len(orders),
                'orders': orders
            }

        except Exception as e:
            print(f"❌ FAILED: {type(e).__name__}: {e}")
            self.test_results['method3_minimal_order'] = {
                'status': 'failed',
                'error_type': type(e).__name__,
                'error_message': str(e)
            }

        print()

    async def generate_summary(self):
        """Generate summary of all findings"""
        print("=" * 80)
        print("INVESTIGATION SUMMARY")
        print("=" * 80)
        print()

        # Summary of Method 1
        method1 = self.test_results.get('method1_raw_ccxt', {})
        if method1.get('status') == 'success':
            print("✅ METHOD 1: Order Creation Successful")
            print(f"   CCXT returned ID: {method1.get('order_id_from_ccxt')} ({method1.get('order_id_type')})")
            print(f"   Has 'side' field: {method1.get('has_side_field')}")
            print(f"   Side value: {method1.get('side_value')}")

            if method1.get('bybit_order_id'):
                print(f"   Bybit order ID (from info): {method1.get('bybit_order_id')}")

            fetch_ccxt = method1.get('fetch_order_with_ccxt_id', {})
            if fetch_ccxt.get('status') == 'success':
                print(f"   fetch_order with CCXT ID: ✅ SUCCESS")
            elif fetch_ccxt.get('status') == 'failed':
                print(f"   fetch_order with CCXT ID: ❌ FAILED ({fetch_ccxt.get('error_type')})")

            fetch_bybit = method1.get('fetch_order_with_bybit_id', {})
            if fetch_bybit.get('status') == 'success':
                print(f"   fetch_order with Bybit ID: ✅ SUCCESS")
            elif fetch_bybit.get('status') == 'failed':
                print(f"   fetch_order with Bybit ID: ❌ FAILED ({fetch_bybit.get('error_type')})")
        else:
            print(f"❌ METHOD 1: {method1.get('status', 'unknown')}")

        print()

        # Key findings
        print("KEY FINDINGS:")
        print()

        if method1.get('order_id_type') == 'UUID':
            print("🎯 CRITICAL: CCXT returned UUID as order ID (CLIENT ORDER ID)")
            print("   This matches GIGAUSDT failure pattern!")
            print()
        elif method1.get('order_id_type') == 'NUMERIC':
            print("ℹ️  INFO: CCXT returned NUMERIC order ID (EXCHANGE ORDER ID)")
            print("   This is different from GIGAUSDT failure!")
            print()

        if not method1.get('has_side_field'):
            print("🎯 CRITICAL: create_market_order response has NO 'side' field")
            print("   This confirms minimal response issue!")
            print()
        elif method1.get('has_side_field'):
            print("ℹ️  INFO: create_market_order response HAS 'side' field")
            print("   This is different from expected minimal response!")
            print()

        # Recommendations
        print("RECOMMENDATIONS:")
        print()

        if method1.get('order_id_type') == 'UUID':
            print("1. Code should extract info['orderId'] instead of using order['id']")
            print("2. OR: Use fetch_positions instead of fetch_order for verification")
            print("3. OR: Cache orders using BOTH exchange and client order IDs")

        print()

        # Save full results
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        results_file = f'test_results_bybit_order_id_{timestamp}.json'

        with open(results_file, 'w') as f:
            json.dump(self.test_results, f, indent=2, default=str)

        print(f"✅ Full results saved to: {results_file}")
        print()

    async def run_full_investigation(self):
        """Run all investigation methods"""
        try:
            await self.setup()

            # Method 1: Create order and analyze response
            await self.method1_raw_ccxt_order()

            # Wait a bit for order to settle
            await asyncio.sleep(2)

            # Method 2: Check positions
            await self.method2_check_existing_positions()

            # Method 3: Check recent orders
            await self.method3_query_recent_orders()

            # Generate summary
            await self.generate_summary()

        except Exception as e:
            print(f"❌ INVESTIGATION FAILED: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

        finally:
            await self.cleanup()


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Bybit Order ID Investigation')
    parser.add_argument('--auto-confirm', action='store_true',
                       help='Auto-confirm order creation (non-interactive mode)')
    args = parser.parse_args()

    print()
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 20 + "BYBIT ORDER ID INVESTIGATION" + " " * 30 + "║")
    print("║" + " " * 78 + "║")
    print("║  Purpose: Investigate CLIENT ORDER ID vs EXCHANGE ORDER ID issue    ║")
    print("║  Issue: GIGAUSDT missing 'side' field - Root cause analysis         ║")
    print("║  Date: 2025-10-29                                                    ║")
    print("╚" + "═" * 78 + "╝")
    print()

    if args.auto_confirm:
        print("🤖 AUTO-CONFIRM MODE: Will create order without asking")
        print()

    investigator = BybitOrderIDInvestigator()
    investigator.auto_confirm = args.auto_confirm
    await investigator.run_full_investigation()


if __name__ == '__main__':
    asyncio.run(main())
