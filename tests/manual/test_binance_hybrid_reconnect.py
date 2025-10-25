"""
Manual test to verify reconnection logic
Artificially closes Mark WS and verifies restoration

Usage:
    BINANCE_API_KEY=xxx BINANCE_API_SECRET=yyy python tests/manual/test_binance_hybrid_reconnect.py

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


async def test_reconnect():
    """Test reconnection and subscription restoration"""

    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_API_SECRET')

    if not api_key or not api_secret:
        logger.error("BINANCE_API_KEY and BINANCE_API_SECRET required")
        return

    logger.info("=" * 80)
    logger.info("🧪 BINANCE HYBRID RECONNECT TEST")
    logger.info("=" * 80)

    events = []

    async def handler(event_type, data):
        events.append((event_type, data))
        logger.info(f"📨 Event: {event_type} | {data.get('symbol')} | {data.get('mark_price')}")

    stream = BinanceHybridStream(api_key, api_secret, handler, testnet=False)

    # Start
    await stream.start()
    await asyncio.sleep(5)

    logger.info("=" * 80)
    logger.info("Phase 1: Initial subscriptions (simulating positions)")
    logger.info("=" * 80)

    # Simulate position opens (trigger subscriptions)
    stream.positions['BTCUSDT'] = {'symbol': 'BTCUSDT', 'side': 'LONG'}
    await stream._request_mark_subscription('BTCUSDT', subscribe=True)
    await asyncio.sleep(2)

    stream.positions['ETHUSDT'] = {'symbol': 'ETHUSDT', 'side': 'LONG'}
    await stream._request_mark_subscription('ETHUSDT', subscribe=True)
    await asyncio.sleep(2)

    logger.info(f"✅ Subscribed symbols: {stream.subscribed_symbols}")
    logger.info(f"📊 Events received: {len(events)}")

    initial_event_count = len(events)

    logger.info("=" * 80)
    logger.info("Phase 2: Force reconnect (close Mark WebSocket)")
    logger.info("=" * 80)

    # Force close Mark WS to simulate reconnect
    if stream.mark_ws and not stream.mark_ws.closed:
        await stream.mark_ws.close()
        logger.info("✅ Closed Mark WebSocket")
    else:
        logger.warning("⚠️ Mark WebSocket already closed or not initialized")

    # Wait for automatic reconnect
    logger.info("⏳ Waiting 10 seconds for automatic reconnect...")
    await asyncio.sleep(10)

    logger.info(f"📡 Mark connected: {stream.mark_connected}")
    logger.info(f"📋 Subscribed symbols after reconnect: {stream.subscribed_symbols}")

    logger.info("=" * 80)
    logger.info("Phase 3: Verify events are flowing again")
    logger.info("=" * 80)

    # Wait for events
    logger.info("⏳ Waiting 10 seconds for new events...")
    await asyncio.sleep(10)

    new_events = len(events) - initial_event_count
    logger.info(f"📊 New events after reconnect: {new_events}")

    # Stop
    await stream.stop()

    # Summary
    logger.info("=" * 80)
    logger.info("📊 TEST SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total events: {len(events)}")
    logger.info(f"Events before reconnect: {initial_event_count}")
    logger.info(f"Events after reconnect: {new_events}")

    if new_events > 0:
        logger.info("✅ TEST PASSED - Events flowing after reconnect")
        logger.info("✅ Subscription restoration is working correctly")
    else:
        logger.error("❌ TEST FAILED - No events after reconnect")
        logger.error("❌ Subscription restoration may not be working")


if __name__ == '__main__':
    asyncio.run(test_reconnect())
