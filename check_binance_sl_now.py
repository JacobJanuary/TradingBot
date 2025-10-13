#!/usr/bin/env python3
"""
Quick check - do Binance positions have stop-loss orders RIGHT NOW?
"""

import asyncio
import ccxt.async_support as ccxt
import os
import logging
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

async def check_now():
    exchange = ccxt.binance({
        'apiKey': os.getenv('BINANCE_API_KEY'),
        'secret': os.getenv('BINANCE_API_SECRET'),
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })

    testnet = os.getenv('BINANCE_TESTNET', 'true').lower() == 'true'
    if testnet:
        exchange.set_sandbox_mode(True)

    try:
        logger.info("🔍 Checking Binance positions and stop-loss orders...")

        positions = await exchange.fetch_positions()
        active = [p for p in positions if float(p.get('contracts', 0)) > 0]

        logger.info(f"📊 Active positions: {len(active)}")

        for pos in active:
            symbol = pos['symbol']
            contracts = pos.get('contracts', 0)
            side = pos.get('side')

            # Check for stop orders
            orders = await exchange.fetch_open_orders(symbol)
            stop_orders = [o for o in orders if 'stop' in o.get('type', '').lower()]

            logger.info(f"\n{symbol} ({side}, {contracts} contracts):")
            if stop_orders:
                for order in stop_orders:
                    logger.info(f"  ✅ Stop order: {order['id']} at {order.get('stopPrice')}")
            else:
                logger.error(f"  ❌ NO STOP ORDERS!")

    finally:
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(check_now())