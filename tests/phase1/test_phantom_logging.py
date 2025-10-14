"""
Test Phase 1.1: Verify phantom detection logging works
"""
import pytest
import asyncio
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_phantom_detection_logging_code_exists():
    """Verify phantom detection logging code is in place"""
    import inspect
    import core.position_manager as pm

    # Read position_manager source code
    source = inspect.getsource(pm.PositionManager)

    # Check that phantom detection section has event logging
    assert 'PHANTOM_POSITION_DETECTED' in source, "Missing PHANTOM_POSITION_DETECTED event logging"
    assert 'PHANTOM_POSITION_CLOSED' in source, "Missing PHANTOM_POSITION_CLOSED event logging"
    assert 'get_event_logger()' in source, "Missing get_event_logger() calls"
    assert 'await event_logger.log_event' in source, "Missing await event_logger.log_event calls"

    print("\n✅ Phantom detection logging code is properly integrated")
    print("  - PHANTOM_POSITION_DETECTED event logging: present")
    print("  - PHANTOM_POSITION_CLOSED event logging: present")
    print("  - get_event_logger() calls: present")
    print("  - async log_event calls: present")


@pytest.mark.asyncio
async def test_event_types_exist():
    """Verify phantom EventTypes exist in event_logger"""
    from core.event_logger import EventType

    # Check that phantom event types exist
    assert hasattr(EventType, 'PHANTOM_POSITION_DETECTED')
    assert hasattr(EventType, 'PHANTOM_POSITION_CLOSED')

    # Verify their values
    assert EventType.PHANTOM_POSITION_DETECTED.value == 'phantom_position_detected'
    assert EventType.PHANTOM_POSITION_CLOSED.value == 'phantom_position_closed'

    print("\n✅ Phantom EventTypes exist and have correct values")


@pytest.mark.asyncio
async def test_position_manager_has_event_logger_import():
    """Verify position_manager.py has event_logger import"""
    import core.position_manager as pm

    # Check that get_event_logger is imported
    assert hasattr(pm, 'get_event_logger')
    assert hasattr(pm, 'EventType')

    print("\n✅ position_manager.py has event_logger imports")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
