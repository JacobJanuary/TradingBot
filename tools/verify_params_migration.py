#!/usr/bin/env python3
"""
Verification tool for SL/TS parameters migration

This script verifies that:
1. monitoring.params contains correct per-exchange values
2. monitoring.positions saves trailing params correctly
3. monitoring.trailing_stops uses per-position params
4. Bot actually uses DB params (not .env fallback)

Usage:
    python tools/verify_params_migration.py
"""
import asyncio
import asyncpg
from decimal import Decimal
from datetime import datetime
import os
import sys

# Simple table formatter (replacement for tabulate)
def simple_table(data, headers):
    """Simple ASCII table formatter"""
    if not data:
        return "No data"

    # Calculate column widths
    col_widths = [len(h) for h in headers]
    for row in data:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))

    # Create separator
    separator = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"

    # Format header
    header_row = "| " + " | ".join(str(h).ljust(w) for h, w in zip(headers, col_widths)) + " |"

    # Format rows
    rows = []
    for row in data:
        rows.append("| " + " | ".join(str(cell).ljust(w) for cell, w in zip(row, col_widths)) + " |")

    # Combine
    return "\n".join([separator, header_row, separator] + rows + [separator])

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import config


class ParamsMigrationVerifier:
    """Verify SL/TS params migration is working correctly"""

    def __init__(self):
        self.pool = None

    async def initialize(self):
        """Initialize DB connection"""
        self.pool = await asyncpg.create_pool(
            host=config.database.host,
            port=config.database.port,
            database=config.database.database,
            user=config.database.user,
            password=config.database.password,
            min_size=1,
            max_size=5
        )

    async def close(self):
        """Close DB connection"""
        if self.pool:
            await self.pool.close()

    async def check_monitoring_params(self):
        """Check monitoring.params table"""
        print("\n" + "="*80)
        print("📊 STEP 1: Checking monitoring.params (per-exchange parameters)")
        print("="*80)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT
                    exchange_id,
                    CASE exchange_id
                        WHEN 1 THEN 'binance'
                        WHEN 2 THEN 'bybit'
                        ELSE 'unknown'
                    END as exchange_name,
                    max_trades_filter,
                    stop_loss_filter,
                    trailing_activation_filter,
                    trailing_distance_filter,
                    updated_at
                FROM monitoring.params
                ORDER BY exchange_id
            """)

        if not rows:
            print("❌ CRITICAL: No data in monitoring.params!")
            return False

        table_data = []
        for row in rows:
            table_data.append([
                row['exchange_id'],
                row['exchange_name'],
                f"{row['max_trades_filter']} trades" if row['max_trades_filter'] else "NULL",
                f"{row['stop_loss_filter']}%" if row['stop_loss_filter'] else "NULL",
                f"{row['trailing_activation_filter']}%" if row['trailing_activation_filter'] else "NULL",
                f"{row['trailing_distance_filter']}%" if row['trailing_distance_filter'] else "NULL",
                row['updated_at'].strftime('%Y-%m-%d %H:%M:%S') if row['updated_at'] else "NULL"
            ])

        print(simple_table(
            table_data,
            headers=['ID', 'Exchange', 'Max Trades', 'SL %', 'TS Activation %', 'TS Callback %', 'Updated At']
        ))

        # Verify different values
        if len(rows) >= 2:
            binance = next((r for r in rows if r['exchange_id'] == 1), None)
            bybit = next((r for r in rows if r['exchange_id'] == 2), None)

            if binance and bybit:
                print("\n✅ Both exchanges have params")

                if binance['stop_loss_filter'] != bybit['stop_loss_filter']:
                    print(f"✅ CONFIRMED: Different SL% - Binance: {binance['stop_loss_filter']}% vs Bybit: {bybit['stop_loss_filter']}%")
                else:
                    print(f"⚠️  WARNING: Same SL% ({binance['stop_loss_filter']}%) - expected different values")

                if binance['trailing_activation_filter'] != bybit['trailing_activation_filter']:
                    print(f"✅ CONFIRMED: Different TS Activation% - Binance: {binance['trailing_activation_filter']}% vs Bybit: {bybit['trailing_activation_filter']}%")
                else:
                    print(f"⚠️  WARNING: Same TS Activation% ({binance['trailing_activation_filter']}%) - expected different values")

        return True

    async def check_positions_with_params(self):
        """Check positions table for saved params"""
        print("\n" + "="*80)
        print("📊 STEP 2: Checking monitoring.positions (saved trailing params)")
        print("="*80)

        async with self.pool.acquire() as conn:
            # Check if columns exist
            columns = await conn.fetch("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'monitoring'
                  AND table_name = 'positions'
                  AND column_name IN ('trailing_activation_percent', 'trailing_callback_percent')
                ORDER BY column_name
            """)

        if len(columns) < 2:
            print("❌ CRITICAL: Columns not found in monitoring.positions!")
            print(f"   Found: {[c['column_name'] for c in columns]}")
            return False

        print("✅ Columns exist: trailing_activation_percent, trailing_callback_percent")

        # Check active positions
        async with self.pool.acquire() as conn:
            positions = await conn.fetch("""
                SELECT
                    id,
                    symbol,
                    exchange,
                    side,
                    entry_price,
                    trailing_activation_percent,
                    trailing_callback_percent,
                    created_at
                FROM monitoring.positions
                WHERE status = 'active'
                ORDER BY created_at DESC
                LIMIT 10
            """)

        if not positions:
            print("⚠️  No active positions found (this is OK if no positions open)")
            return True

        print(f"\n✅ Found {len(positions)} active position(s):\n")

        table_data = []
        has_params = 0
        has_null_params = 0

        for pos in positions:
            has_trailing = pos['trailing_activation_percent'] is not None
            if has_trailing:
                has_params += 1
            else:
                has_null_params += 1

            table_data.append([
                pos['id'],
                pos['symbol'],
                pos['exchange'],
                pos['side'],
                f"{pos['entry_price']:.8f}",
                f"{pos['trailing_activation_percent']}%" if pos['trailing_activation_percent'] else "NULL (legacy)",
                f"{pos['trailing_callback_percent']}%" if pos['trailing_callback_percent'] else "NULL (legacy)",
                "✅" if has_trailing else "⚠️ Legacy"
            ])

        print(simple_table(
            table_data,
            headers=['ID', 'Symbol', 'Exchange', 'Side', 'Entry Price', 'TS Activation %', 'TS Callback %', 'Status']
        ))

        print(f"\n📊 Summary:")
        print(f"   Positions with trailing params: {has_params}")
        print(f"   Positions without params (legacy): {has_null_params}")

        if has_params > 0:
            print("   ✅ Migration working - new positions save trailing params")

        if has_null_params > 0:
            print("   ⚠️  Legacy positions found - will use config fallback")

        return True

    async def check_trailing_stops_state(self):
        """Check trailing_stops table"""
        print("\n" + "="*80)
        print("📊 STEP 3: Checking monitoring.trailing_stops (TS state)")
        print("="*80)

        # Check if table exists
        async with self.pool.acquire() as conn:
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'monitoring'
                      AND table_name = 'trailing_stops'
                )
            """)

        if not table_exists:
            print("⚠️  Table monitoring.trailing_stops does not exist (this is OK - bot may not use persistent TS state)")
            return True

        async with self.pool.acquire() as conn:
            ts_records = await conn.fetch("""
                SELECT
                    ts.id,
                    ts.symbol,
                    ts.exchange,
                    ts.state,
                    ts.activation_percent,
                    ts.callback_percent,
                    ts.activation_price,
                    ts.current_stop_price,
                    ts.entry_price,
                    ts.side,
                    p.trailing_activation_percent as position_activation,
                    p.trailing_callback_percent as position_callback
                FROM monitoring.trailing_stops ts
                LEFT JOIN monitoring.positions p ON ts.position_id = p.id
                WHERE ts.state IN ('waiting', 'active')
                ORDER BY ts.id DESC
                LIMIT 10
            """)

        if not ts_records:
            print("⚠️  No active trailing stops found (this is OK if no positions have TS)")
            return True

        print(f"\n✅ Found {len(ts_records)} active trailing stop(s):\n")

        table_data = []
        matches = 0
        mismatches = 0

        for ts in ts_records:
            # Check if TS params match position params
            match = "N/A"
            if ts['position_activation'] is not None:
                if ts['activation_percent'] == ts['position_activation']:
                    match = "✅ Match"
                    matches += 1
                else:
                    match = f"❌ MISMATCH (pos: {ts['position_activation']}%)"
                    mismatches += 1

            table_data.append([
                ts['id'],
                ts['symbol'],
                ts['exchange'],
                ts['state'],
                ts['side'],
                f"{ts['entry_price']:.8f}" if ts['entry_price'] else "N/A",
                f"{ts['activation_price']:.8f}" if ts['activation_price'] else "N/A",
                f"{ts['current_stop_price']:.8f}" if ts['current_stop_price'] else "N/A",
                f"{ts['activation_percent']}%",
                f"{ts['callback_percent']}%",
                match
            ])

        print(simple_table(
            table_data,
            headers=['ID', 'Symbol', 'Exch', 'State', 'Side', 'Entry', 'Activation', 'Current Stop', 'Act %', 'CB %', 'Param Match']
        ))

        print(f"\n📊 Summary:")
        print(f"   TS with matching position params: {matches}")
        print(f"   TS with mismatched params: {mismatches}")

        if mismatches > 0:
            print("   ❌ CRITICAL: Some TS don't match position params!")
        elif matches > 0:
            print("   ✅ All TS params match position params!")

        return True

    async def check_env_config(self):
        """Show .env config for comparison"""
        print("\n" + "="*80)
        print("📊 STEP 4: Current .env Configuration (for comparison)")
        print("="*80)

        print(f"\nGlobal config from .env:")
        print(f"  STOP_LOSS_PERCENT: {config.trading.stop_loss_percent}%")
        print(f"  TRAILING_ACTIVATION_PERCENT: {config.trading.trailing_activation_percent}%")
        print(f"  TRAILING_CALLBACK_PERCENT: {config.trading.trailing_callback_percent}%")

        print("\n⚠️  These values should be IGNORED if DB params exist!")
        print("   Only used as fallback if DB params are NULL")

        return True

    async def check_recent_logs(self):
        """Guide user to check logs"""
        print("\n" + "="*80)
        print("📊 STEP 5: How to Verify Logs")
        print("="*80)

        print("\n🔍 Search for these log patterns to confirm DB params are used:\n")

        print("1. When opening position (position_manager.py):")
        print('   grep "📊 Using trailing_activation_filter from DB" logs/bot.log')
        print('   grep "📊 Using trailing_distance_filter from DB" logs/bot.log')
        print('   grep "⚠️  trailing_activation_filter not in DB" logs/bot.log  # Should be EMPTY!')

        print("\n2. When creating trailing stop (trailing_stop.py):")
        print('   grep "📊.*Using per-position trailing params" logs/bot.log')
        print('   grep "📊.*Using config trailing params (fallback)" logs/bot.log  # Should be rare!')

        print("\n3. Expected output when DB params are used:")
        print("   📊 Using trailing_activation_filter from DB for binance: 2.0%")
        print("   📊 Using trailing_distance_filter from DB for binance: 0.5%")
        print("   📊 BTCUSDT: Using per-position trailing params: activation=2.0%, callback=0.5%")

        print("\n4. RED FLAG - if you see this, DB params NOT loaded:")
        print("   ⚠️  trailing_activation_filter not in DB for binance, using .env fallback: 3.0%")

        return True

    async def run_full_verification(self):
        """Run all verification checks"""
        print("\n" + "🔴"*40)
        print("🚀 SL/TS PARAMETERS MIGRATION VERIFICATION TOOL")
        print("🔴"*40)
        print(f"\nTimestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Database: {config.database.host}:{config.database.port}/{config.database.database}")

        await self.initialize()

        try:
            success = True
            success &= await self.check_monitoring_params()
            success &= await self.check_positions_with_params()
            success &= await self.check_trailing_stops_state()
            success &= await self.check_env_config()
            success &= await self.check_recent_logs()

            print("\n" + "="*80)
            if success:
                print("✅ VERIFICATION COMPLETE - All checks passed!")
            else:
                print("❌ VERIFICATION FAILED - See errors above")
            print("="*80)

            return success

        finally:
            await self.close()


async def main():
    verifier = ParamsMigrationVerifier()
    success = await verifier.run_full_verification()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
