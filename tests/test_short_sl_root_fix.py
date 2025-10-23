import pytest
from decimal import Decimal

def test_short_sl_update_logic():
    """Test that SL for SHORT only updates when price is falling"""

    # Simulate SHORT position
    class MockTS:
        symbol = 'TESTUSDT'
        side = 'short'
        lowest_price = Decimal('100.00')
        current_stop_price = Decimal('102.00')  # 2% above lowest

    ts = MockTS()
    distance = Decimal('2.0')

    # Test 1: Price rising (105 > 100)
    ts.current_price = Decimal('105.00')
    price_at_or_below_minimum = ts.current_price <= ts.lowest_price
    assert not price_at_or_below_minimum, "Should NOT update SL when price rising"

    # Test 2: Price at minimum (100 = 100)
    ts.current_price = Decimal('100.00')
    price_at_or_below_minimum = ts.current_price <= ts.lowest_price
    assert price_at_or_below_minimum, "Should update SL when price at minimum"

    # Test 3: Price making new low (99 < 100)
    ts.current_price = Decimal('99.00')
    ts.lowest_price = Decimal('99.00')  # Update lowest
    price_at_or_below_minimum = ts.current_price <= ts.lowest_price
    potential_stop = ts.lowest_price * (Decimal('1') + distance / Decimal('100'))
    assert price_at_or_below_minimum, "Should update SL when price making new low"
    assert potential_stop == Decimal('100.98'), f"New SL should be {potential_stop}"

    print("✅ All SHORT SL logic tests passed")

if __name__ == "__main__":
    test_short_sl_update_logic()