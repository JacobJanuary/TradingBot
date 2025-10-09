"""
Order utilities for proper order type identification

Key function: Correctly distinguish Stop Loss from Limit Exit orders
"""

import logging
from typing import Dict, Optional
from decimal import Decimal

from utils.decimal_utils import safe_decimal

logger = logging.getLogger(__name__)


def is_stop_loss_order(order: Dict) -> bool:
    """
    Correctly identify if order is a Stop Loss (not just a limit exit)

    Based on official documentation:
    - Bybit V5: https://bybit-exchange.github.io/docs/v5/enum#stopordertype
    - Binance: https://developers.binance.com/docs/derivatives/usds-margined-futures/trade
    - CCXT: https://github.com/ccxt/ccxt/wiki/Manual#order-structure

    CRITICAL DISTINCTION:
    - Stop Loss: Has stopOrderType OR triggerPrice OR type contains 'stop'
    - Limit Exit: type='limit' with reduceOnly=true but NO stop characteristics

    Args:
        order: Order dict from CCXT

    Returns:
        True if order is Stop Loss, False otherwise
    """
    if not order:
        return False

    # Get raw exchange info
    info = order.get('info', {})

    # ====== PRIORITY 1: stopOrderType (Most reliable) ======
    # Bybit V5 specific field
    stop_order_type = info.get('stopOrderType', '')
    if stop_order_type and stop_order_type not in ['', 'UNKNOWN']:
        # Valid stop order types indicate Stop Loss
        if stop_order_type in [
            'Stop',           # Regular stop
            'StopLoss',       # Explicit stop loss
            'PartialStopLoss',  # Partial stop loss
            'TrailingStop',   # Trailing stop
            'tpslOrder'       # Take Profit/Stop Loss
        ]:
            logger.debug(f"Identified as Stop Loss by stopOrderType: {stop_order_type}")
            return True

    # ====== PRIORITY 2: Order type (CCXT unified) ======
    order_type = order.get('type', '').lower()
    if any(stop_word in order_type for stop_word in ['stop', 'trailing']):
        logger.debug(f"Identified as Stop Loss by order type: {order_type}")
        return True

    # ====== PRIORITY 3: Binance specific fields ======
    # Check origType for Binance
    orig_type = info.get('origType', '')
    if orig_type in ['STOP', 'STOP_MARKET', 'STOP_LIMIT', 'TRAILING_STOP_MARKET']:
        logger.debug(f"Identified as Stop Loss by origType: {orig_type}")
        return True

    # Check workingType for Binance
    working_type = info.get('workingType', '')
    if working_type in ['MARK_PRICE', 'CONTRACT_PRICE']:  # Stop orders use these
        logger.debug(f"Identified as Stop Loss by workingType: {working_type}")
        return True

    # ====== PRIORITY 4: Trigger/Stop price ======
    # Any order with trigger price is likely a stop order
    trigger_price = (
        order.get('triggerPrice') or
        order.get('stopPrice') or
        info.get('triggerPrice') or
        info.get('stopPrice') or
        info.get('triggerBy') or
        0
    )

    if trigger_price:
        trigger_price_decimal = safe_decimal(trigger_price, field_name='trigger_price')
        if trigger_price_decimal > 0:
            logger.debug(f"Identified as Stop Loss by trigger price: {trigger_price}")
            return True

    # ====== PRIORITY 5: Conditional order flags ======
    # Check if it's marked as conditional/stop
    is_conditional = (
        info.get('isConditional') or
        info.get('conditional') or
        info.get('stopLossOrder') or
        False
    )

    if is_conditional:
        logger.debug("Identified as Stop Loss by conditional flag")
        return True

    # ====== NOT a Stop Loss ======
    # If it's just a limit order with reduceOnly, it's a regular exit, NOT stop loss
    is_limit = order.get('type') == 'limit'
    is_reduce_only = order.get('reduceOnly') == True

    if is_limit and is_reduce_only and not any([
        stop_order_type,
        'stop' in order_type.lower(),
        trigger_price
    ]):
        logger.debug("Identified as regular Limit Exit (not Stop Loss)")
        return False

    return False


def is_limit_exit_order(order: Dict) -> bool:
    """
    Identify if order is a Limit Exit order (not Stop Loss)

    Limit Exit characteristics:
    - type = 'limit'
    - reduceOnly = true
    - NO stop characteristics (stopOrderType, triggerPrice, etc.)

    Args:
        order: Order dict from CCXT

    Returns:
        True if order is Limit Exit, False otherwise
    """
    if not order:
        return False

    # Must be limit order
    if order.get('type') != 'limit':
        return False

    # Must be reduce only
    if not order.get('reduceOnly'):
        return False

    # Must NOT be a stop loss
    if is_stop_loss_order(order):
        return False

    logger.debug(f"Identified as Limit Exit order: {order.get('id')}")
    return True


def get_order_category(order: Dict) -> str:
    """
    Categorize order for logging and analysis

    Returns one of:
    - 'stop_loss': Stop Loss order
    - 'limit_exit': Limit exit order (reduce only)
    - 'limit_entry': Regular limit order (not reduce only)
    - 'market': Market order
    - 'unknown': Cannot determine
    """
    if not order:
        return 'unknown'

    order_type = order.get('type', '').lower()

    # Check Stop Loss first (highest priority)
    if is_stop_loss_order(order):
        return 'stop_loss'

    # Check Limit Exit
    if is_limit_exit_order(order):
        return 'limit_exit'

    # Check regular limit
    if order_type == 'limit' and not order.get('reduceOnly'):
        return 'limit_entry'

    # Check market
    if 'market' in order_type:
        return 'market'

    return 'unknown'


def analyze_position_orders(orders: list) -> Dict:
    """
    Analyze all orders for a position

    Returns dict with categorized orders and statistics
    """
    analysis = {
        'stop_loss_orders': [],
        'limit_exit_orders': [],
        'limit_entry_orders': [],
        'market_orders': [],
        'unknown_orders': [],
        'has_stop_loss': False,
        'has_limit_exit': False,
        'total_orders': len(orders)
    }

    for order in orders:
        category = get_order_category(order)

        if category == 'stop_loss':
            analysis['stop_loss_orders'].append(order)
            analysis['has_stop_loss'] = True

        elif category == 'limit_exit':
            analysis['limit_exit_orders'].append(order)
            analysis['has_limit_exit'] = True

        elif category == 'limit_entry':
            analysis['limit_entry_orders'].append(order)

        elif category == 'market':
            analysis['market_orders'].append(order)

        else:
            analysis['unknown_orders'].append(order)

    # Check for duplicate exit orders (PROBLEM!)
    if len(analysis['limit_exit_orders']) > 1:
        logger.warning(
            f"⚠️ Found {len(analysis['limit_exit_orders'])} limit exit orders! "
            f"Possible duplicates detected."
        )

    return analysis


def format_order_summary(order: Dict) -> str:
    """
    Format order information for logging

    Returns formatted string with key order details
    """
    if not order:
        return "No order"

    order_id = order.get('id', 'unknown')
    symbol = order.get('symbol', 'unknown')
    side = order.get('side', 'unknown')
    order_type = order.get('type', 'unknown')
    price = order.get('price', 0)
    amount = order.get('amount', 0)
    filled = order.get('filled', 0)
    reduce_only = order.get('reduceOnly', False)

    category = get_order_category(order)

    # Get stop info if available
    info = order.get('info', {})
    stop_type = info.get('stopOrderType', '')
    trigger = order.get('triggerPrice') or info.get('triggerPrice') or 0

    summary = (
        f"Order {order_id}: {category.upper()} "
        f"{side} {amount} {symbol} @ {price}"
    )

    if filled > 0:
        summary += f" (filled: {filled})"

    if reduce_only:
        summary += " [ReduceOnly]"

    if stop_type:
        summary += f" [StopType: {stop_type}]"

    if trigger:
        summary += f" [Trigger: {trigger}]"

    return summary