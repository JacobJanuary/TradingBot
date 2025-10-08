from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Boolean,
    JSON, ForeignKey, Index, Enum as SQLEnum
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import enum

Base = declarative_base()


class ActionType(enum.Enum):
    """Trading action types"""
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(enum.Enum):
    """Order status"""
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class PositionStatus(enum.Enum):
    """Position status"""
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    LIQUIDATED = "LIQUIDATED"


class Trade(Base):
    """Executed trades"""
    __tablename__ = 'trades'
    __table_args__ = {'schema': 'monitoring'}

    id = Column(Integer, primary_key=True)
    signal_id = Column(Integer, nullable=True)

    symbol = Column(String(50), nullable=False, index=True)
    exchange = Column(String(50), nullable=False, index=True)

    side = Column(String(10), nullable=False)
    order_type = Column(String(20), nullable=False)

    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    executed_qty = Column(Float, nullable=False)
    average_price = Column(Float)

    order_id = Column(String(100), unique=True)
    client_order_id = Column(String(100))

    status = Column(SQLEnum(OrderStatus), nullable=False)
    error_message = Column(String(500))

    fee = Column(Float, default=0)
    fee_currency = Column(String(10))

    created_at = Column(DateTime, default=func.now(), nullable=False)
    executed_at = Column(DateTime)

    # Relationships
    # signal = relationship("Signal", back_populates="trades", foreign_keys=[signal_id])  # Commented for tests
    # position = relationship("Position", back_populates="open_trade", uselist=False)  # Commented for tests


class Order(Base):
    """Order tracking for exchanges"""
    __tablename__ = 'orders'
    __table_args__ = {'schema': 'trading'}
    
    id = Column(String(50), primary_key=True)
    position_id = Column(String(50), ForeignKey('trading.positions.id'))
    exchange = Column(String(50), nullable=False)
    exchange_order_id = Column(String(100))
    symbol = Column(String(50), nullable=False)
    type = Column(String(20), nullable=False)  # market, limit, stop, stop_limit
    side = Column(String(10), nullable=False)  # buy, sell
    price = Column(Float)
    size = Column(Float, nullable=False)
    filled = Column(Float, default=0)
    remaining = Column(Float)
    status = Column(String(20), nullable=False)  # open, filled, cancelled, rejected
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now())
    
    # Relationships
    # position = relationship("Position", back_populates="orders")  # Commented for tests


class Position(Base):
    """Open positions tracking"""
    __tablename__ = 'positions'
    __table_args__ = {'schema': 'monitoring'}

    id = Column(Integer, primary_key=True)
    trade_id = Column(Integer, ForeignKey('monitoring.trades.id'), nullable=False)

    symbol = Column(String(50), nullable=False, index=True)
    exchange = Column(String(50), nullable=False, index=True)

    side = Column(String(10), nullable=False)
    quantity = Column(Float, nullable=False)
    entry_price = Column(Float, nullable=False)

    # Current values from WebSocket
    current_price = Column(Float)
    mark_price = Column(Float)
    unrealized_pnl = Column(Float)
    unrealized_pnl_percent = Column(Float)

    # Stop loss and take profit
    has_stop_loss = Column(Boolean, default=False)
    stop_loss_price = Column(Float)
    stop_loss_order_id = Column(String(100))

    has_take_profit = Column(Boolean, default=False)
    take_profit_price = Column(Float)
    take_profit_order_id = Column(String(100))

    # Trailing stop
    has_trailing_stop = Column(Boolean, default=False)
    trailing_activated = Column(Boolean, default=False)
    trailing_activation_price = Column(Float)
    trailing_callback_rate = Column(Float)

    # Position management
    status = Column(SQLEnum(PositionStatus), default=PositionStatus.OPEN, nullable=False)

    # Exit information
    exit_price = Column(Float)
    exit_quantity = Column(Float)
    realized_pnl = Column(Float)
    realized_pnl_percent = Column(Float)
    fees = Column(Float, default=0.0)  # Trading fees
    exit_reason = Column(String(100))  # 'stop_loss', 'take_profit', 'manual', etc

    opened_at = Column(DateTime, default=func.now(), nullable=False)
    closed_at = Column(DateTime)

    # WebSocket tracking
    ws_position_id = Column(String(100))
    last_update = Column(DateTime)

    # Relationships
    # open_trade = relationship("Trade", back_populates="position")  # Commented for tests
    # orders = relationship("Order", back_populates="position")  # Commented for tests

    # Indexes
    __table_args__ = (
        Index('idx_positions_open', 'status', 'symbol', 'exchange'),
        # Partial unique index - only one OPEN position per symbol/exchange
        Index('uq_one_position_per_symbol', 'symbol', 'exchange',
              unique=True,
              postgresql_where=Column('status') == 'OPEN'),
        {'schema': 'trading'}
    )


class StopLossConfig(Base):
    """Stop loss configuration for positions"""
    __tablename__ = 'stop_loss_configs'
    __table_args__ = {'schema': 'trading'}
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(50), nullable=False)
    use_fixed_stop = Column(Boolean, default=True)
    fixed_stop_percentage = Column(Float, default=2.0)
    use_trailing_stop = Column(Boolean, default=True)
    trailing_activation = Column(Float, default=1.0)
    trailing_distance = Column(Float, default=0.5)
    use_partial_closes = Column(Boolean, default=False)
    use_time_stop = Column(Boolean, default=False)
    max_position_hours = Column(Integer, default=24)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now())


class RiskEvent(Base):
    """Risk management events tracking"""
    __tablename__ = 'risk_events'
    __table_args__ = {'schema': 'monitoring'}
    
    id = Column(Integer, primary_key=True)
    position_id = Column(String(50))
    event_type = Column(String(50), nullable=False)
    risk_level = Column(String(20))
    details = Column(JSON)
    created_at = Column(DateTime, default=func.now(), nullable=False)


class Alert(Base):
    """System alerts and notifications"""
    __tablename__ = 'alerts'
    __table_args__ = {'schema': 'monitoring'}
    
    id = Column(Integer, primary_key=True)
    type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)
    message = Column(String(500))
    details = Column(JSON)
    acknowledged = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    acknowledged_at = Column(DateTime)


class Performance(Base):
    """Performance metrics tracking"""
    __tablename__ = 'performance'
    __table_args__ = {'schema': 'monitoring'}

    id = Column(Integer, primary_key=True)

    timestamp = Column(DateTime, default=func.now(), nullable=False, index=True)

    # Account metrics
    total_balance = Column(Float, nullable=False)
    available_balance = Column(Float, nullable=False)
    total_unrealized_pnl = Column(Float)

    # Position metrics
    open_positions = Column(Integer, default=0)
    total_exposure = Column(Float, default=0)

    # Daily metrics
    daily_pnl = Column(Float)
    daily_trades = Column(Integer, default=0)
    daily_win_rate = Column(Float)

    # Cumulative metrics
    total_trades = Column(Integer, default=0)
    total_wins = Column(Integer, default=0)
    total_losses = Column(Integer, default=0)
    win_rate = Column(Float)
    profit_factor = Column(Float)
    sharpe_ratio = Column(Float)
    max_drawdown = Column(Float)

    meta_data = Column(JSON)