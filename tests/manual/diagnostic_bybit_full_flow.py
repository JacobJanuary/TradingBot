#!/usr/bin/env python3
"""
BYBIT FULL FLOW DIAGNOSTIC SCRIPT
===================================

Purpose: Детальная диагностика ВСЕГО flow создания позиции на Bybit
Date: 2025-10-29
Issue: Позиции создаются на бирже но бот их не видит

Этот скрипт проверяет КАЖДЫЙ шаг:
1. create_market_order - что возвращает?
2. raw_order structure - какие поля есть?
3. fetch_positions - находит ли позицию?
4. Symbol format matching - совпадают ли символы?
5. Timing - сколько времени нужно для появления в fetch_positions?

БЕЗ УПРОЩЕНИЙ! ТОЛЬКО ФАКТЫ!
"""

import asyncio
import json
import os
import sys
from decimal import Decimal
from datetime import datetime
from dotenv import load_dotenv
import time

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

# Load environment
load_dotenv()

# Import after path setup
import ccxt.async_support as ccxt


class BybitFullFlowDiagnostic:
    """Полная диагностика Bybit flow"""

    def __init__(self):
        self.bybit_api_key = os.getenv('BYBIT_API_KEY')
        self.bybit_api_secret = os.getenv('BYBIT_API_SECRET')
        self.testnet = os.getenv('BYBIT_TESTNET', 'false').lower() == 'true'

        if not self.bybit_api_key or not self.bybit_api_secret:
            raise ValueError("BYBIT_API_KEY and BYBIT_API_SECRET must be set in .env")

        self.exchange = None
        self.test_symbol = 'GIGAUSDT'  # Use same symbol as before
        self.results = {
            'step1_create_order': {},
            'step2_raw_order_analysis': {},
            'step3_fetch_positions_immediate': {},
            'step4_fetch_positions_delayed': {},
            'step5_symbol_matching': {},
            'step6_timing_analysis': {},
            'summary': {}
        }

    async def setup(self):
        """Initialize Bybit exchange"""
        print("=" * 80)
        print("BYBIT FULL FLOW DIAGNOSTIC - SETUP")
        print("=" * 80)
        print(f"Testnet: {self.testnet}")
        print(f"Symbol: {self.test_symbol}")
        print()

        self.exchange = ccxt.bybit({
            'apiKey': self.bybit_api_key,
            'secret': self.bybit_api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'linear',
                'recvWindow': 10000,
            }
        })

        if self.testnet:
            self.exchange.set_sandbox_mode(True)

        await self.exchange.load_markets()
        print("✅ Exchange initialized")
        print()

    async def cleanup(self):
        """Close exchange"""
        if self.exchange:
            await self.exchange.close()
            print("✅ Exchange closed")

    async def step1_create_market_order(self):
        """
        STEP 1: Create market order and analyze response
        =================================================
        """
        print("=" * 80)
        print("STEP 1: CREATE MARKET ORDER")
        print("=" * 80)
        print()

        # Check balance
        balance = await self.exchange.fetch_balance()
        usdt_free = float(balance['USDT']['free'])
        print(f"USDT Free: ${usdt_free:.2f}")

        if usdt_free < 10:
            print("❌ ERROR: Insufficient balance")
            self.results['step1_create_order'] = {'error': 'Insufficient balance'}
            return None
        print()

        # Get market info
        ticker = await self.exchange.fetch_ticker(self.test_symbol)
        current_price = float(ticker['last'])
        print(f"Current price: ${current_price:.8f}")

        market = self.exchange.market(self.test_symbol)
        print(f"Min amount: {market['limits']['amount']['min']}")
        print()

        # Calculate order size
        order_value_usd = 6.0
        quantity = order_value_usd / current_price

        amount_precision = market['precision']['amount']
        if amount_precision:
            quantity = round(quantity, int(-1 * abs(amount_precision)) if amount_precision < 1 else int(amount_precision))

        print(f"Order quantity: {quantity} {self.test_symbol.replace('USDT', '')}")
        print(f"Order value: ~${quantity * current_price:.2f}")
        print()

        # Create order
        print("Creating market order...")
        print()

        try:
            start_time = time.time()

            raw_order = await self.exchange.create_market_order(
                self.test_symbol,
                'sell',
                quantity,
                params={'positionIdx': 0}
            )

            create_duration = time.time() - start_time

            print(f"✅ ORDER CREATED in {create_duration:.3f}s")
            print()

            # Store result
            self.results['step1_create_order'] = {
                'success': True,
                'duration_seconds': create_duration,
                'quantity': quantity,
                'raw_order': raw_order
            }

            return raw_order

        except Exception as e:
            print(f"❌ ORDER CREATION FAILED: {type(e).__name__}: {e}")
            self.results['step1_create_order'] = {
                'success': False,
                'error_type': type(e).__name__,
                'error_message': str(e)
            }
            import traceback
            traceback.print_exc()
            return None

    async def step2_analyze_raw_order(self, raw_order):
        """
        STEP 2: Analyze raw_order structure
        ====================================
        """
        if not raw_order:
            print("⚠️ STEP 2 SKIPPED: No raw_order")
            return

        print("=" * 80)
        print("STEP 2: ANALYZE RAW ORDER STRUCTURE")
        print("=" * 80)
        print()

        print("FULL RAW ORDER:")
        print(json.dumps(raw_order, indent=2, default=str))
        print()

        # Extract key fields
        analysis = {
            'id': raw_order.get('id'),
            'id_type': 'UUID' if '-' in str(raw_order.get('id', '')) else 'NUMERIC',
            'symbol': raw_order.get('symbol'),
            'side': raw_order.get('side'),
            'type': raw_order.get('type'),
            'status': raw_order.get('status'),
            'filled': raw_order.get('filled'),
            'amount': raw_order.get('amount'),
            'price': raw_order.get('price'),
            'timestamp': raw_order.get('timestamp'),
            'datetime': raw_order.get('datetime'),
        }

        print("KEY FIELDS:")
        for key, value in analysis.items():
            print(f"  {key}: {value}")
        print()

        # Check info field
        info = raw_order.get('info', {})
        print("INFO FIELD:")
        print(json.dumps(info, indent=2, default=str))
        print()

        analysis['info_orderId'] = info.get('orderId')
        analysis['info_orderLinkId'] = info.get('orderLinkId')
        analysis['info_retCode'] = info.get('retCode')
        analysis['info_retMsg'] = info.get('retMsg')

        # Check what fields are None
        none_fields = [k for k, v in analysis.items() if v is None]
        if none_fields:
            print(f"⚠️  WARNING: Following fields are None: {', '.join(none_fields)}")
            print()

        self.results['step2_raw_order_analysis'] = analysis

    async def step3_fetch_positions_immediate(self, raw_order):
        """
        STEP 3: fetch_positions immediately after create_order
        =======================================================
        """
        if not raw_order:
            print("⚠️ STEP 3 SKIPPED: No raw_order")
            return

        print("=" * 80)
        print("STEP 3: FETCH POSITIONS IMMEDIATELY")
        print("=" * 80)
        print()

        print("Calling fetch_positions IMMEDIATELY after create_order...")
        print()

        try:
            start_time = time.time()

            positions = await self.exchange.fetch_positions(
                symbols=[self.test_symbol],
                params={'category': 'linear'}
            )

            fetch_duration = time.time() - start_time

            print(f"✅ fetch_positions completed in {fetch_duration:.3f}s")
            print(f"✅ Got {len(positions)} position(s)")
            print()

            # Check if our position is there
            our_position = None
            for pos in positions:
                pos_size = float(pos.get('contracts', 0))
                if pos_size != 0:
                    print("POSITION FOUND:")
                    print(f"  pos['symbol'] = {pos.get('symbol')}")
                    print(f"  pos['info']['symbol'] = {pos.get('info', {}).get('symbol')}")
                    print(f"  pos['side'] = {pos.get('side')}")
                    print(f"  pos['info']['side'] = {pos.get('info', {}).get('side')}")
                    print(f"  pos['contracts'] = {pos_size}")
                    print(f"  pos['entryPrice'] = {pos.get('entryPrice')}")
                    print()
                    our_position = pos

            if our_position:
                self.results['step3_fetch_positions_immediate'] = {
                    'found': True,
                    'duration_seconds': fetch_duration,
                    'position': our_position
                }
            else:
                print("❌ POSITION NOT FOUND in immediate fetch_positions")
                self.results['step3_fetch_positions_immediate'] = {
                    'found': False,
                    'duration_seconds': fetch_duration
                }

        except Exception as e:
            print(f"❌ fetch_positions FAILED: {type(e).__name__}: {e}")
            self.results['step3_fetch_positions_immediate'] = {
                'found': False,
                'error_type': type(e).__name__,
                'error_message': str(e)
            }

    async def step4_fetch_positions_delayed(self):
        """
        STEP 4: fetch_positions with delays
        ====================================
        """
        print("=" * 80)
        print("STEP 4: FETCH POSITIONS WITH DELAYS")
        print("=" * 80)
        print()

        delays = [0.5, 1.0, 1.5, 2.0, 3.0]
        results = []

        for delay in delays:
            print(f"Waiting {delay}s before fetch_positions...")
            await asyncio.sleep(delay)

            try:
                start_time = time.time()
                positions = await self.exchange.fetch_positions(
                    symbols=[self.test_symbol],
                    params={'category': 'linear'}
                )
                fetch_duration = time.time() - start_time

                found = any(float(p.get('contracts', 0)) != 0 for p in positions)

                if found:
                    print(f"  ✅ Position FOUND after {delay}s delay (fetch took {fetch_duration:.3f}s)")
                else:
                    print(f"  ❌ Position NOT FOUND after {delay}s delay")

                results.append({
                    'delay_seconds': delay,
                    'found': found,
                    'fetch_duration_seconds': fetch_duration
                })

            except Exception as e:
                print(f"  ❌ ERROR: {type(e).__name__}: {e}")
                results.append({
                    'delay_seconds': delay,
                    'error_type': type(e).__name__,
                    'error_message': str(e)
                })

        print()
        self.results['step4_fetch_positions_delayed'] = results

    async def step5_symbol_matching_test(self):
        """
        STEP 5: Test symbol matching logic
        ===================================
        """
        print("=" * 80)
        print("STEP 5: SYMBOL MATCHING TEST")
        print("=" * 80)
        print()

        try:
            positions = await self.exchange.fetch_positions(
                symbols=[self.test_symbol],
                params={'category': 'linear'}
            )

            for pos in positions:
                pos_size = float(pos.get('contracts', 0))
                if pos_size != 0:
                    symbol_ccxt = pos.get('symbol')  # CCXT format
                    symbol_raw = pos.get('info', {}).get('symbol')  # Raw Bybit format
                    our_symbol = self.test_symbol  # Our format

                    print("SYMBOL MATCHING TEST:")
                    print(f"  Our symbol: '{our_symbol}'")
                    print(f"  pos['symbol']: '{symbol_ccxt}'")
                    print(f"  pos['info']['symbol']: '{symbol_raw}'")
                    print()

                    # Test different matching approaches
                    match1 = (symbol_ccxt == our_symbol)
                    match2 = (symbol_raw == our_symbol)

                    print("MATCHING RESULTS:")
                    print(f"  pos['symbol'] == our_symbol: {match1}")
                    print(f"  pos['info']['symbol'] == our_symbol: {match2}")
                    print()

                    if match2:
                        print("✅ CORRECT: Use pos['info']['symbol'] for matching!")
                    elif match1:
                        print("⚠️  WARNING: pos['symbol'] matches but format is different")
                    else:
                        print("❌ ERROR: No match found!")
                    print()

                    self.results['step5_symbol_matching'] = {
                        'our_symbol': our_symbol,
                        'pos_symbol_ccxt': symbol_ccxt,
                        'pos_symbol_raw': symbol_raw,
                        'ccxt_format_matches': match1,
                        'raw_format_matches': match2,
                        'correct_approach': 'pos[\'info\'][\'symbol\']' if match2 else 'UNKNOWN'
                    }
                    break

        except Exception as e:
            print(f"❌ ERROR: {type(e).__name__}: {e}")
            self.results['step5_symbol_matching'] = {
                'error_type': type(e).__name__,
                'error_message': str(e)
            }

    async def step6_timing_analysis(self):
        """
        STEP 6: Timing analysis
        =======================
        """
        print("=" * 80)
        print("STEP 6: TIMING ANALYSIS")
        print("=" * 80)
        print()

        step1 = self.results.get('step1_create_order', {})
        step3 = self.results.get('step3_fetch_positions_immediate', {})
        step4 = self.results.get('step4_fetch_positions_delayed', [])

        if step1.get('success'):
            print(f"create_market_order duration: {step1.get('duration_seconds', 0):.3f}s")

        if step3.get('found') is not None:
            print(f"fetch_positions immediate: {'FOUND' if step3.get('found') else 'NOT FOUND'} ({step3.get('duration_seconds', 0):.3f}s)")

        print()
        print("fetch_positions with delays:")
        for result in step4:
            delay = result.get('delay_seconds', 0)
            found = result.get('found', False)
            status = '✅ FOUND' if found else '❌ NOT FOUND'
            print(f"  {delay}s delay: {status}")

        # Find minimum delay needed
        min_delay_needed = None
        for result in step4:
            if result.get('found'):
                min_delay_needed = result.get('delay_seconds')
                break

        if min_delay_needed is not None:
            print()
            print(f"🎯 MINIMUM DELAY NEEDED: {min_delay_needed}s")
        else:
            print()
            print("⚠️  Position not found even with delays (may have been closed)")

        self.results['step6_timing_analysis'] = {
            'create_order_duration': step1.get('duration_seconds'),
            'fetch_immediate_duration': step3.get('duration_seconds'),
            'minimum_delay_needed': min_delay_needed,
            'delayed_results': step4
        }

    async def generate_summary(self):
        """Generate summary and recommendations"""
        print("=" * 80)
        print("DIAGNOSTIC SUMMARY")
        print("=" * 80)
        print()

        # Save full results
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        results_file = f'diagnostic_bybit_full_flow_{timestamp}.json'

        with open(results_file, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)

        print(f"✅ Full results saved to: {results_file}")
        print()

        # Generate recommendations
        print("RECOMMENDATIONS:")
        print()

        step5 = self.results.get('step5_symbol_matching', {})
        if step5.get('correct_approach'):
            print(f"1. Symbol matching: Use {step5.get('correct_approach')}")

        step6 = self.results.get('step6_timing_analysis', {})
        min_delay = step6.get('minimum_delay_needed')
        if min_delay:
            print(f"2. Minimum delay needed: {min_delay}s before fetch_positions")

        print()

    async def run_full_diagnostic(self):
        """Run all diagnostic steps"""
        try:
            await self.setup()

            # Step 1: Create order
            raw_order = await self.step1_create_market_order()

            if raw_order:
                # Step 2: Analyze raw_order
                await self.step2_analyze_raw_order(raw_order)

                # Step 3: Immediate fetch_positions
                await self.step3_fetch_positions_immediate(raw_order)

                # Step 4: Delayed fetch_positions
                await self.step4_fetch_positions_delayed()

                # Step 5: Symbol matching
                await self.step5_symbol_matching_test()

                # Step 6: Timing analysis
                await self.step6_timing_analysis()

                # Generate summary
                await self.generate_summary()

        except Exception as e:
            print(f"❌ DIAGNOSTIC FAILED: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

        finally:
            await self.cleanup()


async def main():
    """Main entry point"""
    print()
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 20 + "BYBIT FULL FLOW DIAGNOSTIC" + " " * 32 + "║")
    print("║" + " " * 78 + "║")
    print("║  Purpose: Диагностика ВСЕГО flow создания позиции              ║")
    print("║  Issue: Позиции создаются но бот их не видит                   ║")
    print("║  Date: 2025-10-29                                               ║")
    print("╚" + "═" * 78 + "╝")
    print()

    diagnostic = BybitFullFlowDiagnostic()
    await diagnostic.run_full_diagnostic()


if __name__ == '__main__':
    asyncio.run(main())
