#!/usr/bin/env python3
"""
Generate Test Signals for E2E Testing
Creates 100 test signals (1 every 10 seconds) and monitors execution
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import random
from decimal import Decimal
from datetime import datetime
import asyncpg

# Top 50 trading pairs for each exchange
BINANCE_PAIRS = [
    'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT', 'SOLUSDT',
    'XRPUSDT', 'DOTUSDT', 'DOGEUSDT', 'AVAXUSDT', 'MATICUSDT',
    'LTCUSDT', 'LINKUSDT', 'ATOMUSDT', 'UNIUSDT', 'ETCUSDT',
    'XLMUSDT', 'VETUSDT', 'FILUSDT', 'TRXUSDT', 'ICPUSDT',
    'NEARUSDT', 'ALGOUSDT', 'FTMUSDT', 'HBARUSDT', 'EGLDUSDT',
    'SANDUSDT', 'MANAUSDT', 'AXSUSDT', 'THETAUSDT', 'XTZUSDT',
    'EOSUSDT', 'AAVEUSDT', 'GRTUSDT', 'KSMUSDT', 'CAKEUSDT',
    'MKRUSDT', 'RUNEUSDT', 'WAVESUSDT', 'COMPUSDT', 'ZECUSDT',
    'DASHUSDT', 'ENJUSDT', 'CHZUSDT', 'BATUSDT', 'ZILUSDT',
    'YFIUSDT', 'SUSHIUSDT', 'SNXUSDT', 'CRVUSDT', 'QNTUSDT'
]

BYBIT_PAIRS = [
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT',
    'ADAUSDT', 'AVAXUSDT', 'MATICUSDT', 'DOTUSDT', 'LINKUSDT',
    'LTCUSDT', 'ATOMUSDT', 'NEARUSDT', 'UNIUSDT', 'ETCUSDT',
    'FILUSDT', 'APTUSDT', 'ARBUSDT', 'OPUSDT', 'INJUSDT',
    'SUIUSDT', 'SEIUSDT', 'TIAUSDT', 'WLDUSDT', 'JUPUSDT',
    'RENDERUSDT', 'STRKUSDT', 'PYTHUSDT', 'FETUSDT', 'TAOUSDT',
    'BOMEUSDT', 'ENAUSDT', 'WIFUSDT', 'AIUSDT', 'ARKMUSDT',
    'PONDUSDT', 'MEMEUSDT', 'RNDRUSDT', 'DYMUSDT', 'PIXELUSDT',
    'ACEUSDT', 'NFPUSDT', 'XAIUSDT', 'MANTAUSDT', 'ALTUSDT',
    'JUPUSDT', 'WUSDT', 'RONINUSDT', 'BLURUSDT', 'VANRYUSDT'
]

# Load config from .env
from dotenv import load_dotenv
load_dotenv()

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5433)),
    'database': os.getenv('DB_NAME', 'fox_crypto_test'),
    'user': os.getenv('DB_USER', 'elcrypto'),
    'password': os.getenv('DB_PASSWORD')
}

LEVERAGE = int(os.getenv('LEVERAGE', 10))
STOP_LOSS_PERCENT = float(os.getenv('STOP_LOSS_PERCENT', 2.0))
POSITION_SIZE_USD = float(os.getenv('POSITION_SIZE_USD', 200))


async def get_db_connection():
    """Connect to testnet database"""
    return await asyncpg.connect(**DB_CONFIG)


async def get_latest_price(symbol: str, exchange: str) -> Decimal:
    """Get latest price from market (simplified - returns random for testing)"""
    # In real scenario, fetch from exchange API
    # For testing, return realistic prices
    base_prices = {
        'BTC': 50000.0,
        'ETH': 3000.0,
        'SOL': 100.0,
        'XRP': 0.50,
        'DOGE': 0.08,
        'ADA': 0.40,
        'AVAX': 35.0,
        'MATIC': 0.80,
        'DOT': 6.0,
        'LINK': 15.0
    }

    # Extract base currency
    base = symbol.replace('USDT', '')[:3]
    base_price = base_prices.get(base, 10.0)

    # Add random variation ±5%
    variation = random.uniform(0.95, 1.05)
    return Decimal(str(base_price * variation))


async def create_signal(conn, symbol: str, exchange: str, side: str) -> int:
    """Insert test signal into database"""
    entry_price = await get_latest_price(symbol, exchange)
    score_week = random.uniform(60.0, 90.0)
    score_month = random.uniform(60.0, 90.0)

    query = """
    INSERT INTO monitoring.signals (
        symbol, side, exchange, entry_price, score_week, score_month, created_at
    ) VALUES ($1, $2, $3, $4, $5, $6, NOW())
    RETURNING id
    """

    signal_id = await conn.fetchval(
        query, symbol, side, exchange, entry_price, score_week, score_month
    )

    return signal_id


async def check_position_opened(conn, signal_id: int, timeout: int = 30) -> dict:
    """Check if position was opened for signal"""
    query = """
    SELECT
        id, symbol, side, status,
        has_stop_loss, stop_loss_price,
        entry_price, quantity
    FROM monitoring.positions
    WHERE signal_id = $1
    """

    for i in range(timeout):
        position = await conn.fetchrow(query, signal_id)
        if position:
            return dict(position)
        await asyncio.sleep(1)

    return None


async def monitor_test_progress(conn):
    """Monitor test progress in real-time"""
    while True:
        stats = await conn.fetchrow("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN has_stop_loss THEN 1 END) as with_sl,
                COUNT(CASE WHEN status='open' THEN 1 END) as open_count,
                COUNT(CASE WHEN status='error' THEN 1 END) as error_count
            FROM monitoring.positions
            WHERE created_at > NOW() - INTERVAL '10 minutes'
        """)

        print(f"\r[{datetime.now().strftime('%H:%M:%S')}] "
              f"Positions: {stats['total']} | "
              f"With SL: {stats['with_sl']}/{stats['total']} | "
              f"Open: {stats['open_count']} | "
              f"Errors: {stats['error_count']}",
              end='', flush=True)

        await asyncio.sleep(5)


async def main():
    """Main test execution"""
    print("=" * 80)
    print("🧪 E2E TEST: Generate 100 Test Signals")
    print("=" * 80)
    print(f"Config:")
    print(f"  - Database: {DB_CONFIG['database']} on port {DB_CONFIG['port']}")
    print(f"  - Leverage: {LEVERAGE}x")
    print(f"  - Stop Loss: {STOP_LOSS_PERCENT}%")
    print(f"  - Position Size: ${POSITION_SIZE_USD}")
    print(f"  - Interval: 10 seconds per signal")
    print(f"  - Total signals: 100")
    print("=" * 80)
    print()

    # Connect to database
    conn = await get_db_connection()
    print("✅ Connected to database")

    # Start monitoring task
    monitor_task = asyncio.create_task(monitor_test_progress(conn))

    # Generate signals
    results = {
        'created': 0,
        'opened': 0,
        'with_sl': 0,
        'failed': 0
    }

    try:
        for i in range(100):
            # Select random exchange and pair
            exchange = random.choice(['binance', 'bybit'])
            pairs = BINANCE_PAIRS if exchange == 'binance' else BYBIT_PAIRS
            symbol = random.choice(pairs)
            side = random.choice(['long', 'short'])

            try:
                # Create signal
                signal_id = await create_signal(conn, symbol, exchange, side)
                results['created'] += 1

                print(f"\n[{i+1}/100] Signal #{signal_id}: {exchange.upper()} {symbol} {side.upper()}")

                # Wait for position to open (30 seconds timeout)
                position = await check_position_opened(conn, signal_id, timeout=30)

                if position:
                    results['opened'] += 1
                    if position['has_stop_loss']:
                        results['with_sl'] += 1
                        sl_emoji = "✅"
                    else:
                        sl_emoji = "❌"

                    print(f"  Position #{position['id']}: {position['status']} | "
                          f"SL: {sl_emoji} {position['stop_loss_price']} | "
                          f"Entry: {position['entry_price']}")
                else:
                    results['failed'] += 1
                    print(f"  ⚠️  Position NOT opened after 30s")

            except Exception as e:
                results['failed'] += 1
                print(f"  ❌ Error: {e}")

            # Wait 10 seconds before next signal
            if i < 99:  # Don't wait after last signal
                await asyncio.sleep(10)

        # Final summary
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

        print("\n")
        print("=" * 80)
        print("📊 TEST SUMMARY")
        print("=" * 80)
        print(f"Signals Created:     {results['created']}/100")
        print(f"Positions Opened:    {results['opened']}/{results['created']} "
              f"({results['opened']/max(results['created'],1)*100:.1f}%)")
        print(f"With Stop Loss:      {results['with_sl']}/{results['opened']} "
              f"({results['with_sl']/max(results['opened'],1)*100:.1f}%)")
        print(f"Failed:              {results['failed']}")
        print("=" * 80)

        # Final database check
        final_stats = await conn.fetchrow("""
            SELECT
                COUNT(*) as total_positions,
                COUNT(CASE WHEN has_stop_loss THEN 1 END) as total_with_sl,
                COUNT(CASE WHEN status='open' THEN 1 END) as total_open,
                COUNT(CASE WHEN status='error' THEN 1 END) as total_errors
            FROM monitoring.positions
            WHERE created_at > NOW() - INTERVAL '20 minutes'
        """)

        print(f"\nFinal Database Stats:")
        print(f"  Total Positions:   {final_stats['total_positions']}")
        print(f"  With Stop Loss:    {final_stats['total_with_sl']}")
        print(f"  Open:              {final_stats['total_open']}")
        print(f"  Errors:            {final_stats['total_errors']}")

        # Success criteria
        success_rate = results['opened'] / max(results['created'], 1) * 100
        sl_rate = results['with_sl'] / max(results['opened'], 1) * 100

        print("\n" + "=" * 80)
        if success_rate >= 90 and sl_rate >= 95:
            print("✅ TEST PASSED")
            print(f"  - {success_rate:.1f}% positions opened (target: ≥90%)")
            print(f"  - {sl_rate:.1f}% with stop loss (target: ≥95%)")
        elif success_rate >= 80:
            print("⚠️  TEST PARTIALLY PASSED")
            print(f"  - {success_rate:.1f}% positions opened (acceptable)")
            print(f"  - {sl_rate:.1f}% with stop loss (check logs)")
        else:
            print("❌ TEST FAILED")
            print(f"  - {success_rate:.1f}% positions opened (target: ≥90%)")
            print(f"  - {sl_rate:.1f}% with stop loss (target: ≥95%)")
        print("=" * 80)

        return 0 if success_rate >= 90 and sl_rate >= 95 else 1

    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        monitor_task.cancel()
        return 130

    finally:
        await conn.close()


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
