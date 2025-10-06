"""
Unit tests for utils/order_helpers.py
Tests unified order access regardless of type (dict vs dataclass)
"""
import pytest
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any

from utils.order_helpers import (
    safe_order_get,
    order_to_dict,
    is_order_dict,
    is_order_dataclass,
    normalize_order_timestamp,
    OrderAccessor,
    get_order_id,
    get_order_symbol,
    get_order_status,
    get_order_type,
    get_order_side,
    get_order_amount,
    get_order_filled,
    get_order_price,
    get_order_remaining,
)


@dataclass
class MockOrderResult:
    """Mock OrderResult dataclass for testing"""
    id: str
    symbol: str
    side: str
    type: str
    amount: float
    price: float
    filled: float
    remaining: float
    status: str
    timestamp: datetime


class TestSafeOrderGet:
    """Test safe_order_get function"""
    
    def test_dict_access(self):
        """Test accessing dict order"""
        order = {'id': '123', 'symbol': 'BTC/USDT', 'amount': 0.5}
        
        assert safe_order_get(order, 'id') == '123'
        assert safe_order_get(order, 'symbol') == 'BTC/USDT'
        assert safe_order_get(order, 'amount') == 0.5
    
    def test_dataclass_access(self):
        """Test accessing dataclass order"""
        order = MockOrderResult(
            id='456',
            symbol='ETH/USDT',
            side='buy',
            type='market',
            amount=1.0,
            price=2000.0,
            filled=1.0,
            remaining=0.0,
            status='closed',
            timestamp=datetime.now()
        )
        
        assert safe_order_get(order, 'id') == '456'
        assert safe_order_get(order, 'symbol') == 'ETH/USDT'
        assert safe_order_get(order, 'amount') == 1.0
        assert safe_order_get(order, 'side') == 'buy'
    
    def test_missing_field_with_default(self):
        """Test missing field returns default"""
        order = {'id': '123'}
        
        assert safe_order_get(order, 'missing', default='N/A') == 'N/A'
        assert safe_order_get(order, 'missing', default=0) == 0
        assert safe_order_get(order, 'missing') is None
    
    def test_none_order(self):
        """Test None order returns default"""
        assert safe_order_get(None, 'id', default='default') == 'default'
        assert safe_order_get(None, 'id') is None


class TestOrderToDict:
    """Test order_to_dict function"""
    
    def test_dict_passthrough(self):
        """Test dict is returned as is"""
        order_dict = {'id': '123', 'symbol': 'BTC/USDT'}
        result = order_to_dict(order_dict)
        
        assert result == order_dict
        assert result is order_dict  # Same object
    
    def test_dataclass_conversion(self):
        """Test dataclass is converted to dict"""
        order = MockOrderResult(
            id='456',
            symbol='ETH/USDT',
            side='buy',
            type='market',
            amount=1.0,
            price=2000.0,
            filled=1.0,
            remaining=0.0,
            status='closed',
            timestamp=datetime(2025, 1, 1, 12, 0, 0)
        )
        
        result = order_to_dict(order)
        
        assert isinstance(result, dict)
        assert result['id'] == '456'
        assert result['symbol'] == 'ETH/USDT'
        assert result['amount'] == 1.0
    
    def test_none_order(self):
        """Test None order returns empty dict"""
        assert order_to_dict(None) == {}


class TestOrderTypeChecks:
    """Test is_order_dict and is_order_dataclass"""
    
    def test_is_order_dict(self):
        """Test dict detection"""
        assert is_order_dict({'id': '123'}) is True
        assert is_order_dict([1, 2, 3]) is False
        assert is_order_dict(None) is False
    
    def test_is_order_dataclass(self):
        """Test dataclass detection"""
        order = MockOrderResult(
            id='456', symbol='BTC/USDT', side='buy', type='market',
            amount=1.0, price=50000.0, filled=1.0, remaining=0.0,
            status='closed', timestamp=datetime.now()
        )
        
        assert is_order_dataclass(order) is True
        assert is_order_dataclass({'id': '123'}) is False
        assert is_order_dataclass(None) is False


class TestNormalizeOrderTimestamp:
    """Test timestamp normalization"""
    
    def test_datetime_passthrough(self):
        """Test datetime object is returned as is"""
        dt = datetime(2025, 1, 1, 12, 0, 0)
        order = {'timestamp': dt}
        
        result = normalize_order_timestamp(order)
        assert result == dt
    
    def test_millisecond_conversion(self):
        """Test milliseconds are converted to datetime"""
        # 2025-01-01 12:00:00 UTC in milliseconds
        timestamp_ms = 1735732800000
        order = {'timestamp': timestamp_ms}
        
        result = normalize_order_timestamp(order)
        assert isinstance(result, datetime)
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 1
    
    def test_missing_timestamp(self):
        """Test missing timestamp returns None"""
        order = {'id': '123'}
        assert normalize_order_timestamp(order) is None
    
    def test_none_timestamp(self):
        """Test None timestamp returns None"""
        order = {'timestamp': None}
        assert normalize_order_timestamp(order) is None


class TestOrderAccessor:
    """Test OrderAccessor wrapper class"""
    
    def test_attribute_access(self):
        """Test attribute-style access"""
        order = {'id': '123', 'symbol': 'BTC/USDT', 'amount': 0.5}
        accessor = OrderAccessor(order)
        
        assert accessor.id == '123'
        assert accessor.symbol == 'BTC/USDT'
        assert accessor.amount == 0.5
    
    def test_dict_access(self):
        """Test dict-style access"""
        order = {'id': '123', 'symbol': 'BTC/USDT'}
        accessor = OrderAccessor(order)
        
        assert accessor['id'] == '123'
        assert accessor['symbol'] == 'BTC/USDT'
    
    def test_get_method(self):
        """Test get method with default"""
        order = {'id': '123'}
        accessor = OrderAccessor(order)
        
        assert accessor.get('id') == '123'
        assert accessor.get('missing', 'default') == 'default'
    
    def test_to_dict_method(self):
        """Test conversion to dict"""
        order = {'id': '123', 'symbol': 'BTC/USDT'}
        accessor = OrderAccessor(order)
        
        result = accessor.to_dict()
        assert result == order
    
    def test_raw_property(self):
        """Test raw property returns original order"""
        order = {'id': '123'}
        accessor = OrderAccessor(order)
        
        assert accessor.raw is order


class TestConvenienceFunctions:
    """Test convenience accessor functions"""
    
    @pytest.fixture
    def order_dict(self):
        """Sample order dict"""
        return {
            'id': '123456',
            'symbol': 'BTC/USDT',
            'side': 'buy',
            'type': 'market',
            'amount': 0.5,
            'price': 50000.0,
            'filled': 0.5,
            'remaining': 0.0,
            'status': 'closed'
        }
    
    @pytest.fixture
    def order_dataclass(self):
        """Sample order dataclass"""
        return MockOrderResult(
            id='789',
            symbol='ETH/USDT',
            side='sell',
            type='limit',
            amount=1.0,
            price=2000.0,
            filled=0.5,
            remaining=0.5,
            status='open',
            timestamp=datetime.now()
        )
    
    def test_get_order_id(self, order_dict, order_dataclass):
        """Test get_order_id"""
        assert get_order_id(order_dict) == '123456'
        assert get_order_id(order_dataclass) == '789'
        assert get_order_id(None) is None
    
    def test_get_order_symbol(self, order_dict, order_dataclass):
        """Test get_order_symbol"""
        assert get_order_symbol(order_dict) == 'BTC/USDT'
        assert get_order_symbol(order_dataclass) == 'ETH/USDT'
    
    def test_get_order_status(self, order_dict, order_dataclass):
        """Test get_order_status"""
        assert get_order_status(order_dict) == 'closed'
        assert get_order_status(order_dataclass) == 'open'
    
    def test_get_order_type(self, order_dict, order_dataclass):
        """Test get_order_type"""
        assert get_order_type(order_dict) == 'market'
        assert get_order_type(order_dataclass) == 'limit'
    
    def test_get_order_side(self, order_dict, order_dataclass):
        """Test get_order_side"""
        assert get_order_side(order_dict) == 'buy'
        assert get_order_side(order_dataclass) == 'sell'
    
    def test_get_order_amount(self, order_dict, order_dataclass):
        """Test get_order_amount"""
        assert get_order_amount(order_dict) == 0.5
        assert get_order_amount(order_dataclass) == 1.0
        assert get_order_amount({}) == 0.0  # Default
    
    def test_get_order_filled(self, order_dict, order_dataclass):
        """Test get_order_filled"""
        assert get_order_filled(order_dict) == 0.5
        assert get_order_filled(order_dataclass) == 0.5
        assert get_order_filled({}) == 0.0  # Default
    
    def test_get_order_price(self, order_dict, order_dataclass):
        """Test get_order_price"""
        assert get_order_price(order_dict) == 50000.0
        assert get_order_price(order_dataclass) == 2000.0
        assert get_order_price({}) == 0.0  # Default
    
    def test_get_order_remaining(self, order_dict, order_dataclass):
        """Test get_order_remaining"""
        assert get_order_remaining(order_dict) == 0.0
        assert get_order_remaining(order_dataclass) == 0.5
        assert get_order_remaining({}) == 0.0  # Default

