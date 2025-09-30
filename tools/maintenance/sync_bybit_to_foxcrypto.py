#!/usr/bin/env python3
"""
Sync Bybit positions directly to fox_crypto database
"""
import asyncio
import asyncpg
import ccxt.async_support as ccxt
import os
from datetime import datetime
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()

async def sync_bybit_positions():
    """Sync Bybit positions from exchange to fox_crypto database"""

    # Connect to fox_crypto database using env settings
    conn = await asyncpg.connect(
        host=os.getenv('DB_HOST'),
        port=int(os.getenv('DB_PORT')),
        database=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD')
    )

    # Initialize Bybit
    exchange = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'enableRateLimit': True,
        'options': {
            'defaultType': 'linear',
            'recvWindow': 10000
        }
    })
    exchange.set_sandbox_mode(True)

    print('=== SYNCING BYBIT POSITIONS TO FOX_CRYPTO ===\n')

    try:
        # Get positions from Bybit
        positions = await exchange.fetch_positions()
        open_positions = [p for p in positions if p['contracts'] > 0]

        print(f'Found {len(open_positions)} open positions on Bybit\n')

        if open_positions:
            # Close old Bybit positions in DB
            result = await conn.execute("""
                UPDATE trading_bot.positions
                SET status = 'closed', closed_at = CURRENT_TIMESTAMP
                WHERE exchange = 'bybit' AND status = 'open'
            """)

            # Extract number of affected rows
            closed = int(result.split()[-1]) if result else 0

            if closed:
                print(f'Closed {closed} old Bybit positions in database\n')

            # Add current positions
            added = 0
            for pos in open_positions:
                symbol = pos['symbol']
                side = pos['side']
                contracts = pos['contracts']
                entry_price = float(pos['info'].get('avgPrice', 0)) if pos['info'] else 0
                mark_price = float(pos['info'].get('markPrice', entry_price)) if pos['info'] else entry_price

                # Calculate PnL
                if side == 'long':
                    unrealized_pnl = contracts * (mark_price - entry_price)
                else:
                    unrealized_pnl = contracts * (entry_price - mark_price)

                # Check for existing stop loss orders
                stop_loss = None
                try:
                    orders = await exchange.fetch_open_orders(symbol)
                    for order in orders:
                        if order['type'] in ['stop', 'stop_market', 'stop_loss']:
                            stop_loss = order.get('stopPrice')
                            break
                except:
                    pass

                # Insert into trading_bot.positions
                await conn.execute("""
                    INSERT INTO trading_bot.positions
                    (symbol, exchange, side, quantity, entry_price, current_price,
                     stop_loss, status, pnl, created_at, updated_at, has_stop_loss)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, $10)
                """, symbol, 'bybit', side, float(contracts),
                    float(entry_price), float(mark_price),
                    float(stop_loss) if stop_loss else None,
                    'open', float(unrealized_pnl), stop_loss is not None)

                added += 1
                status = '✅ SL' if stop_loss else '❌ NO SL'
                pnl_pct = ((mark_price - entry_price) / entry_price * 100) if side == 'long' else ((entry_price - mark_price) / entry_price * 100)
                print(f'{added:2}. {symbol:20} | {side:5} | Entry: ${entry_price:.4f} | PnL: {pnl_pct:+.2f}% | {status}')

            print(f'\n✅ Synced {added} positions to fox_crypto database')

            # Verify result
            result = await conn.fetch("""
                SELECT exchange, COUNT(*) as count
                FROM trading_bot.positions
                WHERE status = 'open'
                GROUP BY exchange
                ORDER BY exchange
            """)

            print('\nTotal open positions in database:')
            total = 0
            for row in result:
                print(f'  {row["exchange"]}: {row["count"]}')
                total += row["count"]
            print(f'  TOTAL: {total}')

        else:
            print('No open positions to sync')

    except Exception as e:
        print(f'❌ Error: {e}')
        import traceback
        traceback.print_exc()

    finally:
        await conn.close()
        await exchange.close()

if __name__ == '__main__':
    asyncio.run(sync_bybit_positions())