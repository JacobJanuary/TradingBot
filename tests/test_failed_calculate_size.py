#!/usr/bin/env python3
"""
Comprehensive Investigation Script: "Failed to calculate size" Issue

Tests all 17 problematic symbols to understand WHY position size calculation fails.

Possible failure reasons (from code analysis):
1. size_usd <= 0 (line 1533-1535)
2. quantity < min_amount AND too expensive (line 1566-1567)
3. formatted_qty < min_amount after precision adjustment (line 1585-1590, 1597-1601)
4. can_open_position fails (line 1604-1607)
5. exchange.get_min_amount() returns None or invalid
6. exchange.amount_to_precision() fails
7. Symbol not in markets (no market data)

Problematic symbols (from ERROR_ANALYSIS_10H_20251021.md):
HMSTRUSDT, USTCUSDT, TUSDT, TREEUSDT, SAPIENUSDT, PROMPTUSDT,
PORT3USDT, ONEUSDT, HOLOUSDT, GTCUSDT, FLOCKUSDT, FIOUSDT,
CYBERUSDT, CETUSUSDT, BLESSUSDT, B3USDT, AIAUSDT
"""

import asyncio
import sys
from pathlib import Path
from decimal import Decimal
from typing import Dict, List, Optional
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.exchange_manager import ExchangeManager
from config.settings import config as settings
from utils.decimal_utils import to_decimal


class SymbolDiagnostics:
    """Diagnostic information for a symbol"""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.market_exists = False
        self.market_active = False
        self.market_info = {}
        self.price = None
        self.min_amount = None
        self.step_size = None
        self.raw_quantity = None
        self.formatted_quantity = None
        self.min_cost = None
        self.can_afford_minimum = False
        self.failure_reason = None
        self.additional_info = {}


async def diagnose_symbol(exchange: ExchangeManager, symbol: str, position_size_usd: float) -> SymbolDiagnostics:
    """
    Perform comprehensive diagnostics on why a symbol might fail position size calculation
    """
    diag = SymbolDiagnostics(symbol)

    try:
        # Step 1: Check if market exists
        exchange_symbol = exchange.find_exchange_symbol(symbol) or symbol
        diag.market_info['exchange_symbol'] = exchange_symbol

        if exchange_symbol in exchange.markets:
            diag.market_exists = True
            market = exchange.markets[exchange_symbol]

            # Extract market info
            diag.market_active = market.get('active', False)
            diag.market_info['active'] = market.get('active')
            diag.market_info['type'] = market.get('type')
            diag.market_info['spot'] = market.get('spot')
            diag.market_info['margin'] = market.get('margin')
            diag.market_info['swap'] = market.get('swap')
            diag.market_info['future'] = market.get('future')
            diag.market_info['linear'] = market.get('linear', False)
            diag.market_info['inverse'] = market.get('inverse', False)

            # Check if symbol info exists
            if 'info' in market:
                info = market['info']
                diag.market_info['status'] = info.get('status', 'unknown')
                diag.market_info['contractType'] = info.get('contractType', info.get('contract_type', 'unknown'))

            # Check limits
            limits = market.get('limits', {})
            amount_limits = limits.get('amount', {})
            diag.market_info['min_amount_limit'] = amount_limits.get('min')
            diag.market_info['max_amount_limit'] = amount_limits.get('max')

            cost_limits = limits.get('cost', {})
            diag.market_info['min_cost'] = cost_limits.get('min')

        else:
            diag.failure_reason = "MARKET_NOT_FOUND"
            diag.additional_info['searched_symbol'] = exchange_symbol
            return diag

        # Step 2: Get current price
        try:
            ticker = await exchange.fetch_ticker(symbol)
            if ticker and 'last' in ticker:
                diag.price = ticker['last']
                diag.market_info['bid'] = ticker.get('bid')
                diag.market_info['ask'] = ticker.get('ask')
                diag.market_info['last'] = ticker.get('last')
            else:
                diag.failure_reason = "NO_PRICE_DATA"
                diag.additional_info['ticker'] = ticker
                return diag
        except Exception as e:
            diag.failure_reason = "FETCH_TICKER_FAILED"
            diag.additional_info['error'] = str(e)
            return diag

        # Step 3: Get min_amount
        try:
            diag.min_amount = exchange.get_min_amount(symbol)
            if diag.min_amount is None or diag.min_amount <= 0:
                diag.failure_reason = "INVALID_MIN_AMOUNT"
                diag.additional_info['min_amount'] = diag.min_amount
                return diag
        except Exception as e:
            diag.failure_reason = "GET_MIN_AMOUNT_FAILED"
            diag.additional_info['error'] = str(e)
            return diag

        # Step 4: Get step_size
        try:
            diag.step_size = exchange.get_step_size(symbol)
        except Exception as e:
            diag.additional_info['step_size_error'] = str(e)
            diag.step_size = 0.001  # Default

        # Step 5: Calculate raw quantity
        diag.raw_quantity = Decimal(str(position_size_usd)) / Decimal(str(diag.price))

        # Step 6: Check if quantity < min_amount
        if diag.raw_quantity < Decimal(str(diag.min_amount)):
            diag.min_cost = float(diag.min_amount) * float(diag.price)
            tolerance = position_size_usd * 1.1

            if diag.min_cost <= tolerance:
                diag.can_afford_minimum = True
                # Will use minimum
                diag.raw_quantity = Decimal(str(diag.min_amount))
            else:
                diag.can_afford_minimum = False
                diag.failure_reason = "BELOW_MINIMUM_TOO_EXPENSIVE"
                diag.additional_info['min_cost'] = diag.min_cost
                diag.additional_info['tolerance'] = tolerance
                diag.additional_info['required'] = diag.min_cost - tolerance
                return diag

        # Step 7: Apply precision formatting
        try:
            diag.formatted_quantity = exchange.amount_to_precision(symbol, float(diag.raw_quantity))

            # Check if precision truncated below minimum
            if diag.formatted_quantity < diag.min_amount:
                diag.failure_reason = "PRECISION_TRUNCATED_BELOW_MINIMUM"
                diag.additional_info['raw_qty'] = float(diag.raw_quantity)
                diag.additional_info['formatted_qty'] = diag.formatted_quantity
                diag.additional_info['min_amount'] = diag.min_amount
                diag.additional_info['step_size'] = diag.step_size
                return diag

        except Exception as e:
            diag.failure_reason = "AMOUNT_TO_PRECISION_FAILED"
            diag.additional_info['error'] = str(e)
            return diag

        # Step 8: Check can_open_position
        try:
            can_open, reason = await exchange.can_open_position(symbol, position_size_usd)
            if not can_open:
                diag.failure_reason = "CAN_OPEN_POSITION_FAILED"
                diag.additional_info['reason'] = reason
                return diag
        except Exception as e:
            diag.failure_reason = "CAN_OPEN_POSITION_ERROR"
            diag.additional_info['error'] = str(e)
            return diag

        # If we got here, calculation should succeed
        diag.failure_reason = None  # SUCCESS!

    except Exception as e:
        diag.failure_reason = "UNEXPECTED_ERROR"
        diag.additional_info['error'] = str(e)
        diag.additional_info['error_type'] = type(e).__name__

    return diag


async def run_diagnostics():
    """Run diagnostics on all 17 problematic symbols"""

    print("=" * 100)
    print("🔍 COMPREHENSIVE DIAGNOSTICS: Failed to Calculate Position Size")
    print("=" * 100)
    print()

    # Problematic symbols from error analysis
    problematic_symbols = [
        'HMSTRUSDT', 'USTCUSDT', 'TUSDT', 'TREEUSDT', 'SAPIENUSDT', 'PROMPTUSDT',
        'PORT3USDT', 'ONEUSDT', 'HOLOUSDT', 'GTCUSDT', 'FLOCKUSDT', 'FIOUSDT',
        'CYBERUSDT', 'CETUSUSDT', 'BLESSUSDT', 'B3USDT', 'AIAUSDT'
    ]

    # Load config and initialize exchange
    binance_config = settings.exchanges['binance']

    exchange = ExchangeManager('binance', binance_config.__dict__)
    await exchange.initialize()

    print(f"✅ Exchange initialized: {exchange.name}")
    print(f"📊 Total markets loaded: {len(exchange.markets)}")
    print(f"🎯 Testing {len(problematic_symbols)} problematic symbols")
    print()

    position_size_usd = 200.0  # Standard position size

    results = []
    failure_categories = {}

    for i, symbol in enumerate(problematic_symbols, 1):
        print(f"\n{'=' * 100}")
        print(f"🧪 Symbol {i}/{len(problematic_symbols)}: {symbol}")
        print(f"{'=' * 100}")

        diag = await diagnose_symbol(exchange, symbol, position_size_usd)

        # Print results
        print(f"\n📋 Market Information:")
        print(f"   Exists: {diag.market_exists}")
        if diag.market_exists:
            print(f"   Active: {diag.market_active}")
            print(f"   Status: {diag.market_info.get('status', 'N/A')}")
            print(f"   Type: {diag.market_info.get('type', 'N/A')}")
            print(f"   Contract: {diag.market_info.get('contractType', 'N/A')}")

        print(f"\n💰 Price Data:")
        print(f"   Price: {f'${diag.price:.8f}' if diag.price else 'N/A'}")
        print(f"   Bid: {diag.market_info.get('bid', 'N/A')}")
        print(f"   Ask: {diag.market_info.get('ask', 'N/A')}")

        print(f"\n📏 Limits:")
        print(f"   Min Amount: {diag.min_amount if diag.min_amount else 'N/A'}")
        print(f"   Step Size: {diag.step_size if diag.step_size else 'N/A'}")
        print(f"   Min Cost: ${diag.min_cost:.2f}" if diag.min_cost else "   Min Cost: N/A")

        print(f"\n🧮 Quantity Calculation:")
        print(f"   Position Size: ${position_size_usd}")
        if diag.raw_quantity:
            print(f"   Raw Quantity: {float(diag.raw_quantity):.8f}")
        if diag.formatted_quantity is not None:
            if isinstance(diag.formatted_quantity, (int, float)):
                print(f"   Formatted Quantity: {diag.formatted_quantity:.8f}")
            else:
                print(f"   Formatted Quantity: {diag.formatted_quantity}")

        print(f"\n🎯 Result:")
        if diag.failure_reason:
            print(f"   ❌ FAILED: {diag.failure_reason}")
            if diag.additional_info:
                print(f"   Details: {json.dumps(diag.additional_info, indent=6, default=str)}")

            # Categorize failure
            if diag.failure_reason not in failure_categories:
                failure_categories[diag.failure_reason] = []
            failure_categories[diag.failure_reason].append(symbol)
        else:
            print(f"   ✅ SUCCESS (would create position)")

        results.append({
            'symbol': symbol,
            'market_exists': diag.market_exists,
            'market_active': diag.market_active,
            'price': diag.price,
            'min_amount': diag.min_amount,
            'step_size': diag.step_size,
            'raw_quantity': float(diag.raw_quantity) if diag.raw_quantity else None,
            'formatted_quantity': diag.formatted_quantity,
            'min_cost': diag.min_cost,
            'can_afford_minimum': diag.can_afford_minimum,
            'failure_reason': diag.failure_reason,
            'market_info': diag.market_info,
            'additional_info': diag.additional_info
        })

    # Print summary
    print(f"\n\n{'=' * 100}")
    print("📊 SUMMARY")
    print(f"{'=' * 100}")

    failed = sum(1 for r in results if r['failure_reason'])
    succeeded = len(results) - failed

    print(f"\nTotal Symbols Tested: {len(results)}")
    print(f"❌ Failed: {failed}")
    print(f"✅ Succeeded: {succeeded}")

    print(f"\n\n{'=' * 100}")
    print("🔍 FAILURE BREAKDOWN BY CATEGORY")
    print(f"{'=' * 100}")

    for category, symbols in sorted(failure_categories.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"\n❌ {category} ({len(symbols)} symbols):")
        for sym in symbols:
            result = next(r for r in results if r['symbol'] == sym)
            print(f"   - {sym}")
            if result['additional_info']:
                for key, value in result['additional_info'].items():
                    if key != 'error':
                        print(f"      {key}: {value}")

    # Save detailed results to JSON
    output_file = Path(__file__).parent / 'failed_calculate_size_results.json'
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n\n💾 Detailed results saved to: {output_file}")

    await exchange.close()

    return results, failure_categories


if __name__ == "__main__":
    results, categories = asyncio.run(run_diagnostics())
