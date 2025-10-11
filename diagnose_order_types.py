#!/usr/bin/env python3
"""
Диагностика: какой тип у STOP-LOSS ордеров
"""
import asyncio
import logging
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def diagnose_orders():
    """Check actual order types from exchange"""
    try:
        from core.exchange_manager import ExchangeManager
        from config.settings import config as settings

        logger.info("🔍 DIAGNOSING ORDER TYPES")
        logger.info("=" * 80)

        # Initialize exchange
        binance_config = settings.exchanges.get('binance')
        exchange = ExchangeManager('binance', binance_config.__dict__)
        await exchange.initialize()

        # Fetch all open orders
        orders = await exchange.exchange.fetch_open_orders()

        logger.info(f"Found {len(orders)} open orders\n")

        for i, order in enumerate(orders, 1):
            logger.info(f"Order #{i}:")
            logger.info(f"  ID: {order.get('id')}")
            logger.info(f"  Symbol: {order.get('symbol')}")
            logger.info(f"  Type: '{order.get('type')}'")  # ← КЛЮЧЕВОЕ ПОЛЕ!
            logger.info(f"  Side: {order.get('side')}")
            logger.info(f"  Status: {order.get('status')}")

            # Check info field
            if 'info' in order:
                info_type = order['info'].get('type')
                logger.info(f"  Info.type: '{info_type}'")
                logger.info(f"  Info keys: {list(order['info'].keys())[:10]}")

            logger.info("")

        await exchange.close()

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(diagnose_orders())
