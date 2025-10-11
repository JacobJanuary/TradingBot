#!/usr/bin/env python3
"""
Тестовый скрипт с DEBUG логами
"""
import asyncio
import logging
import os
from dotenv import load_dotenv

load_dotenv()

# Setup DEBUG logging
logging.basicConfig(
    level=logging.DEBUG,  # ← DEBUG!
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_zombie_cleanup():
    """Run zombie cleanup with DEBUG logs"""
    try:
        from core.exchange_manager import ExchangeManager
        from config.settings import config as settings

        print("=" * 80)
        print("🧪 TESTING WITH DEBUG LOGS")
        print("=" * 80)

        binance_config = settings.exchanges.get('binance')
        exchange = ExchangeManager('binance', binance_config.__dict__)
        await exchange.initialize()

        from core.binance_zombie_manager import BinanceZombieIntegration

        integration = BinanceZombieIntegration(exchange.exchange)
        await integration.enable_zombie_protection()

        print("\n🧹 Running zombie cleanup...\n")

        results = await integration.cleanup_zombies(dry_run=False)

        print("\n" + "=" * 80)
        print("📊 RESULTS:")
        print(f"  Found: {results['zombie_orders_found']}")
        print(f"  Cancelled: {results['zombie_orders_cancelled']}")
        print("=" * 80)

        await exchange.close()

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_zombie_cleanup())
