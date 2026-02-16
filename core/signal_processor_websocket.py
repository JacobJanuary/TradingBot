"""
WebSocket Signal Processor — Real-Time Mode

Receives signals from WebSocket server and immediately delegates them
to the composite strategy lifecycle manager.

Replaces the old wave-monitoring loop (2026-02-15):
- OLD: Sleep until WAVE_CHECK_MINUTES → poll buffer → batch process
- NEW: Signal arrives → callback fires → lifecycle manager processes immediately
"""
import logging
import asyncio
import os

from core.signal_lifecycle import SignalLifecycleManager
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

from websocket.signal_client import SignalWebSocketClient
from core.event_logger import get_event_logger, EventType

logger = logging.getLogger(__name__)


class WebSocketSignalProcessor:
    """
    Real-time signal processor via WebSocket.

    Signals are processed immediately as they arrive — no wave batching,
    no scheduled checks, no buffer polling.
    """

    def __init__(self, config, position_manager, repository, event_router):
        self.config = config
        self.position_manager = position_manager
        self.repository = repository
        self.event_router = event_router

        # WebSocket configuration from .env
        self.ws_config = {
            'SIGNAL_WS_URL': os.getenv('SIGNAL_WS_URL', 'ws://localhost:8765'),
            'SIGNAL_WS_TOKEN': os.getenv('SIGNAL_WS_TOKEN'),
            'AUTO_RECONNECT': os.getenv('SIGNAL_WS_AUTO_RECONNECT', 'true').lower() == 'true',
            'RECONNECT_INTERVAL': int(os.getenv('SIGNAL_WS_RECONNECT_INTERVAL', '5')),
            'MAX_RECONNECT_ATTEMPTS': int(os.getenv('SIGNAL_WS_MAX_RECONNECT_ATTEMPTS', '-1')),
            'SIGNAL_BUFFER_SIZE': int(os.getenv('SIGNAL_BUFFER_SIZE', '100'))
        }

        # Initialize WebSocket client
        self.ws_client = SignalWebSocketClient(self.ws_config)

        # Set WebSocket callbacks
        self.ws_client.set_callbacks(
            on_signals=self._on_signals_received,
            on_connect=self._on_ws_connect,
            on_disconnect=self._on_ws_disconnect,
            on_error=self._on_ws_error
        )

        # State
        self.running = False
        self._ws_task = None

        # Composite strategy lifecycle manager (set via set_lifecycle_manager)
        self.lifecycle_manager: SignalLifecycleManager = None

        # Statistics
        self.stats = {
            'signals_received': 0,
            'signals_delegated': 0,
            'signals_unmatched': 0,
            'signals_failed': 0,
            'last_signal_time': None,
            'websocket_reconnections': 0,
        }

        logger.info(
            f"WebSocket Signal Processor initialized (REAL-TIME mode): "
            f"url={self.ws_config['SIGNAL_WS_URL']}"
        )

    async def start(self):
        """Start WebSocket signal processing"""
        logger.info("Starting WebSocket Signal Processor (real-time mode)...")

        self.running = True
        self._ws_task = asyncio.create_task(self.ws_client.run())

        logger.info("✅ WebSocket Signal Processor started — signals processed on arrival")

    async def stop(self):
        """Stop WebSocket processing"""
        logger.info("Stopping WebSocket Signal Processor...")

        self.running = False

        # Stop WebSocket client
        await self.ws_client.stop()

        # Stop WebSocket task
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass

        logger.info("✅ WebSocket Signal Processor stopped")

    def set_lifecycle_manager(self, lifecycle_manager: SignalLifecycleManager):
        """Set lifecycle manager for composite strategy delegation."""
        self.lifecycle_manager = lifecycle_manager
        logger.info("✅ Lifecycle manager set on signal processor")

    async def _on_signals_received(self, ws_signals: List[Dict]):
        """
        Callback when signals arrive from WebSocket server.
        Immediately delegates each signal to lifecycle manager.
        """
        try:
            count = len(ws_signals)
            self.stats['signals_received'] += count
            self.stats['last_signal_time'] = datetime.now(timezone.utc)

            logger.info(f"📡 Received {count} signals — processing immediately")

            # Delegate to lifecycle manager
            remaining = await self._delegate_to_lifecycle(ws_signals)

            if remaining:
                self.stats['signals_unmatched'] += len(remaining)
                for sig in remaining:
                    sym = sig.get('symbol', sig.get('pair_symbol', '?'))
                    sc = sig.get('total_score', sig.get('score_week', 0))
                    rsi = sig.get('rsi', 0)
                    vol = sig.get('volume_zscore', sig.get('vol_zscore', 0))
                    oi = sig.get('oi_delta_pct', sig.get('oi_delta', 0))
                    logger.warning(
                        f"⚠️ DROPPED {sym}: score={sc} rsi={rsi} vol={vol} oi={oi} "
                        f"— no matching rule"
                    )

        except Exception as e:
            logger.error(f"Error processing WebSocket signals: {e}", exc_info=True)
            self.stats['signals_failed'] += len(ws_signals) if ws_signals else 0

    async def _delegate_to_lifecycle(self, signals: List[Dict]) -> List[Dict]:
        """
        Delegate signals matching composite strategy to lifecycle manager.

        Returns list of signals NOT handled by lifecycle (unmatched).
        """
        if not self.lifecycle_manager:
            logger.warning("No lifecycle manager — cannot process signals")
            return signals

        remaining = []
        for signal in signals:
            score = float(signal.get('total_score', signal.get('score_week', 0)))
            rsi = float(signal.get('rsi', 0))
            vol_zscore = float(signal.get('volume_zscore', signal.get('vol_zscore', 0)))
            oi_delta = float(signal.get('oi_delta_pct', signal.get('oi_delta', 0)))

            # Check if composite strategy has a rule for this signal
            params = self.lifecycle_manager.composite_strategy.match_signal(
                score, rsi=rsi, vol_zscore=vol_zscore, oi_delta=oi_delta
            )
            if params:
                symbol = signal.get('symbol', '')
                logger.info(
                    f"🎯 Signal {symbol} score={score} rsi={rsi:.0f} "
                    f"vol={vol_zscore:.1f} oi={oi_delta:.1f} → composite strategy, "
                    f"delegating to lifecycle manager"
                )
                try:
                    await self.lifecycle_manager.on_signal_received(signal, matched_params=params)
                    self.stats['signals_delegated'] += 1
                except Exception as e:
                    logger.error(f"Lifecycle manager error for {symbol}: {e}")
                    self.stats['signals_failed'] += 1
                    event_logger = get_event_logger()
                    if event_logger:
                        asyncio.create_task(event_logger.log_event(
                            EventType.ERROR_OCCURRED,
                            {'symbol': symbol, 'error': str(e), 'context': 'lifecycle_manager', 'score': score},
                            symbol=symbol, severity='ERROR'
                        ))
            else:
                remaining.append(signal)

        delegated = len(signals) - len(remaining)
        if delegated:
            logger.info(f"Lifecycle delegation: {delegated} delegated, {len(remaining)} unmatched")

        return remaining

    # ── WebSocket callbacks ──────────────────────────────────────

    async def _on_ws_connect(self):
        """Callback on WebSocket connect"""
        logger.info("🔌 WebSocket connected to signal server")

    async def _on_ws_disconnect(self):
        """Callback on WebSocket disconnect"""
        logger.warning("⚠️ WebSocket disconnected from signal server")
        self.stats['websocket_reconnections'] += 1

    async def _on_ws_error(self, error):
        """Callback on WebSocket error"""
        logger.error(f"❌ WebSocket error: {error}")

    # ── Stats ────────────────────────────────────────────────────

    def get_stats(self) -> Dict:
        """Get processor statistics"""
        return {
            **self.stats,
            'websocket': self.ws_client.get_stats(),
            'buffer_size': len(self.ws_client.signal_buffer),
        }