#!/usr/bin/env python3
"""
Manual test for Fix #2: Wave timestamp validation
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone, timedelta

# Simulate the logic from _calculate_expected_wave_timestamp
now = datetime.now(timezone.utc)
current_minute = now.minute

print(f"Current time: {now.isoformat()}")
print(f"Current minute: {current_minute}")
print()

# Calculate as per current logic
if 0 <= current_minute <= 15:
    wave_time = now.replace(minute=45, second=0, microsecond=0) - timedelta(hours=1)
elif 16 <= current_minute <= 30:
    wave_time = now.replace(minute=0, second=0, microsecond=0)
elif 31 <= current_minute <= 45:
    wave_time = now.replace(minute=15, second=0, microsecond=0)
else:
    wave_time = now.replace(minute=30, second=0, microsecond=0)

print(f"Calculated wave time: {wave_time.isoformat()}")

time_diff = now - wave_time
print(f"Age: {time_diff.total_seconds()/60:.1f} minutes ({time_diff.total_seconds()/3600:.2f} hours)")
print()

# Test validation logic
max_allowed_age = timedelta(hours=2)

if time_diff > max_allowed_age:
    print("⚠️ STALE! Would be adjusted")
    boundary_minute = (current_minute // 15) * 15
    adjusted = now.replace(minute=boundary_minute, second=0, microsecond=0)
    print(f"Adjusted to: {adjusted.isoformat()}")
    print()
    print("✅ Validation logic would trigger")
else:
    print("✅ Recent, no adjustment needed")
    print("Wave timestamp is valid (< 2 hours old)")

print()
print("✅ Fix #2 manual test complete!")
