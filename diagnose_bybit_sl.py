#!/usr/bin/env python3
"""
Diagnose Bybit stop-loss issue
Check what Bybit API returns for position.info.stopLoss
"""

import asyncio
import ccxt.async_support as ccxt
import os
import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()


async def check_bybit_positions():
    """Check Bybit positions and their stop losses"""

    # Initialize Bybit
    exchange = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'enableRateLimit': True,
        'options': {
            'defaultType': 'linear',  # USDT perpetual futures
            'adjustForTimeDifference': True
        }
    })

    # Set testnet mode
    testnet = os.getenv('BYBIT_TESTNET', 'true').lower() == 'true'
    if testnet:
        exchange.set_sandbox_mode(True)
        logger.info("🧪 Using Bybit TESTNET")
    else:
        logger.info("💰 Using Bybit MAINNET")

    try:
        # Fetch open positions
        logger.info("\n" + "=" * 60)
        logger.info("CHECKING BYBIT POSITIONS")
        logger.info("=" * 60)

        positions = await exchange.fetch_positions()

        active_positions = [p for p in positions if float(p.get('contracts', 0)) > 0]
        logger.info(f"\n📊 Found {len(active_positions)} active positions on Bybit")

        for pos in active_positions:
            symbol = pos['symbol']
            contracts = pos.get('contracts', 0)
            side = pos.get('side')
            mark_price = pos.get('markPrice')
            entry_price = pos.get('average') or pos.get('info', {}).get('avgPrice')

            # CRITICAL: Check position.info.stopLoss
            info = pos.get('info', {})
            stop_loss_raw = info.get('stopLoss', '0')
            take_profit_raw = info.get('takeProfit', '0')

            logger.info(f"\n{'='*50}")
            logger.info(f"📌 Position: {symbol}")
            logger.info(f"  Side: {side}, Contracts: {contracts}")
            logger.info(f"  Entry Price: {entry_price}")
            logger.info(f"  Mark Price: {mark_price}")
            logger.info(f"  ⚠️ stopLoss field: '{stop_loss_raw}' (type: {type(stop_loss_raw)})")
            logger.info(f"  ⚠️ takeProfit field: '{take_profit_raw}' (type: {type(take_profit_raw)})")

            # Check if this is really a stop loss price
            if stop_loss_raw and stop_loss_raw not in ['0', '0.00', '', None]:
                stop_loss_float = float(stop_loss_raw)
                entry_float = float(entry_price) if entry_price else 0

                # For a real stop loss:
                # - Long position: SL should be BELOW entry price
                # - Short position: SL should be ABOVE entry price

                if side == 'long':
                    if stop_loss_float < entry_float:
                        logger.info(f"  ✅ Valid SL for LONG: {stop_loss_float} < {entry_float}")
                    else:
                        logger.error(f"  ❌ INVALID SL for LONG: {stop_loss_float} >= {entry_float}")
                        logger.error(f"  ⚠️ This might be entry price, not stop loss!")
                elif side == 'short':
                    if stop_loss_float > entry_float:
                        logger.info(f"  ✅ Valid SL for SHORT: {stop_loss_float} > {entry_float}")
                    else:
                        logger.error(f"  ❌ INVALID SL for SHORT: {stop_loss_float} <= {entry_float}")
                        logger.error(f"  ⚠️ This might be entry price, not stop loss!")
            else:
                logger.warning(f"  ⚠️ NO STOP LOSS SET (value: '{stop_loss_raw}')")

        # Also check for stop orders
        logger.info(f"\n{'='*60}")
        logger.info("CHECKING STOP ORDERS")
        logger.info("=" * 60)

        for pos in active_positions:
            symbol = pos['symbol']

            try:
                # Check for conditional stop orders
                stop_orders = await exchange.fetch_open_orders(
                    symbol,
                    params={
                        'category': 'linear',
                        'orderFilter': 'StopOrder'
                    }
                )

                if stop_orders:
                    logger.info(f"\n📌 {symbol}: Found {len(stop_orders)} stop orders")
                    for order in stop_orders:
                        logger.info(f"  - Order ID: {order['id']}")
                        logger.info(f"    Type: {order.get('type')}, Side: {order.get('side')}")
                        logger.info(f"    Stop Price: {order.get('stopPrice')}")
                        logger.info(f"    Trigger Price: {order.get('triggerPrice')}")
                else:
                    logger.warning(f"\n📌 {symbol}: NO stop orders found")

            except Exception as e:
                logger.error(f"Error checking stop orders for {symbol}: {e}")

        logger.info(f"\n{'='*60}")
        logger.info("DIAGNOSIS SUMMARY")
        logger.info("=" * 60)

        no_sl_positions = []
        invalid_sl_positions = []

        for pos in active_positions:
            symbol = pos['symbol']
            info = pos.get('info', {})
            stop_loss_raw = info.get('stopLoss', '0')

            if stop_loss_raw in ['0', '0.00', '', None]:
                no_sl_positions.append(symbol)
            else:
                # Check if SL makes sense
                stop_loss_float = float(stop_loss_raw)
                entry_price = float(pos.get('average') or pos.get('info', {}).get('avgPrice') or 0)
                side = pos.get('side')

                if side == 'long' and stop_loss_float >= entry_price:
                    invalid_sl_positions.append(f"{symbol} (SL={stop_loss_float} >= Entry={entry_price})")
                elif side == 'short' and stop_loss_float <= entry_price:
                    invalid_sl_positions.append(f"{symbol} (SL={stop_loss_float} <= Entry={entry_price})")

        if no_sl_positions:
            logger.error(f"\n🔴 Positions WITHOUT stop loss: {', '.join(no_sl_positions)}")

        if invalid_sl_positions:
            logger.error(f"\n🔴 Positions with INVALID stop loss values:")
            for pos in invalid_sl_positions:
                logger.error(f"  - {pos}")

        if not no_sl_positions and not invalid_sl_positions:
            logger.info("\n✅ All positions have valid stop losses")
        else:
            logger.error(f"\n⚠️ CRITICAL: {len(no_sl_positions)} positions without SL, "
                        f"{len(invalid_sl_positions)} with invalid SL values!")

    except Exception as e:
        logger.error(f"Error checking positions: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        await exchange.close()


if __name__ == "__main__":
    asyncio.run(check_bybit_positions())