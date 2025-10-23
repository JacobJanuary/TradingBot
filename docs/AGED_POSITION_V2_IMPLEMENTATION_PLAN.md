# AGED POSITION MANAGER V2: ДЕТАЛЬНЫЙ ПЛАН ИМПЛЕМЕНТАЦИИ

## 📋 QUICK START CHECKLIST

```bash
# 1. Create feature branch
git checkout -b feature/aged-positions-v2

# 2. Backup current implementation
cp core/aged_position_manager.py core/aged_position_manager.py.backup_$(date +%Y%m%d)

# 3. Apply database migration
psql -U $DB_USER -d $DB_NAME -f database/migrations/009_create_aged_positions_tables.sql

# 4. Install additional dependencies (if needed)
pip install websockets aioredis
```

---

## 🏗️ ФАЗА 1: МОДЕЛИ ДАННЫХ И СХЕМЫ

### 1.1 Pydantic Models

**Файл**: `models/aged_position.py`

```python
"""
Aged Position data models for V2 implementation
"""
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, Field, validator


class AgedPositionStatus(str, Enum):
    """States in aged position lifecycle"""
    DETECTED = "detected"                    # Just identified as aged
    GRACE_PENDING = "grace_pending"          # Waiting to enter grace
    GRACE_ACTIVE = "grace_active"            # In grace period (breakeven attempts)
    PROGRESSIVE_ACTIVE = "progressive_active" # Progressive liquidation
    CLOSED = "closed"                        # Successfully closed
    ERROR = "error"                          # Error during processing
    SKIPPED = "skipped"                      # Skipped (e.g., TS active)


class CloseReason(str, Enum):
    """Reasons for position closure"""
    PROFITABLE = "profitable"                # Closed in profit
    BREAKEVEN = "breakeven"                 # Closed at breakeven
    LOSS_ACCEPTABLE = "loss_acceptable"     # Closed with acceptable loss
    MAX_LOSS = "max_loss"                   # Closed at maximum loss
    EMERGENCY = "emergency"                 # Emergency market close
    MANUAL = "manual"                       # Manual intervention
    ERROR = "error"                         # Closed due to error


class AgedPositionEntry(BaseModel):
    """Main aged position tracking entry"""

    # Identity
    id: UUID
    position_id: int

    # Position snapshot
    symbol: str
    exchange: str
    side: str  # 'long', 'short', 'buy', 'sell'
    entry_price: Decimal
    quantity: Decimal

    # Time tracking
    position_opened_at: datetime
    detected_at: datetime
    grace_started_at: Optional[datetime] = None
    progressive_started_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None

    # State
    status: AgedPositionStatus = AgedPositionStatus.DETECTED

    # Targets
    target_price: Optional[Decimal] = None
    breakeven_price: Optional[Decimal] = None
    current_loss_tolerance_percent: Decimal = Field(default=Decimal('0'))

    # Monitoring
    last_price_check: Optional[datetime] = None
    last_checked_price: Optional[Decimal] = None

    # Attempts
    close_attempts: int = 0
    last_close_attempt: Optional[datetime] = None
    last_error_message: Optional[str] = None

    # Metrics
    hours_aged: Decimal = Field(default=Decimal('0'))
    hours_in_grace: Decimal = Field(default=Decimal('0'))
    hours_in_progressive: Decimal = Field(default=Decimal('0'))

    # Results
    close_price: Optional[Decimal] = None
    close_order_id: Optional[str] = None
    actual_pnl: Optional[Decimal] = None
    actual_pnl_percent: Optional[Decimal] = None
    close_reason: Optional[CloseReason] = None

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    config: Optional[Dict[str, Any]] = None

    class Config:
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            Decimal: lambda v: str(v),
            UUID: lambda v: str(v)
        }

    @validator('hours_aged', 'hours_in_grace', 'hours_in_progressive', pre=True)
    def validate_hours(cls, v):
        """Ensure hours are non-negative"""
        if v and v < 0:
            return Decimal('0')
        return v

    def is_active(self) -> bool:
        """Check if position is still active"""
        return self.status not in [
            AgedPositionStatus.CLOSED,
            AgedPositionStatus.ERROR,
            AgedPositionStatus.SKIPPED
        ]

    def can_close(self) -> bool:
        """Check if position can be closed"""
        return self.status in [
            AgedPositionStatus.GRACE_ACTIVE,
            AgedPositionStatus.PROGRESSIVE_ACTIVE
        ]


class PhaseParams(BaseModel):
    """Parameters for current phase"""
    phase: str
    target_price: Decimal
    loss_tolerance_percent: Decimal
    time_in_phase: Decimal  # hours
    next_transition_in: Optional[Decimal] = None  # hours until next phase


class CloseResult(BaseModel):
    """Result of close attempt"""
    success: bool
    order_id: Optional[str] = None
    close_price: Optional[Decimal] = None
    pnl: Optional[Decimal] = None
    pnl_percent: Optional[Decimal] = None
    error: Optional[str] = None
    retry_after: Optional[int] = None  # seconds to wait before retry


class MonitoringEvent(BaseModel):
    """Real-time monitoring event"""
    aged_position_id: UUID
    event_type: str  # price_check, close_triggered, close_executed, etc.
    market_price: Optional[Decimal] = None
    target_price: Optional[Decimal] = None
    price_distance_percent: Optional[Decimal] = None
    action_taken: str  # wait, trigger_close, update_target, skip
    success: bool = True
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

---

## 🎯 ФАЗА 2: STATE MANAGER

**Файл**: `core/aged_position_state_manager.py`

```python
"""
State management for aged positions with database persistence
"""
import logging
from typing import List, Optional
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from models.aged_position import (
    AgedPositionEntry,
    AgedPositionStatus,
    PhaseParams,
    CloseReason
)
from database.repository import Repository

logger = logging.getLogger(__name__)


class AgedPositionStateManager:
    """
    Manages state transitions and persistence for aged positions

    State flow:
    detected → grace_pending → grace_active → progressive_active → closed
    """

    def __init__(
        self,
        repository: Repository,
        max_age_hours: int = 3,
        grace_period_hours: int = 8,
        loss_step_percent: Decimal = Decimal('0.5'),
        max_loss_percent: Decimal = Decimal('10.0'),
        acceleration_factor: Decimal = Decimal('1.2'),
        commission_percent: Decimal = Decimal('0.1')
    ):
        self.repository = repository
        self.max_age_hours = max_age_hours
        self.grace_period_hours = grace_period_hours
        self.loss_step_percent = loss_step_percent
        self.max_loss_percent = max_loss_percent
        self.acceleration_factor = acceleration_factor
        self.commission_percent = commission_percent / 100  # Convert to decimal

        logger.info(
            f"AgedPositionStateManager initialized: "
            f"max_age={max_age_hours}h, grace={grace_period_hours}h, "
            f"loss_step={loss_step_percent}%"
        )

    async def create_aged_entry(
        self,
        position: 'Position'
    ) -> AgedPositionEntry:
        """
        Create new aged position entry

        Args:
            position: Position object from position manager

        Returns:
            Created AgedPositionEntry
        """
        # Calculate breakeven price
        breakeven_price = self._calculate_breakeven_price(
            position.entry_price,
            position.side
        )

        # Create entry
        entry_id = uuid4()

        entry_data = {
            'id': entry_id,
            'position_id': position.id,
            'symbol': position.symbol,
            'exchange': position.exchange,
            'side': position.side,
            'entry_price': Decimal(str(position.entry_price)),
            'quantity': Decimal(str(position.quantity)),
            'position_opened_at': position.opened_at,
            'detected_at': datetime.now(timezone.utc),
            'status': AgedPositionStatus.DETECTED,
            'breakeven_price': breakeven_price,
            'config': {
                'max_age_hours': self.max_age_hours,
                'grace_period_hours': self.grace_period_hours,
                'loss_step_percent': str(self.loss_step_percent),
                'max_loss_percent': str(self.max_loss_percent),
                'acceleration_factor': str(self.acceleration_factor)
            }
        }

        # Save to database
        await self.repository.create_aged_position_entry(entry_data)

        # Create model
        entry = AgedPositionEntry(**entry_data)

        logger.info(
            f"Created aged position entry: {position.symbol} "
            f"(id={entry_id}, breakeven=${breakeven_price:.4f})"
        )

        # Immediately transition to grace_pending
        await self.transition_to_grace_pending(entry)

        return entry

    def _calculate_breakeven_price(
        self,
        entry_price: float,
        side: str
    ) -> Decimal:
        """Calculate breakeven price including double commission"""
        entry_price = Decimal(str(entry_price))
        double_commission = 2 * self.commission_percent

        if side in ['long', 'buy']:
            # LONG: need price to go up to cover commission
            return entry_price * (1 + double_commission)
        else:
            # SHORT: need price to go down to cover commission
            return entry_price * (1 - double_commission)

    async def transition_to_grace_pending(
        self,
        entry: AgedPositionEntry
    ) -> AgedPositionEntry:
        """Transition to grace pending state"""
        if entry.status != AgedPositionStatus.DETECTED:
            logger.warning(
                f"Cannot transition to grace_pending from {entry.status}"
            )
            return entry

        entry.status = AgedPositionStatus.GRACE_PENDING
        entry.grace_started_at = datetime.now(timezone.utc)
        entry.target_price = entry.breakeven_price
        entry.updated_at = datetime.now(timezone.utc)

        await self._persist_state_change(
            entry,
            from_status=AgedPositionStatus.DETECTED,
            to_status=AgedPositionStatus.GRACE_PENDING,
            reason="Starting grace period for breakeven attempts"
        )

        logger.info(f"Transitioned {entry.symbol} to GRACE_PENDING")
        return entry

    async def transition_to_grace_active(
        self,
        entry: AgedPositionEntry
    ) -> AgedPositionEntry:
        """Transition to active grace period monitoring"""
        if entry.status != AgedPositionStatus.GRACE_PENDING:
            return entry

        entry.status = AgedPositionStatus.GRACE_ACTIVE
        entry.updated_at = datetime.now(timezone.utc)

        await self._persist_state_change(
            entry,
            from_status=AgedPositionStatus.GRACE_PENDING,
            to_status=AgedPositionStatus.GRACE_ACTIVE,
            reason="Actively monitoring for breakeven"
        )

        logger.info(f"Transitioned {entry.symbol} to GRACE_ACTIVE")
        return entry

    async def transition_to_progressive(
        self,
        entry: AgedPositionEntry
    ) -> AgedPositionEntry:
        """Transition to progressive liquidation"""
        if entry.status not in [
            AgedPositionStatus.GRACE_ACTIVE,
            AgedPositionStatus.GRACE_PENDING
        ]:
            return entry

        # Calculate hours in grace
        if entry.grace_started_at:
            grace_duration = datetime.now(timezone.utc) - entry.grace_started_at
            entry.hours_in_grace = Decimal(str(grace_duration.total_seconds() / 3600))

        entry.status = AgedPositionStatus.PROGRESSIVE_ACTIVE
        entry.progressive_started_at = datetime.now(timezone.utc)
        entry.current_loss_tolerance_percent = self.loss_step_percent
        entry.updated_at = datetime.now(timezone.utc)

        # Calculate new target price with loss tolerance
        entry.target_price = self._calculate_progressive_target(
            entry,
            entry.current_loss_tolerance_percent
        )

        await self._persist_state_change(
            entry,
            from_status=AgedPositionStatus.GRACE_ACTIVE,
            to_status=AgedPositionStatus.PROGRESSIVE_ACTIVE,
            reason=f"Grace period expired, starting progressive liquidation"
        )

        logger.warning(
            f"⚠️ {entry.symbol} entering PROGRESSIVE liquidation "
            f"(loss tolerance: {entry.current_loss_tolerance_percent}%)"
        )
        return entry

    def _calculate_progressive_target(
        self,
        entry: AgedPositionEntry,
        loss_tolerance: Decimal
    ) -> Decimal:
        """Calculate target price with loss tolerance"""
        if entry.side in ['long', 'buy']:
            # LONG: accept lower price
            return entry.entry_price * (1 - loss_tolerance / 100)
        else:
            # SHORT: accept higher price
            return entry.entry_price * (1 + loss_tolerance / 100)

    async def calculate_progressive_loss_tolerance(
        self,
        entry: AgedPositionEntry
    ) -> Decimal:
        """
        Calculate current loss tolerance based on time in progressive phase

        Returns:
            Loss tolerance percentage
        """
        if not entry.progressive_started_at:
            return Decimal('0')

        # Calculate hours in progressive
        progressive_duration = datetime.now(timezone.utc) - entry.progressive_started_at
        hours_in_progressive = Decimal(str(progressive_duration.total_seconds() / 3600))

        # Base calculation: 0.5% per hour
        loss_tolerance = hours_in_progressive * self.loss_step_percent

        # Apply acceleration after 10 hours
        if hours_in_progressive > 10:
            extra_hours = hours_in_progressive - 10
            acceleration_loss = extra_hours * self.loss_step_percent * (self.acceleration_factor - 1)
            loss_tolerance += acceleration_loss

        # Cap at maximum
        loss_tolerance = min(loss_tolerance, self.max_loss_percent)

        # Update entry
        entry.hours_in_progressive = hours_in_progressive
        entry.current_loss_tolerance_percent = loss_tolerance

        return loss_tolerance

    async def mark_as_closed(
        self,
        entry: AgedPositionEntry,
        close_price: Decimal,
        close_order_id: str,
        actual_pnl: Decimal,
        actual_pnl_percent: Decimal,
        close_reason: CloseReason
    ) -> AgedPositionEntry:
        """Mark position as successfully closed"""

        # Calculate total time metrics
        total_duration = datetime.now(timezone.utc) - entry.detected_at
        entry.hours_aged = Decimal(str(total_duration.total_seconds() / 3600))

        # Update entry
        entry.status = AgedPositionStatus.CLOSED
        entry.closed_at = datetime.now(timezone.utc)
        entry.close_price = close_price
        entry.close_order_id = close_order_id
        entry.actual_pnl = actual_pnl
        entry.actual_pnl_percent = actual_pnl_percent
        entry.close_reason = close_reason
        entry.updated_at = datetime.now(timezone.utc)

        await self._persist_state_change(
            entry,
            from_status=entry.status,
            to_status=AgedPositionStatus.CLOSED,
            reason=f"Position closed: {close_reason.value}"
        )

        emoji = "✅" if actual_pnl > 0 else "❌"
        logger.info(
            f"{emoji} Aged position {entry.symbol} CLOSED: "
            f"PnL={actual_pnl_percent:.2f}%, reason={close_reason.value}"
        )

        return entry

    async def get_current_phase_params(
        self,
        entry: AgedPositionEntry
    ) -> PhaseParams:
        """Get current phase parameters"""

        current_time = datetime.now(timezone.utc)

        # Calculate current age
        total_age = (current_time - entry.position_opened_at).total_seconds() / 3600
        aged_hours = max(0, total_age - self.max_age_hours)

        if entry.status in [
            AgedPositionStatus.GRACE_PENDING,
            AgedPositionStatus.GRACE_ACTIVE
        ]:
            # Grace period phase
            time_in_grace = 0
            if entry.grace_started_at:
                time_in_grace = (current_time - entry.grace_started_at).total_seconds() / 3600

            return PhaseParams(
                phase="GRACE_PERIOD",
                target_price=entry.breakeven_price,
                loss_tolerance_percent=Decimal('0'),
                time_in_phase=Decimal(str(time_in_grace)),
                next_transition_in=Decimal(str(max(0, self.grace_period_hours - time_in_grace)))
            )

        elif entry.status == AgedPositionStatus.PROGRESSIVE_ACTIVE:
            # Progressive phase
            loss_tolerance = await self.calculate_progressive_loss_tolerance(entry)
            target_price = self._calculate_progressive_target(entry, loss_tolerance)

            time_in_progressive = 0
            if entry.progressive_started_at:
                time_in_progressive = (
                    current_time - entry.progressive_started_at
                ).total_seconds() / 3600

            return PhaseParams(
                phase="PROGRESSIVE_LIQUIDATION",
                target_price=target_price,
                loss_tolerance_percent=loss_tolerance,
                time_in_phase=Decimal(str(time_in_progressive)),
                next_transition_in=None  # No next phase, continues until closed
            )

        else:
            # Default/error case
            return PhaseParams(
                phase="UNKNOWN",
                target_price=entry.target_price or entry.breakeven_price,
                loss_tolerance_percent=Decimal('0'),
                time_in_phase=Decimal('0'),
                next_transition_in=None
            )

    async def get_active_entries(
        self,
        statuses: Optional[List[AgedPositionStatus]] = None
    ) -> List[AgedPositionEntry]:
        """Get all active aged position entries"""

        if statuses is None:
            # Default to all active statuses
            statuses = [
                AgedPositionStatus.GRACE_PENDING,
                AgedPositionStatus.GRACE_ACTIVE,
                AgedPositionStatus.PROGRESSIVE_ACTIVE
            ]

        entries = await self.repository.get_active_aged_positions(statuses)

        return [
            AgedPositionEntry(**entry)
            for entry in entries
        ]

    async def _persist_state_change(
        self,
        entry: AgedPositionEntry,
        from_status: AgedPositionStatus,
        to_status: AgedPositionStatus,
        reason: str
    ):
        """Persist state change to database"""

        # Update main table
        await self.repository.update_aged_position_status(
            aged_id=entry.id,
            new_status=to_status,
            transition_reason=reason,
            target_price=entry.target_price,
            loss_tolerance=entry.current_loss_tolerance_percent
        )

        # History is logged automatically via database trigger

    async def recover_from_restart(self) -> List[AgedPositionEntry]:
        """
        Recover aged positions after bot restart

        Returns:
            List of active aged position entries
        """
        logger.info("Recovering aged positions from database...")

        entries = await self.get_active_entries()

        if entries:
            logger.info(f"Recovered {len(entries)} active aged positions:")
            for entry in entries:
                logger.info(
                    f"  - {entry.symbol}: status={entry.status}, "
                    f"aged={entry.hours_aged:.1f}h"
                )
        else:
            logger.info("No active aged positions to recover")

        return entries
```

---

## 🔌 ФАЗА 3: WEBSOCKET INTEGRATION

### 3.1 Ticker Stream для Mainnet

**Файл**: `websocket/aged_ticker_stream.py`

```python
"""
WebSocket ticker stream for aged position monitoring
"""
import asyncio
import logging
from typing import Dict, Set, Callable, Optional
from decimal import Decimal
import json

logger = logging.getLogger(__name__)


class AgedPositionTickerStream:
    """
    Dedicated WebSocket stream for ticker updates
    Used only for symbols in aged position monitoring
    """

    def __init__(self, exchange_name: str, testnet: bool = False):
        self.exchange_name = exchange_name
        self.testnet = testnet
        self.subscribed_symbols: Set[str] = set()
        self.callbacks: Dict[str, List[Callable]] = {}
        self.ws_connection = None
        self._running = False
        self._reconnect_attempts = 0
        self.max_reconnect_attempts = 10

    async def start(self):
        """Start the WebSocket connection"""
        self._running = True

        # Different approach for testnet (use polling)
        if self.testnet:
            logger.info(
                f"Starting polling ticker stream for {self.exchange_name} (testnet)"
            )
            asyncio.create_task(self._polling_loop())
        else:
            logger.info(
                f"Starting WebSocket ticker stream for {self.exchange_name}"
            )
            await self._connect_websocket()

    async def _connect_websocket(self):
        """Establish WebSocket connection"""
        try:
            if self.exchange_name == 'binance':
                await self._connect_binance_stream()
            elif self.exchange_name == 'bybit':
                await self._connect_bybit_stream()
            else:
                logger.error(f"Unsupported exchange: {self.exchange_name}")

        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            await self._handle_disconnect()

    async def _connect_binance_stream(self):
        """Connect to Binance WebSocket"""
        import websockets

        # Build stream names
        streams = [
            f"{symbol.lower()}@ticker"
            for symbol in self.subscribed_symbols
        ]

        if not streams:
            return

        url = f"wss://stream.binance.com:9443/stream?streams={'/'.join(streams)}"

        async with websockets.connect(url) as ws:
            self.ws_connection = ws
            self._reconnect_attempts = 0
            logger.info(f"Connected to Binance WebSocket")

            while self._running:
                try:
                    message = await asyncio.wait_for(
                        ws.recv(),
                        timeout=30  # 30 second timeout
                    )
                    await self._process_binance_message(message)

                except asyncio.TimeoutError:
                    # Send ping to keep connection alive
                    await ws.ping()

                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    break

    async def _connect_bybit_stream(self):
        """Connect to Bybit WebSocket"""
        import websockets

        url = "wss://stream.bybit.com/v5/public/linear"

        async with websockets.connect(url) as ws:
            self.ws_connection = ws
            self._reconnect_attempts = 0
            logger.info(f"Connected to Bybit WebSocket")

            # Subscribe to tickers
            for symbol in self.subscribed_symbols:
                subscribe_msg = {
                    "op": "subscribe",
                    "args": [f"tickers.{symbol}"]
                }
                await ws.send(json.dumps(subscribe_msg))

            while self._running:
                try:
                    message = await asyncio.wait_for(
                        ws.recv(),
                        timeout=30
                    )
                    await self._process_bybit_message(message)

                except asyncio.TimeoutError:
                    # Send ping
                    await ws.send(json.dumps({"op": "ping"}))

                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    break

    async def _process_binance_message(self, message: str):
        """Process Binance ticker message"""
        try:
            data = json.loads(message)

            if 'data' in data:
                ticker_data = data['data']

                # Extract data
                symbol = ticker_data['s']  # e.g., "BTCUSDT"
                last_price = Decimal(ticker_data['c'])  # Last price
                timestamp = ticker_data['E']  # Event time

                # Trigger callbacks
                await self._trigger_callbacks(symbol, last_price, timestamp)

        except Exception as e:
            logger.error(f"Error processing Binance message: {e}")

    async def _process_bybit_message(self, message: str):
        """Process Bybit ticker message"""
        try:
            data = json.loads(message)

            if data.get('topic', '').startswith('tickers.'):
                ticker_data = data['data']

                # Extract data
                symbol = ticker_data['symbol']  # e.g., "BTCUSDT"
                last_price = Decimal(ticker_data['lastPrice'])
                timestamp = data['ts']

                # Trigger callbacks
                await self._trigger_callbacks(symbol, last_price, timestamp)

        except Exception as e:
            logger.error(f"Error processing Bybit message: {e}")

    async def _trigger_callbacks(
        self,
        symbol: str,
        price: Decimal,
        timestamp: int
    ):
        """Trigger registered callbacks"""
        if symbol in self.callbacks:
            event_data = {
                'symbol': symbol,
                'price': price,
                'timestamp': timestamp
            }

            for callback in self.callbacks[symbol]:
                try:
                    await callback(event_data)
                except Exception as e:
                    logger.error(f"Callback error for {symbol}: {e}")

    async def subscribe(
        self,
        symbol: str,
        callback: Callable
    ):
        """
        Subscribe to ticker updates for a symbol

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            callback: Async function to call on price update
        """
        # Add to subscriptions
        self.subscribed_symbols.add(symbol)

        # Register callback
        if symbol not in self.callbacks:
            self.callbacks[symbol] = []
        self.callbacks[symbol].append(callback)

        # If already connected, subscribe dynamically
        if self.ws_connection and not self.testnet:
            await self._subscribe_symbol_live(symbol)

        logger.info(f"Subscribed to ticker updates for {symbol}")

    async def _subscribe_symbol_live(self, symbol: str):
        """Subscribe to symbol while connected"""
        if self.exchange_name == 'bybit':
            subscribe_msg = {
                "op": "subscribe",
                "args": [f"tickers.{symbol}"]
            }
            await self.ws_connection.send(json.dumps(subscribe_msg))
        # Binance requires reconnection to add new streams

    async def unsubscribe(self, symbol: str):
        """Unsubscribe from ticker updates"""
        if symbol in self.subscribed_symbols:
            self.subscribed_symbols.remove(symbol)

        if symbol in self.callbacks:
            del self.callbacks[symbol]

        # Unsubscribe from WebSocket if connected
        if self.ws_connection and not self.testnet:
            await self._unsubscribe_symbol_live(symbol)

        logger.info(f"Unsubscribed from {symbol}")

    async def _unsubscribe_symbol_live(self, symbol: str):
        """Unsubscribe from symbol while connected"""
        if self.exchange_name == 'bybit':
            unsubscribe_msg = {
                "op": "unsubscribe",
                "args": [f"tickers.{symbol}"]
            }
            await self.ws_connection.send(json.dumps(unsubscribe_msg))

    async def _polling_loop(self):
        """Polling fallback for testnet"""
        from core.exchange_manager import ExchangeManager

        # Get exchange instance
        # This is a simplified version - in real implementation
        # you would pass the exchange instance properly

        while self._running:
            try:
                for symbol in self.subscribed_symbols.copy():
                    # Fetch current price
                    # In real implementation, use exchange.fetch_ticker()
                    price = await self._fetch_price_testnet(symbol)

                    if price:
                        await self._trigger_callbacks(
                            symbol,
                            price,
                            int(asyncio.get_event_loop().time() * 1000)
                        )

                await asyncio.sleep(5)  # Poll every 5 seconds

            except Exception as e:
                logger.error(f"Polling error: {e}")
                await asyncio.sleep(10)

    async def _fetch_price_testnet(self, symbol: str) -> Optional[Decimal]:
        """Fetch price for testnet (placeholder)"""
        # In real implementation, this would call exchange.fetch_ticker()
        # For now, return a mock price
        import random
        return Decimal(str(40000 + random.uniform(-1000, 1000)))

    async def _handle_disconnect(self):
        """Handle WebSocket disconnection"""
        if self._reconnect_attempts < self.max_reconnect_attempts:
            self._reconnect_attempts += 1
            wait_time = min(60, 2 ** self._reconnect_attempts)

            logger.warning(
                f"WebSocket disconnected. Reconnecting in {wait_time}s "
                f"(attempt {self._reconnect_attempts}/{self.max_reconnect_attempts})"
            )

            await asyncio.sleep(wait_time)

            if self._running:
                await self._connect_websocket()
        else:
            logger.error("Max reconnection attempts reached. Stopping ticker stream.")
            self._running = False

    async def stop(self):
        """Stop the ticker stream"""
        self._running = False

        if self.ws_connection:
            await self.ws_connection.close()

        logger.info(f"Ticker stream stopped for {self.exchange_name}")
```

---

## 🎯 ФАЗА 4: MONITOR & CLOSER

Смотри полную реализацию в основном документе `AGED_POSITION_MANAGER_V2_REDESIGN.md`

---

## 📊 ФАЗА 5: MIGRATION SCRIPT

**Файл**: `scripts/migrate_aged_positions.py`

```python
#!/usr/bin/env python3
"""
Migration script for existing aged positions to V2 system
"""
import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal

from database.repository import Repository
from core.aged_position_manager import AgedPositionManager  # Old version
from core.aged_position_state_manager import AgedPositionStateManager  # New version

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate_aged_positions():
    """Migrate existing aged positions to new system"""

    repository = Repository()
    old_manager = AgedPositionManager(...)  # Initialize with config
    new_state_manager = AgedPositionStateManager(repository)

    logger.info("Starting aged positions migration...")

    # 1. Find all positions with existing limit orders
    positions_with_orders = []

    for symbol, position in old_manager.position_manager.positions.items():
        if position and hasattr(position, 'opened_at'):
            # Calculate age
            age = datetime.now(timezone.utc) - position.opened_at
            age_hours = age.total_seconds() / 3600

            if age_hours > old_manager.max_position_age_hours:
                positions_with_orders.append(position)

    logger.info(f"Found {len(positions_with_orders)} aged positions to migrate")

    # 2. Cancel existing limit orders
    for position in positions_with_orders:
        try:
            exchange = old_manager.exchanges.get(position.exchange)
            orders = await exchange.fetch_open_orders(position.symbol)

            for order in orders:
                if order.get('type') == 'limit' and order.get('reduceOnly'):
                    logger.info(f"Cancelling order {order['id']} for {position.symbol}")
                    await exchange.cancel_order(order['id'], position.symbol)
                    await asyncio.sleep(0.5)  # Rate limit

        except Exception as e:
            logger.error(f"Error cancelling orders for {position.symbol}: {e}")

    # 3. Create aged entries in new system
    migrated_count = 0

    for position in positions_with_orders:
        try:
            # Skip if trailing stop is active
            if hasattr(position, 'trailing_activated') and position.trailing_activated:
                logger.info(f"Skipping {position.symbol} - trailing stop active")
                continue

            # Create aged entry
            entry = await new_state_manager.create_aged_entry(position)

            # Determine initial phase based on age
            age_hours = (datetime.now(timezone.utc) - position.opened_at).total_seconds() / 3600
            hours_over_limit = age_hours - new_state_manager.max_age_hours

            if hours_over_limit > new_state_manager.grace_period_hours:
                # Already past grace period
                await new_state_manager.transition_to_grace_active(entry)
                await new_state_manager.transition_to_progressive(entry)
            else:
                # Still in grace period
                await new_state_manager.transition_to_grace_active(entry)

            migrated_count += 1
            logger.info(f"Migrated {position.symbol} to new system")

        except Exception as e:
            logger.error(f"Error migrating {position.symbol}: {e}")

    logger.info(f"Migration complete: {migrated_count} positions migrated")

    # 4. Update configuration to use new system
    logger.info("Update .env to set USE_AGED_V2=true")

    return migrated_count


if __name__ == "__main__":
    asyncio.run(migrate_aged_positions())
```

---

## 🚀 DEPLOYMENT CHECKLIST

### Pre-deployment
```bash
# 1. Run tests
pytest tests/test_aged_position_v2.py -v

# 2. Check database migration
psql -U $DB_USER -d $DB_NAME -c "SELECT * FROM monitoring.aged_positions LIMIT 1;"

# 3. Backup production data
pg_dump -U $DB_USER -d $DB_NAME -t monitoring.positions > backup_positions_$(date +%Y%m%d).sql
```

### Deployment Steps

1. **Deploy with feature flag OFF**:
```python
# .env
USE_AGED_V2=false
```

2. **Test in parallel mode**:
```python
# main.py
if os.getenv('USE_AGED_V2', 'false').lower() == 'true':
    self.aged_manager = AgedPositionManagerV2(...)
else:
    self.aged_manager = AgedPositionManager(...)  # Old version
```

3. **Monitor metrics**:
```sql
-- Check new system performance
SELECT
    status,
    COUNT(*) as count,
    AVG(hours_aged) as avg_age,
    AVG(actual_pnl_percent) as avg_pnl
FROM monitoring.aged_positions
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY status;
```

4. **Gradual rollout**:
```python
# Enable for specific symbols first
AGED_V2_SYMBOLS=BTCUSDT,ETHUSDT

# Then enable for all
USE_AGED_V2=true
```

5. **Remove old code** (after 2 weeks stable):
```bash
git rm core/aged_position_manager.py
git commit -m "Remove deprecated aged position manager"
```

---

## 📈 MONITORING & METRICS

### Prometheus Metrics

```python
# monitoring/aged_metrics.py
from prometheus_client import Counter, Histogram, Gauge

# Counters
aged_positions_detected = Counter(
    'aged_positions_detected_total',
    'Total aged positions detected'
)

aged_positions_closed = Counter(
    'aged_positions_closed_total',
    'Total aged positions closed',
    ['close_reason']
)

# Gauges
aged_positions_active = Gauge(
    'aged_positions_active',
    'Currently active aged positions',
    ['status']
)

# Histograms
aged_position_age = Histogram(
    'aged_position_age_hours',
    'Age of positions when closed',
    buckets=[3, 6, 12, 24, 48, 72]
)

aged_position_pnl = Histogram(
    'aged_position_pnl_percent',
    'PnL percentage of closed aged positions',
    buckets=[-10, -5, -2, -1, 0, 1, 2, 5, 10]
)
```

### Grafana Dashboard

```json
{
  "dashboard": {
    "title": "Aged Positions V2",
    "panels": [
      {
        "title": "Active Aged Positions by Status",
        "targets": [
          {
            "expr": "aged_positions_active"
          }
        ]
      },
      {
        "title": "Closure Success Rate",
        "targets": [
          {
            "expr": "rate(aged_positions_closed_total[1h])"
          }
        ]
      },
      {
        "title": "Average PnL on Close",
        "targets": [
          {
            "expr": "histogram_quantile(0.5, aged_position_pnl_percent)"
          }
        ]
      }
    ]
  }
}
```

---

## 🐛 TROUBLESHOOTING

### Common Issues

1. **WebSocket disconnections**:
```python
# Check logs
grep "WebSocket disconnected" /var/log/trading_bot.log

# Solution: Increase reconnect attempts
MAX_RECONNECT_ATTEMPTS=20
```

2. **Positions not being detected**:
```sql
-- Check detection query
SELECT * FROM monitoring.positions
WHERE opened_at < NOW() - INTERVAL '3 hours'
AND trailing_activated = false
AND status = 'OPEN';
```

3. **Target price not updating**:
```python
# Debug state transitions
logger.debug(f"State transition: {from_status} -> {to_status}")
logger.debug(f"New target: {target_price}, tolerance: {loss_tolerance}%")
```

---

## 📚 REFERENCES

- [CCXT Pro Documentation](https://docs.ccxt.com/en/latest/ccxt.pro.html)
- [WebSocket Best Practices](https://websockets.readthedocs.io/)
- [PostgreSQL Triggers](https://www.postgresql.org/docs/current/plpgsql-trigger.html)
- [AsyncIO Patterns](https://docs.python.org/3/library/asyncio-task.html)

---

*План подготовлен: 2025-10-23*
*Версия: 1.0*
*Автор: AI Assistant*