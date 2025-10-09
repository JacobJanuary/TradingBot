"""
Unit Tests for Wave Timestamp Calculation

Tests the critical _calculate_expected_wave_timestamp() function
to prevent regression of the timestamp calculation bug fixed in Phase 5.

BUG HISTORY:
- Original bug: Used hardcoded offset (20-21 minutes) → wrong timestamps
- Result: 0% wave detection rate, no positions opened
- Fix: Time-range based mapping (0-15→45, 16-30→00, 31-45→15, 46-59→30)

Date: 2025-10-10
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timezone
from core.signal_processor_websocket import WebSocketSignalProcessor


class TestWaveTimestampCalculation:
    """Test suite for wave timestamp calculation logic"""

    @pytest.fixture
    def processor(self):
        """Create a minimal WebSocketSignalProcessor instance for testing"""
        # Create minimal mock to avoid complex initialization
        processor = Mock(spec=WebSocketSignalProcessor)
        processor.wave_check_minutes = [6, 20, 35, 50]

        # Bind the real method to the mock
        from types import MethodType
        processor._calculate_expected_wave_timestamp = MethodType(
            WebSocketSignalProcessor._calculate_expected_wave_timestamp,
            processor
        )

        return processor

    def test_early_hour_range_0_to_15_minutes(self, processor):
        """
        Test: 0-15 minutes → expects :45 of previous hour

        Example: 00:06:00 → expects 23:45:00 (previous day)
        """
        # Mock datetime to 2025-10-10 00:06:00 UTC
        test_time = datetime(2025, 10, 10, 0, 6, 0, tzinfo=timezone.utc)

        with patch('core.signal_processor_websocket.datetime') as mock_datetime:
            mock_datetime.now.return_value = test_time

            result = processor._calculate_expected_wave_timestamp()

            # Expected: 2025-10-09 23:45:00
            assert '2025-10-09T23:45:00' in result
            assert result == '2025-10-09T23:45:00+00:00'

    def test_early_hour_boundary_minute_0(self, processor):
        """Test boundary: exactly 00:00 → expects :45 of previous hour"""
        test_time = datetime(2025, 10, 10, 0, 0, 0, tzinfo=timezone.utc)

        with patch('core.signal_processor_websocket.datetime') as mock_datetime:
            mock_datetime.now.return_value = test_time

            result = processor._calculate_expected_wave_timestamp()

            assert '2025-10-09T23:45:00' in result

    def test_early_hour_boundary_minute_15(self, processor):
        """Test boundary: exactly 00:15 → expects :45 of previous hour"""
        test_time = datetime(2025, 10, 10, 0, 15, 0, tzinfo=timezone.utc)

        with patch('core.signal_processor_websocket.datetime') as mock_datetime:
            mock_datetime.now.return_value = test_time

            result = processor._calculate_expected_wave_timestamp()

            assert '2025-10-09T23:45:00' in result

    def test_first_quarter_range_16_to_30_minutes(self, processor):
        """
        Test: 16-30 minutes → expects :00 of current hour

        Example: 00:20:00 → expects 00:00:00
        """
        test_time = datetime(2025, 10, 10, 0, 20, 0, tzinfo=timezone.utc)

        with patch('core.signal_processor_websocket.datetime') as mock_datetime:
            mock_datetime.now.return_value = test_time

            result = processor._calculate_expected_wave_timestamp()

            # Expected: 2025-10-10 00:00:00
            assert '2025-10-10T00:00:00' in result
            assert result == '2025-10-10T00:00:00+00:00'

    def test_first_quarter_boundary_minute_16(self, processor):
        """Test boundary: exactly 00:16 → expects :00"""
        test_time = datetime(2025, 10, 10, 0, 16, 0, tzinfo=timezone.utc)

        with patch('core.signal_processor_websocket.datetime') as mock_datetime:
            mock_datetime.now.return_value = test_time

            result = processor._calculate_expected_wave_timestamp()

            assert '2025-10-10T00:00:00' in result

    def test_first_quarter_boundary_minute_30(self, processor):
        """Test boundary: exactly 00:30 → expects :00"""
        test_time = datetime(2025, 10, 10, 0, 30, 0, tzinfo=timezone.utc)

        with patch('core.signal_processor_websocket.datetime') as mock_datetime:
            mock_datetime.now.return_value = test_time

            result = processor._calculate_expected_wave_timestamp()

            assert '2025-10-10T00:00:00' in result

    def test_second_quarter_range_31_to_45_minutes(self, processor):
        """
        Test: 31-45 minutes → expects :15 of current hour

        Example: 00:35:00 → expects 00:15:00
        """
        test_time = datetime(2025, 10, 10, 0, 35, 0, tzinfo=timezone.utc)

        with patch('core.signal_processor_websocket.datetime') as mock_datetime:
            mock_datetime.now.return_value = test_time

            result = processor._calculate_expected_wave_timestamp()

            # Expected: 2025-10-10 00:15:00
            assert '2025-10-10T00:15:00' in result
            assert result == '2025-10-10T00:15:00+00:00'

    def test_second_quarter_boundary_minute_31(self, processor):
        """Test boundary: exactly 00:31 → expects :15"""
        test_time = datetime(2025, 10, 10, 0, 31, 0, tzinfo=timezone.utc)

        with patch('core.signal_processor_websocket.datetime') as mock_datetime:
            mock_datetime.now.return_value = test_time

            result = processor._calculate_expected_wave_timestamp()

            assert '2025-10-10T00:15:00' in result

    def test_second_quarter_boundary_minute_45(self, processor):
        """Test boundary: exactly 00:45 → expects :15"""
        test_time = datetime(2025, 10, 10, 0, 45, 0, tzinfo=timezone.utc)

        with patch('core.signal_processor_websocket.datetime') as mock_datetime:
            mock_datetime.now.return_value = test_time

            result = processor._calculate_expected_wave_timestamp()

            assert '2025-10-10T00:15:00' in result

    def test_third_quarter_range_46_to_59_minutes(self, processor):
        """
        Test: 46-59 minutes → expects :30 of current hour

        Example: 00:50:00 → expects 00:30:00
        """
        test_time = datetime(2025, 10, 10, 0, 50, 0, tzinfo=timezone.utc)

        with patch('core.signal_processor_websocket.datetime') as mock_datetime:
            mock_datetime.now.return_value = test_time

            result = processor._calculate_expected_wave_timestamp()

            # Expected: 2025-10-10 00:30:00
            assert '2025-10-10T00:30:00' in result
            assert result == '2025-10-10T00:30:00+00:00'

    def test_third_quarter_boundary_minute_46(self, processor):
        """Test boundary: exactly 00:46 → expects :30"""
        test_time = datetime(2025, 10, 10, 0, 46, 0, tzinfo=timezone.utc)

        with patch('core.signal_processor_websocket.datetime') as mock_datetime:
            mock_datetime.now.return_value = test_time

            result = processor._calculate_expected_wave_timestamp()

            assert '2025-10-10T00:30:00' in result

    def test_third_quarter_boundary_minute_59(self, processor):
        """Test boundary: exactly 00:59 → expects :30"""
        test_time = datetime(2025, 10, 10, 0, 59, 0, tzinfo=timezone.utc)

        with patch('core.signal_processor_websocket.datetime') as mock_datetime:
            mock_datetime.now.return_value = test_time

            result = processor._calculate_expected_wave_timestamp()

            assert '2025-10-10T00:30:00' in result

    def test_hour_boundary_23_59_to_00_00(self, processor):
        """Test day boundary: 23:59 → expects 23:30, then 00:00 → expects 23:45 previous day"""
        # Test 23:59
        test_time_1 = datetime(2025, 10, 10, 23, 59, 0, tzinfo=timezone.utc)

        with patch('core.signal_processor_websocket.datetime') as mock_datetime:
            mock_datetime.now.return_value = test_time_1
            result_1 = processor._calculate_expected_wave_timestamp()
            assert '2025-10-10T23:30:00' in result_1

        # Test 00:00 next day
        test_time_2 = datetime(2025, 10, 11, 0, 0, 0, tzinfo=timezone.utc)

        with patch('core.signal_processor_websocket.datetime') as mock_datetime:
            mock_datetime.now.return_value = test_time_2
            result_2 = processor._calculate_expected_wave_timestamp()
            assert '2025-10-10T23:45:00' in result_2

    def test_different_hours_same_pattern(self, processor):
        """Test that pattern repeats correctly across different hours"""
        test_cases = [
            # (hour, minute, expected_hour, expected_minute)
            (3, 6, 2, 45),   # 03:06 → 02:45
            (3, 20, 3, 0),   # 03:20 → 03:00
            (3, 35, 3, 15),  # 03:35 → 03:15
            (3, 50, 3, 30),  # 03:50 → 03:30
            (12, 6, 11, 45), # 12:06 → 11:45
            (12, 20, 12, 0), # 12:20 → 12:00
            (23, 35, 23, 15),# 23:35 → 23:15
            (23, 50, 23, 30),# 23:50 → 23:30
        ]

        for hour, minute, exp_hour, exp_minute in test_cases:
            test_time = datetime(2025, 10, 10, hour, minute, 0, tzinfo=timezone.utc)

            with patch('core.signal_processor_websocket.datetime') as mock_datetime:
                mock_datetime.now.return_value = test_time
                result = processor._calculate_expected_wave_timestamp()

                # Extract hour and minute from result
                time_part = result.split('T')[1].split('+')[0]
                result_hour = int(time_part.split(':')[0])
                result_minute = int(time_part.split(':')[1])

                assert result_minute == exp_minute, \
                    f"At {hour}:{minute:02d}, expected minute {exp_minute} but got {result_minute}"

                # Hour might be different due to day boundary
                if hour == 0 and minute < 16:
                    # Previous day
                    assert result.startswith('2025-10-09'), \
                        f"At {hour}:{minute:02d}, expected previous day"
                else:
                    assert result_hour == exp_hour, \
                        f"At {hour}:{minute:02d}, expected hour {exp_hour} but got {result_hour}"

    def test_iso_format_compliance(self, processor):
        """Verify output matches ISO format required by signal matching"""
        test_time = datetime(2025, 10, 10, 0, 20, 0, tzinfo=timezone.utc)

        with patch('core.signal_processor_websocket.datetime') as mock_datetime:
            mock_datetime.now.return_value = test_time

            result = processor._calculate_expected_wave_timestamp()

            # Must have 'T' separator
            assert 'T' in result

            # Must have timezone info
            assert '+00:00' in result or 'Z' in result

            # Must match datetime.isoformat() output
            expected_format = datetime(2025, 10, 10, 0, 0, 0, tzinfo=timezone.utc).isoformat()
            assert result == expected_format

    def test_regression_original_bug_scenarios(self, processor):
        """
        Test scenarios from the original bug report

        ORIGINAL BUG:
        - At 00:06 → looked for 19:46 (WRONG)
        - At 00:20 → looked for 19:59 (WRONG)

        CORRECT BEHAVIOR:
        - At 00:06 → should look for 23:45 previous day
        - At 00:20 → should look for 00:00
        """
        # Scenario 1: Bug reported at 00:06
        test_time_1 = datetime(2025, 10, 10, 0, 6, 0, tzinfo=timezone.utc)

        with patch('core.signal_processor_websocket.datetime') as mock_datetime:
            mock_datetime.now.return_value = test_time_1
            result_1 = processor._calculate_expected_wave_timestamp()

            # Must NOT contain 19:46
            assert '19:46' not in result_1

            # Must contain 23:45 of previous day
            assert '2025-10-09T23:45:00' in result_1

        # Scenario 2: Bug reported at 00:20
        test_time_2 = datetime(2025, 10, 10, 0, 20, 0, tzinfo=timezone.utc)

        with patch('core.signal_processor_websocket.datetime') as mock_datetime:
            mock_datetime.now.return_value = test_time_2
            result_2 = processor._calculate_expected_wave_timestamp()

            # Must NOT contain 19:59
            assert '19:59' not in result_2

            # Must contain 00:00 of current day
            assert '2025-10-10T00:00:00' in result_2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
