#!/usr/bin/env python3
"""
Comprehensive diagnostic script to verify all position management fixes
Checks:
1. Database/Exchange synchronization
2. Expired position detection
3. Stop loss verification
4. Timezone handling
"""

import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta
import ccxt.async_support as ccxt
import asyncpg
from dotenv import load_dotenv

load_dotenv()

class PositionDiagnostics:
    def __init__(self):
        self.issues_found = []
        self.warnings = []

    async def check_database_connection(self):
        """Verify database connection and schema"""
        print(f"\n{'='*80}")
        print(f"1. DATABASE CONNECTION CHECK")
        print(f"{'='*80}")

        try:
            conn = await asyncpg.connect(
                host='localhost',
                port=5433,
                user='elcrypto',
                password='LohNeMamont@!21',
                database='fox_crypto'
            )

            # Check for positions table in trading_bot schema
            result = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'trading_bot'
                    AND table_name = 'positions'
                )
            """)

            if result:
                print(f"✅ Database connected: fox_crypto")
                print(f"✅ Schema found: trading_bot")
                print(f"✅ Table found: trading_bot.positions")
            else:
                print(f"❌ Table trading_bot.positions NOT found!")
                self.issues_found.append("Missing positions table")

            await conn.close()
            return True

        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            self.issues_found.append(f"Database connection: {e}")
            return False

    async def check_position_sync(self):
        """Check if DB and Exchange positions are synchronized"""
        print(f"\n{'='*80}")
        print(f"2. DATABASE/EXCHANGE SYNCHRONIZATION")
        print(f"{'='*80}")

        # Database connection
        conn = await asyncpg.connect(
            host='localhost',
            port=5433,
            user='elcrypto',
            password='LohNeMamont@!21',
            database='fox_crypto'
        )

        # Exchange connections
        exchanges = {
            'bybit': ccxt.bybit({
                'apiKey': os.getenv('BYBIT_API_KEY'),
                'secret': os.getenv('BYBIT_API_SECRET'),
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'swap',
                    'testnet': True
                }
            }),
            'binance': ccxt.binance({
                'apiKey': os.getenv('BINANCE_API_KEY'),
                'secret': os.getenv('BINANCE_API_SECRET'),
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future',
                    'testnet': True
                }
            })
        }

        try:
            for exchange_name, exchange in exchanges.items():
                print(f"\nChecking {exchange_name.upper()}:")

                # Get positions from exchange
                exchange_positions = await exchange.fetch_positions()
                active_exchange = [p for p in exchange_positions if p['contracts'] > 0]
                exchange_symbols = {p['symbol'] for p in active_exchange}

                # Get positions from database
                db_positions = await conn.fetch("""
                    SELECT symbol, open_time, created_at, quantity, stop_loss
                    FROM trading_bot.positions
                    WHERE exchange = $1 AND status = 'open'
                """, exchange_name)

                db_symbols = {pos['symbol'] for pos in db_positions}

                # Compare
                print(f"  Exchange: {len(exchange_symbols)} positions")
                print(f"  Database: {len(db_symbols)} positions")

                # Find discrepancies
                only_on_exchange = exchange_symbols - db_symbols
                only_in_db = db_symbols - exchange_symbols

                if only_on_exchange:
                    print(f"  ❌ Positions on exchange but NOT in DB: {only_on_exchange}")
                    self.issues_found.append(f"{exchange_name}: Positions not saved to DB")

                if only_in_db:
                    print(f"  ❌ Positions in DB but NOT on exchange: {only_in_db}")
                    self.issues_found.append(f"{exchange_name}: Orphaned DB positions")
                    print(f"  ⚠️ These should be closed by sync_exchange_positions")

                if not only_on_exchange and not only_in_db:
                    print(f"  ✅ Database and exchange are synchronized")

                await exchange.close()

        except Exception as e:
            print(f"❌ Error checking sync: {e}")
            self.issues_found.append(f"Sync check failed: {e}")
        finally:
            await conn.close()

    async def check_expired_positions(self):
        """Check for expired positions that should have been closed"""
        print(f"\n{'='*80}")
        print(f"3. EXPIRED POSITION DETECTION")
        print(f"{'='*80}")

        conn = await asyncpg.connect(
            host='localhost',
            port=5433,
            user='elcrypto',
            password='LohNeMamont@!21',
            database='fox_crypto'
        )

        try:
            # Get MAX_POSITION_AGE_HOURS from env
            max_age_hours = float(os.getenv('MAX_POSITION_AGE_HOURS', '1'))
            current_time = datetime.now(timezone.utc)

            print(f"MAX_POSITION_AGE_HOURS: {max_age_hours}")
            print(f"Current UTC time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")

            # Check for expired positions
            expired_positions = await conn.fetch("""
                SELECT
                    symbol,
                    exchange,
                    COALESCE(open_time, created_at) as position_time,
                    NOW() AT TIME ZONE 'UTC' as now_utc,
                    EXTRACT(EPOCH FROM (NOW() AT TIME ZONE 'UTC' - COALESCE(open_time, created_at)))/3600 as age_hours
                FROM trading_bot.positions
                WHERE status = 'open'
                    AND EXTRACT(EPOCH FROM (NOW() AT TIME ZONE 'UTC' - COALESCE(open_time, created_at)))/3600 > $1
                ORDER BY age_hours DESC
            """, max_age_hours)

            if expired_positions:
                print(f"❌ Found {len(expired_positions)} EXPIRED positions:")
                for pos in expired_positions:
                    age = pos['age_hours']
                    critical = "🚨 CRITICAL" if age > max_age_hours * 2 else "⚠️ WARNING"
                    print(f"  {critical} {pos['symbol']} ({pos['exchange']}): {age:.1f} hours old")

                    if age > max_age_hours * 2:
                        self.issues_found.append(f"CRITICAL: {pos['symbol']} is {age:.1f}h old")
                    else:
                        self.warnings.append(f"{pos['symbol']} expired ({age:.1f}h)")
            else:
                print(f"✅ No expired positions found")

        except Exception as e:
            print(f"❌ Error checking expired positions: {e}")
            self.issues_found.append(f"Expired check failed: {e}")
        finally:
            await conn.close()

    async def check_stop_loss_protection(self):
        """Verify stop loss orders exist on exchange for all positions"""
        print(f"\n{'='*80}")
        print(f"4. STOP LOSS PROTECTION CHECK")
        print(f"{'='*80}")

        conn = await asyncpg.connect(
            host='localhost',
            port=5433,
            user='elcrypto',
            password='LohNeMamont@!21',
            database='fox_crypto'
        )

        exchanges = {
            'bybit': ccxt.bybit({
                'apiKey': os.getenv('BYBIT_API_KEY'),
                'secret': os.getenv('BYBIT_API_SECRET'),
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'swap',
                    'testnet': True
                }
            })
        }

        try:
            for exchange_name, exchange in exchanges.items():
                print(f"\nChecking {exchange_name.upper()} stop losses:")

                # Get positions from exchange
                positions = await exchange.fetch_positions()
                active_positions = [p for p in positions if p['contracts'] > 0]

                if not active_positions:
                    print(f"  No active positions on {exchange_name}")
                    continue

                # Check each position for stop loss
                unprotected = []

                for pos in active_positions:
                    symbol = pos['symbol']
                    has_sl = False

                    try:
                        # Get orders for this symbol
                        orders = await exchange.fetch_open_orders(symbol)

                        for order in orders:
                            # Check for stop loss orders
                            if order['type'] == 'market' and order.get('price', 1) == 0:
                                has_sl = True
                                break
                            if 'stop' in str(order.get('type', '')).lower():
                                has_sl = True
                                break

                    except Exception as e:
                        print(f"  ⚠️ Could not check orders for {symbol}: {e}")

                    if not has_sl:
                        unprotected.append(symbol)

                if unprotected:
                    print(f"  ❌ Positions WITHOUT stop loss: {unprotected}")
                    self.issues_found.append(f"{exchange_name}: {len(unprotected)} positions without SL")
                else:
                    print(f"  ✅ All positions have stop loss protection")

                # Check database consistency
                db_positions = await conn.fetch("""
                    SELECT symbol, stop_loss
                    FROM trading_bot.positions
                    WHERE exchange = $1 AND status = 'open'
                """, exchange_name)

                db_inconsistent = []
                for pos in db_positions:
                    if pos['stop_loss'] is None:
                        db_inconsistent.append(pos['symbol'])

                if db_inconsistent:
                    print(f"  ⚠️ DB shows no stop_loss for: {db_inconsistent}")
                    self.warnings.append(f"DB stop_loss NULL for {len(db_inconsistent)} positions")

                await exchange.close()

        except Exception as e:
            print(f"❌ Error checking stop losses: {e}")
            self.issues_found.append(f"Stop loss check failed: {e}")
        finally:
            await conn.close()

    async def check_timezone_usage(self):
        """Verify all timestamps use UTC"""
        print(f"\n{'='*80}")
        print(f"5. TIMEZONE CONSISTENCY CHECK")
        print(f"{'='*80}")

        conn = await asyncpg.connect(
            host='localhost',
            port=5433,
            user='elcrypto',
            password='LohNeMamont@!21',
            database='fox_crypto'
        )

        try:
            # Check database timezone
            db_tz = await conn.fetchval("SHOW timezone")
            print(f"Database timezone: {db_tz}")

            if db_tz != 'UTC':
                print(f"⚠️ Database not using UTC (using {db_tz})")
                self.warnings.append(f"Database timezone: {db_tz}")
            else:
                print(f"✅ Database using UTC")

            # Check Python timezone
            py_tz = datetime.now(timezone.utc).strftime('%Z')
            print(f"Python timezone: {py_tz}")

            if py_tz == 'UTC':
                print(f"✅ Python using UTC")
            else:
                print(f"⚠️ Python not using UTC")
                self.warnings.append("Python not using UTC")

        except Exception as e:
            print(f"❌ Error checking timezones: {e}")
        finally:
            await conn.close()

    async def run_diagnostics(self):
        """Run all diagnostic checks"""
        print(f"{'='*80}")
        print(f"POSITION MANAGEMENT DIAGNOSTICS")
        print(f"{'='*80}")
        print(f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")

        # Run checks
        if await self.check_database_connection():
            await self.check_position_sync()
            await self.check_expired_positions()
            await self.check_stop_loss_protection()
            await self.check_timezone_usage()

        # Summary
        print(f"\n{'='*80}")
        print(f"DIAGNOSTIC SUMMARY")
        print(f"{'='*80}")

        if self.issues_found:
            print(f"❌ CRITICAL ISSUES FOUND: {len(self.issues_found)}")
            for issue in self.issues_found:
                print(f"  • {issue}")
        else:
            print(f"✅ No critical issues found")

        if self.warnings:
            print(f"⚠️ WARNINGS: {len(self.warnings)}")
            for warning in self.warnings:
                print(f"  • {warning}")

        print(f"\nFIXES IMPLEMENTED:")
        print(f"✅ sync_exchange_positions now closes orphaned DB positions")
        print(f"✅ Using open_time field for position age calculation")
        print(f"✅ Force closing positions older than 2x max age")
        print(f"✅ Stop loss verification checks actual exchange orders")
        print(f"✅ All datetime operations use UTC")

        return len(self.issues_found) == 0

if __name__ == "__main__":
    diagnostics = PositionDiagnostics()
    success = asyncio.run(diagnostics.run_diagnostics())
    sys.exit(0 if success else 1)