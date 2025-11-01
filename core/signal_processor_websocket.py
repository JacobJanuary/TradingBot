"""
WebSocket Signal Processor - Миграция с PostgreSQL polling на WebSocket stream
Реализует ту же логику мониторинга волн что и старый SignalProcessor
"""
import logging
import asyncio
import os
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from websocket.signal_client import SignalWebSocketClient
from websocket.signal_adapter import SignalAdapter
from core.wave_signal_processor import WaveSignalProcessor
from core.symbol_filter import SymbolFilter
from models.validation import validate_signal, OrderSide
from core.event_logger import get_event_logger, EventType

logger = logging.getLogger(__name__)


class WebSocketSignalProcessor:
    """
    Обработчик сигналов через WebSocket вместо прямых запросов к БД
    
    Логика мониторинга волн (аналогично старому SignalProcessor):
    1. Ждать до времени проверки волны (WAVE_CHECK_MINUTES)
    2. Вычислить timestamp ожидаемой волны (15-минутная свеча)
    3. Мониторить появление сигналов с этим timestamp (до 120 сек)
    4. Обработать волну когда сигналы появились
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
        
        # Wave monitoring configuration (из .env, как в старом SignalProcessor)
        wave_minutes_str = os.getenv('WAVE_CHECK_MINUTES')
        if not wave_minutes_str:
            raise ValueError("WAVE_CHECK_MINUTES must be set in .env file")
        self.wave_check_minutes = sorted([int(m.strip()) for m in wave_minutes_str.split(',')])
        
        self.wave_check_duration = int(os.getenv('WAVE_CHECK_DURATION_SECONDS', '120'))
        self.wave_check_interval = int(os.getenv('WAVE_CHECK_INTERVAL_SECONDS', '1'))
        
        # Initialize WebSocket client
        self.ws_client = SignalWebSocketClient(self.ws_config)
        
        # Initialize signal adapter
        self.signal_adapter = SignalAdapter()
        
        # Initialize wave processor (existing logic)
        self.wave_processor = WaveSignalProcessor(config, position_manager)
        
        # ✅ FIX: Initialize symbol filter для фильтрации стоп-листа
        self.symbol_filter = SymbolFilter(config)
        
        # Set WebSocket callbacks
        self.ws_client.set_callbacks(
            on_signals=self._on_signals_received,
            on_connect=self._on_ws_connect,
            on_disconnect=self._on_ws_disconnect,
            on_error=self._on_ws_error
        )
        
        # State
        self.running = False
        self._wave_monitoring_task = None
        self._ws_task = None

        # Wave tracking (как в старом SignalProcessor)
        self.processed_waves = {}  # {wave_timestamp: {'signal_ids': set(), 'count': int}}

        
        # Statistics
        self.stats = {
            'signals_received': 0,
            'signals_processed': 0,
            'signals_failed': 0,
            'waves_detected': 0,
            'waves_processed': 0,
            'last_signal_time': None,
            'websocket_reconnections': 0,
            'current_wave': None
        }
        
        logger.info(
            f"WebSocket Signal Processor initialized: "
            f"url={self.ws_config['SIGNAL_WS_URL']}, "
            f"wave_check_minutes={self.wave_check_minutes}"
        )
    
    async def start(self):
        """Start WebSocket signal processing"""
        logger.info("Starting WebSocket Signal Processor...")
        
        # Start WebSocket client (runs in background)
        self.running = True
        self._ws_task = asyncio.create_task(self.ws_client.run())
        
        # Start wave monitoring loop (главная логика)
        self._wave_monitoring_task = asyncio.create_task(self._wave_monitoring_loop())
        
        logger.info("✅ WebSocket Signal Processor started")
    
    async def stop(self):
        """Stop WebSocket processing"""
        logger.info("Stopping WebSocket Signal Processor...")
        
        self.running = False
        
        # Stop WebSocket client
        await self.ws_client.stop()
        
        # Stop wave monitoring task
        if self._wave_monitoring_task:
            self._wave_monitoring_task.cancel()
            try:
                await self._wave_monitoring_task
            except asyncio.CancelledError:
                pass
        
        # Stop WebSocket task
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
        
        logger.info("✅ WebSocket Signal Processor stopped")
    
    async def _on_signals_received(self, ws_signals: List[Dict]):
        """
        Callback когда получены сигналы от WebSocket сервера
        
        НОВАЯ ЛОГИКА: Только логирование и статистика, НЕ накапливает
        Сигналы уже в buffer клиента (RAW формат), будут адаптированы при извлечении
        
        Args:
            ws_signals: Raw сигналы от WebSocket (формат сервера)
        """
        try:
            logger.info(f"📡 Received {len(ws_signals)} RAW signals from WebSocket (added to buffer)")
            
            # Update stats
            self.stats['signals_received'] += len(ws_signals)
            self.stats['last_signal_time'] = datetime.now(timezone.utc)
            
            # ВСЁ! Сигналы уже в buffer клиента (self.ws_client.signal_buffer)
            # Они будут извлечены и адаптированы в _monitor_wave_appearance
            
        except Exception as e:
            logger.error(f"Error handling WebSocket signals: {e}", exc_info=True)
            self.stats['signals_failed'] += len(ws_signals) if ws_signals else 0
    
    async def _wave_monitoring_loop(self):
        """
        Основной цикл мониторинга волн (аналог старого _process_loop)
        
        Логика:
        1. Ждать до следующего времени проверки волны (например, 22 минута)
        2. Вычислить timestamp ожидаемой волны (например, 00 минута = 15 минут назад)
        3. Мониторить появление сигналов с этим timestamp (до 120 секунд)
        4. Обработать волну когда сигналы появились
        """
        logger.info("🌊 Wave monitoring loop started")
        
        while self.running:
            try:
                # 1. Ждём до следующего времени проверки волны
                await self._wait_for_next_wave_check()
                
                if not self.running:
                    break
                
                # 2. Вычисляем timestamp ожидаемой волны
                expected_wave_timestamp = self._calculate_expected_wave_timestamp()
                
                logger.info(f"🔍 Looking for wave with timestamp: {expected_wave_timestamp}")
                
                # Проверяем не обработали ли мы уже эту волну
                if expected_wave_timestamp in self.processed_waves:
                    logger.info(f"Wave {expected_wave_timestamp} already processed, skipping")
                    continue

                # ✅ АТОМАРНАЯ ЗАЩИТА: Помечаем волну как "в обработке" СРАЗУ
                # Это предотвращает параллельную обработку той же волны
                self.processed_waves[expected_wave_timestamp] = {
                    'status': 'processing',
                    'started_at': datetime.now(timezone.utc),
                    'signal_ids': set(),
                    'count': 0
                }
                logger.info(f"🔒 Wave {expected_wave_timestamp} marked as processing")

                # 3. Мониторим появление волны (до WAVE_CHECK_DURATION_SECONDS)
                wave_signals = await self._monitor_wave_appearance(expected_wave_timestamp)

                if wave_signals:
                    # 4. Обрабатываем волну
                    logger.info(f"🌊 Wave detected! Processing {len(wave_signals)} signals for {expected_wave_timestamp}")

                    # Log wave detection
                    event_logger = get_event_logger()
                    if event_logger:
                        await event_logger.log_event(
                            EventType.WAVE_DETECTED,
                            {
                                'wave_timestamp': expected_wave_timestamp,
                                'signal_count': len(wave_signals),
                                'signal_ids': [s.get('id') for s in wave_signals],
                                'detection_time': datetime.now(timezone.utc).isoformat()
                            },
                            severity='INFO'
                        )

                    # Update wave metadata
                    self.processed_waves[expected_wave_timestamp].update({
                        'status': 'executing',
                        'signal_ids': set(s.get('id') for s in wave_signals),
                        'count': len(wave_signals),
                        'first_seen': datetime.now(timezone.utc)
                    })
                    self.stats['waves_detected'] += 1
                    self.stats['current_wave'] = expected_wave_timestamp

                    # ========== STEP 1: Update params BEFORE selection (CRITICAL) ==========
                    logger.info(f"📊 Step 1: Updating exchange params from wave {expected_wave_timestamp}")
                    try:
                        await self._update_exchange_params(wave_signals, expected_wave_timestamp)
                        logger.info("✅ Exchange params updated successfully")
                    except Exception as e:
                        logger.error(f"❌ Failed to update exchange params: {e}", exc_info=True)
                        logger.warning("⚠️ Continuing with existing params in database")

                    # ========== STEP 2: Query params from DB ==========
                    logger.info(f"📊 Step 2: Querying params for all exchanges")
                    params_by_exchange = await self._get_params_for_all_exchanges()

                    # ========== STEP 3: Process wave per exchange ==========
                    logger.info(
                        f"📊 Step 3: Processing {len(wave_signals)} signals with per-exchange logic"
                    )

                    wave_result = await self._process_wave_per_exchange(
                        wave_signals=wave_signals,
                        wave_timestamp=expected_wave_timestamp,
                        params_by_exchange=params_by_exchange
                    )

                    results_by_exchange = wave_result['results_by_exchange']
                    total_executed = wave_result['total_executed']
                    total_failed = wave_result['total_failed']
                    total_validated = wave_result['total_validated']

                    # ========== STEP 4: Log detailed stats ==========
                    logger.info(f"📊 Wave {expected_wave_timestamp} statistics:")
                    logger.info(f"  • Total signals in wave: {len(wave_signals)}")
                    logger.info(f"  • Exchanges processed: {len(results_by_exchange)}")

                    for exchange_id, stats in results_by_exchange.items():
                        if 'error' in stats:
                            logger.warning(
                                f"  • {stats['exchange_name']}: SKIPPED ({stats.get('error')}, "
                                f"{stats.get('skipped', 0)} signals)"
                            )
                        else:
                            buffer_info = "✅ saved us" if stats.get('buffer_saved_us') else "not needed"
                            logger.info(
                                f"  • {stats['exchange_name']}: "
                                f"{stats['executed']}/{stats['target']} positions "
                                f"(validated: {stats['validated_successful']}, "
                                f"topped up: {stats.get('topped_up', 0)}, "
                                f"duplicates: {stats['duplicates']}, "
                                f"buffer: {buffer_info}, "
                                f"params: {stats['params_source']})"
                            )

                    logger.info(
                        f"  • Total: {total_executed} positions opened, "
                        f"{total_failed} failed, {total_validated} validated"
                    )

                    # ========== STEP 5: Update global stats ==========
                    self.stats['waves_processed'] += 1
                    self.stats['signals_processed'] += total_executed

                    logger.info(
                        f"🎯 Wave {expected_wave_timestamp} complete: "
                        f"{total_executed} positions opened from {len(results_by_exchange)} exchanges"
                    )

                    # ========== STEP 6: Log wave completion event ==========
                    event_logger = get_event_logger()
                    if event_logger:
                        # Calculate totals
                        total_validation_errors = sum(
                            stats.get('validation_failed', 0)
                            for stats in results_by_exchange.values()
                        )
                        total_duplicates = sum(
                            stats.get('duplicates', 0)
                            for stats in results_by_exchange.values()
                        )

                        await event_logger.log_event(
                            EventType.WAVE_COMPLETED,
                            {
                                'wave_timestamp': expected_wave_timestamp,
                                'total_signals': len(wave_signals),
                                'exchanges_processed': len(results_by_exchange),
                                'positions_opened': total_executed,
                                'failed': total_failed,
                                'validation_errors': total_validation_errors,
                                'duplicates': total_duplicates,
                                'per_exchange_stats': {
                                    str(ex_id): {
                                        'name': stats['exchange_name'],
                                        'executed': stats.get('executed', 0),
                                        'target': stats.get('target', 0),
                                        'target_reached': stats.get('target_reached', False)
                                    }
                                    for ex_id, stats in results_by_exchange.items()
                                    if 'error' not in stats
                                },
                                'completion_time': datetime.now(timezone.utc).isoformat()
                            },
                            severity='INFO'
                        )

                    # Mark wave as completed
                    self.processed_waves[expected_wave_timestamp]['status'] = 'completed'
                    self.processed_waves[expected_wave_timestamp]['completed_at'] = datetime.now(timezone.utc)

                    # Note: pending_signals already cleared by pop() in _monitor_wave_appearance
                    # New signals for this timestamp will be rejected by processed_waves check
                else:
                    logger.info(f"⚠️ No wave detected for timestamp {expected_wave_timestamp}")
                    # Mark as not found
                    self.processed_waves[expected_wave_timestamp]['status'] = 'not_found'
                
            except asyncio.CancelledError:
                logger.info("Wave monitoring loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in wave monitoring loop: {e}", exc_info=True)
                # При ошибке ждём 10 секунд и продолжаем
                await asyncio.sleep(10)
    
    async def _wait_for_next_wave_check(self):
        """
        Ждать до следующего времени проверки волны (WAVE_CHECK_MINUTES)
        Аналог метода из старого SignalProcessor
        """
        now = datetime.now(timezone.utc)
        current_minute = now.minute
        
        logger.info(f"[DEBUG] _wait_for_next_wave_check: now={now.strftime('%H:%M:%S')}, current_minute={current_minute}")
        
        # Find the next check minute
        next_check_minute = None
        for check_minute in self.wave_check_minutes:
            if current_minute < check_minute:
                next_check_minute = check_minute
                break
        
        logger.info(f"[DEBUG] next_check_minute after loop: {next_check_minute}")
        
        # If no check minute found in current hour, use first one of next hour
        if next_check_minute is None:
            next_check_minute = self.wave_check_minutes[0]
            next_check_time = now.replace(minute=next_check_minute, second=0, microsecond=0)
            next_check_time += timedelta(hours=1)
            logger.info(f"[DEBUG] Using next hour: {next_check_time.strftime('%H:%M:%S')}")
        else:
            next_check_time = now.replace(minute=next_check_minute, second=0, microsecond=0)
            logger.info(f"[DEBUG] Using current hour: {next_check_time.strftime('%H:%M:%S')}")
        
        # Calculate wait time
        wait_seconds = (next_check_time - now).total_seconds()
        
        logger.info(f"[DEBUG] wait_seconds={wait_seconds:.1f}")
        
        if wait_seconds > 0:
            logger.info(f"⏰ Waiting {wait_seconds:.0f}s until next wave check at {next_check_time.strftime('%H:%M UTC')}")
            await asyncio.sleep(wait_seconds)
        else:
            logger.warning(f"⚠️ wait_seconds <= 0: {wait_seconds:.1f}, skipping wait")
    
    def _calculate_expected_wave_timestamp(self) -> str:
        """
        Вычислить timestamp ожидаемой волны (время ОТКРЫТИЯ 15-минутной свечи)

        ⚠️ CRITICAL: DO NOT CHANGE THIS LOGIC WITHOUT EXPLICIT PERMISSION!

        Логика: Сигналы генерируются для 15-минутных свечей и приходят через 5-8 минут.
        Timestamp в сигнале = время ОТКРЫТИЯ свечи (:00, :15, :30, :45).

        Бот проверяет волны начиная с WAVE_CHECK_MINUTES=[6, 20, 35, 50].

        ⚠️ TIME-RANGE BASED MAPPING (verified and tested):
        - Если сейчас 0-15 минут → ждем волну с timestamp :45 (предыдущего часа)
        - Если сейчас 16-30 минут → ждем волну с timestamp :00
        - Если сейчас 31-45 минут → ждем волну с timestamp :15
        - Если сейчас 46-59 минут → ждем волну с timestamp :30

        ⚠️ NO FORMULAS, NO CALCULATIONS - ONLY RANGE CHECKS!

        Примеры:
        - 00:06 (после закрытия свечи 45-00) → ищем timestamp 45 предыдущего часа
        - 00:20 (после закрытия свечи 00-15) → ищем timestamp 00
        - 00:35 (после закрытия свечи 15-30) → ищем timestamp 15
        - 00:50 (после закрытия свечи 30-45) → ищем timestamp 30

        Returns:
            Timestamp волны в формате строки (с 'T' между датой и временем)
        """
        now = datetime.now(timezone.utc)
        current_minute = now.minute

        # ⚠️ CRITICAL: Time-range based mapping - DO NOT MODIFY!
        if 0 <= current_minute <= 15:
            # Ждем волну с timestamp :45 предыдущего часа
            wave_time = now.replace(minute=45, second=0, microsecond=0) - timedelta(hours=1)
        elif 16 <= current_minute <= 30:
            # Ждем волну с timestamp :00 текущего часа
            wave_time = now.replace(minute=0, second=0, microsecond=0)
        elif 31 <= current_minute <= 45:
            # Ждем волну с timestamp :15 текущего часа
            wave_time = now.replace(minute=15, second=0, microsecond=0)
        else:  # 46-59
            # Ждем волну с timestamp :30 текущего часа
            wave_time = now.replace(minute=30, second=0, microsecond=0)

        # VALIDATION: Ensure wave_time is not too far in the past
        # This prevents using stale timestamps after bot restart
        time_diff = now - wave_time
        max_allowed_age = timedelta(hours=2)

        if time_diff > max_allowed_age:
            logger.warning(
                f"⚠️ Calculated wave timestamp is {time_diff.total_seconds()/3600:.1f} hours old! "
                f"Wave: {wave_time.isoformat()}, Now: {now.isoformat()}"
            )

            # Recalculate from current time's 15-minute boundary
            boundary_minute = (current_minute // 15) * 15
            wave_time = now.replace(minute=boundary_minute, second=0, microsecond=0)

            logger.info(
                f"✅ Adjusted wave timestamp to recent boundary: {wave_time.isoformat()}"
            )

        # ✅ Используем .isoformat() для формата с 'T' (как в сигналах от сервера)
        return wave_time.isoformat()
    
    async def _monitor_wave_appearance(self, expected_timestamp: str) -> Optional[List[Dict]]:
        """
        Мониторит появление волны с заданным timestamp
        Запрашивает сигналы каждую секунду до 120 секунд
        
        НОВАЯ ЛОГИКА: 
        1. Извлекает RAW сигналы из buffer WebSocket клиента
        2. Адаптирует их в формат бота через SignalAdapter
        3. Возвращает адаптированные сигналы для обработки
        
        Args:
            expected_timestamp: ISO timestamp ожидаемой волны
            
        Returns:
            List of ADAPTED signals if wave detected, None otherwise
        """
        detection_start = datetime.now(timezone.utc)
        
        logger.info(f"🔍 Monitoring wave appearance for {self.wave_check_duration}s...")
        
        while (datetime.now(timezone.utc) - detection_start).total_seconds() < self.wave_check_duration:
            # Запрашиваем свежие сигналы с сервера
            await self.ws_client.request_signals()
            
            # Даём время на ответ от сервера
            await asyncio.sleep(1)
            
            # Проверяем buffer клиента на наличие RAW сигналов с нужным timestamp
            raw_signals = self.ws_client.get_signals_by_timestamp(expected_timestamp)
            
            if raw_signals:
                logger.info(f"✅ Found {len(raw_signals)} RAW signals for wave {expected_timestamp}")
                
                # Адаптируем в формат бота
                adapted_signals = self.signal_adapter.adapt_signals(raw_signals)
                
                if adapted_signals:
                    logger.info(f"✅ Adapted {len(adapted_signals)} signals to bot format")
                    return adapted_signals
                else:
                    logger.warning(f"No signals after adaptation for wave {expected_timestamp}")
            
            # Ждём перед следующей проверкой
            await asyncio.sleep(self.wave_check_interval)
        
        logger.debug(f"No signals found for wave {expected_timestamp} after {self.wave_check_duration}s")
        return None
    
    async def _on_ws_connect(self):
        """Callback при подключении к WebSocket"""
        logger.info("🔌 WebSocket connected to signal server")
    
    async def _on_ws_disconnect(self):
        """Callback при отключении от WebSocket"""
        logger.warning("⚠️ WebSocket disconnected from signal server")
        self.stats['websocket_reconnections'] += 1
    
    async def _on_ws_error(self, error):
        """Callback при ошибке WebSocket"""
        logger.error(f"❌ WebSocket error: {error}")

    def _group_signals_by_exchange(self, signals: List[Dict]) -> Dict[int, List[Dict]]:
        """
        Group signals by exchange_id

        Args:
            signals: List of signal dicts with exchange_id field

        Returns:
            Dict mapping exchange_id → list of signals for that exchange
            Example: {1: [signal1, signal2], 2: [signal3, signal4]}
        """
        grouped = {}
        for signal in signals:
            exchange_id = signal.get('exchange_id')
            if exchange_id:
                if exchange_id not in grouped:
                    grouped[exchange_id] = []
                grouped[exchange_id].append(signal)
        return grouped

    async def _get_exchange_params(self, exchange_id: int) -> Dict:
        """
        Get parameters for exchange from database with fallback to config

        Args:
            exchange_id: Exchange ID (1=Binance, 2=Bybit)

        Returns:
            Dict with max_trades_filter and other params
            Falls back to config defaults if DB query fails or returns NULL
        """
        try:
            # Query database
            db_params = await self.repository.get_params(exchange_id)

            # If DB has params and max_trades_filter is set, use them
            if db_params and db_params.get('max_trades_filter') is not None:
                return {
                    'max_trades_filter': db_params['max_trades_filter'],
                    'stop_loss_filter': db_params.get('stop_loss_filter'),
                    'trailing_activation_filter': db_params.get('trailing_activation_filter'),
                    'trailing_distance_filter': db_params.get('trailing_distance_filter')
                }

        except Exception as e:
            logger.warning(
                f"Failed to get params for exchange_id={exchange_id} from DB: {e}. "
                f"Falling back to config defaults."
            )

        # Fallback to config defaults
        return {
            'max_trades_filter': self.wave_processor.max_trades_per_wave,
            'stop_loss_filter': None,
            'trailing_activation_filter': None,
            'trailing_distance_filter': None
        }

    async def _get_params_for_exchange(
        self,
        exchange_id: int,
        config_fallback: int = 5
    ) -> Dict[str, Any]:
        """
        Get parameters for specific exchange from monitoring.params

        Args:
            exchange_id: Exchange ID (1=Binance, 2=Bybit)
            config_fallback: Fallback value if DB returns NULL

        Returns:
            Dict with max_trades and buffer_size
            Example: {'max_trades': 6, 'buffer_size': 9, 'source': 'database'}
        """
        exchange_name = 'Binance' if exchange_id == 1 else 'Bybit' if exchange_id == 2 else f'Unknown({exchange_id})'

        try:
            # Query database
            params = await self.repository.get_params(exchange_id=exchange_id)

            if params and params.get('max_trades_filter') is not None:
                max_trades = int(params['max_trades_filter'])
                buffer_size = max_trades + self.config.signal_buffer_fixed

                logger.debug(
                    f"📊 {exchange_name}: max_trades={max_trades} (from DB), buffer={buffer_size} (+3)"
                )

                return {
                    'max_trades': max_trades,
                    'buffer_size': buffer_size,
                    'source': 'database',
                    'exchange_id': exchange_id,
                    'exchange_name': exchange_name
                }
            else:
                # NULL in database - fallback to config
                logger.warning(
                    f"⚠️ {exchange_name}: max_trades_filter is NULL in DB, "
                    f"using config fallback={config_fallback}"
                )

                max_trades = config_fallback
                buffer_size = max_trades + self.config.signal_buffer_fixed

                return {
                    'max_trades': max_trades,
                    'buffer_size': buffer_size,
                    'source': 'config_fallback',
                    'exchange_id': exchange_id,
                    'exchange_name': exchange_name
                }

        except Exception as e:
            # Database error - fallback to config
            logger.error(
                f"❌ {exchange_name}: Failed to query params from DB: {e}",
                exc_info=True
            )
            logger.warning(f"⚠️ Using config fallback={config_fallback}")

            max_trades = config_fallback
            buffer_size = max_trades + self.config.signal_buffer_fixed

            return {
                'max_trades': max_trades,
                'buffer_size': buffer_size,
                'source': 'config_error_fallback',
                'exchange_id': exchange_id,
                'exchange_name': exchange_name,
                'error': str(e)
            }

    async def _get_params_for_all_exchanges(self) -> Dict[int, Dict[str, Any]]:
        """
        Get parameters for all exchanges (Binance and Bybit)

        Returns:
            Dict mapping exchange_id to params
            Example: {
                1: {'max_trades': 6, 'buffer_size': 9, 'source': 'database'},
                2: {'max_trades': 4, 'buffer_size': 7, 'source': 'database'}
            }
        """
        config_fallback = self.wave_processor.max_trades_per_wave  # Use config default

        logger.debug(f"Querying params for all exchanges (fallback={config_fallback})")

        # Query both exchanges in parallel
        binance_params_task = self._get_params_for_exchange(exchange_id=1, config_fallback=config_fallback)
        bybit_params_task = self._get_params_for_exchange(exchange_id=2, config_fallback=config_fallback)

        binance_params, bybit_params = await asyncio.gather(
            binance_params_task,
            bybit_params_task,
            return_exceptions=True
        )

        # Handle exceptions
        params_by_exchange = {}

        if isinstance(binance_params, Exception):
            logger.error(f"Failed to get Binance params: {binance_params}")
            # Create fallback
            params_by_exchange[1] = {
                'max_trades': config_fallback,
                'buffer_size': config_fallback + self.config.signal_buffer_fixed,
                'source': 'exception_fallback',
                'exchange_id': 1,
                'exchange_name': 'Binance'
            }
        else:
            params_by_exchange[1] = binance_params

        if isinstance(bybit_params, Exception):
            logger.error(f"Failed to get Bybit params: {bybit_params}")
            # Create fallback
            params_by_exchange[2] = {
                'max_trades': config_fallback,
                'buffer_size': config_fallback + self.config.signal_buffer_fixed,
                'source': 'exception_fallback',
                'exchange_id': 2,
                'exchange_name': 'Bybit'
            }
        else:
            params_by_exchange[2] = bybit_params

        logger.info(
            f"📊 Params loaded: Binance max_trades={params_by_exchange[1]['max_trades']} "
            f"(source: {params_by_exchange[1]['source']}), "
            f"Bybit max_trades={params_by_exchange[2]['max_trades']} "
            f"(source: {params_by_exchange[2]['source']})"
        )

        return params_by_exchange

    async def _execute_signals_for_exchange(
        self,
        validated_signals: List[Dict],
        max_trades: int,
        exchange_name: str
    ) -> Dict[str, Any]:
        """
        Execute signals for one exchange with target-based stopping

        CRITICAL: Stops execution when executed_count >= max_trades
        This is the buffer logic - we have extra signals but stop at target

        Args:
            validated_signals: Signals that passed validation
            max_trades: Target number of positions (e.g., 6 for Binance)
            exchange_name: Exchange name for logging

        Returns:
            Dict with execution results
        """
        executed_count = 0
        failed_count = 0
        execution_details = []

        logger.info(
            f"{exchange_name}: Starting execution of {len(validated_signals)} validated signals "
            f"(target: {max_trades} positions)"
        )

        for idx, signal_result in enumerate(validated_signals):
            # CRITICAL: Stop when target reached
            if executed_count >= max_trades:
                logger.info(
                    f"✅ {exchange_name}: Target reached {executed_count}/{max_trades} positions, "
                    f"stopping execution ({len(validated_signals) - idx} signals unused from buffer)"
                )
                break

            # Extract signal
            signal = signal_result.get('signal_data')
            if not signal:
                logger.warning(f"{exchange_name}: Signal #{idx+1} has no signal_data, skipping")
                failed_count += 1
                execution_details.append({
                    'index': idx + 1,
                    'symbol': 'UNKNOWN',
                    'result': 'no_data',
                    'executed': False
                })
                continue

            symbol = signal.get('symbol', 'UNKNOWN')
            logger.info(
                f"📈 {exchange_name}: Executing signal {idx+1}/{len(validated_signals)}: {symbol} "
                f"(opened: {executed_count}/{max_trades})"
            )

            # Execute signal
            try:
                success = await self._execute_signal(signal)

                if success:
                    executed_count += 1
                    logger.info(
                        f"✅ {exchange_name}: Signal {idx+1} ({symbol}) executed "
                        f"(total: {executed_count}/{max_trades})"
                    )
                    execution_details.append({
                        'index': idx + 1,
                        'symbol': symbol,
                        'result': 'success',
                        'executed': True
                    })
                else:
                    failed_count += 1
                    logger.warning(
                        f"❌ {exchange_name}: Signal {idx+1} ({symbol}) failed "
                        f"(total: {executed_count}/{max_trades})"
                    )
                    execution_details.append({
                        'index': idx + 1,
                        'symbol': symbol,
                        'result': 'failed',
                        'executed': False
                    })

            except Exception as e:
                failed_count += 1
                logger.error(
                    f"❌ {exchange_name}: Error executing signal {symbol}: {e}",
                    exc_info=True
                )
                execution_details.append({
                    'index': idx + 1,
                    'symbol': symbol,
                    'result': 'exception',
                    'error': str(e),
                    'executed': False
                })

            # Delay between signals (rate limiting)
            if idx < len(validated_signals) - 1 and executed_count < max_trades:
                await asyncio.sleep(1)

        # Buffer effectiveness
        buffer_used = executed_count < len(validated_signals)
        buffer_saved_us = buffer_used and executed_count == max_trades

        logger.info(
            f"🎯 {exchange_name}: Execution complete - "
            f"{executed_count} positions opened, {failed_count} failed "
            f"(buffer {'saved us' if buffer_saved_us else 'not needed' if not buffer_used else 'helped'})"
        )

        return {
            'executed_count': executed_count,
            'failed_count': failed_count,
            'target': max_trades,
            'target_reached': executed_count >= max_trades,
            'buffer_used': buffer_used,
            'buffer_saved_us': buffer_saved_us,
            'execution_details': execution_details
        }

    async def _process_wave_per_exchange(
        self,
        wave_signals: List[Dict],
        wave_timestamp: str,
        params_by_exchange: Dict[int, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Process wave signals with per-exchange logic

        Uses WaveSignalProcessor for filtering and validation:
        1. Sort signals by combined score
        2. Select top signals with buffer
        3. Apply filters (OI, volume, duplicates) via WaveSignalProcessor
        4. Execute validated signals until target reached

        Args:
            wave_signals: All signals in wave
            wave_timestamp: Wave timestamp
            params_by_exchange: Params for each exchange from DB

        Returns:
            Dict with results per exchange and totals
        """
        logger.info(f"🌊 Processing wave {wave_timestamp} with WaveSignalProcessor")

        # Group signals by exchange
        signals_by_exchange = self._group_signals_by_exchange(wave_signals)

        # Process each exchange separately
        results_by_exchange = {}
        total_executed = 0
        total_failed = 0
        total_validated = 0

        for exchange_id, exchange_signals in signals_by_exchange.items():
            exchange_name = 'binance' if exchange_id == 1 else 'bybit'
            exchange_name_cap = 'Binance' if exchange_id == 1 else 'Bybit'
            params = params_by_exchange.get(exchange_id, {})

            # Get target and buffer
            max_trades = params.get('max_trades', 5)
            buffer_size = params.get('buffer_size', max_trades + 5)

            # 1. Применяем фильтры ко ВСЕМ сигналам
            logger.info(f"{exchange_name_cap}: Applying filters to {len(exchange_signals)} signals")

            filter_result = await self.wave_processor.process_wave_signals(
                signals=exchange_signals,  # ВСЕ сигналы
                wave_timestamp=wave_timestamp,
                mode='filter'  # Только фильтрация, без side effects
            )

            # 2. Извлекаем прошедшие фильтры
            filtered_signals = [
                s['signal_data'] for s in filter_result.get('successful', [])
            ]

            # 3. Собираем статистику фильтрации
            filter_stats = {
                'total': len(exchange_signals),
                'passed': len(filtered_signals),
                'filtered': len(filter_result.get('skipped', [])),
                'failed': len(filter_result.get('failed', []))
            }

            # Детализация по причинам
            skipped = filter_result.get('skipped', [])
            filter_reasons = {
                'duplicates': len([s for s in skipped if 'already exists' in s.get('reason', '').lower()]),
                'low_oi': len([s for s in skipped if 'oi' in s.get('reason', '').lower()]),
                'low_volume': len([s for s in skipped if 'volume' in s.get('reason', '').lower()]),
                'price_change': len([s for s in skipped if 'price' in s.get('reason', '').lower() and 'oi' not in s.get('reason', '').lower()])
            }

            logger.info(
                f"{exchange_name_cap}: Filtered {filter_stats['filtered']}/{filter_stats['total']} "
                f"(Dup:{filter_reasons['duplicates']}, OI:{filter_reasons['low_oi']}, "
                f"Vol:{filter_reasons['low_volume']}, Price:{filter_reasons['price_change']})"
            )

            # 4. Проверка: есть ли сигналы после фильтрации
            if not filtered_signals:
                logger.warning(f"⚠️ {exchange_name_cap}: All signals filtered out!")
                results_by_exchange[exchange_id] = {
                    'exchange_name': exchange_name_cap,
                    'executed': 0,
                    'target': max_trades,
                    'total_signals': len(exchange_signals),
                    'filtered': filter_stats['filtered'],
                    'no_signals_after_filter': True
                }
                continue

            # Edge case: недостаточно сигналов после фильтрации
            if len(filtered_signals) < max_trades:
                logger.warning(
                    f"⚠️ {exchange_name_cap}: Only {len(filtered_signals)} signals passed filters, "
                    f"target was {max_trades}. Will open max possible positions."
                )

            # 5. Сортируем ОТФИЛЬТРОВАННЫЕ по score
            sorted_filtered = sorted(
                filtered_signals,
                key=lambda s: (s.get('score_week', 0) + s.get('score_month', 0)),
                reverse=True
            )

            # 6. Выбираем топ N для исполнения
            # Берём немного больше target для компенсации возможных ошибок исполнения
            execution_buffer = min(3, len(sorted_filtered) - max_trades) if len(sorted_filtered) > max_trades else 0
            signals_to_execute = sorted_filtered[:max_trades + execution_buffer]

            logger.info(
                f"{exchange_name_cap}: Selected top {len(signals_to_execute)} from {len(filtered_signals)} "
                f"filtered signals (target: {max_trades})"
            )

            # 7. Полная обработка выбранных сигналов
            process_result = await self.wave_processor.process_wave_signals(
                signals=signals_to_execute,
                wave_timestamp=wave_timestamp,
                mode='process'  # Полная обработка с записью в БД
            )

            # Execute successful signals until target reached
            executed = 0
            failed = 0

            for signal_result in process_result.get('successful', []):
                if executed >= max_trades:
                    logger.info(f"✅ {exchange_name_cap}: Target {max_trades} reached, stopping")
                    break

                signal_data = signal_result.get('signal_data')
                if signal_data:
                    # Open position using PositionManager
                    try:
                        from core.position_manager import PositionRequest

                        # Create position request
                        from decimal import Decimal

                        # Get signal direction - CRITICAL: must be explicit
                        side = signal_data.get('signal_type') or signal_data.get('recommended_action') or signal_data.get('action')
                        if not side:
                            logger.error(f"❌ Signal has no direction/side field: {signal_data}")
                            failed += 1
                            continue  # Skip this signal - cannot open position without direction

                        # Normalize side to BUY/SELL
                        side = side.upper()
                        if side not in ['BUY', 'SELL', 'LONG', 'SHORT']:
                            logger.error(f"❌ Unknown signal direction: {side} for signal: {signal_data}")
                            failed += 1
                            continue

                        # Convert LONG/SHORT to BUY/SELL
                        if side == 'LONG':
                            side = 'BUY'
                        elif side == 'SHORT':
                            side = 'SELL'

                        # Get symbol and exchange
                        symbol = signal_data.get('symbol', signal_data.get('pair_symbol'))
                        exchange_name = signal_data.get('exchange', signal_data.get('exchange_name'))

                        # Get entry price - CRITICAL: must be > 0
                        entry_price_raw = signal_data.get('entry_price') or signal_data.get('price')

                        if entry_price_raw and float(entry_price_raw) > 0:
                            entry_price = Decimal(str(entry_price_raw))
                        else:
                            # No valid price in signal - fetch current market price
                            logger.warning(f"⚠️ Signal {signal_data.get('id')} has no valid entry_price, fetching current market price")

                            try:
                                exchange_manager = self.position_manager.exchanges.get(exchange_name)
                                if exchange_manager:
                                    ticker = await exchange_manager.fetch_ticker(symbol)
                                    current_price = ticker.get('last') or ticker.get('close')
                                    if current_price and float(current_price) > 0:
                                        entry_price = Decimal(str(current_price))
                                        logger.info(f"Using current market price: {entry_price} for {symbol}")
                                    else:
                                        logger.error(f"❌ Cannot get valid market price for {symbol}: {ticker}")
                                        failed += 1
                                        continue
                                else:
                                    logger.error(f"❌ Exchange {exchange_name} not available to fetch price")
                                    failed += 1
                                    continue
                            except Exception as e:
                                logger.error(f"❌ Error fetching market price for {symbol}: {e}")
                                failed += 1
                                continue

                        # Final validation - price must be positive
                        if entry_price <= 0:
                            logger.error(f"❌ Invalid entry price {entry_price} for signal {signal_data.get('id')}")
                            failed += 1
                            continue

                        position_request = PositionRequest(
                            signal_id=signal_data.get('id') or signal_data.get('signal_id'),
                            symbol=symbol,
                            exchange=exchange_name,
                            side=side,
                            entry_price=entry_price
                        )

                        # Open position
                        result = await self.position_manager.open_position(position_request)

                        if result and not isinstance(result, dict):
                            executed += 1
                            logger.info(f"✅ Opened position for {position_request.symbol}")
                        else:
                            failed += 1
                            if isinstance(result, dict):
                                logger.warning(f"Failed to open position: {result.get('error', 'Unknown error')}")

                    except Exception as e:
                        logger.error(f"Error executing signal: {e}")
                        failed += 1

            # Статистика уже собрана в filter_reasons из filter phase
            results_by_exchange[exchange_id] = {
                'exchange_name': exchange_name_cap,
                'executed': executed,
                'target': max_trades,
                'buffer_size': buffer_size,
                'total_signals': len(exchange_signals),
                'after_filters': len(filtered_signals),  # NEW
                'selected_for_execution': len(signals_to_execute),  # RENAMED
                'validated_successful': len(process_result.get('successful', [])),
                'duplicates': filter_reasons['duplicates'],  # FROM filter phase
                'filtered': filter_stats['filtered'],
                'filtered_oi': filter_reasons['low_oi'],
                'filtered_volume': filter_reasons['low_volume'],
                'filtered_price': filter_reasons['price_change'],  # NEW
                'failed': failed + len(process_result.get('failed', [])),
                'target_reached': executed >= max_trades,
                'buffer_saved_us': executed == max_trades and len(process_result.get('successful', [])) > max_trades,
                'params_source': params.get('source', 'unknown')
            }

            total_executed += executed
            total_failed += failed + len(process_result.get('failed', []))
            total_validated += len(process_result.get('successful', []))

            logger.info(
                f"{exchange_name_cap}: Executed {executed}/{max_trades}, "
                f"filtered: {filter_stats['filtered']} "
                f"(OI: {filter_reasons['low_oi']}, Vol: {filter_reasons['low_volume']}, "
                f"Dup: {filter_reasons['duplicates']}, Price: {filter_reasons['price_change']})"
            )

        # Return final results in expected format
        return {
            'results_by_exchange': results_by_exchange,
            'total_executed': total_executed,
            'total_failed': total_failed,
            'total_validated': total_validated,
            'duplicates': sum(r['duplicates'] for r in results_by_exchange.values())
        }

    async def _execute_signal(self, signal: Dict) -> bool:
        """
        Execute signal: validate and open position
        Adapted from old signal_processor.py::_process_signal()
        
        Args:
            signal: Signal dict with all necessary data
            
        Returns:
            bool: True if position opened successfully, False otherwise
        """
        signal_id = signal.get('id')  # None if not present
        
        try:
            # Check if action is present
            if not signal.get('action'):
                logger.warning(f"Signal #{signal_id} has no action field, skipping")
                return False

            # Validate signal data using pydantic
            try:
                validated_signal = validate_signal(signal)
                if not validated_signal:
                    logger.warning(f"Signal #{signal_id} failed validation")

                    # FIX BUG #1: Log validation failure in background (non-blocking)
                    event_logger = get_event_logger()
                    if event_logger:
                        asyncio.create_task(
                            event_logger.log_event(
                                EventType.SIGNAL_VALIDATION_FAILED,
                                {
                                    'signal_id': signal_id,
                                    'reason': 'validation_returned_none',
                                    'signal_data': signal
                                },
                                severity='WARNING'
                            )
                        )

                    return False
            except Exception as e:
                logger.error(f"Error validating signal #{signal_id}: {e}")

                # FIX BUG #1: Log validation error in background (non-blocking)
                event_logger = get_event_logger()
                if event_logger:
                    asyncio.create_task(
                        event_logger.log_event(
                            EventType.SIGNAL_VALIDATION_FAILED,
                            {
                                'signal_id': signal_id,
                                'reason': 'validation_exception',
                                'error': str(e)
                            },
                            severity='ERROR'
                        )
                    )

                return False
            
            symbol = validated_signal.symbol
            exchange = validated_signal.exchange
            
            # ✅ FIX: Check symbol filter (stop-list) BEFORE proceeding
            is_allowed, reason = self.symbol_filter.is_symbol_allowed(symbol)
            if not is_allowed:
                logger.info(
                    f"⏸️ Signal #{signal_id} skipped: {symbol} is blocked ({reason})"
                )

                # FIX BUG #1: Log signal filtered in background (non-blocking)
                event_logger = get_event_logger()
                if event_logger:
                    asyncio.create_task(
                        event_logger.log_event(
                            EventType.SIGNAL_FILTERED,
                            {
                                'signal_id': signal_id,
                                'symbol': symbol,
                                'exchange': exchange,
                                'filter_reason': reason
                            },
                            symbol=symbol,
                            exchange=exchange,
                            severity='INFO'
                        )
                    )

                return False
            
            logger.info(
                f"Executing signal #{signal_id}: {symbol} on {exchange} "
                f"(week: {validated_signal.score_week}, month: {validated_signal.score_month})"
            )

            # Get exchange manager
            exchange_manager = self.position_manager.exchanges.get(exchange)
            if not exchange_manager:
                logger.error(f"Exchange {exchange} not available")
                return False

            # Get current price
            ticker = await exchange_manager.fetch_ticker(symbol)
            if not ticker:
                # MINIMAL FIX: Changed from error to info - symbol might not exist on exchange
                logger.info(f"Symbol {symbol} not available on {exchange}, skipping")
                return False

            # FIX: Handle Binance returning ticker with last=None during low-liquidity
            # Try 'last' first, fallback to 'close', then retry if both None
            current_price = ticker.get('last') or ticker.get('close', 0)

            if not current_price or current_price <= 0:
                # Retry up to 2 times with fresh fetch (bypass cache)
                MAX_PRICE_RETRIES = 2
                PRICE_RETRY_DELAY = 2.0

                for attempt in range(MAX_PRICE_RETRIES):
                    logger.warning(
                        f"Invalid price for {symbol}: {current_price}, "
                        f"retrying {attempt + 1}/{MAX_PRICE_RETRIES}..."
                    )
                    await asyncio.sleep(PRICE_RETRY_DELAY)

                    ticker = await exchange_manager.fetch_ticker(symbol, use_cache=False)
                    if ticker:
                        current_price = ticker.get('last') or ticker.get('close', 0)
                        if current_price and current_price > 0:
                            logger.info(f"✅ Got valid price for {symbol} on retry: {current_price}")
                            break

                # Final check after retries
                if not current_price or current_price <= 0:
                    logger.error(f"Invalid price for {symbol} after {MAX_PRICE_RETRIES} retries: {current_price}")
                    return False

            # Determine side (PositionRequest expects 'BUY' or 'SELL')
            if validated_signal.action in [OrderSide.BUY, OrderSide.LONG]:
                side = 'BUY'
            elif validated_signal.action in [OrderSide.SELL, OrderSide.SHORT]:
                side = 'SELL'
            else:
                logger.error(f"Invalid signal action: {validated_signal.action}")
                return False
            
            # Create position request (dataclass from position_manager)
            from core.position_manager import PositionRequest
            
            request = PositionRequest(
                signal_id=signal_id,
                symbol=validated_signal.symbol,
                exchange=validated_signal.exchange,
                side=side,
                entry_price=Decimal(str(current_price))
            )

            # Execute position opening
            position = await self.position_manager.open_position(request)

            if position:
                logger.info(f"✅ Signal #{signal_id} ({symbol}) executed successfully")

                # FIX BUG #1: Log signal execution success in background (non-blocking)
                event_logger = get_event_logger()
                if event_logger:
                    asyncio.create_task(
                        event_logger.log_event(
                            EventType.SIGNAL_EXECUTED,
                            {
                                'signal_id': signal_id,
                                'symbol': symbol,
                                'exchange': exchange,
                                'side': side,
                                'entry_price': float(current_price),
                                'position_id': position.id if hasattr(position, 'id') else None,
                                'score_week': validated_signal.score_week,
                                'score_month': validated_signal.score_month
                            },
                            symbol=symbol,
                            exchange=exchange,
                            severity='INFO'
                        )
                    )

                return True
            else:
                logger.warning(f"❌ Signal #{signal_id} ({symbol}) - position_manager returned None")

                # FIX BUG #1: Log signal execution failure in background (non-blocking)
                event_logger = get_event_logger()
                if event_logger:
                    asyncio.create_task(
                        event_logger.log_event(
                            EventType.SIGNAL_EXECUTION_FAILED,
                            {
                                'signal_id': signal_id,
                                'symbol': symbol,
                                'exchange': exchange,
                                'side': side,
                                'reason': 'position_manager_returned_none',
                                'entry_price': float(current_price)
                            },
                            symbol=symbol,
                            exchange=exchange,
                            severity='WARNING'
                        )
                    )

                return False

        except Exception as e:
            logger.error(f"❌ Error executing signal #{signal_id}: {e}", exc_info=True)
            return False

    async def _update_exchange_params(self, wave_signals: List[Dict], wave_timestamp: str):
        """
        Update monitoring.params from first signal per exchange in wave

        Extracts filter parameters from:
        - First Binance signal (exchange_id=1) → UPDATE exchange_id=1
        - First Bybit signal (exchange_id=2) → UPDATE exchange_id=2

        Runs asynchronously to avoid blocking wave processing.

        Args:
            wave_signals: List of adapted signals with filter_params
            wave_timestamp: Wave timestamp for logging
        """
        if not wave_signals:
            return

        try:
            # Group signals by exchange_id
            signals_by_exchange = {}
            for signal in wave_signals:
                exchange_id = signal.get('exchange_id')
                if exchange_id and exchange_id not in signals_by_exchange:
                    # Take first signal per exchange
                    signals_by_exchange[exchange_id] = signal

            logger.debug(
                f"Found {len(signals_by_exchange)} unique exchanges in wave {wave_timestamp}: "
                f"{list(signals_by_exchange.keys())}"
            )

            # Update params for each exchange
            update_tasks = []
            for exchange_id, signal in signals_by_exchange.items():
                filter_params = signal.get('filter_params')

                if filter_params:
                    logger.info(
                        f"📊 Updating params for exchange_id={exchange_id} from signal #{signal.get('id')}: "
                        f"{filter_params}"
                    )

                    # Create update task (non-blocking)
                    task = self._update_params_for_exchange(exchange_id, filter_params, wave_timestamp)
                    update_tasks.append(task)
                else:
                    logger.debug(
                        f"No filter_params in signal #{signal.get('id')} for exchange_id={exchange_id}"
                    )

            # Execute all updates in parallel (non-blocking)
            if update_tasks:
                await asyncio.gather(*update_tasks, return_exceptions=True)

        except Exception as e:
            # CRITICAL: Catch all exceptions to prevent breaking wave processing
            logger.error(f"Error updating exchange params for wave {wave_timestamp}: {e}", exc_info=True)

    async def _update_params_for_exchange(
        self,
        exchange_id: int,
        filter_params: Dict,
        wave_timestamp: str
    ):
        """
        Update monitoring.params for specific exchange

        Args:
            exchange_id: Exchange ID (1=Binance, 2=Bybit)
            filter_params: Filter parameters dict
            wave_timestamp: Wave timestamp for logging
        """
        try:
            # Update database
            success = await self.repository.update_params(
                exchange_id=exchange_id,
                max_trades_filter=filter_params.get('max_trades_filter'),
                stop_loss_filter=filter_params.get('stop_loss_filter'),
                trailing_activation_filter=filter_params.get('trailing_activation_filter'),
                trailing_distance_filter=filter_params.get('trailing_distance_filter')
            )

            if success:
                logger.info(
                    f"✅ Params updated for exchange_id={exchange_id} at wave {wave_timestamp}"
                )
            else:
                logger.warning(
                    f"⚠️ Failed to update params for exchange_id={exchange_id} at wave {wave_timestamp}"
                )

        except Exception as e:
            logger.error(
                f"Error updating params for exchange_id={exchange_id}: {e}",
                exc_info=True
            )

    def get_stats(self) -> Dict:
        """Get processor statistics"""
        return {
            **self.stats,
            'websocket': self.ws_client.get_stats(),
            'buffer_size': len(self.ws_client.signal_buffer),
            'processed_waves_count': len(self.processed_waves)
        }