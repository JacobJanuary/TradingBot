#!/usr/bin/env python3
"""
Test improved WebSocket reconnection logic
"""
import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from websocket.binance_stream import BinancePrivateStream, BinanceMarketStream
from websocket.bybit_stream import BybitPrivateStream, BybitMarketStream
from config.config_manager import ConfigManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WebSocketReconnectionTest:
    """Test WebSocket reconnection capabilities"""
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self.config = self.config_manager.config
        self.streams = []
        self.event_count = {
            'connected': 0,
            'disconnected': 0,
            'reconnected': 0,
            'errors': 0,
            'position_update': 0,
            'order_update': 0,
            'balance_update': 0,
            'ticker': 0,
            'orderbook': 0
        }
        self.test_duration = 120  # 2 minutes test
        
    async def event_handler(self, event_type: str, data: dict):
        """Handle WebSocket events"""
        if event_type in self.event_count:
            self.event_count[event_type] += 1
        
        # Log important events
        if event_type in ['connected', 'disconnected', 'error']:
            logger.info(f"🔔 {event_type.upper()}: {data.get('exchange', 'Unknown')}")
        elif event_type == 'position_update':
            pos_data = data['data']
            logger.info(f"📊 Position: {pos_data.get('symbol')} - PnL: {pos_data.get('unrealized_pnl', 0):.2f}")
        elif event_type == 'order_update':
            order_data = data['data']
            logger.info(f"📝 Order: {order_data.get('symbol')} {order_data.get('side')} - Status: {order_data.get('status')}")
    
    async def test_binance_reconnection(self):
        """Test Binance WebSocket reconnection"""
        logger.info("\n" + "="*60)
        logger.info("🔧 Testing Binance WebSocket Reconnection")
        logger.info("="*60)
        
        # Get Binance config
        binance_config = self.config['exchanges']['binance']
        
        if not binance_config.get('enabled'):
            logger.warning("Binance is disabled in config")
            return
        
        # Create streams
        private_stream = BinancePrivateStream(
            config=binance_config,
            api_key=binance_config['api_key'],
            api_secret=binance_config['api_secret'],
            event_handler=self.event_handler
        )
        
        market_stream = BinanceMarketStream(
            config=binance_config,
            symbols=['BTC/USDT', 'ETH/USDT'],
            event_handler=self.event_handler
        )
        
        self.streams.extend([private_stream, market_stream])
        
        # Start streams
        logger.info("Starting Binance streams...")
        await private_stream.start()
        await market_stream.start()
        
        # Monitor for 30 seconds
        await asyncio.sleep(30)
        
        # Simulate disconnect by stopping streams
        logger.info("\n⚡ Simulating disconnect...")
        await private_stream.stop()
        await market_stream.stop()
        
        await asyncio.sleep(5)
        
        # Restart streams to test reconnection
        logger.info("\n🔄 Testing reconnection...")
        await private_stream.start()
        await market_stream.start()
        
        # Monitor for another 30 seconds
        await asyncio.sleep(30)
        
        # Check statistics
        stats_private = private_stream.get_stats()
        stats_market = market_stream.get_stats()
        
        logger.info("\n📊 Binance Statistics:")
        logger.info(f"  Private Stream:")
        logger.info(f"    - State: {stats_private['state']}")
        logger.info(f"    - Messages: {stats_private['messages_received']}")
        logger.info(f"    - Errors: {stats_private['errors']}")
        logger.info(f"    - Reconnections: {stats_private['reconnections']}")
        
        logger.info(f"  Market Stream:")
        logger.info(f"    - State: {stats_market['state']}")
        logger.info(f"    - Messages: {stats_market['messages_received']}")
        logger.info(f"    - Errors: {stats_market['errors']}")
        logger.info(f"    - Reconnections: {stats_market['reconnections']}")
        
        # Clean up
        await private_stream.stop()
        await market_stream.stop()
        
        return stats_private['reconnections'] > 0 or stats_market['reconnections'] > 0
    
    async def test_bybit_reconnection(self):
        """Test Bybit WebSocket reconnection"""
        logger.info("\n" + "="*60)
        logger.info("🔧 Testing Bybit WebSocket Reconnection")
        logger.info("="*60)
        
        # Get Bybit config
        bybit_config = self.config['exchanges']['bybit']
        
        if not bybit_config.get('enabled'):
            logger.warning("Bybit is disabled in config")
            return
        
        # Create streams
        private_stream = BybitPrivateStream(
            config=bybit_config,
            api_key=bybit_config['api_key'],
            api_secret=bybit_config['api_secret'],
            event_handler=self.event_handler
        )
        
        market_stream = BybitMarketStream(
            config=bybit_config,
            symbols=['BTCUSDT', 'ETHUSDT'],
            event_handler=self.event_handler
        )
        
        self.streams.extend([private_stream, market_stream])
        
        # Start streams
        logger.info("Starting Bybit streams...")
        await private_stream.start()
        await market_stream.start()
        
        # Monitor for 30 seconds
        await asyncio.sleep(30)
        
        # Simulate disconnect
        logger.info("\n⚡ Simulating disconnect...")
        await private_stream.stop()
        await market_stream.stop()
        
        await asyncio.sleep(5)
        
        # Restart streams
        logger.info("\n🔄 Testing reconnection...")
        await private_stream.start()
        await market_stream.start()
        
        # Monitor for another 30 seconds
        await asyncio.sleep(30)
        
        # Check statistics
        stats_private = private_stream.get_stats()
        stats_market = market_stream.get_stats()
        
        logger.info("\n📊 Bybit Statistics:")
        logger.info(f"  Private Stream:")
        logger.info(f"    - State: {stats_private['state']}")
        logger.info(f"    - Messages: {stats_private['messages_received']}")
        logger.info(f"    - Errors: {stats_private['errors']}")
        logger.info(f"    - Reconnections: {stats_private['reconnections']}")
        
        logger.info(f"  Market Stream:")
        logger.info(f"    - State: {stats_market['state']}")
        logger.info(f"    - Messages: {stats_market['messages_received']}")
        logger.info(f"    - Errors: {stats_market['errors']}")
        logger.info(f"    - Reconnections: {stats_market['reconnections']}")
        
        # Clean up
        await private_stream.stop()
        await market_stream.stop()
        
        return stats_private['reconnections'] > 0 or stats_market['reconnections'] > 0
    
    async def test_long_running_stability(self):
        """Test long-running stability with automatic reconnection"""
        logger.info("\n" + "="*60)
        logger.info("🔧 Testing Long-Running Stability")
        logger.info("="*60)
        
        # Get enabled exchanges
        binance_enabled = self.config['exchanges']['binance'].get('enabled', False)
        bybit_enabled = self.config['exchanges']['bybit'].get('enabled', False)
        
        if not binance_enabled and not bybit_enabled:
            logger.warning("No exchanges enabled for testing")
            return
        
        streams = []
        
        # Setup Binance if enabled
        if binance_enabled:
            binance_config = self.config['exchanges']['binance']
            binance_stream = BinanceMarketStream(
                config=binance_config,
                symbols=['BTC/USDT'],
                event_handler=self.event_handler
            )
            streams.append(('Binance', binance_stream))
        
        # Setup Bybit if enabled
        if bybit_enabled:
            bybit_config = self.config['exchanges']['bybit']
            bybit_stream = BybitMarketStream(
                config=bybit_config,
                symbols=['BTCUSDT'],
                event_handler=self.event_handler
            )
            streams.append(('Bybit', bybit_stream))
        
        # Start all streams
        logger.info(f"Starting {len(streams)} streams for stability test...")
        for name, stream in streams:
            await stream.start()
            logger.info(f"  ✅ {name} stream started")
        
        # Monitor for test duration
        start_time = datetime.now()
        check_interval = 10  # Check every 10 seconds
        
        while (datetime.now() - start_time).total_seconds() < self.test_duration:
            await asyncio.sleep(check_interval)
            
            # Check stream health
            logger.info("\n🏥 Health Check:")
            for name, stream in streams:
                stats = stream.get_stats()
                logger.info(f"  {name}:")
                logger.info(f"    - State: {stats['state']}")
                logger.info(f"    - Uptime: {stats['uptime_seconds']:.0f}s")
                logger.info(f"    - Messages: {stats['messages_received']}")
                logger.info(f"    - Errors: {stats['errors']}")
                logger.info(f"    - Reconnections: {stats['reconnections']}")
        
        # Final statistics
        logger.info("\n" + "="*60)
        logger.info("📊 FINAL STATISTICS")
        logger.info("="*60)
        
        all_stable = True
        for name, stream in streams:
            stats = stream.get_stats()
            is_connected = stats['state'] == 'connected'
            
            logger.info(f"\n{name}:")
            logger.info(f"  - Final State: {stats['state']} {'✅' if is_connected else '❌'}")
            logger.info(f"  - Total Messages: {stats['messages_received']}")
            logger.info(f"  - Total Errors: {stats['errors']}")
            logger.info(f"  - Total Reconnections: {stats['reconnections']}")
            logger.info(f"  - Uptime: {stats['uptime_seconds']:.0f}s")
            
            if not is_connected or stats['errors'] > 10:
                all_stable = False
        
        # Event summary
        logger.info("\n📈 Event Summary:")
        for event_type, count in self.event_count.items():
            if count > 0:
                logger.info(f"  - {event_type}: {count}")
        
        # Clean up
        for name, stream in streams:
            await stream.stop()
        
        return all_stable
    
    async def run_all_tests(self):
        """Run all reconnection tests"""
        logger.info("\n" + "="*60)
        logger.info("🚀 WEBSOCKET RECONNECTION TEST SUITE")
        logger.info("="*60)
        
        results = {}
        
        # Test Binance
        try:
            binance_result = await self.test_binance_reconnection()
            results['Binance'] = 'PASSED' if binance_result else 'FAILED'
        except Exception as e:
            logger.error(f"Binance test error: {e}")
            results['Binance'] = 'ERROR'
        
        # Test Bybit
        try:
            bybit_result = await self.test_bybit_reconnection()
            results['Bybit'] = 'PASSED' if bybit_result else 'FAILED'
        except Exception as e:
            logger.error(f"Bybit test error: {e}")
            results['Bybit'] = 'ERROR'
        
        # Test long-running stability
        try:
            stability_result = await self.test_long_running_stability()
            results['Stability'] = 'PASSED' if stability_result else 'FAILED'
        except Exception as e:
            logger.error(f"Stability test error: {e}")
            results['Stability'] = 'ERROR'
        
        # Summary
        logger.info("\n" + "="*60)
        logger.info("✅ TEST RESULTS SUMMARY")
        logger.info("="*60)
        
        for test_name, result in results.items():
            emoji = '✅' if result == 'PASSED' else '❌' if result == 'FAILED' else '⚠️'
            logger.info(f"  {emoji} {test_name}: {result}")
        
        # Overall result
        all_passed = all(r == 'PASSED' for r in results.values())
        
        if all_passed:
            logger.info("\n🎉 ALL TESTS PASSED! WebSocket reconnection is working correctly.")
        else:
            logger.warning("\n⚠️ Some tests did not pass. Review the logs for details.")
        
        return all_passed


async def main():
    """Main test runner"""
    test = WebSocketReconnectionTest()
    
    try:
        success = await test.run_all_tests()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("\n⚠️ Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())