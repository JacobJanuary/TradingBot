# Position Cleanup Architecture

## Overview
All position cleanup operations now go through centralized method `_cleanup_position_monitoring`
in `position_manager.py`.

## Cleanup Steps (in order):
1. Remove from `position_manager.positions` dict
2. Notify `trailing_stop_manager.on_position_closed()`
3. Remove from `aged_adapter.monitoring_positions`
4. Log `POSITION_CLEANUP` event

## Callers:
- `position_manager.close_position()` - main cleanup path
- `position_manager._reconcile_positions()` - phantom/pre-registered cleanup
- `aged_position_monitor_v2._trigger_market_close()` - aged position cleanup

## Skip Flags:
Use skip flags for partial cleanup scenarios:
- `skip_position_removal` - don't touch positions dict
- `skip_trailing_stop` - don't notify TS manager
- `skip_aged_adapter` - don't remove from aged monitoring
- `skip_events` - don't log cleanup event

## Error Handling:
Method never raises exceptions. All errors are logged and returned in result dict.

## Testing:
See TESTING.md for cleanup verification procedures.
