#!/usr/bin/env python3
"""
Real-time monitoring of Trailing Stop activations

Shows live data about:
- Current price vs activation price for each position
- Distance to activation (in %)
- Whether activation percent is from DB or .env
- Live updates every 5 seconds

Usage:
    python tools/monitor_ts_activations.py
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


class TSActivationMonitor:
    """Monitor TS activations in real-time"""

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
            max_size=3
        )

    async def close(self):
        """Close DB connection"""
        if self.pool:
            await self.pool.close()

    async def get_exchange_params(self):
        """Get current monitoring.params"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT
                    CASE exchange_id
                        WHEN 1 THEN 'binance'
                        WHEN 2 THEN 'bybit'
                        ELSE 'unknown'
                    END as exchange_name,
                    trailing_activation_filter,
                    trailing_distance_filter
                FROM monitoring.params
            """)

        return {row['exchange_name']: row for row in rows}

    async def get_ts_status(self):
        """Get current TS status"""
        # Check if trailing_stops table exists
        async with self.pool.acquire() as conn:
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'monitoring'
                      AND table_name = 'trailing_stops'
                )
            """)

        if not table_exists:
            # If no trailing_stops table, get data from positions only
            async with self.pool.acquire() as conn:
                ts_data = await conn.fetch("""
                    SELECT
                        p.id as ts_id,
                        p.symbol,
                        p.exchange,
                        p.side,
                        'active' as state,
                        p.entry_price,
                        NULL as activation_price,
                        NULL as ts_activation_percent,
                        NULL as ts_callback_percent,
                        NULL as current_stop_price,
                        NULL as highest_price,
                        NULL as lowest_price,
                        p.id as position_id,
                        p.quantity,
                        p.trailing_activation_percent as position_activation_percent,
                        p.trailing_callback_percent as position_callback_percent
                    FROM monitoring.positions p
                    WHERE p.status = 'active'
                      AND p.has_trailing_stop = TRUE
                    ORDER BY p.exchange, p.symbol
                """)
            return ts_data

        # If table exists, get full TS data
        async with self.pool.acquire() as conn:
            ts_data = await conn.fetch("""
                SELECT
                    ts.id as ts_id,
                    ts.symbol,
                    ts.exchange,
                    ts.side,
                    ts.state,
                    ts.entry_price,
                    ts.activation_price,
                    ts.activation_percent as ts_activation_percent,
                    ts.callback_percent as ts_callback_percent,
                    ts.current_stop_price,
                    ts.highest_price,
                    ts.lowest_price,
                    p.id as position_id,
                    p.quantity,
                    p.trailing_activation_percent as position_activation_percent,
                    p.trailing_callback_percent as position_callback_percent
                FROM monitoring.trailing_stops ts
                JOIN monitoring.positions p ON ts.position_id = p.id
                WHERE ts.state IN ('waiting', 'active')
                  AND p.status = 'active'
                ORDER BY ts.exchange, ts.symbol
            """)

        return ts_data

    def calculate_distance_to_activation(self, current_price, activation_price, side):
        """Calculate % distance to activation"""
        if not current_price or not activation_price:
            return None

        current_price = Decimal(str(current_price))
        activation_price = Decimal(str(activation_price))

        if side == 'long':
            # For long: need price to go UP to activation_price
            if current_price >= activation_price:
                return 0  # Already at or above activation
            distance_pct = ((activation_price - current_price) / current_price) * 100
        else:  # short
            # For short: need price to go DOWN to activation_price
            if current_price <= activation_price:
                return 0  # Already at or below activation
            distance_pct = ((current_price - activation_price) / current_price) * 100

        return float(distance_pct)

    def format_price_source(self, ts_activation, position_activation, exchange_params, exchange):
        """Determine where activation % comes from"""
        if position_activation is not None:
            # From position (saved from DB at creation time)
            db_value = exchange_params.get(exchange, {}).get('trailing_activation_filter')
            if db_value and abs(float(position_activation) - float(db_value)) < 0.01:
                return f"✅ DB ({position_activation}%)"
            else:
                return f"📌 Position ({position_activation}%)"
        elif ts_activation is not None:
            # From TS state (might be from config fallback)
            return f"⚠️  Config ({ts_activation}%)"
        else:
            # No params saved - legacy position
            return "⚠️  Legacy (no params)"

    async def display_status(self, exchange_params):
        """Display current status"""
        ts_data = await self.get_ts_status()

        # Clear screen (optional)
        print("\033[2J\033[H")  # ANSI escape codes to clear screen and move cursor to top

        print("="*120)
        print(f"🔴 TRAILING STOP ACTIVATION MONITOR - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*120)

        if not ts_data:
            print("\n⚠️  No active trailing stops found")
            return

        # Group by exchange
        exchanges = {}
        for ts in ts_data:
            exch = ts['exchange']
            if exch not in exchanges:
                exchanges[exch] = []
            exchanges[exch].append(ts)

        # Display by exchange
        for exchange, ts_list in exchanges.items():
            print(f"\n📊 Exchange: {exchange.upper()}")

            # Show exchange DB params
            if exchange in exchange_params:
                ep = exchange_params[exchange]
                print(f"   DB Params: activation={ep['trailing_activation_filter']}%, callback={ep['trailing_distance_filter']}%")
            else:
                print(f"   ⚠️  No DB params for {exchange}")

            table_data = []
            for ts in ts_list:
                # Determine current price (highest for long, lowest for short)
                if ts['side'] == 'long':
                    current_price = ts['highest_price'] or ts['entry_price']
                else:
                    current_price = ts['lowest_price'] or ts['entry_price']

                # Calculate activation_price if not available (when using positions table only)
                activation_price = ts['activation_price']
                if activation_price is None and ts['position_activation_percent'] is not None:
                    # Calculate from position params
                    entry_price = Decimal(str(ts['entry_price']))
                    activation_pct = Decimal(str(ts['position_activation_percent']))
                    if ts['side'] == 'long':
                        activation_price = float(entry_price * (1 + activation_pct / 100))
                    else:
                        activation_price = float(entry_price * (1 - activation_pct / 100))

                # Calculate distance to activation
                distance = self.calculate_distance_to_activation(
                    current_price,
                    activation_price,
                    ts['side']
                )

                # Format distance
                if distance is not None:
                    if distance == 0:
                        distance_str = "✅ ACTIVATED"
                    elif distance < 0.5:
                        distance_str = f"🔥 {distance:.2f}% (CLOSE!)"
                    elif distance < 1.0:
                        distance_str = f"🟡 {distance:.2f}%"
                    else:
                        distance_str = f"⚪ {distance:.2f}%"
                else:
                    distance_str = "N/A"

                # Determine param source
                param_source = self.format_price_source(
                    ts['ts_activation_percent'],
                    ts['position_activation_percent'],
                    exchange_params,
                    exchange
                )

                # State indicator
                state_icon = "⏳" if ts['state'] == 'waiting' else "✅"

                # Use callback percent (from TS state or position)
                callback_pct = ts['ts_callback_percent'] or ts['position_callback_percent'] or "N/A"

                table_data.append([
                    ts['symbol'],
                    ts['side'].upper(),
                    f"{current_price:.8f}",
                    f"{activation_price:.8f}" if activation_price else "N/A",
                    distance_str,
                    param_source,
                    f"{callback_pct}%" if callback_pct != "N/A" else "N/A",
                    f"{state_icon} {ts['state']}",
                    f"{ts['current_stop_price']:.8f}" if ts['current_stop_price'] else "N/A"
                ])

            print(simple_table(
                table_data,
                headers=['Symbol', 'Side', 'Current Price', 'Activation Price', 'Distance', 'Activation % Source', 'Callback %', 'State', 'Current Stop']
            ))

        print(f"\n📊 Total Active TS: {len(ts_data)}")
        print("\nLegend:")
        print("  ✅ DB (X%) - Activation % loaded from monitoring.params (CORRECT)")
        print("  📌 Position (X%) - Activation % saved in position (per-position params)")
        print("  ⚠️  Config (X%) - Activation % from .env fallback (SHOULD BE RARE!)")
        print("  ⚠️  Legacy (no params) - Old position created before migration (uses .env)")
        print("\nPress Ctrl+C to exit")

    async def monitor_loop(self):
        """Main monitoring loop"""
        await self.initialize()

        try:
            while True:
                exchange_params = await self.get_exchange_params()
                await self.display_status(exchange_params)
                await asyncio.sleep(5)  # Update every 5 seconds

        except KeyboardInterrupt:
            print("\n\n✅ Monitoring stopped by user")
        finally:
            await self.close()


async def main():
    monitor = TSActivationMonitor()
    await monitor.monitor_loop()


if __name__ == "__main__":
    asyncio.run(main())
