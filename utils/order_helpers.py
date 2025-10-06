"""
Order Helper Utilities
Provides unified access to order data regardless of format (OrderResult dataclass or raw Dict)

This module solves the inconsistency problem where CCXT returns raw dicts but 
ExchangeManager._parse_order() converts them to OrderResult dataclasses.
"""
from typing import Any, Union, Optional, Dict, TypeVar
from dataclasses import is_dataclass
from datetime import datetime

# Type alias for order data
OrderLike = Union[Dict[str, Any], Any]  # Any to support dataclass instances

T = TypeVar('T')


def safe_order_get(order: OrderLike, field: str, default: T = None) -> T:
    """
    Safely get field value from order regardless of type (dict or dataclass).
    
    Args:
        order: Order data (dict or OrderResult/OrderInfo dataclass)
        field: Field name to retrieve
        default: Default value if field not found
        
    Returns:
        Field value or default
        
    Examples:
        >>> order_dict = {'id': '123', 'symbol': 'BTC/USDT'}
        >>> safe_order_get(order_dict, 'id')
        '123'
        
        >>> from core.exchange_manager import OrderResult
        >>> order_obj = OrderResult(id='123', symbol='BTC/USDT', ...)
        >>> safe_order_get(order_obj, 'id')
        '123'
        
        >>> safe_order_get(order_dict, 'missing', default='N/A')
        'N/A'
    """
    if order is None:
        return default
    
    # Try dict access first (most common case for CCXT raw orders)
    if isinstance(order, dict):
        return order.get(field, default)
    
    # Try object attribute access (for OrderResult/OrderInfo dataclasses)
    if is_dataclass(order) or hasattr(order, field):
        return getattr(order, field, default)
    
    # Last resort: try dict-like access in case it's a custom object
    if hasattr(order, 'get'):
        return order.get(field, default)
    
    return default


def order_to_dict(order: OrderLike) -> Dict[str, Any]:
    """
    Convert order to dictionary regardless of input type.
    
    Args:
        order: Order data (dict or dataclass)
        
    Returns:
        Dictionary representation of order
        
    Examples:
        >>> order_dict = {'id': '123', 'symbol': 'BTC/USDT'}
        >>> order_to_dict(order_dict)
        {'id': '123', 'symbol': 'BTC/USDT'}
        
        >>> order_obj = OrderResult(id='123', symbol='BTC/USDT', ...)
        >>> order_to_dict(order_obj)
        {'id': '123', 'symbol': 'BTC/USDT', ...}
    """
    if order is None:
        return {}
    
    if isinstance(order, dict):
        return order
    
    # For dataclasses
    if is_dataclass(order):
        from dataclasses import asdict
        return asdict(order)
    
    # For objects with __dict__
    if hasattr(order, '__dict__'):
        return order.__dict__.copy()
    
    # Fallback: return empty dict
    return {}


def is_order_dict(order: OrderLike) -> bool:
    """Check if order is a dictionary."""
    return isinstance(order, dict)


def is_order_dataclass(order: OrderLike) -> bool:
    """Check if order is a dataclass (OrderResult/OrderInfo)."""
    return is_dataclass(order)


def normalize_order_timestamp(order: OrderLike) -> Optional[datetime]:
    """
    Extract and normalize timestamp from order.
    
    CCXT returns timestamps in milliseconds, need to convert to datetime.
    
    Args:
        order: Order data
        
    Returns:
        datetime object or None
    """
    timestamp = safe_order_get(order, 'timestamp')
    
    if timestamp is None:
        return None
    
    # If already datetime, return as is
    if isinstance(timestamp, datetime):
        return timestamp
    
    # Convert from milliseconds to datetime
    try:
        if isinstance(timestamp, (int, float)):
            return datetime.fromtimestamp(timestamp / 1000)
    except (ValueError, OSError):
        pass
    
    return None


class OrderAccessor:
    """
    Convenience wrapper for accessing order fields uniformly.
    
    Usage:
        >>> order = OrderAccessor(raw_ccxt_order)
        >>> order.id
        '123456'
        >>> order.symbol
        'BTC/USDT'
        >>> order.filled
        0.5
    """
    
    def __init__(self, order: OrderLike):
        self._order = order
    
    def __getattr__(self, name: str) -> Any:
        """Allow attribute access: order.id, order.symbol, etc."""
        return safe_order_get(self._order, name)
    
    def __getitem__(self, name: str) -> Any:
        """Allow dict-like access: order['id'], order['symbol'], etc."""
        return safe_order_get(self._order, name)
    
    def get(self, name: str, default: Any = None) -> Any:
        """Dict-like get method with default."""
        return safe_order_get(self._order, name, default)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return order_to_dict(self._order)
    
    @property
    def raw(self) -> OrderLike:
        """Get raw underlying order data."""
        return self._order


# Convenience functions for common order fields
def get_order_id(order: OrderLike) -> Optional[str]:
    """Get order ID."""
    return safe_order_get(order, 'id')


def get_order_symbol(order: OrderLike) -> Optional[str]:
    """Get order symbol."""
    return safe_order_get(order, 'symbol')


def get_order_status(order: OrderLike) -> Optional[str]:
    """Get order status."""
    return safe_order_get(order, 'status')


def get_order_type(order: OrderLike) -> Optional[str]:
    """Get order type."""
    return safe_order_get(order, 'type')


def get_order_side(order: OrderLike) -> Optional[str]:
    """Get order side (buy/sell)."""
    return safe_order_get(order, 'side')


def get_order_amount(order: OrderLike) -> float:
    """Get order amount (quantity)."""
    return safe_order_get(order, 'amount', default=0.0)


def get_order_filled(order: OrderLike) -> float:
    """Get filled amount."""
    return safe_order_get(order, 'filled', default=0.0)


def get_order_price(order: OrderLike) -> float:
    """Get order price."""
    return safe_order_get(order, 'price', default=0.0)


def get_order_remaining(order: OrderLike) -> float:
    """Get remaining amount."""
    return safe_order_get(order, 'remaining', default=0.0)

