"""
Unit tests for Re-Entry trigger logic fix.

Tests verify that:
1. get_reentry_trigger_price() uses max_price_after_exit (dynamic) not last_exit_price (static)
2. Fallback to exit price when max not tracked yet
3. SHORT positions use min_price_after_exit correctly

Date: 2026-01-04
"""
import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta

# Import directly from the module under test
import sys
sys.path.insert(0, '/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot')

from core.reentry_manager import ReentrySignal


class TestReentryTriggerPrice:
    """Tests for get_reentry_trigger_price() fix"""
    
    def test_long_uses_max_price_not_exit_price(self):
        """
        Scenario (LONG):
        - Exit @ $3000
        - Price rallies to $3200 (max_price_after_exit = 3200)
        - Drop threshold = 5%
        - Trigger price should be $3200 * 0.95 = $3040
        - NOT $3000 * 0.95 = $2850
        """
        signal = ReentrySignal(
            signal_id=1,
            symbol='ETHUSDT',
            exchange='binance',
            side='long',
            original_entry_price=Decimal('2900'),
            original_entry_time=datetime.now(timezone.utc) - timedelta(hours=1),
            last_exit_price=Decimal('3000'),
            last_exit_time=datetime.now(timezone.utc),
            last_exit_reason='trailing_stop',
            drop_percent=Decimal('5.0'),
            max_price_after_exit=Decimal('3200'),  # Rallied from 3000 to 3200
            min_price_after_exit=Decimal('3000'),
        )
        
        trigger = signal.get_reentry_trigger_price()
        
        # Should be 5% drop from 3200, not from 3000
        expected = Decimal('3200') * Decimal('0.95')  # = 3040
        assert trigger == expected, f"Expected {expected}, got {trigger}"
        
        # Verify it's NOT the old (wrong) calculation
        wrong_value = Decimal('3000') * Decimal('0.95')  # = 2850
        assert trigger != wrong_value, "Bug! Still using exit_price instead of max"
    
    def test_long_fallback_when_max_is_none(self):
        """When max_price_after_exit is None, fallback to exit price"""
        signal = ReentrySignal(
            signal_id=2,
            symbol='BTCUSDT',
            exchange='binance',
            side='long',
            original_entry_price=Decimal('50000'),
            original_entry_time=datetime.now(timezone.utc),
            last_exit_price=Decimal('55000'),
            last_exit_time=datetime.now(timezone.utc),
            last_exit_reason='trailing_stop',
            drop_percent=Decimal('5.0'),
            max_price_after_exit=None,  # Not tracked yet
            min_price_after_exit=None,
        )
        
        trigger = signal.get_reentry_trigger_price()
        
        # Fallback to exit price: 55000 * 0.95 = 52250
        expected = Decimal('55000') * Decimal('0.95')
        assert trigger == expected, f"Expected fallback {expected}, got {trigger}"
    
    def test_short_uses_min_price_not_exit_price(self):
        """
        Scenario (SHORT):
        - Exit @ $3000
        - Price drops to $2800 (min_price_after_exit = 2800)  
        - Rise threshold = 5%
        - Trigger price should be $2800 * 1.05 = $2940
        - NOT $3000 * 1.05 = $3150
        """
        signal = ReentrySignal(
            signal_id=3,
            symbol='ETHUSDT',
            exchange='binance',
            side='short',
            original_entry_price=Decimal('3100'),
            original_entry_time=datetime.now(timezone.utc) - timedelta(hours=1),
            last_exit_price=Decimal('3000'),
            last_exit_time=datetime.now(timezone.utc),
            last_exit_reason='trailing_stop',
            drop_percent=Decimal('5.0'),
            max_price_after_exit=Decimal('3000'),
            min_price_after_exit=Decimal('2800'),  # Dropped from 3000 to 2800
        )
        
        trigger = signal.get_reentry_trigger_price()
        
        # Should be 5% rise from 2800, not from 3000
        expected = Decimal('2800') * Decimal('1.05')  # = 2940
        assert trigger == expected, f"Expected {expected}, got {trigger}"
        
        # Verify it's NOT the old (wrong) calculation
        wrong_value = Decimal('3000') * Decimal('1.05')  # = 3150
        assert trigger != wrong_value, "Bug! Still using exit_price instead of min"
    
    def test_short_fallback_when_min_is_none(self):
        """When min_price_after_exit is None, fallback to exit price"""
        signal = ReentrySignal(
            signal_id=4,
            symbol='BTCUSDT',
            exchange='binance',
            side='short',
            original_entry_price=Decimal('60000'),
            original_entry_time=datetime.now(timezone.utc),
            last_exit_price=Decimal('55000'),
            last_exit_time=datetime.now(timezone.utc),
            last_exit_reason='trailing_stop',
            drop_percent=Decimal('5.0'),
            max_price_after_exit=None,
            min_price_after_exit=None,  # Not tracked yet
        )
        
        trigger = signal.get_reentry_trigger_price()
        
        # Fallback to exit price: 55000 * 1.05 = 57750
        expected = Decimal('55000') * Decimal('1.05')
        assert trigger == expected, f"Expected fallback {expected}, got {trigger}"


class TestReentryTriggerCondition:
    """Tests for the actual trigger condition in update_price()"""
    
    def test_long_trigger_at_correct_drop_level(self):
        """LONG triggers when price <= trigger_price (5% below max)"""
        signal = ReentrySignal(
            signal_id=5,
            symbol='ETHUSDT',
            exchange='binance',
            side='long',
            original_entry_price=Decimal('2900'),
            original_entry_time=datetime.now(timezone.utc) - timedelta(hours=1),
            last_exit_price=Decimal('3000'),
            last_exit_time=datetime.now(timezone.utc) - timedelta(minutes=10),  # Past cooldown
            last_exit_reason='trailing_stop',
            drop_percent=Decimal('5.0'),
            max_price_after_exit=Decimal('3200'),
            min_price_after_exit=Decimal('3000'),
            cooldown_sec=300,  # 5 min, already past
            max_reentries=3,
            reentry_count=0,
            status='active',
        )
        
        trigger = signal.get_reentry_trigger_price()
        assert trigger == Decimal('3040'), f"Trigger should be 3040, got {trigger}"
        
        # Price at 3050 - should NOT trigger (above trigger)
        price_high = Decimal('3050')
        should_trigger_high = price_high <= trigger
        assert should_trigger_high == False, "Should NOT trigger at 3050"
        
        # Price at 3035 - SHOULD trigger (below trigger)
        price_low = Decimal('3035')
        should_trigger_low = price_low <= trigger
        assert should_trigger_low == True, "SHOULD trigger at 3035"
    
    def test_short_trigger_at_correct_rise_level(self):
        """SHORT triggers when price >= trigger_price (5% above min)"""
        signal = ReentrySignal(
            signal_id=6,
            symbol='ETHUSDT',
            exchange='binance',
            side='short',
            original_entry_price=Decimal('3100'),
            original_entry_time=datetime.now(timezone.utc) - timedelta(hours=1),
            last_exit_price=Decimal('3000'),
            last_exit_time=datetime.now(timezone.utc) - timedelta(minutes=10),
            last_exit_reason='trailing_stop',
            drop_percent=Decimal('5.0'),
            max_price_after_exit=Decimal('3000'),
            min_price_after_exit=Decimal('2800'),
            cooldown_sec=300,
            max_reentries=3,
            reentry_count=0,
            status='active',
        )
        
        trigger = signal.get_reentry_trigger_price()
        assert trigger == Decimal('2940'), f"Trigger should be 2940, got {trigger}"
        
        # Price at 2930 - should NOT trigger (below trigger)
        price_low = Decimal('2930')
        should_trigger_low = price_low >= trigger
        assert should_trigger_low == False, "Should NOT trigger at 2930"
        
        # Price at 2950 - SHOULD trigger (above trigger)
        price_high = Decimal('2950')
        should_trigger_high = price_high >= trigger
        assert should_trigger_high == True, "SHOULD trigger at 2950"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
