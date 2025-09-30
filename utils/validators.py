"""
Input validation utilities
"""
from typing import Any, Optional
from decimal import Decimal
import re
import logging

logger = logging.getLogger(__name__)


def validate_symbol(symbol: str) -> bool:
    """
    Validate trading symbol format

    Args:
        symbol: Trading pair symbol (e.g., BTCUSDT)

    Returns:
        True if valid, False otherwise
    """
    # Check format: should be uppercase letters only
    pattern = r'^[A-Z]{4,12}$'
    return bool(re.match(pattern, symbol))


def validate_price(price: Any, min_price: float = 0.0) -> Optional[float]:
    """
    Validate and convert price

    Args:
        price: Price value
        min_price: Minimum allowed price

    Returns:
        Float price if valid, None otherwise
    """
    try:
        price_float = float(price)
        if price_float <= min_price:
            return None
        return price_float
    except (ValueError, TypeError):
        return None


def validate_quantity(quantity: Any, min_qty: float = 0.0) -> Optional[float]:
    """
    Validate and convert quantity

    Args:
        quantity: Quantity value
        min_qty: Minimum allowed quantity

    Returns:
        Float quantity if valid, None otherwise
    """
    try:
        qty_float = float(quantity)
        if qty_float <= min_qty:
            return None
        return qty_float
    except (ValueError, TypeError):
        return None


def validate_percentage(percentage: Any, min_val: float = 0, max_val: float = 100) -> Optional[float]:
    """
    Validate percentage value

    Args:
        percentage: Percentage value
        min_val: Minimum allowed value
        max_val: Maximum allowed value

    Returns:
        Float percentage if valid, None otherwise
    """
    try:
        pct_float = float(percentage)
        if pct_float < min_val or pct_float > max_val:
            return None
        return pct_float
    except (ValueError, TypeError):
        return None


def validate_side(side: str) -> Optional[str]:
    """
    Validate order side

    Args:
        side: Order side (BUY/SELL, LONG/SHORT)

    Returns:
        Normalized side if valid, None otherwise
    """
    side_upper = side.upper()

    if side_upper in ['BUY', 'LONG']:
        return 'BUY'
    elif side_upper in ['SELL', 'SHORT']:
        return 'SELL'
    else:
        return None


def validate_decimal(value: Any, precision: int = 8) -> Optional[Decimal]:
    """
    Validate and convert to Decimal

    Args:
        value: Value to convert
        precision: Decimal precision

    Returns:
        Decimal if valid, None otherwise
    """
    try:
        decimal_value = Decimal(str(value))
        # Check if within precision
        if decimal_value.as_tuple().exponent < -precision:
            # Round to precision
            decimal_value = decimal_value.quantize(Decimal(10) ** -precision)
        return decimal_value
    except (ValueError, TypeError, ArithmeticError) as e:
        logger.warning(f"Failed to validate decimal value {value}: {e}")
        return None