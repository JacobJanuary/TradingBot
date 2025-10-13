#!/usr/bin/env python3
"""
Diagnose Binance stop-loss issue
Check what orders are being mistaken for stop-loss orders
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


async def check_binance_positions():
    """Check Binance positions and their orders"""

    # Initialize Binance
    exchange = ccxt.binance({
        'apiKey': os.getenv('BINANCE_API_KEY'),
        'secret': os.getenv('BINANCE_API_SECRET'),
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',  # USDT perpetual futures
            'adjustForTimeDifference': True
        }
    })

    # Set testnet mode
    testnet = os.getenv('BINANCE_TESTNET', 'true').lower() == 'true'
    if testnet:
        exchange.set_sandbox_mode(True)
        logger.info("🧪 Using Binance TESTNET")
    else:
        logger.info("💰 Using Binance MAINNET")

    try:
        # Fetch open positions
        logger.info("\n" + "=" * 60)
        logger.info("CHECKING BINANCE POSITIONS")
        logger.info("=" * 60)

        positions = await exchange.fetch_positions()

        active_positions = [p for p in positions if float(p.get('contracts', 0)) > 0]
        logger.info(f"\n📊 Found {len(active_positions)} active positions on Binance")

        symbols_to_check = []

        for pos in active_positions:
            symbol = pos['symbol']
            contracts = pos.get('contracts', 0)
            side = pos.get('side')
            mark_price = pos.get('markPrice')
            entry_price = pos.get('average')
            pnl = pos.get('percentage')

            symbols_to_check.append(symbol)

            logger.info(f"\n{'='*50}")
            logger.info(f"📌 Position: {symbol}")
            logger.info(f"  Side: {side}, Contracts: {contracts}")
            logger.info(f"  Entry Price: {entry_price}")
            logger.info(f"  Mark Price: {mark_price}")
            logger.info(f"  PnL: {pnl}%")

        # Check orders for each position
        logger.info(f"\n{'='*60}")
        logger.info("CHECKING ORDERS FOR EACH POSITION")
        logger.info("=" * 60)

        for symbol in symbols_to_check:
            logger.info(f"\n📌 Checking orders for {symbol}:")

            try:
                # Get ALL open orders
                all_orders = await exchange.fetch_open_orders(symbol)

                if all_orders:
                    logger.info(f"  Found {len(all_orders)} open orders:")

                    for order in all_orders:
                        order_id = order['id']
                        order_type = order.get('type')
                        order_side = order.get('side')
                        order_price = order.get('price')
                        stop_price = order.get('stopPrice')
                        trigger_price = order.get('triggerPrice')

                        # Check info field for more details
                        info = order.get('info', {})
                        orig_type = info.get('origType', '')

                        logger.info(f"\n  Order ID: {order_id}")
                        logger.info(f"    Type: {order_type}, Side: {order_side}")
                        logger.info(f"    Price: {order_price}")
                        logger.info(f"    Stop Price: {stop_price}")
                        logger.info(f"    Trigger Price: {trigger_price}")
                        logger.info(f"    Original Type: {orig_type}")
                        logger.info(f"    Status: {order.get('status')}")

                        # Analyze if this could be mistaken for SL
                        is_stop_loss = False
                        reason = ""

                        # Check various conditions
                        if order_type and 'stop' in order_type.lower():
                            is_stop_loss = True
                            reason = "Has 'stop' in type"
                        elif stop_price is not None and stop_price > 0:
                            is_stop_loss = True
                            reason = f"Has stopPrice={stop_price}"
                        elif trigger_price is not None and trigger_price > 0:
                            is_stop_loss = True
                            reason = f"Has triggerPrice={trigger_price}"
                        elif orig_type and 'stop' in orig_type.lower():
                            is_stop_loss = True
                            reason = f"Has 'stop' in origType={orig_type}"

                        if is_stop_loss:
                            logger.warning(f"    ⚠️ DETECTED AS STOP LOSS: {reason}")

                            # Verify if it's a REAL stop loss
                            pos = next((p for p in active_positions if p['symbol'] == symbol), None)
                            if pos:
                                entry = float(pos.get('average', 0))
                                side = pos.get('side')

                                if stop_price:
                                    check_price = float(stop_price)
                                elif trigger_price:
                                    check_price = float(trigger_price)
                                elif order_price:
                                    check_price = float(order_price)
                                else:
                                    check_price = 0

                                if check_price > 0:
                                    if side == 'long':
                                        if check_price < entry:
                                            logger.info(f"    ✅ Valid SL for LONG: {check_price} < {entry}")
                                        else:
                                            logger.error(f"    ❌ NOT A REAL SL! Price {check_price} >= Entry {entry}")
                                            logger.error(f"    🔴 This might be a TAKE PROFIT or LIMIT ORDER!")
                                    elif side == 'short':
                                        if check_price > entry:
                                            logger.info(f"    ✅ Valid SL for SHORT: {check_price} > {entry}")
                                        else:
                                            logger.error(f"    ❌ NOT A REAL SL! Price {check_price} <= Entry {entry}")
                                            logger.error(f"    🔴 This might be a TAKE PROFIT or LIMIT ORDER!")
                else:
                    logger.warning(f"  ⚠️ NO open orders found for {symbol}")

            except Exception as e:
                logger.error(f"  Error checking orders for {symbol}: {e}")

        # Summary
        logger.info(f"\n{'='*60}")
        logger.info("DIAGNOSIS SUMMARY")
        logger.info("=" * 60)

        positions_without_real_sl = []

        for symbol in symbols_to_check:
            orders = await exchange.fetch_open_orders(symbol)
            has_real_sl = False

            for order in orders:
                # Get position info
                pos = next((p for p in active_positions if p['symbol'] == symbol), None)
                if not pos:
                    continue

                entry = float(pos.get('average', 0))
                side = pos.get('side')

                # Check if order is a real stop loss
                stop_price = order.get('stopPrice')
                trigger_price = order.get('triggerPrice')

                if stop_price or trigger_price:
                    check_price = float(stop_price or trigger_price)

                    if side == 'long' and check_price < entry:
                        has_real_sl = True
                        break
                    elif side == 'short' and check_price > entry:
                        has_real_sl = True
                        break

            if not has_real_sl:
                positions_without_real_sl.append(symbol)

        if positions_without_real_sl:
            logger.error(f"\n🔴 CRITICAL: {len(positions_without_real_sl)} positions WITHOUT real stop loss:")
            for symbol in positions_without_real_sl:
                logger.error(f"  - {symbol}")
        else:
            logger.info("\n✅ All positions have real stop losses")

    except Exception as e:
        logger.error(f"Error checking positions: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        await exchange.close()


if __name__ == "__main__":
    asyncio.run(check_binance_positions())