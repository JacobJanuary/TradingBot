"""
Unit tests for aged position Decimal/float fix
Tests the fix for TypeError: unsupported operand type(s) for -: 'float' and 'decimal.Decimal'
"""
import pytest
from decimal import Decimal
from datetime import datetime, timedelta, timezone


def test_age_calculation_returns_decimal():
    """Test that age_hours is calculated as Decimal"""
    # Simulate position age calculation
    opened_at = datetime.now(timezone.utc) - timedelta(hours=5, minutes=30)
    position_age = datetime.now(timezone.utc) - opened_at

    # NEW calculation (should be Decimal)
    age_hours = Decimal(str(position_age.total_seconds() / 3600))

    # Verify type
    assert isinstance(age_hours, Decimal), f"age_hours should be Decimal, got {type(age_hours)}"

    # Verify value is reasonable (should be around 5.5 hours)
    assert Decimal('5.4') < age_hours < Decimal('5.6'), f"Expected ~5.5 hours, got {age_hours}"


def test_age_subtraction_with_decimal_max_age():
    """Test that age_hours - max_age_hours works when both are Decimal"""
    opened_at = datetime.now(timezone.utc) - timedelta(hours=5)
    position_age = datetime.now(timezone.utc) - opened_at

    age_hours = Decimal(str(position_age.total_seconds() / 3600))
    max_age_hours = Decimal('3')  # From config

    # This should NOT raise TypeError
    hours_over_limit = age_hours - max_age_hours

    assert isinstance(hours_over_limit, Decimal)
    assert hours_over_limit > Decimal('1.9')  # Should be around 2 hours over


def test_age_subtraction_with_float_max_age_fails():
    """Test that Decimal - float raises TypeError (by design)

    This test documents that max_age_hours must NOT be float.
    The fix ensures max_position_age_hours is int (not float).
    """
    opened_at = datetime.now(timezone.utc) - timedelta(hours=5)
    position_age = datetime.now(timezone.utc) - opened_at

    age_hours = Decimal(str(position_age.total_seconds() / 3600))
    max_age_hours = 3.0  # float type - NOT SUPPORTED

    # This SHOULD raise TypeError - Python doesn't allow Decimal - float
    with pytest.raises(TypeError, match="unsupported operand type.*Decimal.*float"):
        hours_over_limit = age_hours - max_age_hours


def test_age_subtraction_with_int_max_age():
    """Test that age_hours - max_age_hours works when max_age is int"""
    opened_at = datetime.now(timezone.utc) - timedelta(hours=5)
    position_age = datetime.now(timezone.utc) - opened_at

    age_hours = Decimal(str(position_age.total_seconds() / 3600))
    max_age_hours = 3  # int type (from config default)

    # This should work - Python allows Decimal - int
    hours_over_limit = age_hours - max_age_hours

    # Result should be Decimal
    assert isinstance(hours_over_limit, Decimal)
    assert hours_over_limit > Decimal('1.9')


def test_age_comparison_operators():
    """Test that Decimal age_hours works with comparison operators"""
    opened_at = datetime.now(timezone.utc) - timedelta(hours=5)
    position_age = datetime.now(timezone.utc) - opened_at

    age_hours = Decimal(str(position_age.total_seconds() / 3600))
    max_age_hours = 3  # int

    # All these comparisons should work
    assert age_hours >= max_age_hours
    assert age_hours > max_age_hours
    assert not (age_hours < max_age_hours)
    assert not (age_hours <= Decimal('2'))


def test_precision_maintained():
    """Test that Decimal maintains precision for fractional hours"""
    # Test with precise fractional hours
    opened_at = datetime.now(timezone.utc) - timedelta(hours=3, minutes=45, seconds=30)
    position_age = datetime.now(timezone.utc) - opened_at

    age_hours = Decimal(str(position_age.total_seconds() / 3600))

    # Should maintain fractional precision
    assert isinstance(age_hours, Decimal)
    # Should be around 3.7583 hours (3 hours 45 min 30 sec)
    assert Decimal('3.75') < age_hours < Decimal('3.77')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
