#!/usr/bin/env python3
"""
Проверка: какой 'type' у STOP-LOSS ордеров
"""
import asyncio
import logging
import os
import json
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def check_stop_loss_type():
    """Create STOP-LOSS and check its type"""
    try:
        from core.exchange_manager import ExchangeManager
        from config.settings import config as settings

        logger.info("🔍 CHECKING STOP-LOSS ORDER TYPE")
        logger.info("=" * 80)

        # Initialize exchange
        binance_config = settings.exchanges.get('binance')
        exchange = ExchangeManager('binance', binance_config.__dict__)
        await exchange.initialize()

        # Disable the warning
        exchange.exchange.options['warnOnFetchOpenOrdersWithoutSymbol'] = False

        symbol = 'ICNT/USDT:USDT'

        # Get current price
        ticker = await exchange.exchange.fetch_ticker(symbol)
        current_price = ticker['last']
        logger.info(f"Current price for {symbol}: {current_price}")

        # Create a STOP-LOSS order (far from current price so it won't trigger)
        stop_price = current_price * 1.5  # 50% higher (won't trigger for short)

        # Calculate quantity to meet $5 minimum
        quantity = max(50, int(6 / current_price))  # At least $6 worth

        logger.info(f"\n📝 Creating STOP-LOSS order:")
        logger.info(f"  Symbol: {symbol}")
        logger.info(f"  Stop price: {stop_price}")
        logger.info(f"  Quantity: {quantity}")
        logger.info(f"  Notional: ${quantity * current_price:.2f}")

        # Create STOP-LOSS order
        order = await exchange.exchange.create_order(
            symbol=symbol,
            type='STOP_MARKET',  # Binance STOP type
            side='buy',
            amount=quantity,
            params={
                'stopPrice': stop_price,
            }
        )

        logger.info(f"\n✅ Order created: {order.get('id')}")

        # Fetch the order back to see how CCXT represents it
        logger.info(f"\n🔍 Fetching order back from exchange...")

        orders = await exchange.exchange.fetch_open_orders(symbol)

        logger.info(f"\nFound {len(orders)} open orders for {symbol}\n")

        for o in orders:
            logger.info("=" * 80)
            logger.info(f"Order ID: {o.get('id')}")
            logger.info(f"  type (CCXT):  '{o.get('type')}'")  # ← ЭТО МЫ ПРОВЕРЯЕМ!
            logger.info(f"  side:         {o.get('side')}")
            logger.info(f"  status:       {o.get('status')}")

            if 'info' in o:
                info_type = o['info'].get('type')
                logger.info(f"  info.type:    '{info_type}'")
                logger.info(f"  info.workingType: '{o['info'].get('workingType')}'")
                logger.info(f"\n  RAW info:")
                logger.info(json.dumps(o['info'], indent=4))

            logger.info("=" * 80)

        # Clean up - cancel the test order
        logger.info(f"\n🧹 Cleaning up test order...")
        for o in orders:
            await exchange.exchange.cancel_order(o['id'], symbol)
            logger.info(f"✅ Cancelled order {o['id']}")

        await exchange.close()

    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(check_stop_loss_type())
