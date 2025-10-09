"""
Decimal utilities for safe financial calculations
Ensures precision in monetary operations
"""
from decimal import Decimal, ROUND_DOWN, ROUND_UP, getcontext, InvalidOperation
from typing import Union, Optional, Any
import logging

logger = logging.getLogger(__name__)

# Set precision for financial calculations
getcontext().prec = 18
getcontext().rounding = ROUND_DOWN


def safe_decimal(
    value: Any,
    default: Decimal = Decimal('0'),
    field_name: str = "value",
    precision: int = 8
) -> Decimal:
    """
    Safely convert any value to Decimal with error handling

    Handles all edge cases: None, invalid strings, NaN, Infinity, etc.

    Args:
        value: Value to convert (any type)
        default: Default value if conversion fails (default: Decimal('0'))
        field_name: Field name for logging (helps debug)
        precision: Number of decimal places to round to

    Returns:
        Decimal value or default if conversion fails

    Example:
        >>> safe_decimal("123.45")
        Decimal('123.45')
        >>> safe_decimal("invalid", default=Decimal('0'))
        Decimal('0')
        >>> safe_decimal(None)
        Decimal('0')
    """
    # Handle None
    if value is None:
        return default

    # Already Decimal
    if isinstance(value, Decimal):
        try:
            return round_decimal(value, precision)
        except (InvalidOperation, ValueError) as e:
            logger.warning(f"Invalid Decimal value for {field_name}: {value} - {e}")
            return default

    # Try conversion
    try:
        # Convert to string first to avoid float precision issues
        str_value = str(value).strip()

        # Handle empty string
        if not str_value or str_value.lower() in ('', 'none', 'null', 'nan'):
            return default

        # Convert to Decimal
        decimal_value = Decimal(str_value)

        # Check for infinity
        if decimal_value.is_infinite():
            logger.warning(f"Infinite value for {field_name}: {value}")
            return default

        # Check for NaN
        if decimal_value.is_nan():
            logger.warning(f"NaN value for {field_name}: {value}")
            return default

        return round_decimal(decimal_value, precision)

    except (InvalidOperation, ValueError, TypeError, ArithmeticError) as e:
        logger.warning(f"Failed to convert {field_name}='{value}' to Decimal: {e}")
        return default


def to_decimal(value: Union[str, int, float, Decimal], precision: int = 8) -> Decimal:
    """
    Safely convert any numeric type to Decimal
    
    Args:
        value: Value to convert
        precision: Number of decimal places to round to
        
    Returns:
        Decimal value rounded to specified precision
    """
    if value is None:
        return Decimal('0')
    
    if isinstance(value, Decimal):
        return round_decimal(value, precision)
    
    # Convert to string first to avoid float precision issues
    str_value = str(value)
    decimal_value = Decimal(str_value)
    
    return round_decimal(decimal_value, precision)


def round_decimal(value: Decimal, precision: int = 8, rounding=ROUND_DOWN) -> Decimal:
    """
    Round decimal to specified precision
    
    Args:
        value: Decimal value to round
        precision: Number of decimal places
        rounding: Rounding mode (default ROUND_DOWN for safety)
        
    Returns:
        Rounded decimal value
    """
    if precision == 0:
        return value.quantize(Decimal('1'), rounding=rounding)
    
    quantizer = Decimal('0.1') ** precision
    return value.quantize(quantizer, rounding=rounding)


def calculate_quantity(size_usd: Decimal, price: Decimal, precision: int = 8) -> Decimal:
    """
    Calculate quantity from USD size and price
    
    Args:
        size_usd: Position size in USD
        price: Asset price
        precision: Precision for quantity
        
    Returns:
        Quantity rounded down to precision
    """
    if price == 0:
        return Decimal('0')
    
    quantity = size_usd / price
    return round_decimal(quantity, precision, ROUND_DOWN)


def calculate_pnl(
    entry_price: Decimal,
    exit_price: Decimal,
    quantity: Decimal,
    side: str,
    commission_rate: Decimal = Decimal('0.001')
) -> tuple[Decimal, Decimal]:
    """
    Calculate PnL for a position
    
    Args:
        entry_price: Entry price
        exit_price: Exit price
        quantity: Position quantity
        side: 'long' or 'short'
        commission_rate: Commission rate (default 0.1%)
        
    Returns:
        Tuple of (pnl_amount, pnl_percent)
    """
    # Calculate gross PnL
    if side.lower() == 'long':
        gross_pnl = (exit_price - entry_price) * quantity
    else:  # short
        gross_pnl = (entry_price - exit_price) * quantity
    
    # Calculate commissions
    entry_value = entry_price * quantity
    exit_value = exit_price * quantity
    total_commission = (entry_value + exit_value) * commission_rate
    
    # Net PnL
    net_pnl = gross_pnl - total_commission
    
    # PnL percentage
    if entry_value > 0:
        pnl_percent = (net_pnl / entry_value) * Decimal('100')
    else:
        pnl_percent = Decimal('0')
    
    return round_decimal(net_pnl, 2), round_decimal(pnl_percent, 2)


def calculate_stop_loss(
    entry_price: Decimal,
    side: str,
    stop_loss_percent: Decimal,
    tick_size: Optional[Decimal] = None
) -> Decimal:
    """
    Calculate stop loss price
    
    Args:
        entry_price: Entry price
        side: 'long' or 'short'
        stop_loss_percent: Stop loss percentage
        tick_size: Minimum price movement
        
    Returns:
        Stop loss price
    """
    sl_distance = entry_price * (stop_loss_percent / Decimal('100'))
    
    if side.lower() == 'long':
        sl_price = entry_price - sl_distance
    else:  # short
        sl_price = entry_price + sl_distance
    
    # Round to tick size if provided
    if tick_size and tick_size > 0:
        sl_price = round_to_tick_size(sl_price, tick_size)
    
    return sl_price


def round_to_tick_size(price: Decimal, tick_size: Decimal) -> Decimal:
    """
    Round price to nearest tick size
    
    Args:
        price: Price to round
        tick_size: Minimum price movement
        
    Returns:
        Price rounded to tick size
    """
    if tick_size == 0:
        return price
    
    return (price / tick_size).quantize(Decimal('1'), rounding=ROUND_DOWN) * tick_size


def format_decimal(value: Decimal, precision: int = 2) -> str:
    """
    Format decimal for display
    
    Args:
        value: Decimal value
        precision: Display precision
        
    Returns:
        Formatted string
    """
    format_str = f"{{:.{precision}f}}"
    return format_str.format(value)


def safe_divide(numerator: Decimal, denominator: Decimal, default: Decimal = Decimal('0')) -> Decimal:
    """
    Safe division with zero check
    
    Args:
        numerator: Dividend
        denominator: Divisor
        default: Default value if division by zero
        
    Returns:
        Result or default if division by zero
    """
    if denominator == 0:
        return default
    return numerator / denominator