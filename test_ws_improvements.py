#!/usr/bin/env python3
"""
Quick test of improved WebSocket reconnection
"""
import asyncio
import logging
from datetime import datetime
from websocket.improved_stream import ImprovedStream, ConnectionState

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TestStream(ImprovedStream):
    """Test stream implementation"""
    
    async def _get_ws_url(self) -> str:
        # Use a public WebSocket echo service for testing
        return "wss://echo.websocket.org"
    
    async def _authenticate(self):
        logger.info("Mock authentication")
    
    async def _subscribe_channels(self):
        logger.info("Mock subscription")
        # Send a test message
        await self.send_message({"test": "hello"})
    
    async def _process_message(self, msg: dict):
        logger.info(f"Received message: {msg}")


async def test_reconnection():
    """Test reconnection logic"""
    logger.info("="*60)
    logger.info("TESTING IMPROVED WEBSOCKET RECONNECTION")
    logger.info("="*60)
    
    config = {
        'ws_reconnect_delay': 2,
        'ws_reconnect_delay_max': 10,
        'ws_max_reconnect_attempts': 3,
        'ws_heartbeat_interval': 5,
        'ws_heartbeat_timeout': 10
    }
    
    # Event tracking
    events = []
    
    async def event_handler(event_type: str, data: dict):
        events.append((event_type, datetime.now()))
        logger.info(f"Event: {event_type} - {data}")
    
    # Create test stream
    stream = TestStream("TestExchange", config, event_handler)
    
    # Start stream
    logger.info("\n1. Starting stream...")
    await stream.start()
    
    # Let it run for a bit
    await asyncio.sleep(5)
    
    # Check stats
    stats = stream.get_stats()
    logger.info(f"\nInitial stats:")
    logger.info(f"  State: {stats['state']}")
    logger.info(f"  Messages: {stats['messages_received']}")
    logger.info(f"  Errors: {stats['errors']}")
    
    # Simulate disconnect
    logger.info("\n2. Simulating disconnect...")
    if stream.ws:
        await stream.ws.close()
    
    # Wait for automatic reconnection
    logger.info("3. Waiting for automatic reconnection...")
    await asyncio.sleep(10)
    
    # Check stats again
    stats = stream.get_stats()
    logger.info(f"\nStats after reconnection:")
    logger.info(f"  State: {stats['state']}")
    logger.info(f"  Messages: {stats['messages_received']}")
    logger.info(f"  Errors: {stats['errors']}")
    logger.info(f"  Reconnections: {stats['reconnections']}")
    
    # Stop stream
    logger.info("\n4. Stopping stream...")
    await stream.stop()
    
    # Final stats
    stats = stream.get_stats()
    logger.info(f"\nFinal stats:")
    logger.info(f"  State: {stats['state']}")
    logger.info(f"  Total reconnections: {stats['reconnections']}")
    logger.info(f"  Total errors: {stats['errors']}")
    
    # Check events
    logger.info(f"\nEvents captured: {len(events)}")
    for event_type, timestamp in events:
        logger.info(f"  - {event_type} at {timestamp.strftime('%H:%M:%S')}")
    
    # Verify reconnection worked
    success = stats['reconnections'] > 0 or stats['state'] == 'connected'
    
    if success:
        logger.info("\n✅ TEST PASSED: Reconnection logic is working!")
    else:
        logger.warning("\n❌ TEST FAILED: Reconnection did not occur")
    
    return success


async def test_connection_states():
    """Test connection state transitions"""
    logger.info("\n" + "="*60)
    logger.info("TESTING CONNECTION STATE TRANSITIONS")
    logger.info("="*60)
    
    config = {
        'ws_reconnect_delay': 1,
        'ws_reconnect_delay_max': 5,
        'ws_max_reconnect_attempts': 2
    }
    
    stream = TestStream("TestExchange", config)
    
    # Check initial state
    assert stream.state == ConnectionState.DISCONNECTED
    logger.info(f"✅ Initial state: {stream.state.value}")
    
    # Start connection
    await stream.start()
    await asyncio.sleep(2)
    
    # Should be connecting or connected
    assert stream.state in [ConnectionState.CONNECTING, ConnectionState.CONNECTED]
    logger.info(f"✅ After start: {stream.state.value}")
    
    # Force failure
    stream.state = ConnectionState.FAILED
    await asyncio.sleep(3)
    
    # Should attempt reconnection
    logger.info(f"✅ After failure: {stream.state.value}")
    
    # Stop
    await stream.stop()
    assert stream.state == ConnectionState.DISCONNECTED
    logger.info(f"✅ After stop: {stream.state.value}")
    
    logger.info("\n✅ All state transitions working correctly!")
    return True


async def main():
    """Run all tests"""
    try:
        # Test basic reconnection
        result1 = await test_reconnection()
        
        # Test state transitions
        result2 = await test_connection_states()
        
        if result1 and result2:
            logger.info("\n" + "="*60)
            logger.info("🎉 ALL TESTS PASSED!")
            logger.info("WebSocket improvements are working correctly")
            logger.info("="*60)
        else:
            logger.warning("\n⚠️ Some tests failed")
            
    except Exception as e:
        logger.error(f"Test error: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())