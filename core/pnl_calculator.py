"""
PnL Calculator

Pure functions for position P&L calculation per spec §8.

Commission: 0.04% taker fee × 2 (open + close) × leverage
PnL: price change% × leverage, capped at -100%, minus commission
Liquidation: PnL = -100% (no commission)

Based on: TRADING_BOT_ALGORITHM_SPEC.md §8
"""

COMMISSION_PCT = 0.04  # Taker fee percentage


def calculate_commission(leverage: int) -> float:
    """
    Calculate round-trip commission cost in % of position.
    
    Formula: COMMISSION_PCT × 2 × leverage
    Example: 0.04 × 2 × 10 = 0.8%
    
    Args:
        leverage: Position leverage
        
    Returns:
        Commission cost as percentage of position
    """
    return COMMISSION_PCT * 2 * leverage


def calculate_pnl_from_entry(entry_price: float, current_price: float) -> float:
    """
    Calculate price change percentage (not leveraged).
    
    Formula: (current - entry) / entry × 100
    
    Args:
        entry_price: Position entry price
        current_price: Current market price
        
    Returns:
        Price change percentage (e.g., 15.0 for +15%)
    """
    if entry_price <= 0:
        return 0.0
    return (current_price - entry_price) / entry_price * 100


def calculate_drawdown_from_max(max_price: float, current_price: float) -> float:
    """
    Calculate drawdown from peak.
    
    Formula: (max - current) / max × 100
    
    Args:
        max_price: Highest price since entry
        current_price: Current market price
        
    Returns:
        Drawdown percentage (e.g., 3.0 for -3% from peak)
    """
    if max_price <= 0:
        return 0.0
    return (max_price - current_price) / max_price * 100


def calculate_realized_pnl(
    pnl_from_entry: float,
    leverage: int,
    reason: str,
) -> float:
    """
    Calculate realized PnL for a closed position (§8.1).
    
    Formulas by reason:
    - LIQUIDATED: -100% (no commission)
    - TIMEOUT/SL/TRAILING: max(pnl × leverage, -100%) - commission
    
    Args:
        pnl_from_entry: Price change % (from calculate_pnl_from_entry)
        leverage: Position leverage
        reason: Exit reason ('SL', 'TRAILING', 'TIMEOUT', 'LIQUIDATED')
        
    Returns:
        Realized PnL as percentage of position
    """
    if reason == 'LIQUIDATED' or reason == 'LIQ+TIMEOUT':
        return -100.0

    leveraged_pnl = max(pnl_from_entry * leverage, -100.0)
    commission = calculate_commission(leverage)
    return leveraged_pnl - commission


def get_liquidation_threshold(leverage: int) -> float:
    """
    Price drop % that triggers liquidation (§6.4).
    
    Formula: 100.0 / leverage
    Example: 100 / 10 = 10% price drop → liquidation
    
    Args:
        leverage: Position leverage
        
    Returns:
        Price change threshold for liquidation
    """
    return 100.0 / leverage
