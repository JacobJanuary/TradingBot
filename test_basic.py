#!/usr/bin/env python3
"""
Basic test to verify system components work
"""

import asyncio
import sys
from decimal import Decimal

# Test basic imports
print("Testing imports...")

try:
    from database.models import Position, Order, Signal
    print("✓ Database models")
except ImportError as e:
    print(f"✗ Database models: {e}")
    sys.exit(1)

try:
    from database.repository import Repository
    print("✓ Repository")
except ImportError as e:
    print(f"✗ Repository: {e}")

try:
    from core.exchange_manager import ExchangeManager
    from core.risk_manager import RiskManager
    print("✓ Core components")
except ImportError as e:
    print(f"✗ Core components: {e}")

try:
    from protection.stop_loss_manager import StopLossManager
    from protection.trailing_stop import SmartTrailingStopManager
    from protection.position_guard import PositionGuard
    print("✓ Protection components")
except ImportError as e:
    print(f"✗ Protection components: {e}")

try:
    from websocket.binance_stream import BinancePrivateStream
    from websocket.bybit_stream import BybitStream
    from websocket.event_router import EventRouter
    print("✓ WebSocket components")
except ImportError as e:
    print(f"✗ WebSocket components: {e}")

try:
    from monitoring.metrics import MetricsCollector
    from monitoring.health_check import HealthChecker
    from monitoring.performance import PerformanceTracker
    print("✓ Monitoring components")
except ImportError as e:
    print(f"✗ Monitoring components: {e}")

# Test basic functionality
print("\nTesting basic functionality...")

async def test_basic():
    # Test Position creation
    try:
        pos = Position(
            id=1,
            trade_id=1,
            symbol='BTC/USDT',
            exchange='binance',
            side='long',
            quantity=0.1,
            entry_price=50000.0,
            status='OPEN'
        )
        print(f"✓ Position creation: {pos.symbol} {pos.quantity} @ {pos.entry_price}")
    except Exception as e:
        print(f"✗ Position creation: {e}")
        return False

    # Test Order creation
    try:
        order = Order(
            id='order_123',
            symbol='BTC/USDT',
            exchange='binance',
            type='limit',
            side='buy',
            size=0.1,
            price=49999.0,
            status='open'
        )
        print(f"✓ Order creation: {order.symbol} {order.size} @ {order.price}")
    except Exception as e:
        print(f"✗ Order creation: {e}")
        return False

    # Test risk calculations
    try:
        config = {
            'max_position_size': 10000,
            'max_daily_loss': 1000,
            'max_open_positions': 5,
            'default_stop_loss': 2.0
        }
        
        # Mock repository
        class MockRepo:
            async def get_active_positions(self, exchange=None):
                return []
            async def get_daily_pnl(self):
                return Decimal('0')
        
        risk_manager = RiskManager(MockRepo(), config)
        
        # Test position size calculation
        size = await risk_manager.calculate_position_size(
            symbol='BTC/USDT',
            price=Decimal('50000'),
            stop_loss=Decimal('49000'),
            account_balance=Decimal('10000')
        )
        print(f"✓ Risk calculation: position size = {size}")
        
        # Test position limit check
        can_open = await risk_manager.check_position_limit('binance')
        print(f"✓ Position limit check: {can_open}")
        
    except Exception as e:
        print(f"✗ Risk calculations: {e}")
        return False

    return True

# Run tests
if __name__ == "__main__":
    print("=" * 50)
    print("Trading Bot Basic Test")
    print("=" * 50)
    
    result = asyncio.run(test_basic())
    
    if result:
        print("\n✅ All basic tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed!")
        sys.exit(1)