#!/usr/bin/env python3
"""
Тестовый скрипт для ручного запуска zombie cleanup
"""
import asyncio
import logging
import os
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_zombie_cleanup():
    """Run zombie cleanup manually"""
    try:
        # Import exchange manager
        from core.exchange_manager import ExchangeManager
        from config.settings import config as settings

        logger.info("=" * 80)
        logger.info("🧪 TESTING ZOMBIE CLEANUP WITH STOP-LOSS FIX")
        logger.info("=" * 80)

        # Initialize Binance exchange
        binance_config = settings.exchanges.get('binance')
        if not binance_config or not binance_config.enabled:
            logger.error("Binance exchange not configured")
            return

        exchange = ExchangeManager('binance', binance_config.__dict__)
        await exchange.initialize()
        logger.info("✅ Binance exchange initialized")

        # Import and run zombie cleanup
        from core.binance_zombie_manager import BinanceZombieIntegration

        integration = BinanceZombieIntegration(exchange.exchange)
        logger.info("✅ BinanceZombieIntegration initialized")

        # Enable protection
        await integration.enable_zombie_protection()
        logger.info("✅ Zombie protection enabled")

        # Run cleanup
        logger.info("")
        logger.info("🧹 Running zombie cleanup (dry_run=False)...")
        logger.info("")

        results = await integration.cleanup_zombies(dry_run=False)

        # Show results
        logger.info("")
        logger.info("=" * 80)
        logger.info("📊 CLEANUP RESULTS:")
        logger.info("=" * 80)
        logger.info(f"  Zombie orders found: {results['zombie_orders_found']}")
        logger.info(f"  Zombie orders cancelled: {results['zombie_orders_cancelled']}")
        logger.info(f"  OCO orders handled: {results.get('oco_orders_handled', 0)}")
        logger.info(f"  API weight used: {results.get('weight_used', 0)}")
        logger.info(f"  Empty responses mitigated: {results.get('empty_responses_mitigated', 0)}")
        logger.info(f"  Async delays detected: {results.get('async_delays_detected', 0)}")

        if results.get('errors'):
            logger.error(f"  Errors: {results['errors']}")

        if results.get('zombie_details'):
            logger.info("")
            logger.info("  Zombie details:")
            for zombie in results['zombie_details'][:5]:
                logger.info(f"    - {zombie}")

        logger.info("=" * 80)

        # Close exchange
        await exchange.close()
        logger.info("✅ Exchange closed")

    except Exception as e:
        logger.error(f"❌ Test failed: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(test_zombie_cleanup())
