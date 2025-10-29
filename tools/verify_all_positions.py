#!/usr/bin/env python3
"""
Comprehensive position verification tool

Checks:
1. Database positions vs Exchange positions
2. Direction (side) matches
3. Entry price matches
4. Position size matches
5. Stop-loss correctly set per exchange (different % for each)
"""
import asyncio
import asyncpg
import sys
import os
from decimal import Decimal

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import config


async def get_db_positions():
    """Get all active positions from database"""
    pool = await asyncpg.create_pool(
        host=config.database.host,
        port=config.database.port,
        database=config.database.database,
        user=config.database.user,
        password=config.database.password,
        min_size=1,
        max_size=2
    )

    try:
        async with pool.acquire() as conn:
            # Get positions with their params
            positions = await conn.fetch("""
                SELECT
                    id,
                    symbol,
                    exchange,
                    side,
                    quantity,
                    entry_price,
                    stop_loss_price,
                    trailing_activation_percent,
                    trailing_callback_percent,
                    current_price,
                    status,
                    has_trailing_stop,
                    created_at
                FROM monitoring.positions
                WHERE status = 'active'
                ORDER BY exchange, symbol
            """)

            # Get exchange params for comparison
            params = await conn.fetch("""
                SELECT
                    CASE exchange_id
                        WHEN 1 THEN 'binance'
                        WHEN 2 THEN 'bybit'
                        ELSE 'unknown'
                    END as exchange_name,
                    stop_loss_filter,
                    trailing_activation_filter,
                    trailing_distance_filter
                FROM monitoring.params
            """)

            return positions, {p['exchange_name']: p for p in params}

    finally:
        await pool.close()


async def get_exchange_positions():
    """Get positions from exchanges via API"""
    import ccxt.async_support as ccxt

    # Get API keys from config
    binance_cfg = config.exchanges.get('binance')
    bybit_cfg = config.exchanges.get('bybit')

    # Create exchanges
    binance = ccxt.binance({
        'apiKey': binance_cfg.api_key,
        'secret': binance_cfg.api_secret,
        'enableRateLimit': True
    })

    bybit = ccxt.bybit({
        'apiKey': bybit_cfg.api_key,
        'secret': bybit_cfg.api_secret,
        'enableRateLimit': True
    })

    positions_by_exchange = {}

    # Fetch Binance positions
    try:
        positions = await binance.fetch_positions()
        active = []
        for pos in positions:
            size = float(pos.get('info', {}).get('positionAmt', 0))
            if abs(size) > 0:
                active.append(pos)
        positions_by_exchange['binance'] = active
        print(f"   ✅ Binance: {len(active)} active positions")
        if active:
            symbols = [p['symbol'] for p in active]
            print(f"      Symbols: {', '.join(symbols)}")
    except Exception as e:
        print(f"   ❌ Binance error: {e}")
        positions_by_exchange['binance'] = []

    # Fetch Bybit positions
    try:
        positions = await bybit.fetch_positions(params={'category': 'linear'})
        active = []
        for pos in positions:
            contracts = float(pos.get('contracts', 0) or 0)
            if abs(contracts) > 0:
                active.append(pos)
        positions_by_exchange['bybit'] = active
        print(f"   ✅ Bybit: {len(active)} active positions")
        if active:
            symbols = [p['symbol'] for p in active]
            print(f"      Symbols: {', '.join(symbols)}")
    except Exception as e:
        print(f"   ❌ Bybit error: {e}")
        positions_by_exchange['bybit'] = []

    # Close exchanges
    await binance.close()
    await bybit.close()

    return positions_by_exchange


def calculate_expected_sl(entry_price, side, sl_percent):
    """Calculate expected stop-loss price"""
    entry = Decimal(str(entry_price))
    sl_pct = Decimal(str(sl_percent))

    if side == 'long':
        # SL below entry for long
        expected_sl = entry * (1 - sl_pct / 100)
    else:
        # SL above entry for short
        expected_sl = entry * (1 + sl_pct / 100)

    return float(expected_sl)


async def verify_positions():
    """Main verification function"""
    print("=" * 120)
    print("🔍 COMPREHENSIVE POSITION VERIFICATION")
    print("=" * 120)
    print()

    # Get data
    print("📊 Fetching positions from database...")
    db_positions, exchange_params = await get_db_positions()
    print(f"   Found {len(db_positions)} active positions in DB")
    print()

    print("📡 Fetching positions from exchanges...")
    api_positions = await get_exchange_positions()
    print(f"   Binance: {len(api_positions.get('binance', []))} positions")
    print(f"   Bybit: {len(api_positions.get('bybit', []))} positions")
    print()

    # Display exchange params
    print("📋 Exchange Parameters (from monitoring.params):")
    for exch, params in exchange_params.items():
        print(f"   {exch.upper()}:")
        print(f"     Stop Loss: {params['stop_loss_filter']}%")
        print(f"     TS Activation: {params['trailing_activation_filter']}%")
        print(f"     TS Callback: {params['trailing_distance_filter']}%")
    print()
    print("=" * 120)
    print()

    # Verify each position
    issues = []
    verified_count = 0

    for db_pos in db_positions:
        symbol = db_pos['symbol']
        exchange = db_pos['exchange']

        print(f"🔍 Verifying {symbol} on {exchange.upper()}")
        print("-" * 120)

        # Get exchange position
        # Normalize symbol for comparison (API returns "SUSHI/USDT:USDT", DB has "SUSHIUSDT")
        def normalize_symbol(api_symbol):
            # Remove / and :USDT from API symbol
            return api_symbol.replace('/', '').replace(':USDT', '')

        api_pos_list = api_positions.get(exchange, [])
        api_pos = next((p for p in api_pos_list if normalize_symbol(p['symbol']) == symbol), None)

        if not api_pos:
            print(f"   ❌ NOT FOUND on exchange API!")
            issues.append({
                'symbol': symbol,
                'exchange': exchange,
                'issue': 'Position not found on exchange',
                'severity': 'CRITICAL'
            })
            print()
            continue

        # Extract data
        db_side = db_pos['side']
        db_entry = float(db_pos['entry_price'])
        db_quantity = float(db_pos['quantity'])
        db_sl = float(db_pos['stop_loss_price']) if db_pos['stop_loss_price'] else None

        # Get exchange data
        api_side_raw = api_pos.get('side', '').lower()
        api_entry = float(api_pos.get('entryPrice', 0))
        api_quantity = abs(float(api_pos.get('contracts', 0) or api_pos.get('info', {}).get('positionAmt', 0)))

        # Normalize side
        if exchange == 'binance':
            api_side = 'long' if api_side_raw == 'long' or float(api_pos.get('info', {}).get('positionAmt', 0)) > 0 else 'short'
        else:
            api_side = api_side_raw

        # Get expected SL %
        expected_sl_percent = float(exchange_params[exchange]['stop_loss_filter'])
        expected_sl_price = calculate_expected_sl(db_entry, db_side, expected_sl_percent)

        # Check #1: Side matches
        side_match = db_side == api_side
        if not side_match:
            print(f"   ❌ SIDE MISMATCH: DB={db_side}, API={api_side}")
            issues.append({
                'symbol': symbol,
                'exchange': exchange,
                'issue': f'Side mismatch: DB={db_side}, API={api_side}',
                'severity': 'CRITICAL'
            })
        else:
            print(f"   ✅ Side: {db_side} == {api_side}")

        # Check #2: Entry price matches (within 0.01% tolerance)
        entry_diff_pct = abs(db_entry - api_entry) / db_entry * 100 if db_entry else 0
        entry_match = entry_diff_pct < 0.01
        if not entry_match:
            print(f"   ⚠️  Entry price diff: DB={db_entry:.8f}, API={api_entry:.8f} ({entry_diff_pct:.4f}%)")
            issues.append({
                'symbol': symbol,
                'exchange': exchange,
                'issue': f'Entry price mismatch: {entry_diff_pct:.4f}%',
                'severity': 'WARNING'
            })
        else:
            print(f"   ✅ Entry: {db_entry:.8f} ≈ {api_entry:.8f}")

        # Check #3: Quantity matches (within 1% tolerance)
        qty_diff_pct = abs(db_quantity - api_quantity) / db_quantity * 100 if db_quantity else 0
        qty_match = qty_diff_pct < 1.0
        if not qty_match:
            print(f"   ⚠️  Quantity diff: DB={db_quantity:.8f}, API={api_quantity:.8f} ({qty_diff_pct:.2f}%)")
            issues.append({
                'symbol': symbol,
                'exchange': exchange,
                'issue': f'Quantity mismatch: {qty_diff_pct:.2f}%',
                'severity': 'WARNING'
            })
        else:
            print(f"   ✅ Quantity: {db_quantity:.8f} ≈ {api_quantity:.8f}")

        # Check #4: Stop-loss correct for exchange
        if db_sl:
            # Calculate actual SL %
            if db_side == 'long':
                actual_sl_pct = (db_entry - db_sl) / db_entry * 100
            else:
                actual_sl_pct = (db_sl - db_entry) / db_entry * 100

            sl_diff = abs(actual_sl_pct - expected_sl_percent)
            sl_match = sl_diff < 0.1  # Within 0.1%

            if not sl_match:
                print(f"   ❌ SL INCORRECT: Expected {expected_sl_percent}%, Actual {actual_sl_pct:.2f}%")
                print(f"      DB SL: {db_sl:.8f}")
                print(f"      Expected SL: {expected_sl_price:.8f}")
                print(f"      Diff: {sl_diff:.2f}%")
                issues.append({
                    'symbol': symbol,
                    'exchange': exchange,
                    'issue': f'SL incorrect: Expected {expected_sl_percent}%, got {actual_sl_pct:.2f}%',
                    'severity': 'HIGH'
                })
            else:
                print(f"   ✅ Stop-loss: {actual_sl_pct:.2f}% ≈ {expected_sl_percent}% (price={db_sl:.8f})")
        else:
            print(f"   ⚠️  No stop-loss in DB")
            issues.append({
                'symbol': symbol,
                'exchange': exchange,
                'issue': 'No stop-loss set',
                'severity': 'HIGH'
            })

        # Check #5: Trailing params (if saved)
        if db_pos['trailing_activation_percent'] is not None:
            ts_activation = float(db_pos['trailing_activation_percent'])
            expected_ts_activation = float(exchange_params[exchange]['trailing_activation_filter'])

            if abs(ts_activation - expected_ts_activation) < 0.01:
                print(f"   ✅ TS Activation: {ts_activation}% == {expected_ts_activation}%")
            else:
                print(f"   ⚠️  TS Activation: {ts_activation}% != {expected_ts_activation}%")
        else:
            print(f"   ⚠️  No TS params saved (legacy position)")

        if side_match and entry_match and qty_match and sl_match:
            verified_count += 1
            print(f"   🎯 VERIFIED: All checks passed")
        else:
            print(f"   ⚠️  ISSUES FOUND")

        print()

    # Summary
    print("=" * 120)
    print("📊 VERIFICATION SUMMARY")
    print("=" * 120)
    print(f"Total positions checked: {len(db_positions)}")
    print(f"Fully verified: {verified_count}")
    print(f"Issues found: {len(issues)}")
    print()

    if issues:
        print("❌ ISSUES DETAILS:")
        print()

        # Group by severity
        critical = [i for i in issues if i['severity'] == 'CRITICAL']
        high = [i for i in issues if i['severity'] == 'HIGH']
        warnings = [i for i in issues if i['severity'] == 'WARNING']

        if critical:
            print("🔴 CRITICAL:")
            for issue in critical:
                print(f"   {issue['symbol']} ({issue['exchange']}): {issue['issue']}")
            print()

        if high:
            print("🟠 HIGH:")
            for issue in high:
                print(f"   {issue['symbol']} ({issue['exchange']}): {issue['issue']}")
            print()

        if warnings:
            print("🟡 WARNINGS:")
            for issue in warnings:
                print(f"   {issue['symbol']} ({issue['exchange']}): {issue['issue']}")
            print()

    else:
        print("✅ ALL POSITIONS VERIFIED SUCCESSFULLY!")
        print()

    # Final verdict
    print("=" * 120)
    if not issues:
        print("🎯 VERDICT: ✅ PERFECT - All positions match DB and have correct SL for their exchange")
    elif critical:
        print("🎯 VERDICT: 🔴 CRITICAL ISSUES - Immediate action required")
    elif high:
        print("🎯 VERDICT: 🟠 HIGH PRIORITY - Review and fix recommended")
    else:
        print("🎯 VERDICT: 🟡 MINOR ISSUES - Cosmetic differences only")
    print("=" * 120)


if __name__ == "__main__":
    asyncio.run(verify_positions())
