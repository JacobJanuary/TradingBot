"""
Leverage Manager - Smart leverage selection based on position notional and exchange brackets

Inspired by:
- Freqtrade leverage handling
- CCXT leverage brackets implementation
- Binance/Bybit leverage tier system

Handles:
1. Leverage brackets (notional-based leverage limits)
2. Dynamic leverage selection based on position size
3. Fallback to safe defaults when brackets unavailable
"""

import logging
from typing import Optional, Dict, Tuple
from decimal import Decimal

logger = logging.getLogger(__name__)


class LeverageManager:
    """
    Manages leverage selection based on exchange brackets and position notional
    
    Features:
    - Automatic leverage selection based on notional value
    - Support for Binance/Bybit leverage brackets
    - Fallback to safe defaults
    - Validation against exchange limits
    """
    
    def __init__(self, exchange_name: str):
        """
        Initialize leverage manager
        
        Args:
            exchange_name: Name of exchange ('binance', 'bybit', etc.)
        """
        self.exchange_name = exchange_name.lower()
        self.logger = logger
        
        # Safe default leverages per exchange
        self.default_leverage = {
            'binance': 10,
            'bybit': 10,
            'okx': 10
        }
    
    def calculate_optimal_leverage(
        self,
        symbol: str,
        notional: float,
        requested_leverage: int,
        market_info: Optional[Dict] = None
    ) -> Tuple[int, str]:
        """
        Calculate optimal leverage based on notional and brackets
        
        Args:
            symbol: Trading symbol
            notional: Position notional value (price * quantity)
            requested_leverage: User's requested leverage
            market_info: Market information from CCXT (contains brackets)
        
        Returns:
            tuple: (optimal_leverage, reason)
        
        Logic:
        1. If market_info unavailable → use safe default
        2. If brackets available → find matching bracket
        3. If requested leverage valid → use it
        4. Otherwise → use bracket's max leverage
        """
        # Safety check
        if notional <= 0:
            return self._get_default_leverage(), "Invalid notional, using default"
        
        # No market info → use safe default
        if not market_info:
            default_lev = self._get_default_leverage()
            self.logger.warning(
                f"⚠️ No market_info for {symbol}, using safe default leverage: {default_lev}x"
            )
            return default_lev, "No market_info available"
        
        # Try to get leverage brackets from market info
        brackets = self._extract_brackets(market_info)
        
        if not brackets:
            # No brackets → validate against simple limits
            return self._validate_simple_leverage(
                symbol, requested_leverage, market_info
            )
        
        # Find matching bracket for this notional
        matching_bracket = self._find_matching_bracket(notional, brackets)
        
        if not matching_bracket:
            default_lev = self._get_default_leverage()
            self.logger.warning(
                f"⚠️ No matching bracket for {symbol} notional ${notional:.2f}, "
                f"using default {default_lev}x"
            )
            return default_lev, "No matching bracket"
        
        # Get max leverage for this bracket
        bracket_max_leverage = matching_bracket.get('initialLeverage', requested_leverage)
        
        # ✅ CRITICAL FIX: ALWAYS use requested leverage if it's within bracket limits
        # NEVER auto-increase leverage above what user requested
        if requested_leverage <= bracket_max_leverage:
            # User's leverage is safe for this bracket → use it
            self.logger.debug(
                f"✅ Using requested leverage {requested_leverage}x for {symbol} "
                f"(notional ${notional:.2f}, bracket allows up to {bracket_max_leverage}x)"
            )
            return requested_leverage, "User requested (within bracket)"
        
        # Requested leverage too high → reduce to bracket max
        self.logger.warning(
            f"⚠️ Requested leverage {requested_leverage}x exceeds bracket max {bracket_max_leverage}x "
            f"for {symbol} (notional ${notional:.2f}). Reducing to {bracket_max_leverage}x"
        )
        return bracket_max_leverage, f"Reduced to bracket max (notional ${notional:.2f})"
    
    def _extract_brackets(self, market_info: Dict) -> Optional[list]:
        """
        Extract leverage brackets from market_info
        
        Binance format:
        market_info['info']['brackets'] = [
            {'bracket': 1, 'initialLeverage': 75, 'notionalCap': 5000, 'notionalFloor': 0},
            ...
        ]
        
        Bybit format (similar):
        market_info['info']['leverageFilter'] = {...}
        """
        try:
            # Binance style
            info = market_info.get('info', {})
            
            # Try direct brackets
            if 'brackets' in info:
                return info['brackets']
            
            # Try leverageFilter (Bybit)
            if 'leverageFilter' in info:
                leverage_filter = info['leverageFilter']
                if 'brackets' in leverage_filter:
                    return leverage_filter['brackets']
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Failed to extract brackets: {e}")
            return None
    
    def _find_matching_bracket(self, notional: float, brackets: list) -> Optional[Dict]:
        """
        Find bracket that matches the notional value
        
        Args:
            notional: Position notional value
            brackets: List of bracket dictionaries
        
        Returns:
            Matching bracket or None
        """
        for bracket in brackets:
            floor = bracket.get('notionalFloor', 0)
            cap = bracket.get('notionalCap', float('inf'))
            
            if floor <= notional < cap:
                return bracket
        
        return None
    
    def _validate_simple_leverage(
        self,
        symbol: str,
        requested_leverage: int,
        market_info: Dict
    ) -> Tuple[int, str]:
        """
        Validate leverage against simple min/max limits (no brackets)
        
        Args:
            symbol: Trading symbol
            requested_leverage: Requested leverage
            market_info: Market information
        
        Returns:
            tuple: (validated_leverage, reason)
        """
        limits = market_info.get('limits', {})
        leverage_limits = limits.get('leverage', {})
        
        min_leverage = leverage_limits.get('min', 1)
        max_leverage = leverage_limits.get('max', 125)
        
        # Handle None values
        if min_leverage is None:
            min_leverage = 1
        if max_leverage is None:
            max_leverage = 125
        
        # Validate
        if requested_leverage < min_leverage:
            self.logger.warning(
                f"⚠️ Requested leverage {requested_leverage}x below minimum {min_leverage}x "
                f"for {symbol}. Using {min_leverage}x"
            )
            return min_leverage, f"Below minimum"
        
        if requested_leverage > max_leverage:
            self.logger.warning(
                f"⚠️ Requested leverage {requested_leverage}x exceeds maximum {max_leverage}x "
                f"for {symbol}. Using {max_leverage}x"
            )
            return max_leverage, f"Exceeds maximum"
        
        return requested_leverage, "Valid"
    
    def _get_default_leverage(self) -> int:
        """Get safe default leverage for this exchange"""
        return self.default_leverage.get(self.exchange_name, 5)
    
    def validate_position_size_for_leverage(
        self,
        symbol: str,
        quantity: float,
        price: float,
        leverage: int,
        market_info: Optional[Dict] = None
    ) -> Tuple[bool, Optional[float], str]:
        """
        Validate if position size is acceptable for given leverage
        
        Args:
            symbol: Trading symbol
            quantity: Position quantity
            price: Entry price
            leverage: Leverage to use
            market_info: Market information
        
        Returns:
            tuple: (is_valid, adjusted_quantity, reason)
        """
        notional = quantity * price
        
        # No market info → can't validate
        if not market_info:
            return True, None, "No market_info to validate"
        
        brackets = self._extract_brackets(market_info)
        
        if not brackets:
            return True, None, "No brackets to validate"
        
        # Find bracket for this notional
        matching_bracket = self._find_matching_bracket(notional, brackets)
        
        if not matching_bracket:
            # Notional exceeds all brackets → reduce to fit largest bracket
            largest_bracket = max(brackets, key=lambda b: b.get('notionalCap', 0))
            max_notional = largest_bracket.get('notionalCap', notional)
            
            if notional > max_notional:
                adjusted_quantity = (max_notional * 0.99) / price  # 99% for safety
                self.logger.warning(
                    f"⚠️ Position notional ${notional:.2f} exceeds max ${max_notional:.2f} "
                    f"for {symbol}. Reducing quantity from {quantity} to {adjusted_quantity:.6f}"
                )
                return False, adjusted_quantity, f"Notional exceeds bracket max"
        
        # Check if leverage is valid for this bracket
        bracket_max_leverage = matching_bracket.get('initialLeverage', leverage)
        
        if leverage > bracket_max_leverage:
            self.logger.error(
                f"❌ Leverage {leverage}x exceeds bracket max {bracket_max_leverage}x "
                f"for {symbol} notional ${notional:.2f}. Position will likely fail!"
            )
            return False, None, f"Leverage {leverage}x invalid for notional ${notional:.2f}"
        
        return True, None, "Valid"


def get_leverage_manager(exchange_name: str) -> LeverageManager:
    """
    Factory function to get leverage manager for exchange
    
    Args:
        exchange_name: Name of exchange
    
    Returns:
        LeverageManager instance
    """
    return LeverageManager(exchange_name)
