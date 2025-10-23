#!/usr/bin/env python3
"""
MINIMAL test for unified protection system
Can be run standalone to verify integration
"""

import asyncio
import logging
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import Mock

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def test_unified_price_monitor():
    """Test UnifiedPriceMonitor in isolation"""

    print("\n" + "="*60)
    print("TEST 1: UnifiedPriceMonitor")
    print("="*60)

    from websocket.unified_price_monitor import UnifiedPriceMonitor

    monitor = UnifiedPriceMonitor()
    await monitor.start()

    # Track callbacks
    callback_results = []

    async def test_callback(symbol, price):
        callback_results.append((symbol, price))
        logger.info(f"Callback received: {symbol} = ${price}")

    # Subscribe
    await monitor.subscribe('BTCUSDT', test_callback, 'test_module', priority=10)

    # Send price updates
    await monitor.update_price('BTCUSDT', Decimal('50000'))
    await asyncio.sleep(0.1)
    await monitor.update_price('BTCUSDT', Decimal('50100'))

    # Check results
    assert len(callback_results) >= 1, "No callbacks received"
    assert callback_results[0] == ('BTCUSDT', Decimal('50000'))

    stats = monitor.get_stats()
    print(f"\nStats: {stats}")

    await monitor.stop()
    print("✅ UnifiedPriceMonitor test PASSED")


async def test_trailing_stop_adapter():
    """Test TrailingStop integration through adapter"""

    print("\n" + "="*60)
    print("TEST 2: TrailingStop Adapter")
    print("="*60)

    from websocket.unified_price_monitor import UnifiedPriceMonitor
    from core.protection_adapters import TrailingStopAdapter

    # Mock trailing manager
    mock_ts = Mock()
    async def mock_update_price(s, p):
        return None
    mock_ts.update_price = Mock(side_effect=mock_update_price)

    # Create monitor and adapter
    monitor = UnifiedPriceMonitor()
    await monitor.start()

    adapter = TrailingStopAdapter(mock_ts, monitor)

    # Mock position
    position = Mock()
    position.symbol = 'ETHUSDT'

    # Register position
    await adapter.register_position(position)

    # Send price update
    await monitor.update_price('ETHUSDT', Decimal('3000'))
    await asyncio.sleep(0.1)

    # Verify trailing stop was called
    mock_ts.update_price.assert_called()

    await monitor.stop()
    print("✅ TrailingStop Adapter test PASSED")


async def test_aged_position_monitor():
    """Test AgedPositionMonitor V2"""

    print("\n" + "="*60)
    print("TEST 3: AgedPositionMonitor V2")
    print("="*60)

    from core.aged_position_monitor_v2 import AgedPositionMonitorV2

    # Mock exchanges and repository
    mock_exchanges = {'binance': Mock()}
    mock_repository = None

    # Create monitor
    aged_monitor = AgedPositionMonitorV2(mock_exchanges, mock_repository)

    # Mock aged position
    position = Mock()
    position.symbol = 'BTCUSDT'
    from datetime import timezone
    position.opened_at = datetime.now(timezone.utc) - timedelta(hours=5)  # 5 hours old
    position.entry_price = 45000
    position.side = 'long'
    position.quantity = 1.0
    position.trailing_activated = False

    # Check if aged
    is_aged = await aged_monitor.check_position_age(position)
    assert is_aged == True, "Position should be aged"

    # Add to monitoring
    await aged_monitor.add_aged_position(position)

    # Check stats
    stats = aged_monitor.get_stats()
    print(f"\nAged Monitor Stats: {stats}")
    assert stats['monitored'] == 1

    print("✅ AgedPositionMonitor V2 test PASSED")


async def test_full_integration():
    """Test full unified protection flow"""

    print("\n" + "="*60)
    print("TEST 4: Full Integration")
    print("="*60)

    from datetime import timezone
    from websocket.unified_price_monitor import UnifiedPriceMonitor
    from core.protection_adapters import TrailingStopAdapter, AgedPositionAdapter
    from core.aged_position_monitor_v2 import AgedPositionMonitorV2

    # Create components
    monitor = UnifiedPriceMonitor()
    await monitor.start()

    # Mock trailing stop
    mock_ts = Mock()
    async def mock_update_price(s, p):
        return None
    mock_ts.update_price = Mock(side_effect=mock_update_price)

    # Real aged monitor
    aged_monitor = AgedPositionMonitorV2({}, None)

    # Create adapters
    ts_adapter = TrailingStopAdapter(mock_ts, monitor)
    aged_adapter = AgedPositionAdapter(aged_monitor, monitor)

    # Create two positions
    profitable_position = Mock()
    profitable_position.symbol = 'PROFITUSDT'
    profitable_position.trailing_activated = True

    aged_position = Mock()
    aged_position.symbol = 'OLDUSDT'
    aged_position.opened_at = datetime.now(timezone.utc) - timedelta(hours=6)
    aged_position.trailing_activated = False
    aged_position.entry_price = 100
    aged_position.side = 'long'

    # Register positions
    await ts_adapter.register_position(profitable_position)
    await aged_adapter.add_aged_position(aged_position)

    # Send price updates
    await monitor.update_price('PROFITUSDT', Decimal('500'))
    await monitor.update_price('OLDUSDT', Decimal('95'))

    await asyncio.sleep(0.2)

    # Check stats
    monitor_stats = monitor.get_stats()
    print(f"\nMonitor Stats: {monitor_stats}")
    assert monitor_stats['update_count'] >= 2
    assert monitor_stats['total_subscribers'] >= 1

    await monitor.stop()
    print("✅ Full Integration test PASSED")


async def main():
    """Run all tests"""

    print("\n" + "#"*60)
    print("# UNIFIED PROTECTION MINIMAL TESTS")
    print("#"*60)

    try:
        await test_unified_price_monitor()
        await test_trailing_stop_adapter()
        await test_aged_position_monitor()
        await test_full_integration()

        print("\n" + "="*60)
        print("🎉 ALL TESTS PASSED!")
        print("="*60)

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)