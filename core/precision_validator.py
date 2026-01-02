"""
Precision Validator - Prevents Binance API error -1111

This module ensures that all price and amount values sent to Binance API
have the correct number of decimal places, preventing the error:
"Precision is over the maximum defined for this asset"

Critical for low-price symbols like JELLYJELLYUSDT where float conversion
can result in excessive decimal places (e.g., 0.0461340000000000 instead of 0.04613400)
"""
from decimal import Decimal, ROUND_DOWN
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class PrecisionValidator:
    """
    Validates and enforces price/amount precision for exchange API calls.
    
    Prevents Binance error -1111 (Precision is over the maximum)
    
    Usage:
        validated_price = PrecisionValidator.validate_price(price, symbol, 'binance')
        validated_amount = PrecisionValidator.validate_amount(amount, symbol, 'binance')
    """
    
    # Binance precision limits (from API documentation)
    # https://binance-docs.github.io/apidocs/futures/en/#public-endpoints-info
    BINANCE_MAX_PRICE_PRECISION = 8  # Maximum decimal places for price
    BINANCE_MAX_AMOUNT_PRECISION = 8  # Maximum decimal places for amount
    
    @staticmethod
    def validate_price(
        price: Decimal,
        symbol: str,
        exchange_name: str = 'binance'
    ) -> Decimal:
        """
        Validate and adjust price precision.
        
        Args:
            price: Price to validate (Decimal)
            symbol: Trading symbol (e.g., 'JELLYJELLYUSDT')
            exchange_name: Exchange name (default: 'binance')
            
        Returns:
            Price with correct precision (Decimal)
            
        Example:
            >>> price = Decimal('0.0461340000000000')  # 16 decimals
            >>> validated = PrecisionValidator.validate_price(price, 'JELLYJELLYUSDT')
            >>> print(validated)  # 0.04613400 (8 decimals)
        """
        if exchange_name != 'binance':
            return price  # Only Binance has strict precision requirements
            
        # Convert to string to count decimal places
        price_str = str(price)
        
        if '.' in price_str:
            decimal_places = len(price_str.split('.')[1])
            
            if decimal_places > PrecisionValidator.BINANCE_MAX_PRICE_PRECISION:
                # Too many decimal places - round down to avoid rejection
                quantize_str = '0.' + '0' * PrecisionValidator.BINANCE_MAX_PRICE_PRECISION
                validated_price = price.quantize(Decimal(quantize_str), rounding=ROUND_DOWN)
                
                logger.debug(
                    f"{symbol}: Price precision reduced from {decimal_places} to "
                    f"{PrecisionValidator.BINANCE_MAX_PRICE_PRECISION} decimals: "
                    f"{price} → {validated_price}"
                )
                
                return validated_price
        
        return price
    
    @staticmethod
    def validate_amount(
        amount: Decimal,
        symbol: str,
        exchange_name: str = 'binance'
    ) -> Decimal:
        """
        Validate and adjust amount precision.
        
        Args:
            amount: Amount to validate (Decimal)
            symbol: Trading symbol (e.g., 'JELLYJELLYUSDT')
            exchange_name: Exchange name (default: 'binance')
            
        Returns:
            Amount with correct precision (Decimal)
            
        Example:
            >>> amount = Decimal('390.123456789')  # 9 decimals
            >>> validated = PrecisionValidator.validate_amount(amount, 'JELLYJELLYUSDT')
            >>> print(validated)  # 390.12345678 (8 decimals)
        """
        if exchange_name != 'binance':
            return amount
            
        amount_str = str(amount)
        
        if '.' in amount_str:
            decimal_places = len(amount_str.split('.')[1])
            
            if decimal_places > PrecisionValidator.BINANCE_MAX_AMOUNT_PRECISION:
                # Too many decimal places - round down
                quantize_str = '0.' + '0' * PrecisionValidator.BINANCE_MAX_AMOUNT_PRECISION
                validated_amount = amount.quantize(Decimal(quantize_str), rounding=ROUND_DOWN)
                
                logger.debug(
                    f"{symbol}: Amount precision reduced from {decimal_places} to "
                    f"{PrecisionValidator.BINANCE_MAX_AMOUNT_PRECISION} decimals: "
                    f"{amount} → {validated_amount}"
                )
                
                return validated_amount
        
        return amount
    
    @staticmethod
    def validate_price_str(
        price: str,
        symbol: str,
        exchange_name: str = 'binance'
    ) -> str:
        """
        Validate price from string (convenience method).
        
        Args:
            price: Price as string
            symbol: Trading symbol
            exchange_name: Exchange name
            
        Returns:
            Validated price as string
        """
        price_decimal = Decimal(price)
        validated = PrecisionValidator.validate_price(price_decimal, symbol, exchange_name)
        return str(validated)
    
    @staticmethod
    def validate_amount_str(
        amount: str,
        symbol: str,
        exchange_name: str = 'binance'
    ) -> str:
        """
        Validate amount from string (convenience method).
        
        Args:
            amount: Amount as string
            symbol: Trading symbol
            exchange_name: Exchange name
            
        Returns:
            Validated amount as string
        """
        amount_decimal = Decimal(amount)
        validated = PrecisionValidator.validate_amount(amount_decimal, symbol, exchange_name)
        return str(validated)
