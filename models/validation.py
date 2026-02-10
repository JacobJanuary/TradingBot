"""
Pydantic models for data validation
Ensures type safety and data integrity
"""
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, Dict, Any, List, Union
from decimal import Decimal
from datetime import datetime
from enum import Enum


# Enums for validation
class OrderSide(str, Enum):
    """Valid order sides"""
    BUY = "BUY"
    SELL = "SELL"
    LONG = "LONG"
    SHORT = "SHORT"


class OrderType(str, Enum):
    """Valid order types"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_MARKET = "STOP_MARKET"
    STOP_LIMIT = "STOP_LIMIT"
    TRAILING_STOP = "TRAILING_STOP"


class OrderStatus(str, Enum):
    """Valid order statuses"""
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class PositionStatus(str, Enum):
    """Valid position statuses"""
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CLOSING = "CLOSING"
    ERROR = "ERROR"


# WebSocket Models
class WebSocketMessage(BaseModel):
    """Base WebSocket message"""
    event: str
    timestamp: datetime = Field(default_factory=datetime.now)
    data: Dict[str, Any]

    @field_validator('event')
    @classmethod
    def validate_event(cls, v):
        if not v or not isinstance(v, str):
            raise ValueError("Event must be a non-empty string")
        return v.upper()


class PriceUpdate(BaseModel):
    """Price update from WebSocket"""
    symbol: str
    price: Decimal = Field(gt=0)
    bid: Optional[Decimal] = Field(default=None, gt=0)
    ask: Optional[Decimal] = Field(default=None, gt=0)
    volume: Optional[Decimal] = Field(default=None, ge=0)
    timestamp: datetime

    @field_validator('symbol')
    @classmethod
    def validate_symbol(cls, v):
        if not v or len(v) < 3:
            raise ValueError("Invalid symbol format")
        return v.upper().replace('/', '').replace('-', '')

    @model_validator(mode='after')
    def validate_bid_ask(self):
        if self.bid and self.ask and self.bid >= self.ask:
            raise ValueError(f"Bid {self.bid} must be less than ask {self.ask}")
        return self


class PositionUpdate(BaseModel):
    """Position update from WebSocket"""
    symbol: str
    side: OrderSide
    quantity: Decimal = Field(gt=0)
    entry_price: Decimal = Field(gt=0)
    mark_price: Optional[Decimal] = Field(default=None, gt=0)
    unrealized_pnl: Optional[Decimal] = None
    realized_pnl: Optional[Decimal] = None
    margin_ratio: Optional[Decimal] = Field(default=None, ge=0, le=100)
    timestamp: datetime

    @field_validator('quantity')
    @classmethod
    def validate_quantity(cls, v):
        if v <= 0:
            raise ValueError("Quantity must be positive")
        # Check reasonable limits
        if v > Decimal('1000000'):
            raise ValueError("Quantity exceeds maximum limit")
        return v


class OrderUpdate(BaseModel):
    """Order update from WebSocket"""
    order_id: str
    symbol: str
    side: OrderSide
    type: OrderType
    status: OrderStatus
    price: Optional[Decimal] = Field(default=None, gt=0)
    quantity: Decimal = Field(gt=0)
    filled_quantity: Decimal = Field(ge=0)
    remaining_quantity: Decimal = Field(ge=0)
    timestamp: datetime
    client_order_id: Optional[str] = None

    @model_validator(mode='after')
    def validate_quantities(self):
        if self.quantity and self.filled_quantity and self.remaining_quantity:
            if abs(self.quantity - (self.filled_quantity + self.remaining_quantity)) > Decimal('0.00000001'):
                raise ValueError("Quantity mismatch: total != filled + remaining")
        return self


class BalanceUpdate(BaseModel):
    """Balance update from WebSocket"""
    asset: str
    free: Decimal = Field(ge=0)
    locked: Decimal = Field(ge=0)
    total: Optional[Decimal] = None
    timestamp: datetime

    @model_validator(mode='after')
    def calculate_total(self):
        if self.total is None:
            self.total = self.free + self.locked
        return self


# Signal Models
class TradingSignal(BaseModel):
    """Trading signal validation"""
    id: Optional[int] = None  # May not be present in some signal formats
    symbol: str
    action: Optional[Union[OrderSide, str]] = None
    score_week: Decimal = Field(default=Decimal('0'), ge=0)
    score_month: Decimal = Field(default=Decimal('0'), ge=0)
    total_score: Optional[Decimal] = Field(default=None, ge=0)  # New: from signal server
    entry_price: Optional[Decimal] = Field(default=None, gt=0)
    stop_loss: Optional[Decimal] = Field(default=None, gt=0)
    take_profit: Optional[Decimal] = Field(default=None, gt=0)
    created_at: Optional[datetime] = None
    exchange: str = 'binance'

    @field_validator('action', mode='before')
    @classmethod
    def validate_action(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            # Convert string to OrderSide enum
            try:
                return OrderSide(v.upper())
            except ValueError:
                return None
        return v
    
    @field_validator('symbol')
    @classmethod
    def validate_symbol(cls, v):
        # Remove common separators and standardize
        cleaned = v.upper().replace('/', '').replace('-', '').replace('_', '')
        if not cleaned.endswith('USDT'):
            raise ValueError(f"Symbol {v} must be a USDT pair")
        if len(cleaned) < 5:  # At least XUSDT
            raise ValueError(f"Invalid symbol format: {v}")
        return cleaned
    
    @field_validator('exchange')
    @classmethod
    def validate_exchange(cls, v):
        valid_exchanges = ['binance']
        if v.lower() not in valid_exchanges:
            raise ValueError(f"Invalid exchange. Must be one of: {valid_exchanges}")
        return v.lower()

    @model_validator(mode='after')
    def validate_prices(self):
        if self.entry_price and self.stop_loss:
            if self.action in [OrderSide.BUY, OrderSide.LONG]:
                if self.stop_loss >= self.entry_price:
                    raise ValueError("Stop loss must be below entry for long positions")
            else:
                if self.stop_loss <= self.entry_price:
                    raise ValueError("Stop loss must be above entry for short positions")
        
        if self.entry_price and self.take_profit:
            if self.action in [OrderSide.BUY, OrderSide.LONG]:
                if self.take_profit <= self.entry_price:
                    raise ValueError("Take profit must be above entry for long positions")
            else:
                if self.take_profit >= self.entry_price:
                    raise ValueError("Take profit must be below entry for short positions")
        
        return self


# API Response Models
class ExchangeBalance(BaseModel):
    """Exchange balance response"""
    exchange: str
    currency: str
    total: Decimal = Field(ge=0)
    free: Decimal = Field(ge=0)
    used: Decimal = Field(ge=0)
    timestamp: datetime = Field(default_factory=datetime.now)

    @model_validator(mode='after')
    def validate_balances(self):
        if abs(self.total - (self.free + self.used)) > Decimal('0.00000001'):
            raise ValueError("Balance mismatch: total != free + used")
        return self


class MarketData(BaseModel):
    """Market data validation"""
    symbol: str
    bid: Decimal = Field(gt=0)
    ask: Decimal = Field(gt=0)
    last_price: Decimal = Field(gt=0)
    volume_24h: Decimal = Field(ge=0)
    high_24h: Decimal = Field(gt=0)
    low_24h: Decimal = Field(gt=0)
    timestamp: datetime

    @model_validator(mode='after')
    def validate_price_ranges(self):
        if self.high_24h <= self.low_24h:
            raise ValueError("High price must be greater than low price")
        
        if self.bid >= self.ask:
            raise ValueError("Bid must be less than ask")
        
        if self.last_price > self.high_24h:
            raise ValueError("Last price cannot exceed 24h high")
        
        if self.last_price < self.low_24h:
            raise ValueError("Last price cannot be below 24h low")
        
        return self


# Request Models
class CreateOrderRequest(BaseModel):
    """Order creation request validation"""
    symbol: str
    side: OrderSide
    type: OrderType
    quantity: Decimal = Field(gt=0)
    price: Optional[Decimal] = Field(default=None, gt=0)
    stop_price: Optional[Decimal] = Field(default=None, gt=0)
    reduce_only: bool = False
    client_order_id: Optional[str] = None
    
    @field_validator('symbol')
    @classmethod
    def validate_symbol(cls, v):
        return v.upper().replace('/', '')
    
    @model_validator(mode='after')
    def validate_order_params(self):
        # Validate price requirements based on order type
        if self.type == OrderType.LIMIT and not self.price:
            raise ValueError("Limit orders require a price")
        
        if self.type in [OrderType.STOP_LIMIT, OrderType.STOP_MARKET] and not self.stop_price:
            raise ValueError("Stop orders require a stop price")
        
        return self


class ClosePositionRequest(BaseModel):
    """Position closure request validation"""
    position_id: int
    symbol: str
    exchange: str
    reason: str
    reduce_only: bool = True
    
    @field_validator('reason')
    @classmethod
    def validate_reason(cls, v):
        valid_reasons = ['stop_loss', 'take_profit', 'manual', 'timeout', 'emergency', 'signal']
        if v.lower() not in valid_reasons:
            raise ValueError(f"Invalid reason. Must be one of: {valid_reasons}")
        return v.lower()


# Validation helper functions
def validate_websocket_data(event_type: str, data: Dict[str, Any]) -> Optional[BaseModel]:
    """
    Validate WebSocket data based on event type
    
    Args:
        event_type: Type of WebSocket event
        data: Raw data from WebSocket
        
    Returns:
        Validated pydantic model or None if validation fails
    """
    validators = {
        'price': PriceUpdate,
        'position': PositionUpdate,
        'order': OrderUpdate,
        'balance': BalanceUpdate,
    }
    
    validator_class = validators.get(event_type.lower())
    if not validator_class:
        return None
    
    try:
        return validator_class(**data)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Validation failed for {event_type}: {e}")
        return None


def validate_signal(signal_data: Dict[str, Any]) -> Optional[TradingSignal]:
    """
    Validate trading signal data
    
    Args:
        signal_data: Raw signal data
        
    Returns:
        Validated TradingSignal or None if validation fails
    """
    try:
        return TradingSignal(**signal_data)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Signal validation failed: {e}")
        return None