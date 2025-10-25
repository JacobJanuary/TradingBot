"""
Quick manual test for BinanceHybridStream (60 seconds)
Tests basic connectivity without trading

Usage:
    BINANCE_API_KEY=xxx BINANCE_API_SECRET=yyy python tests/manual/test_binance_hybrid_quick.py

Date: 2025-10-25
"""

import asyncio
import os
import logging
from websocket.binance_hybrid_stream import BinanceHybridStream

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def test_quick():
    """Quick connection test"""

    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_API_SECRET')

    if not api_key or not api_secret:
        logger.error("BINANCE_API_KEY and BINANCE_API_SECRET required")
        return

    logger.info("=" * 80)
    logger.info("🧪 BINANCE HYBRID STREAM - QUICK TEST (60s)")
    logger.info("=" * 80)

    events_received = []

    async def event_handler(event_type, data):
        """Capture events"""
        events_received.append((event_type, data))
        logger.info(f"📨 Event: {event_type} | Symbol: {data.get('symbol')} | Mark: {data.get('mark_price')}")

    # Create stream
    stream = BinanceHybridStream(
        api_key=api_key,
        api_secret=api_secret,
        event_handler=event_handler,
        testnet=False  # Use mainnet
    )

    # Start
    await stream.start()

    # Monitor for 60 seconds
    for i in range(60):
        await asyncio.sleep(1)

        if i % 10 == 0:
            status = stream.get_status()
            logger.info(f"⏱️  T+{i}s | Status: {status}")

    # Stop
    await stream.stop()

    # Summary
    logger.info("=" * 80)
    logger.info("📊 TEST SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Events received: {len(events_received)}")
    logger.info(f"Final status: {stream.get_status()}")

    if stream.user_connected and stream.mark_connected:
        logger.info("✅ QUICK TEST PASSED")
    else:
        logger.error("❌ QUICK TEST FAILED - Not fully connected")


if __name__ == '__main__':
    asyncio.run(test_quick())
