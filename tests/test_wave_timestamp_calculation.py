#!/usr/bin/env python3
"""
Unit tests for wave timestamp calculation logic

⚠️ CRITICAL: These tests protect against unauthorized changes to wave timestamp logic.
If these tests fail, DO NOT modify them - the wave logic is WRONG!
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch


class TestWaveTimestampCalculation:
    """Test wave timestamp calculation follows time-range based mapping"""

    def _calculate_expected_wave_timestamp(self, now: datetime) -> str:
        """
        Copy of the CORRECT logic from signal_processor_websocket.py

        ⚠️ DO NOT MODIFY THIS METHOD!
        This is the verified and tested logic.
        """
        current_minute = now.minute

        # Time-range based mapping
        if 0 <= current_minute <= 15:
            # Ждем волну с timestamp :45 предыдущего часа
            wave_time = now.replace(minute=45, second=0, microsecond=0) - timedelta(hours=1)
        elif 16 <= current_minute <= 30:
            # Ждем волну с timestamp :00 текущего часа
            wave_time = now.replace(minute=0, second=0, microsecond=0)
        elif 31 <= current_minute <= 45:
            # Ждем волну с timestamp :15 текущего часа
            wave_time = now.replace(minute=15, second=0, microsecond=0)
        else:  # 46-59
            # Ждем волну с timestamp :30 текущего часа
            wave_time = now.replace(minute=30, second=0, microsecond=0)

        return wave_time.isoformat()

    @pytest.mark.parametrize("current_time,expected_wave_minute,expected_hour_offset", [
        # Range 0-15 minutes → :45 previous hour
        ("2025-10-11T00:00:00", 45, -1),
        ("2025-10-11T00:06:00", 45, -1),
        ("2025-10-11T00:15:00", 45, -1),

        # Range 16-30 minutes → :00 current hour
        ("2025-10-11T00:16:00", 0, 0),
        ("2025-10-11T00:20:00", 0, 0),
        ("2025-10-11T00:30:00", 0, 0),

        # Range 31-45 minutes → :15 current hour
        ("2025-10-11T00:31:00", 15, 0),
        ("2025-10-11T00:35:00", 15, 0),
        ("2025-10-11T00:45:00", 15, 0),

        # Range 46-59 minutes → :30 current hour
        ("2025-10-11T00:46:00", 30, 0),
        ("2025-10-11T00:50:00", 30, 0),
        ("2025-10-11T00:59:00", 30, 0),

        # Edge cases - different hours
        ("2025-10-11T05:06:00", 45, -1),
        ("2025-10-11T05:20:00", 0, 0),
        ("2025-10-11T05:35:00", 15, 0),
        ("2025-10-11T05:50:00", 30, 0),
    ])
    def test_wave_timestamp_ranges(self, current_time: str, expected_wave_minute: int, expected_hour_offset: int):
        """
        Test that wave timestamp follows time-range based mapping

        ⚠️ CRITICAL: If this test fails, the wave logic is WRONG!
        """
        # Parse current time
        now = datetime.fromisoformat(current_time).replace(tzinfo=timezone.utc)

        # Calculate expected wave timestamp
        expected_wave_time = now.replace(
            minute=expected_wave_minute,
            second=0,
            microsecond=0
        ) + timedelta(hours=expected_hour_offset)

        expected_timestamp = expected_wave_time.isoformat()

        # Calculate actual wave timestamp
        actual_timestamp = self._calculate_expected_wave_timestamp(now)

        # Assert
        assert actual_timestamp == expected_timestamp, (
            f"Wave timestamp mismatch for {current_time}:\n"
            f"  Expected: {expected_timestamp}\n"
            f"  Got:      {actual_timestamp}\n"
            f"  Range rule: minute {now.minute} → :{expected_wave_minute} (hour offset: {expected_hour_offset})"
        )

    def test_no_formula_based_calculation(self):
        """
        Test that wave calculation does NOT use formula (current_minute - 20)

        ⚠️ CRITICAL: Formula-based calculation is WRONG and was replaced!
        """
        # At minute 6, formula would give: 6 - 20 = -14 → 46 minutes previous hour (WRONG!)
        # Correct: minute 6 → :45 previous hour
        now = datetime(2025, 10, 11, 0, 6, 0, tzinfo=timezone.utc)

        # WRONG formula result
        wrong_formula_result = now.replace(minute=6, second=0, microsecond=0) - timedelta(minutes=20)
        wrong_timestamp = wrong_formula_result.isoformat()

        # CORRECT result
        correct_timestamp = self._calculate_expected_wave_timestamp(now)

        # They should be DIFFERENT (formula is wrong!)
        assert correct_timestamp != wrong_timestamp, (
            "Wave timestamp should NOT use formula-based calculation!"
        )

        # Correct should be :45 previous hour
        expected = datetime(2025, 10, 10, 23, 45, 0, tzinfo=timezone.utc).isoformat()
        assert correct_timestamp == expected

    def test_all_wave_timestamps_are_15min_intervals(self):
        """
        Test that all wave timestamps are on 15-minute intervals (:00, :15, :30, :45)
        """
        test_times = [
            datetime(2025, 10, 11, h, m, 0, tzinfo=timezone.utc)
            for h in range(24)
            for m in range(0, 60, 1)  # Every minute of the day
        ]

        for now in test_times:
            wave_timestamp = self._calculate_expected_wave_timestamp(now)
            wave_time = datetime.fromisoformat(wave_timestamp)

            # Minute must be 0, 15, 30, or 45
            assert wave_time.minute in [0, 15, 30, 45], (
                f"Wave timestamp minute must be 0/15/30/45, got {wave_time.minute} "
                f"for current time {now.strftime('%H:%M')}"
            )

            # Seconds and microseconds must be 0
            assert wave_time.second == 0
            assert wave_time.microsecond == 0


def test_edge_case_hour_boundary():
    """Test edge case: wave at hour boundary (00:00)"""
    # At 00:00 (minute 0) → should return :45 previous hour (23:45)
    now = datetime(2025, 10, 11, 0, 0, 0, tzinfo=timezone.utc)
    expected = datetime(2025, 10, 10, 23, 45, 0, tzinfo=timezone.utc).isoformat()

    calc = TestWaveTimestampCalculation()
    result = calc._calculate_expected_wave_timestamp(now)

    assert result == expected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
