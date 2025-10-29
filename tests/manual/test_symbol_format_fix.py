#!/usr/bin/env python3
"""
BYBIT SYMBOL FORMAT FIX VERIFICATION
=====================================

Date: 2025-10-29 05:20
Purpose: Test if symbol format conversion fixes fetch_positions issue

Test Plan:
1. Open small test position (~$6)
2. Try fetch_positions with raw format ("GIGAUSDT")
3. Try fetch_positions with unified format ("GIGA/USDT:USDT")
4. Compare results
5. Close test position

Expected Result:
- Raw format: NOT FOUND (current bug)
- Unified format: FOUND (fix works)
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

# Load environment
load_dotenv()

# Import after path setup
import ccxt.async_support as ccxt


class SymbolFormatFixTest:
    """Test symbol format fix for fetch_positions"""

    def __init__(self):
        self.bybit_api_key = os.getenv('BYBIT_API_KEY')
        self.bybit_api_secret = os.getenv('BYBIT_API_SECRET')
        self.testnet = os.getenv('BYBIT_TESTNET', 'false').lower() == 'true'

        if not self.bybit_api_key or not self.bybit_api_secret:
            raise ValueError("BYBIT_API_KEY and BYBIT_API_SECRET must be set")

        self.exchange = None
        self.test_symbol = 'GIGAUSDT'  # Raw format
        self.test_unified_symbol = 'GIGA/USDT:USDT'  # Unified format
        self.test_amount = None  # Will calculate based on $6 target
        self.order_id = None
        self.results = {}

    async def setup(self):
        """Initialize exchange connection"""
        self.exchange = ccxt.bybit({
            'apiKey': self.bybit_api_key,
            'secret': self.bybit_api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',
            }
        })

        if self.testnet:
            self.exchange.set_sandbox_mode(True)
            print("⚠️  Using TESTNET")
        else:
            print("✅ Using MAINNET")

        # Load markets
        await self.exchange.load_markets()
        print(f"✅ Markets loaded: {len(self.exchange.markets)} markets")
        print()

    async def calculate_test_amount(self):
        """Calculate position size for ~$6"""
        ticker = await self.exchange.fetch_ticker(self.test_unified_symbol)
        current_price = float(ticker['last'])

        # Target $6, calculate contracts needed
        target_usd = 6.0
        contracts = target_usd / current_price

        # Round to step size
        market = self.exchange.market(self.test_unified_symbol)
        step_size = float(market['limits']['amount']['min'])

        # Round up to nearest step
        contracts = max(step_size, round(contracts / step_size) * step_size)

        actual_usd = contracts * current_price

        print(f"💰 Position Sizing:")
        print(f"   Current price: ${current_price:.6f}")
        print(f"   Target: ${target_usd}")
        print(f"   Calculated contracts: {contracts}")
        print(f"   Actual cost: ${actual_usd:.2f}")
        print()

        self.test_amount = contracts
        return contracts

    async def open_test_position(self):
        """Open small test position"""
        print("=" * 80)
        print("STEP 1: OPEN TEST POSITION")
        print("=" * 80)
        print()

        # Calculate amount
        await self.calculate_test_amount()

        # Confirm
        print(f"⚠️  CREATING REAL POSITION!")
        print(f"   Symbol: {self.test_symbol}")
        print(f"   Amount: {self.test_amount} contracts")
        print(f"   Cost: ~$6")
        print()
        print("🤖 AUTO-CONFIRM: Proceeding...")
        print()

        # Set leverage
        try:
            await self.exchange.set_leverage(1, self.test_unified_symbol)
            print(f"✅ Leverage set to 1x")
        except Exception as e:
            if 'leverage not modified' in str(e):
                print(f"✅ Leverage already at 1x")
            else:
                raise

        # Create order
        print(f"Creating market order...")
        order = await self.exchange.create_market_order(
            self.test_unified_symbol,
            'sell',  # Short position
            self.test_amount,
            params={'reduce_only': False}
        )

        self.order_id = order['id']
        print(f"✅ Order created: {self.order_id}")
        print()

        # Wait for order to fill
        print("⏳ Waiting 2 seconds for order to fill...")
        await asyncio.sleep(2)
        print()

        return True

    async def test_raw_format(self):
        """Test fetch_positions with RAW format (current code)"""
        print("=" * 80)
        print("STEP 2: TEST fetch_positions WITH RAW FORMAT")
        print("=" * 80)
        print()

        print(f"CALL: exchange.fetch_positions(symbols=['{self.test_symbol}'], params={{'category': 'linear'}})")
        print("(This is what CURRENT production code does)")
        print()

        try:
            positions = await self.exchange.fetch_positions(
                symbols=[self.test_symbol],  # RAW format
                params={'category': 'linear'}
            )

            non_zero = [p for p in positions if float(p.get('contracts', 0)) != 0]

            print(f"Result: {len(positions)} total positions, {len(non_zero)} non-zero")
            print()

            if non_zero:
                print("✅ POSITION FOUND!")
                for pos in non_zero:
                    print(f"   Symbol: {pos.get('symbol')}")
                    print(f"   Contracts: {pos.get('contracts')}")
                    print(f"   Side: {pos.get('side')}")
                print()
                self.results['raw_format'] = {
                    'status': 'FOUND',
                    'count': len(non_zero)
                }
            else:
                print("❌ POSITION NOT FOUND!")
                print("   This confirms the BUG - raw format doesn't work!")
                print()
                self.results['raw_format'] = {
                    'status': 'NOT_FOUND',
                    'count': 0
                }

        except Exception as e:
            print(f"❌ ERROR: {e}")
            print()
            self.results['raw_format'] = {
                'status': 'ERROR',
                'error': str(e)
            }

    async def test_unified_format(self):
        """Test fetch_positions with UNIFIED format (proposed fix)"""
        print("=" * 80)
        print("STEP 3: TEST fetch_positions WITH UNIFIED FORMAT")
        print("=" * 80)
        print()

        print(f"CALL: exchange.fetch_positions(symbols=['{self.test_unified_symbol}'], params={{'category': 'linear'}})")
        print("(This is what the FIX would do)")
        print()

        try:
            positions = await self.exchange.fetch_positions(
                symbols=[self.test_unified_symbol],  # UNIFIED format
                params={'category': 'linear'}
            )

            non_zero = [p for p in positions if float(p.get('contracts', 0)) != 0]

            print(f"Result: {len(positions)} total positions, {len(non_zero)} non-zero")
            print()

            if non_zero:
                print("✅ POSITION FOUND!")
                for pos in non_zero:
                    print(f"   Symbol: {pos.get('symbol')}")
                    print(f"   Contracts: {pos.get('contracts')}")
                    print(f"   Side: {pos.get('side')}")
                    print(f"   Entry Price: {pos.get('entryPrice')}")
                print()
                self.results['unified_format'] = {
                    'status': 'FOUND',
                    'count': len(non_zero),
                    'position': non_zero[0]
                }
            else:
                print("❌ POSITION NOT FOUND!")
                print("   This would mean the fix DOESN'T work!")
                print()
                self.results['unified_format'] = {
                    'status': 'NOT_FOUND',
                    'count': 0
                }

        except Exception as e:
            print(f"❌ ERROR: {e}")
            print()
            self.results['unified_format'] = {
                'status': 'ERROR',
                'error': str(e)
            }

    async def test_no_symbols_param(self):
        """Test fetch_positions WITHOUT symbols parameter"""
        print("=" * 80)
        print("STEP 4: TEST fetch_positions WITHOUT symbols (fetch all)")
        print("=" * 80)
        print()

        print("CALL: exchange.fetch_positions(params={'category': 'linear'})")
        print("(Alternative approach - fetch all positions)")
        print()

        try:
            positions = await self.exchange.fetch_positions(
                params={'category': 'linear'}
            )

            non_zero = [p for p in positions if float(p.get('contracts', 0)) != 0]

            # Find our test position
            our_position = None
            for pos in non_zero:
                pos_symbol = pos.get('info', {}).get('symbol', '')
                if pos_symbol == self.test_symbol:
                    our_position = pos
                    break

            print(f"Result: {len(positions)} total positions, {len(non_zero)} non-zero")
            print()

            if our_position:
                print("✅ OUR POSITION FOUND!")
                print(f"   Symbol (unified): {our_position.get('symbol')}")
                print(f"   Symbol (raw): {our_position.get('info', {}).get('symbol')}")
                print(f"   Contracts: {our_position.get('contracts')}")
                print(f"   Side: {our_position.get('side')}")
                print()
                self.results['no_symbols'] = {
                    'status': 'FOUND',
                    'total_positions': len(non_zero)
                }
            else:
                print("❌ OUR POSITION NOT FOUND!")
                print(f"   (Found {len(non_zero)} other positions)")
                print()
                self.results['no_symbols'] = {
                    'status': 'NOT_FOUND',
                    'total_positions': len(non_zero)
                }

        except Exception as e:
            print(f"❌ ERROR: {e}")
            print()
            self.results['no_symbols'] = {
                'status': 'ERROR',
                'error': str(e)
            }

    async def close_test_position(self):
        """Close test position"""
        print("=" * 80)
        print("STEP 5: CLOSE TEST POSITION")
        print("=" * 80)
        print()

        try:
            # Close position with market order
            order = await self.exchange.create_market_order(
                self.test_unified_symbol,
                'buy',  # Close short
                self.test_amount,
                params={'reduce_only': True}
            )

            print(f"✅ Position closed: {order['id']}")
            print()

        except Exception as e:
            print(f"❌ Failed to close position: {e}")
            print("   ⚠️  MANUAL ACTION REQUIRED: Close position manually!")
            print()

    async def show_verdict(self):
        """Show final verdict"""
        print()
        print("=" * 80)
        print("FINAL VERDICT")
        print("=" * 80)
        print()

        print("Results Summary:")
        print(json.dumps(self.results, indent=2, default=str))
        print()

        raw_found = self.results.get('raw_format', {}).get('status') == 'FOUND'
        unified_found = self.results.get('unified_format', {}).get('status') == 'FOUND'
        no_symbols_found = self.results.get('no_symbols', {}).get('status') == 'FOUND'

        print("Analysis:")
        print("-" * 80)
        print(f"Raw format ('{self.test_symbol}'):         {'✅ FOUND' if raw_found else '❌ NOT FOUND'}")
        print(f"Unified format ('{self.test_unified_symbol}'):  {'✅ FOUND' if unified_found else '❌ NOT FOUND'}")
        print(f"No symbols param (fetch all):                {'✅ FOUND' if no_symbols_found else '❌ NOT FOUND'}")
        print()

        if not raw_found and unified_found:
            print("🎯 VERDICT: FIX IS CORRECT!")
            print()
            print("   ❌ Raw format DOESN'T work (confirms bug)")
            print("   ✅ Unified format WORKS (confirms fix)")
            print()
            print("   RECOMMENDATION: Implement symbol conversion fix")
            print()
        elif raw_found and unified_found:
            print("⚠️  VERDICT: BOTH WORK?")
            print()
            print("   This is unexpected - both formats found position")
            print("   Need to investigate why production code fails")
            print()
        elif not raw_found and not unified_found:
            print("❌ VERDICT: NEITHER WORKS!")
            print()
            print("   Something else is wrong - neither format found position")
            print("   Need deeper investigation")
            print()
        else:
            print("❓ VERDICT: UNEXPECTED RESULT")
            print()
            print("   Need to review results manually")
            print()

        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"test_results_symbol_format_fix_{timestamp}.json"
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)

        print(f"📁 Results saved to: {filename}")
        print()

    async def run(self):
        """Run full test"""
        try:
            await self.setup()

            # Open position
            success = await self.open_test_position()
            if not success:
                return

            # Run tests
            await self.test_raw_format()
            await self.test_unified_format()
            await self.test_no_symbols_param()

            # Close position
            await self.close_test_position()

            # Show verdict
            await self.show_verdict()

        finally:
            if self.exchange:
                await self.exchange.close()


async def main():
    """Main entry point"""
    test = SymbolFormatFixTest()
    await test.run()


if __name__ == '__main__':
    asyncio.run(main())
