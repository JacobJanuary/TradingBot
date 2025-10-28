"""Unit tests for exchange ID mapping helpers"""
import pytest
from utils.exchange_helpers import exchange_name_to_id, exchange_id_to_name


class TestExchangeNameToId:
    """Tests for exchange_name_to_id()"""

    def test_binance_lowercase(self):
        """Test 'binance' → 1"""
        assert exchange_name_to_id('binance') == 1

    def test_binance_uppercase(self):
        """Test 'BINANCE' → 1 (case-insensitive)"""
        assert exchange_name_to_id('BINANCE') == 1

    def test_binance_mixed_case(self):
        """Test 'Binance' → 1"""
        assert exchange_name_to_id('Binance') == 1

    def test_bybit_lowercase(self):
        """Test 'bybit' → 2"""
        assert exchange_name_to_id('bybit') == 2

    def test_bybit_uppercase(self):
        """Test 'BYBIT' → 2"""
        assert exchange_name_to_id('BYBIT') == 2

    def test_unknown_exchange(self):
        """Test unknown exchange raises ValueError"""
        with pytest.raises(ValueError, match="Unknown exchange name: 'ftx'"):
            exchange_name_to_id('ftx')

    def test_with_whitespace(self):
        """Test with leading/trailing whitespace"""
        assert exchange_name_to_id('  binance  ') == 1
        assert exchange_name_to_id('bybit   ') == 2


class TestExchangeIdToName:
    """Tests for exchange_id_to_name()"""

    def test_binance_id(self):
        """Test 1 → 'binance'"""
        assert exchange_id_to_name(1) == 'binance'

    def test_bybit_id(self):
        """Test 2 → 'bybit'"""
        assert exchange_id_to_name(2) == 'bybit'

    def test_unknown_id(self):
        """Test unknown ID raises ValueError"""
        with pytest.raises(ValueError, match="Unknown exchange_id: 3"):
            exchange_id_to_name(3)

    def test_roundtrip_binance(self):
        """Test 'binance' → 1 → 'binance'"""
        name = 'binance'
        exchange_id = exchange_name_to_id(name)
        result = exchange_id_to_name(exchange_id)
        assert result == name

    def test_roundtrip_bybit(self):
        """Test 'bybit' → 2 → 'bybit'"""
        name = 'bybit'
        exchange_id = exchange_name_to_id(name)
        result = exchange_id_to_name(exchange_id)
        assert result == name
