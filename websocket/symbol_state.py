"""
SymbolStateManager — Per-symbol state machine for WebSocket subscriptions

Replaces the 4 overlapping data structures in BinanceHybridStream:
  - subscribed_symbols (set)
  - pending_subscriptions (set)
  - subscription_queue (asyncio.Queue)
  - mark_prices timestamps (dict)

Each symbol transitions through a clean state machine:
  INIT → SUBSCRIBED → STALE → REST_FALLBACK → SUBSCRIBED
                              → REMOVED

Expert Panel Decision (2026-02-12):
  Expert A (Hedge Fund): per-symbol state machine, not global
  Expert B (Citi Group): circuit breaker pattern per symbol
  Expert C (Binance): max 3 retries before REST fallback

Date: 2026-02-12
"""

import asyncio
import logging
import time
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Set, Dict, Optional, Callable

logger = logging.getLogger(__name__)


class SymbolState(Enum):
    """Per-symbol subscription state"""
    INIT = auto()            # Just added, subscription not yet sent
    SUBSCRIBING = auto()     # Subscription request sent, awaiting data
    SUBSCRIBED = auto()      # Receiving WS data normally
    STALE = auto()           # WS data not received for > threshold
    REST_FALLBACK = auto()   # Switched to REST polling
    REMOVED = auto()         # Position closed, cleanup pending


@dataclass
class SymbolEntry:
    """Tracks state and metadata for a single symbol"""
    symbol: str
    state: SymbolState = SymbolState.INIT
    last_ws_update: float = 0.0       # monotonic time of last WS price
    last_price: Optional[str] = None  # last known price (WS or REST)
    retry_count: int = 0              # subscription retries (circuit breaker)
    created_at: float = field(default_factory=time.monotonic)

    MAX_RETRIES: int = 3  # Circuit breaker threshold

    @property
    def is_active(self) -> bool:
        return self.state not in (SymbolState.REMOVED,)

    @property
    def circuit_open(self) -> bool:
        """True if this symbol has exhausted WS retries → must use REST"""
        return self.retry_count >= self.MAX_RETRIES

    def record_ws_update(self, price: str):
        """Called when WS price data arrives for this symbol"""
        self.last_ws_update = time.monotonic()
        self.last_price = price
        self.state = SymbolState.SUBSCRIBED
        self.retry_count = 0  # Reset circuit breaker on success

    def record_rest_update(self, price: str):
        """Called when REST fallback provides price for this symbol"""
        self.last_price = price
        # Don't change state back to SUBSCRIBED — REST is a degraded mode

    def mark_stale(self):
        """Transition to STALE when WS data stops flowing"""
        if self.state == SymbolState.SUBSCRIBED:
            self.state = SymbolState.STALE

    def mark_rest_fallback(self):
        """Transition to REST_FALLBACK after circuit breaker opens"""
        self.state = SymbolState.REST_FALLBACK

    def increment_retry(self):
        """Track failed subscription attempt"""
        self.retry_count += 1
        if self.circuit_open:
            self.mark_rest_fallback()
            logger.warning(
                f"🔌 [STATE] Circuit breaker OPEN for {self.symbol} "
                f"(retries={self.retry_count}). Falling back to REST."
            )

    def data_age(self) -> float:
        """Seconds since last WS update"""
        if self.last_ws_update == 0:
            return float('inf')
        return time.monotonic() - self.last_ws_update


class SymbolStateManager:
    """
    Central state manager for all symbol subscriptions.

    Eliminates race conditions by being the single source of truth
    for subscription state, replacing 4 separate data structures.

    Thread-safe within asyncio (all mutations happen in coroutines,
    no concurrent access across threads).
    """

    def __init__(self, stale_threshold: float = 3.0):
        self._symbols: Dict[str, SymbolEntry] = {}
        self._stale_threshold = stale_threshold
        self._on_symbols_changed: Optional[Callable] = None

    def set_change_callback(self, callback: Callable):
        """Set callback invoked when active symbol set changes (add/remove)"""
        self._on_symbols_changed = callback

    # ==================== Mutations ====================

    def add(self, symbol: str) -> SymbolEntry:
        """Add symbol for subscription tracking"""
        if symbol in self._symbols and self._symbols[symbol].is_active:
            return self._symbols[symbol]

        entry = SymbolEntry(symbol=symbol)
        self._symbols[symbol] = entry
        logger.info(f"➕ [STATE] Added {symbol} (state=INIT)")
        return entry

    def remove(self, symbol: str):
        """Mark symbol as removed (position closed)"""
        if symbol in self._symbols:
            self._symbols[symbol].state = SymbolState.REMOVED
            logger.info(f"➖ [STATE] Removed {symbol}")

    def mark_subscribing(self, symbol: str):
        """Mark symbol as subscription-in-progress"""
        if symbol in self._symbols:
            self._symbols[symbol].state = SymbolState.SUBSCRIBING

    def record_ws_update(self, symbol: str, price: str):
        """Record incoming WS price data"""
        entry = self._symbols.get(symbol)
        if entry and entry.is_active:
            entry.record_ws_update(price)

    def record_rest_update(self, symbol: str, price: str):
        """Record incoming REST price data"""
        entry = self._symbols.get(symbol)
        if entry and entry.is_active:
            entry.record_rest_update(price)

    def increment_retry(self, symbol: str):
        """Record failed subscription attempt (circuit breaker)"""
        entry = self._symbols.get(symbol)
        if entry:
            entry.increment_retry()

    def reset_all_for_reconnect(self):
        """
        Reset all active symbols to INIT for reconnection.
        Preserves last_price for trailing stop fallback.
        Does NOT clear price data (Fix 1.3 from expert panel).
        """
        for entry in self._symbols.values():
            if entry.is_active:
                entry.state = SymbolState.INIT
                entry.retry_count = 0
        logger.info(f"🔄 [STATE] Reset {len(self.active_symbols)} symbols for reconnect")

    def cleanup_removed(self):
        """Purge REMOVED entries from memory"""
        removed = [s for s, e in self._symbols.items() if e.state == SymbolState.REMOVED]
        for s in removed:
            del self._symbols[s]
        if removed:
            logger.debug(f"🧹 [STATE] Cleaned up {len(removed)} removed symbols")

    # ==================== Queries ====================

    @property
    def active_symbols(self) -> Set[str]:
        """All symbols that need subscription (not REMOVED)"""
        return {s for s, e in self._symbols.items() if e.is_active}

    @property
    def subscribed_symbols(self) -> Set[str]:
        """Symbols confirmed receiving WS data"""
        return {s for s, e in self._symbols.items() if e.state == SymbolState.SUBSCRIBED}

    @property
    def pending_symbols(self) -> Set[str]:
        """Symbols awaiting subscription (INIT or SUBSCRIBING)"""
        return {
            s for s, e in self._symbols.items()
            if e.state in (SymbolState.INIT, SymbolState.SUBSCRIBING)
        }

    @property
    def stale_symbols(self) -> Set[str]:
        """Symbols that haven't received WS data recently"""
        return {s for s, e in self._symbols.items() if e.state == SymbolState.STALE}

    @property
    def rest_fallback_symbols(self) -> Set[str]:
        """Symbols using REST polling (circuit breaker open)"""
        return {s for s, e in self._symbols.items() if e.state == SymbolState.REST_FALLBACK}

    def get_entry(self, symbol: str) -> Optional[SymbolEntry]:
        return self._symbols.get(symbol)

    def get_last_price(self, symbol: str) -> Optional[str]:
        entry = self._symbols.get(symbol)
        return entry.last_price if entry else None

    def check_stale(self) -> Set[str]:
        """
        Check all SUBSCRIBED symbols for staleness.
        Transitions stale symbols to STALE state.
        Returns set of newly-stale symbols.
        """
        newly_stale = set()
        for symbol, entry in self._symbols.items():
            if entry.state == SymbolState.SUBSCRIBED:
                if entry.data_age() > self._stale_threshold:
                    entry.mark_stale()
                    newly_stale.add(symbol)
        return newly_stale

    # ==================== Diagnostics ====================

    def get_status(self) -> Dict:
        """Get summary status for monitoring"""
        state_counts = {}
        for entry in self._symbols.values():
            state_name = entry.state.name
            state_counts[state_name] = state_counts.get(state_name, 0) + 1

        return {
            'total': len(self._symbols),
            'active': len(self.active_symbols),
            'subscribed': len(self.subscribed_symbols),
            'pending': len(self.pending_symbols),
            'stale': len(self.stale_symbols),
            'rest_fallback': len(self.rest_fallback_symbols),
            'states': state_counts,
        }

    def __repr__(self):
        status = self.get_status()
        return (
            f"SymbolStateManager("
            f"active={status['active']}, "
            f"subscribed={status['subscribed']}, "
            f"pending={status['pending']}, "
            f"stale={status['stale']}, "
            f"rest_fallback={status['rest_fallback']})"
        )
