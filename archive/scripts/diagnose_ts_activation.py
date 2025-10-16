#!/usr/bin/env python3
"""
Diagnostic script to compare position data between DB and exchange API
and investigate why Trailing Stop is not activating for profitable positions
"""

import asyncio
import sys
from decimal import Decimal
from datetime import datetime
import json

# Add project root to path
sys.path.insert(0, '/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot')

from database.repository import Repository
from config.settings import config
import ccxt.async_support as ccxt


async def get_db_positions(repository):
    """Get all active positions from database"""
    query = """
        SELECT
            id,
            symbol,
            exchange,
            side,
            quantity,
            entry_price,
            current_price,
            pnl_percentage as pnl_percent,
            trailing_activated,
            has_trailing_stop,
            created_at
        FROM monitoring.positions
        WHERE status = 'active'
        ORDER BY exchange, symbol
    """

    async with repository.pool.acquire() as conn:
        result = await conn.fetch(query)
        return result


async def get_exchange_positions(exchange_name):
    """Get all positions from exchange API"""
    try:
        if exchange_name == 'binance':
            exchange = ccxt.binance({
                'apiKey': config.exchanges['binance'].api_key,
                'secret': config.exchanges['binance'].api_secret,
                'options': {'defaultType': 'future'}
            })
        elif exchange_name == 'bybit':
            exchange = ccxt.bybit({
                'apiKey': config.exchanges['bybit'].api_key,
                'secret': config.exchanges['bybit'].api_secret,
                'options': {'defaultType': 'linear'}
            })
        else:
            return []

        try:
            await exchange.load_markets()
            positions = await exchange.fetch_positions()
            # Filter only open positions
            open_positions = [p for p in positions if float(p.get('contracts', 0)) != 0]
            return open_positions
        finally:
            await exchange.close()

    except Exception as e:
        print(f"❌ Error fetching positions from {exchange_name}: {e}")
        return []


async def get_ts_state(repository, symbol):
    """Get trailing stop state from database"""
    query = """
        SELECT
            symbol,
            state,
            side,
            entry_price,
            highest_price,
            lowest_price,
            current_stop_price,
            activation_percent,
            callback_percent,
            is_activated,
            update_count,
            last_update_time
        FROM monitoring.trailing_stop_state
        WHERE symbol = $1
    """

    async with repository.pool.acquire() as conn:
        result = await conn.fetchrow(query, symbol)
        return result


def calculate_pnl_percent(entry_price, current_price, side):
    """Calculate PnL percentage"""
    if not entry_price or entry_price == 0:
        return 0

    entry = float(entry_price)
    current = float(current_price)

    if side == 'long':
        return ((current - entry) / entry) * 100
    else:  # short
        return ((entry - current) / entry) * 100


async def main():
    print("=" * 80)
    print("TRAILING STOP ACTIVATION DIAGNOSTIC")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Initialize managers
    db_config = {
        'host': config.database.host,
        'port': config.database.port,
        'database': config.database.database,
        'user': config.database.user,
        'password': config.database.password,
    }

    repository = Repository(db_config)
    await repository.initialize()

    try:
        # Get positions from DB
        print("📊 Fetching positions from database...")
        db_positions = await get_db_positions(repository)
        print(f"   Found {len(db_positions)} open positions in DB")
        print()

        # Skip exchange API calls - focus on DB analysis
        print("⚠️  Skipping exchange API (focusing on DB analysis)")
        print()

        # Create empty exchange positions map
        exchange_data = {}

        # Analyze each position
        print("=" * 80)
        print("DETAILED ANALYSIS")
        print("=" * 80)
        print()

        issues_found = []
        positions_with_profit = []

        for db_pos in db_positions:
            symbol = db_pos['symbol']
            exchange = db_pos['exchange']
            side = db_pos['side']

            print(f"{'─' * 80}")
            print(f"🔍 {symbol} ({exchange.upper()}) - {side.upper()}")
            print(f"{'─' * 80}")

            # DB data
            db_entry = float(db_pos['entry_price']) if db_pos['entry_price'] else 0
            db_current = float(db_pos['current_price']) if db_pos['current_price'] else 0
            db_pnl = float(db_pos['pnl_percent']) if db_pos['pnl_percent'] else 0
            db_trailing_activated = db_pos['trailing_activated']
            db_has_trailing_stop = db_pos['has_trailing_stop']

            print(f"📂 DATABASE:")
            print(f"   Entry Price:        ${db_entry:.8f}")
            print(f"   Current Price:      ${db_current:.8f}")
            print(f"   PnL%:               {db_pnl:+.2f}%")
            print(f"   has_trailing_stop:  {db_has_trailing_stop}")
            print(f"   trailing_activated: {db_trailing_activated}")

            # Exchange data
            exchange_pos = exchange_data.get(symbol)
            if exchange_pos:
                ex_entry = float(exchange_pos.get('entryPrice', 0))
                ex_current = float(exchange_pos.get('markPrice', 0))
                ex_pnl_percent = calculate_pnl_percent(ex_entry, ex_current, side)
                ex_unrealized_pnl = float(exchange_pos.get('unrealizedPnl', 0))

                print(f"\n🌐 EXCHANGE API:")
                print(f"   Entry Price:        ${ex_entry:.8f}")
                print(f"   Mark Price:         ${ex_current:.8f}")
                print(f"   PnL%:               {ex_pnl_percent:+.2f}%")
                print(f"   Unrealized PnL:     ${ex_unrealized_pnl:+.2f}")

                # Compare
                entry_diff = abs(db_entry - ex_entry)
                price_diff = abs(db_current - ex_current)
                pnl_diff = abs(db_pnl - ex_pnl_percent)

                print(f"\n📊 COMPARISON:")
                print(f"   Entry Price Diff:   ${entry_diff:.8f}")
                print(f"   Current Price Diff: ${price_diff:.8f}")
                print(f"   PnL% Diff:          {pnl_diff:.2f}%")

                # Check for issues
                if entry_diff > 0.00001:
                    print(f"   ⚠️  Entry price mismatch!")
                    issues_found.append({
                        'symbol': symbol,
                        'issue': 'Entry price mismatch',
                        'db_value': db_entry,
                        'exchange_value': ex_entry
                    })

                if price_diff > ex_current * 0.01:  # More than 1% difference
                    print(f"   ⚠️  Current price significantly outdated!")
                    issues_found.append({
                        'symbol': symbol,
                        'issue': 'Current price outdated',
                        'db_value': db_current,
                        'exchange_value': ex_current
                    })
            else:
                print(f"\n❌ EXCHANGE API: Position not found on {exchange}!")
                issues_found.append({
                    'symbol': symbol,
                    'issue': 'Position not found on exchange',
                    'db_value': 'exists',
                    'exchange_value': 'not found'
                })

            # Get TS state
            ts_state = await get_ts_state(repository, symbol)
            if ts_state:
                print(f"\n🛡️  TRAILING STOP STATE:")
                print(f"   State:              {ts_state['state']}")
                print(f"   Is Activated:       {ts_state['is_activated']}")
                print(f"   Entry Price:        ${float(ts_state['entry_price']):.8f}" if ts_state['entry_price'] else "   Entry Price:        None")
                print(f"   Highest Price:      ${float(ts_state['highest_price']):.8f}" if ts_state['highest_price'] and float(ts_state['highest_price']) < 999999 else "   Highest Price:      N/A (SHORT)")
                print(f"   Lowest Price:       ${float(ts_state['lowest_price']):.8f}" if ts_state['lowest_price'] and float(ts_state['lowest_price']) < 999999 else "   Lowest Price:       N/A (LONG)")
                print(f"   Current Stop:       ${float(ts_state['current_stop_price']):.8f}" if ts_state['current_stop_price'] else "   Current Stop:       None")
                print(f"   Activation Thresh:  {float(ts_state['activation_percent']):.2f}%")
                print(f"   Callback:           {float(ts_state['callback_percent']):.2f}%")
                print(f"   Update Count:       {ts_state['update_count']}")
                print(f"   Last Update:        {ts_state['last_update_time']}")
            else:
                print(f"\n❌ TRAILING STOP: No TS state found in database!")
                issues_found.append({
                    'symbol': symbol,
                    'issue': 'No TS state in database',
                    'db_value': 'missing',
                    'exchange_value': 'N/A'
                })

            # Check if TS should be active
            if exchange_pos:
                actual_pnl = ex_pnl_percent
            else:
                actual_pnl = db_pnl

            print(f"\n🎯 TS ACTIVATION ANALYSIS:")
            print(f"   Current PnL:        {actual_pnl:+.2f}%")
            print(f"   Activation Thresh:  +1.50%")

            if actual_pnl >= 1.5:
                print(f"   ✅ Should be ACTIVE (profit >= +1.5%)")
                positions_with_profit.append({
                    'symbol': symbol,
                    'exchange': exchange,
                    'side': side,
                    'pnl_percent': actual_pnl,
                    'trailing_activated': db_trailing_activated,
                    'has_trailing_stop': db_has_trailing_stop,
                    'ts_state': ts_state['state'] if ts_state else 'NO_STATE'
                })

                if not db_trailing_activated:
                    print(f"   ❌ BUT trailing_activated = False in DB!")
                    issues_found.append({
                        'symbol': symbol,
                        'issue': 'TS should be active but trailing_activated=False',
                        'db_value': db_trailing_activated,
                        'exchange_value': f'PnL={actual_pnl:.2f}%'
                    })

                if not db_has_trailing_stop:
                    print(f"   ❌ BUT has_trailing_stop = False in DB!")
                    issues_found.append({
                        'symbol': symbol,
                        'issue': 'TS should be active but has_trailing_stop=False',
                        'db_value': db_has_trailing_stop,
                        'exchange_value': f'PnL={actual_pnl:.2f}%'
                    })

                if ts_state and ts_state['state'] == 'inactive':
                    print(f"   ❌ BUT TS state = 'inactive' in DB!")
                    issues_found.append({
                        'symbol': symbol,
                        'issue': 'TS should be active but state=inactive',
                        'db_value': ts_state['state'],
                        'exchange_value': f'PnL={actual_pnl:.2f}%'
                    })
            else:
                print(f"   ⚪ Should be INACTIVE (profit < +1.5%)")

            print()

        # Summary
        print("=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print()

        print(f"📊 Total positions analyzed: {len(db_positions)}")
        print(f"💰 Positions with profit >= +1.5%: {len(positions_with_profit)}")
        print(f"⚠️  Issues found: {len(issues_found)}")
        print()

        if positions_with_profit:
            print("💰 POSITIONS THAT SHOULD HAVE ACTIVE TS:")
            print("─" * 80)
            for pos in positions_with_profit:
                status = "✅" if pos['trailing_activated'] else "❌"
                print(f"{status} {pos['symbol']:15s} {pos['exchange']:8s} {pos['side']:6s} "
                      f"PnL: {pos['pnl_percent']:+7.2f}% | "
                      f"trailing_activated={pos['trailing_activated']} | "
                      f"has_trailing_stop={pos['has_trailing_stop']} | "
                      f"ts_state={pos['ts_state']}")
            print()

        if issues_found:
            print("⚠️  ISSUES DETECTED:")
            print("─" * 80)
            for issue in issues_found:
                print(f"❌ {issue['symbol']:15s} - {issue['issue']}")
                print(f"   DB: {issue['db_value']}, Exchange: {issue['exchange_value']}")
            print()

        # Save results to JSON
        report = {
            'timestamp': datetime.now().isoformat(),
            'total_positions': len(db_positions),
            'positions_with_profit': len(positions_with_profit),
            'issues_count': len(issues_found),
            'positions': positions_with_profit,
            'issues': issues_found
        }

        report_file = f"ts_diagnostic_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)

        print(f"📄 Full report saved to: {report_file}")
        print()

    except Exception as e:
        print(f"❌ Error during diagnostics: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await repository.close()


if __name__ == "__main__":
    asyncio.run(main())
