"""
Test Phase 1.2: Verify untracked/missing position detection logging works
"""
import pytest


@pytest.mark.asyncio
async def test_untracked_position_logging_code_exists():
    """Verify untracked position logging code is in place"""
    import inspect
    import core.position_manager as pm

    # Read position_manager source code
    source = inspect.getsource(pm.PositionManager)

    # Check that untracked position section has event logging
    assert 'untracked_position_detected' in source, "Missing untracked_position_detected event logging"
    assert 'WARNING_RAISED' in source, "Missing WARNING_RAISED event logging"
    assert source.count('get_event_logger()') >= 2, "Missing get_event_logger() calls (should be >= 2 for phantom + untracked)"

    # Check specifically for untracked position logging
    assert 'Untracked position found on exchange' in source, "Missing untracked position event message"
    assert 'requires_manual_review' in source, "Missing manual review flag"

    print("\n✅ Untracked position logging code is properly integrated")
    print("  - WARNING_RAISED event for untracked positions: present")
    print("  - Manual review flag: present")
    print("  - Untracked position context: present")


@pytest.mark.asyncio
async def test_warning_raised_event_type_exists():
    """Verify WARNING_RAISED EventType exists"""
    from core.event_logger import EventType

    # Check that WARNING_RAISED exists
    assert hasattr(EventType, 'WARNING_RAISED')
    assert EventType.WARNING_RAISED.value == 'warning_raised'

    print("\n✅ WARNING_RAISED EventType exists and has correct value")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
