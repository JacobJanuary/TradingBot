#!/usr/bin/env python3
"""
Simulation script to test ReentryManager logic without real trailing stop exit.

Tests:
1. register_exit() creates signal correctly
2. update_price() tracks max correctly
3. Reentry triggers at correct price (drop% from max)
4. Multiple reentries work (up to max_reentries)
5. Delta confirmation logic
6. Cooldown period respected

Usage:
    python scripts/simulate_reentry.py
"""

import asyncio
import sys
import os
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.reentry_manager import ReentryManager, ReentrySignal


class SimulationResult:
    """Holds results of a simulation test"""
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.message = ""
        self.details = {}
    
    def __str__(self):
        status = "✅ PASS" if self.passed else "❌ FAIL"
        return f"{status} | {self.name}: {self.message}"


async def create_mock_manager() -> ReentryManager:
    """Create a ReentryManager with mocked dependencies"""
    # Mock position manager
    position_manager = MagicMock()
    position_manager.positions = {}
    position_manager.open_position = AsyncMock(return_value=True)
    
    # Mock aggtrades stream (for delta confirmation)
    aggtrades_stream = MagicMock()
    aggtrades_stream.get_large_trade_counts = MagicMock(return_value=(10, 5))  # large_buys=10, large_sells=5
    aggtrades_stream.subscribe = AsyncMock()
    
    # Mock mark price stream
    mark_price_stream = MagicMock()
    mark_price_stream.subscribe_symbol = AsyncMock()
    
    # Create manager
    manager = ReentryManager(
        position_manager=position_manager,
        aggtrades_stream=aggtrades_stream,
        mark_price_stream=mark_price_stream,
        cooldown_sec=5,  # Short cooldown for testing
        drop_percent=5.0,
        max_reentries=3,
        instant_reentry_enabled=False,  # Disable for predictable testing
        repository=None
    )
    
    # Mock DB operations
    manager._save_signal_state = AsyncMock()
    manager._load_active_signals = AsyncMock()
    
    return manager


async def test_1_register_exit_creates_signal() -> SimulationResult:
    """Test that register_exit creates a signal correctly"""
    result = SimulationResult("register_exit creates signal")
    
    manager = await create_mock_manager()
    
    await manager.register_exit(
        signal_id=123,
        symbol="TESTUSDT",
        exchange="binance",
        side="long",
        original_entry_price=Decimal("100.0"),
        original_entry_time=datetime.now(timezone.utc),
        exit_price=Decimal("105.0"),
        exit_reason="trailing_stop"
    )
    
    if "TESTUSDT" in manager.signals:
        signal = manager.signals["TESTUSDT"]
        result.passed = True
        result.message = f"Signal created: count={signal.reentry_count}, status={signal.status}"
        result.details = {
            "symbol": signal.symbol,
            "side": signal.side,
            "exit_price": float(signal.last_exit_price),
            "reentry_count": signal.reentry_count,
            "status": signal.status
        }
    else:
        result.message = "Signal NOT created"
    
    return result


async def test_2_update_price_tracks_max() -> SimulationResult:
    """Test that update_price tracks max_price_after_exit correctly"""
    result = SimulationResult("update_price tracks max")
    
    manager = await create_mock_manager()
    
    # Create signal first
    await manager.register_exit(
        signal_id=123,
        symbol="TESTUSDT",
        exchange="binance",
        side="long",
        original_entry_price=Decimal("100.0"),
        original_entry_time=datetime.now(timezone.utc),
        exit_price=Decimal("105.0"),
        exit_reason="trailing_stop"
    )
    
    # Simulate price updates
    await manager.update_price("TESTUSDT", Decimal("106.0"))  # New max
    await manager.update_price("TESTUSDT", Decimal("107.0"))  # New max
    await manager.update_price("TESTUSDT", Decimal("105.5"))  # Drop (no update to max)
    
    signal = manager.signals["TESTUSDT"]
    
    if signal.max_price_after_exit == Decimal("107.0"):
        result.passed = True
        result.message = f"Max tracked correctly: {signal.max_price_after_exit}"
    else:
        result.message = f"Max NOT tracked: got {signal.max_price_after_exit}, expected 107.0"
    
    result.details = {
        "max_price_after_exit": float(signal.max_price_after_exit) if signal.max_price_after_exit else None,
        "current_price": float(signal.current_price) if signal.current_price else None
    }
    
    return result


async def test_3_reentry_triggers_at_correct_price() -> SimulationResult:
    """Test that reentry triggers when price drops by drop_percent from max"""
    result = SimulationResult("reentry triggers at correct price")
    
    manager = await create_mock_manager()
    manager.cooldown_sec = 0  # No cooldown for this test
    
    # Create signal
    exit_time = datetime.now(timezone.utc) - timedelta(seconds=10)  # Past cooldown
    signal = ReentrySignal(
        signal_id=123,
        symbol="TESTUSDT",
        exchange="binance",
        side="long",
        original_entry_price=Decimal("100.0"),
        original_entry_time=datetime.now(timezone.utc) - timedelta(hours=1),
        last_exit_price=Decimal("105.0"),
        last_exit_time=exit_time,
        last_exit_reason="trailing_stop",
        cooldown_sec=0,
        drop_percent=Decimal("5.0"),
        max_reentries=3,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=23)
    )
    signal.max_price_after_exit = Decimal("110.0")  # Max = 110
    signal.min_price_after_exit = Decimal("105.0")  # Min = 105
    # Trigger price = 110 * 0.95 = 104.5
    
    manager.signals["TESTUSDT"] = signal
    
    # Price above trigger - should NOT trigger
    await manager.update_price("TESTUSDT", Decimal("105.0"))
    reentry_count_before = signal.reentry_count
    
    # Price at trigger - should trigger
    await manager.update_price("TESTUSDT", Decimal("104.5"))
    
    if signal.status == "reentered" and signal.reentry_count == reentry_count_before + 1:
        result.passed = True
        result.message = f"Reentry triggered at 104.5 (5% drop from max 110)"
    else:
        result.message = f"Reentry NOT triggered: status={signal.status}, count={signal.reentry_count}"
    
    result.details = {
        "max_price": 110.0,
        "trigger_price": 104.5,
        "final_status": signal.status,
        "reentry_count": signal.reentry_count
    }
    
    return result


async def test_4_multiple_reentries_work() -> SimulationResult:
    """Test that multiple reentries work up to max_reentries"""
    result = SimulationResult("multiple reentries work")
    
    manager = await create_mock_manager()
    max_reentries = 3
    
    # Create initial signal
    await manager.register_exit(
        signal_id=123,
        symbol="TESTUSDT",
        exchange="binance",
        side="long",
        original_entry_price=Decimal("100.0"),
        original_entry_time=datetime.now(timezone.utc) - timedelta(hours=1),
        exit_price=Decimal("105.0"),
        exit_reason="trailing_stop"
    )
    
    signal = manager.signals["TESTUSDT"]
    signal.cooldown_sec = 0
    signal.max_price_after_exit = Decimal("110.0")
    
    reentry_attempts = []
    
    for i in range(max_reentries + 1):  # Try one more than max
        # Only reset to active if not max reached
        if signal.status == "max_reached":
            break
            
        signal.status = "active"
        signal.max_price_after_exit = Decimal("110.0")
        signal.min_price_after_exit = Decimal("104.0")
        
        await manager.update_price("TESTUSDT", Decimal("104.0"))  # Below trigger
        
        reentry_attempts.append({
            "attempt": i + 1,
            "status": signal.status,
            "count": signal.reentry_count
        })
        
        if signal.status == "reentered":
            # Simulate exit after reentry
            await manager.register_exit(
                signal_id=123,
                symbol="TESTUSDT",
                exchange="binance",
                side="long",
                original_entry_price=Decimal("100.0"),
                original_entry_time=datetime.now(timezone.utc) - timedelta(hours=1),
                exit_price=Decimal("108.0"),
                exit_reason="trailing_stop"
            )
    
    # Check final state
    if signal.reentry_count == max_reentries and signal.status == "max_reached":
        result.passed = True
        result.message = f"Stopped at max_reentries={max_reentries}"
    else:
        result.message = f"Did not stop correctly: count={signal.reentry_count}, status={signal.status}"
    
    result.details = {
        "max_reentries": max_reentries,
        "final_count": signal.reentry_count,
        "final_status": signal.status,
        "attempts": reentry_attempts
    }
    
    return result


async def test_5_cooldown_respected() -> SimulationResult:
    """Test that cooldown period is respected"""
    result = SimulationResult("cooldown respected")
    
    manager = await create_mock_manager()
    manager.cooldown_sec = 300  # 5 minutes
    
    # Create signal with recent exit (within cooldown)
    signal = ReentrySignal(
        signal_id=123,
        symbol="TESTUSDT",
        exchange="binance",
        side="long",
        original_entry_price=Decimal("100.0"),
        original_entry_time=datetime.now(timezone.utc) - timedelta(hours=1),
        last_exit_price=Decimal("105.0"),
        last_exit_time=datetime.now(timezone.utc),  # Just exited
        last_exit_reason="trailing_stop",
        cooldown_sec=300,
        drop_percent=Decimal("5.0"),
        max_reentries=3,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=23)
    )
    signal.max_price_after_exit = Decimal("110.0")
    signal.min_price_after_exit = Decimal("100.0")
    
    manager.signals["TESTUSDT"] = signal
    
    # Try to trigger reentry during cooldown
    await manager.update_price("TESTUSDT", Decimal("100.0"))  # Way below trigger
    
    if signal.status == "active" and signal.reentry_count == 0:
        result.passed = True
        result.message = f"Reentry blocked during cooldown (300s)"
    else:
        result.message = f"Reentry NOT blocked: status={signal.status}, count={signal.reentry_count}"
    
    result.details = {
        "is_in_cooldown": signal.is_in_cooldown(),
        "can_reenter": signal.can_reenter(),
        "cooldown_sec": signal.cooldown_sec
    }
    
    return result


async def test_6_delta_confirmation() -> SimulationResult:
    """Test that delta confirmation logic works"""
    result = SimulationResult("delta confirmation")
    
    manager = await create_mock_manager()
    
    # Create signal
    signal = ReentrySignal(
        signal_id=123,
        symbol="TESTUSDT",
        exchange="binance",
        side="long",
        original_entry_price=Decimal("100.0"),
        original_entry_time=datetime.now(timezone.utc) - timedelta(hours=1),
        last_exit_price=Decimal("105.0"),
        last_exit_time=datetime.now(timezone.utc) - timedelta(minutes=10),
        last_exit_reason="trailing_stop",
        cooldown_sec=0,
        drop_percent=Decimal("5.0"),
        max_reentries=3,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=23)
    )
    signal.max_price_after_exit = Decimal("110.0")
    manager.signals["TESTUSDT"] = signal
    
    # Test with positive delta (large_buys > large_sells) - should confirm
    manager.aggtrades_stream.get_large_trade_counts = MagicMock(return_value=(10, 5))
    confirmed_positive = await manager._check_delta_confirmation(signal)
    
    # Test with negative delta (large_buys < large_sells) - should NOT confirm
    manager.aggtrades_stream.get_large_trade_counts = MagicMock(return_value=(5, 10))
    confirmed_negative = await manager._check_delta_confirmation(signal)
    
    if confirmed_positive and not confirmed_negative:
        result.passed = True
        result.message = "Delta confirmation works correctly"
    else:
        result.message = f"Delta logic wrong: positive={confirmed_positive}, negative={confirmed_negative}"
    
    result.details = {
        "positive_delta_confirms": confirmed_positive,
        "negative_delta_confirms": confirmed_negative
    }
    
    return result


async def run_all_tests():
    """Run all simulation tests"""
    print("=" * 60)
    print("🧪 ReentryManager Simulation Tests")
    print("=" * 60)
    print()
    
    tests = [
        test_1_register_exit_creates_signal,
        test_2_update_price_tracks_max,
        test_3_reentry_triggers_at_correct_price,
        test_4_multiple_reentries_work,
        test_5_cooldown_respected,
        test_6_delta_confirmation,
    ]
    
    results = []
    
    for test_func in tests:
        try:
            result = await test_func()
            results.append(result)
            print(result)
            if result.details:
                for key, value in result.details.items():
                    print(f"    {key}: {value}")
            print()
        except Exception as e:
            print(f"❌ FAIL | {test_func.__name__}: Exception - {e}")
            import traceback
            traceback.print_exc()
            print()
    
    # Summary
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    
    print("=" * 60)
    print(f"📊 Results: {passed}/{total} tests passed")
    print("=" * 60)
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
