"""
WebSocket Signal Processor - Миграция с PostgreSQL polling на WebSocket stream
"""
import logging
import asyncio
import os
from typing import Dict, List, Optional
from datetime import datetime, timezone

from websocket.signal_client import SignalWebSocketClient
from websocket.signal_adapter import SignalAdapter
from core.wave_signal_processor import WaveSignalProcessor

logger = logging.getLogger(__name__)


class WebSocketSignalProcessor:
    """
    Обработчик сигналов через WebSocket вместо прямых запросов к БД
    
    Features:
    - Real-time сигналы через WebSocket (<10ms латентность)
    - Автоматическое переподключение при обрыве связи
    - Адаптация формата сигналов для существующей логики
    - Graceful shutdown
    """
    
    def __init__(self, config, position_manager, repository, event_router):
        """
        Initialize WebSocket Signal Processor
        
        Args:
            config: Trading configuration
            position_manager: Position manager instance
            repository: Database repository (для загрузки mapping)
            event_router: Event router for notifications
        """
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
        
        # Initialize signal adapter
        self.signal_adapter = SignalAdapter()
        
        # Initialize wave processor (existing logic)
        self.wave_processor = WaveSignalProcessor(config, position_manager)
        
        # Set WebSocket callbacks
        self.ws_client.set_callbacks(
            on_signals=self._on_signals_received,
            on_connect=self._on_ws_connect,
            on_disconnect=self._on_ws_disconnect,
            on_error=self._on_ws_error
        )
        
        # State
        self.running = False
        self._signal_queue = asyncio.Queue()
        self._processing_task = None
        
        # Statistics
        self.stats = {
            'signals_received': 0,
            'signals_processed': 0,
            'signals_failed': 0,
            'waves_processed': 0,
            'last_signal_time': None,
            'websocket_reconnections': 0
        }
        
        logger.info(
            f"WebSocket Signal Processor initialized: "
            f"url={self.ws_config['SIGNAL_WS_URL']}, "
            f"auto_reconnect={self.ws_config['AUTO_RECONNECT']}"
        )
    
    async def start(self):
        """Start WebSocket signal processing"""
        logger.info("Starting WebSocket Signal Processor...")
        
        # Load trading pair mapping from database
        logger.info("Loading trading pair mapping from database...")
        await self.signal_adapter.load_trading_pair_mapping_from_db(self.repository)
        
        # Start signal processing task
        self._processing_task = asyncio.create_task(self._process_signal_queue())
        
        # Start WebSocket client (runs in background)
        self.running = True
        asyncio.create_task(self.ws_client.run())
        
        logger.info("✅ WebSocket Signal Processor started")
    
    async def stop(self):
        """Stop WebSocket processing"""
        logger.info("Stopping WebSocket Signal Processor...")
        
        self.running = False
        
        # Stop WebSocket client
        await self.ws_client.stop()
        
        # Stop processing task
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
        
        logger.info("✅ WebSocket Signal Processor stopped")
    
    async def _on_signals_received(self, ws_signals: List[Dict]):
        """
        Callback когда получены сигналы от WebSocket сервера
        
        Args:
            ws_signals: Raw сигналы от WebSocket (формат сервера)
        """
        try:
            logger.info(f"📡 Received {len(ws_signals)} signals from WebSocket")
            
            # Update stats
            self.stats['signals_received'] += len(ws_signals)
            self.stats['last_signal_time'] = datetime.now(timezone.utc)
            
            # Adapt signals to bot format
            adapted_signals = self.signal_adapter.adapt_signals(ws_signals)
            
            if not adapted_signals:
                logger.warning("No signals after adaptation")
                return
            
            logger.info(f"✅ Adapted {len(adapted_signals)} signals to bot format")
            
            # Group signals by wave_timestamp
            waves = self._group_signals_by_wave(adapted_signals)
            
            logger.info(f"🌊 Grouped into {len(waves)} wave(s)")
            
            # Put each wave into processing queue
            for wave_timestamp, wave_signals in waves.items():
                await self._signal_queue.put({
                    'wave_timestamp': wave_timestamp,
                    'signals': wave_signals
                })
                logger.debug(f"Queued wave {wave_timestamp} with {len(wave_signals)} signals")
            
        except Exception as e:
            logger.error(f"Error handling WebSocket signals: {e}", exc_info=True)
            self.stats['signals_failed'] += len(ws_signals) if ws_signals else 0
    
    def _group_signals_by_wave(self, signals: List[Dict]) -> Dict[datetime, List[Dict]]:
        """
        Group signals by wave_timestamp (15-minute intervals)
        
        Args:
            signals: Adapted signals in bot format
            
        Returns:
            Dict[wave_timestamp, List[signals]]
        """
        waves = {}
        
        for signal in signals:
            wave_ts = signal.get('wave_timestamp')
            if wave_ts not in waves:
                waves[wave_ts] = []
            waves[wave_ts].append(signal)
        
        return waves
    
    async def _process_signal_queue(self):
        """
        Background task для обработки очереди сигналов
        """
        logger.info("Signal queue processing started")
        
        while self.running:
            try:
                # Wait for wave with timeout
                try:
                    wave_data = await asyncio.wait_for(
                        self._signal_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                wave_timestamp = wave_data['wave_timestamp']
                wave_signals = wave_data['signals']
                
                logger.info(
                    f"🌊 Processing wave {wave_timestamp} with {len(wave_signals)} signals"
                )
                
                # Process wave using existing wave processor logic
                result = await self.wave_processor.process_wave_signals(
                    signals=wave_signals,
                    wave_timestamp=str(wave_timestamp)
                )
                
                # Update stats
                self.stats['waves_processed'] += 1
                self.stats['signals_processed'] += result.get('processed', 0)
                self.stats['signals_failed'] += result.get('failed_count', 0)
                
                logger.info(
                    f"✅ Wave {wave_timestamp} complete: "
                    f"{result.get('processed', 0)} processed, "
                    f"{result.get('failed_count', 0)} failed"
                )
                
            except asyncio.CancelledError:
                logger.info("Signal queue processing cancelled")
                break
            except Exception as e:
                logger.error(f"Error processing signal queue: {e}", exc_info=True)
                await asyncio.sleep(1)
        
        logger.info("Signal queue processing stopped")
    
    async def _on_ws_connect(self):
        """Callback когда WebSocket подключился"""
        logger.info("🔌 WebSocket connected to signal server")
        
        # Emit event
        await self.event_router.emit('signal_stream.connected', {
            'url': self.ws_config['SIGNAL_WS_URL'],
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    
    async def _on_ws_disconnect(self):
        """Callback когда WebSocket отключился"""
        logger.warning("⚠️ WebSocket disconnected from signal server")
        
        # Emit event
        await self.event_router.emit('signal_stream.disconnected', {
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    
    async def _on_ws_error(self, error):
        """Callback когда произошла ошибка WebSocket"""
        logger.error(f"❌ WebSocket error: {error}")
        
        # Emit event
        await self.event_router.emit('signal_stream.error', {
            'error': str(error),
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    
    def get_stats(self) -> Dict:
        """Get statistics"""
        return {
            'processor': self.stats,
            'websocket': self.ws_client.get_stats(),
            'queue_size': self._signal_queue.qsize() if self._signal_queue else 0
        }
