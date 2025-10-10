"""
WebSocket Signal Processor - Миграция с PostgreSQL polling на WebSocket stream
Реализует ту же логику мониторинга волн что и старый SignalProcessor
"""
import logging
import asyncio
import os
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from websocket.signal_client import SignalWebSocketClient
from websocket.signal_adapter import SignalAdapter
from core.wave_signal_processor import WaveSignalProcessor
from core.symbol_filter import SymbolFilter
from models.validation import validate_signal, OrderSide

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

                    # Update wave metadata
                    self.processed_waves[expected_wave_timestamp].update({
                        'status': 'executing',
                        'signal_ids': set(s.get('id') for s in wave_signals),
                        'count': len(wave_signals),
                        'first_seen': datetime.now(timezone.utc)
                    })
                    self.stats['waves_detected'] += 1
                    self.stats['current_wave'] = expected_wave_timestamp
                    
                    # Calculate buffer size (signals already sorted by score_week)
                    max_trades = self.wave_processor.max_trades_per_wave
                    buffer_percent = self.wave_processor.buffer_percent
                    buffer_size = int(max_trades * (1 + buffer_percent / 100))
                    
                    # Take only top signals with buffer
                    signals_to_process = wave_signals[:buffer_size]
                    
                    logger.info(
                        f"📊 Wave {expected_wave_timestamp}: {len(wave_signals)} total signals, "
                        f"processing top {len(signals_to_process)} (max={max_trades} +{buffer_percent}% buffer)"
                    )
                    
                    # Validate signals
                    result = await self.wave_processor.process_wave_signals(
                        signals=signals_to_process,
                        wave_timestamp=expected_wave_timestamp
                    )
                    
                    # Get successful after validation
                    final_signals = result.get('successful', [])
                    
                    # If not enough successful - try more from remaining
                    if len(final_signals) < max_trades and len(wave_signals) > buffer_size:
                        remaining_needed = max_trades - len(final_signals)
                        extra_size = int(remaining_needed * 1.5)  # +50% для запаса
                        
                        logger.info(
                            f"⚠️ Only {len(final_signals)}/{max_trades} successful, "
                            f"processing {extra_size} more signals"
                        )
                        
                        next_batch = wave_signals[buffer_size : buffer_size + extra_size]
                        extra_result = await self.wave_processor.process_wave_signals(
                            next_batch, 
                            expected_wave_timestamp
                        )
                        extra_successful = extra_result.get('successful', [])
                        final_signals.extend(extra_successful[:remaining_needed])
                    
                    logger.info(
                        f"✅ Wave {expected_wave_timestamp} validated: "
                        f"{len(final_signals)} signals with buffer (target: {max_trades} positions)"
                    )
                    
                    # EXECUTE: Open positions with buffer logic
                    # Continue trying signals until we open max_trades positions or run out of signals
                    executed_count = 0
                    failed_count = 0
                    
                    for idx, signal_result in enumerate(final_signals):
                        if not self.running:
                            break
                        
                        # CRITICAL: Stop when we have enough successful positions
                        if executed_count >= max_trades:
                            logger.info(f"✅ Target reached: {executed_count}/{max_trades} positions opened, stopping execution")
                            break
                        
                        # Extract original signal
                        signal = signal_result.get('signal_data')
                        if not signal:
                            logger.warning(f"Signal #{idx+1} has no signal_data, skipping")
                            failed_count += 1
                            continue
                        
                        symbol = signal.get('symbol', 'UNKNOWN')
                        logger.info(f"📈 Executing signal {idx+1}/{len(final_signals)}: {symbol} (opened: {executed_count}/{max_trades})")
                        
                        # Open position
                        try:
                            success = await self._execute_signal(signal)
                            if success:
                                executed_count += 1
                                logger.info(f"✅ Signal {idx+1}/{len(final_signals)} ({symbol}) executed")
                            else:
                                failed_count += 1
                                logger.warning(f"❌ Signal {idx+1}/{len(final_signals)} ({symbol}) failed")
                        except Exception as e:
                            failed_count += 1
                            logger.error(f"❌ Error executing signal {symbol}: {e}", exc_info=True)
                        
                        # Delay between signals
                        if idx < len(final_signals) - 1:
                            await asyncio.sleep(1)
                    
                    # Update stats
                    self.stats['waves_processed'] += 1
                    self.stats['signals_processed'] += executed_count
                    
                    logger.info(
                        f"🎯 Wave {expected_wave_timestamp} complete: "
                        f"{executed_count} positions opened, {failed_count} failed, "
                        f"{len(result.get('failed', []))} validation errors, "
                        f"{len(result.get('skipped', []))} duplicates"
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
        Вычислить timestamp ожидаемой волны
        
        Логика: Волна появляется на сервере через ~20 минут после своего timestamp.
        Бот проверяет в минуты WAVE_CHECK_MINUTES (например, [6, 20, 35, 50]).
        Нужно вернуть timestamp волны, которая должна появиться СЕЙЧАС.
        
        Для WAVE_CHECK_MINUTES=[6, 20, 35, 50]:
        - Проверка в 06 минут → ищем волну timestamp 45 (предыдущего часа)
        - Проверка в 20 минут → ищем волну timestamp 00
        - Проверка в 35 минут → ищем волну timestamp 15
        - Проверка в 50 минут → ищем волну timestamp 30
        
        Общая формула: wave_timestamp = current_check_minute - 20 минут
        
        Returns:
            Timestamp волны в формате строки (с 'T' между датой и временем)
        """
        now = datetime.now(timezone.utc)
        current_minute = now.minute
        
        # Найти ближайшую предыдущую check_minute (на которой мы сейчас)
        current_check_minute = None
        for check_minute in sorted(self.wave_check_minutes, reverse=True):
            if current_minute >= check_minute:
                current_check_minute = check_minute
                break
        
        # Если не нашли (current_minute < самой маленькой check_minute), значит мы в начале часа
        # и проверяем волну из предыдущего часа
        if current_check_minute is None:
            current_check_minute = self.wave_check_minutes[-1]  # Последняя check_minute предыдущего часа
            wave_time = now.replace(minute=current_check_minute, second=0, microsecond=0) - timedelta(hours=1, minutes=20)
        else:
            # Вычитаем 20 минут от текущей check_minute
            wave_time = now.replace(minute=current_check_minute, second=0, microsecond=0) - timedelta(minutes=20)
        
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
    
    async def _execute_signal(self, signal: Dict) -> bool:
        """
        Execute signal: validate and open position
        Adapted from old signal_processor.py::_process_signal()
        
        Args:
            signal: Signal dict with all necessary data
            
        Returns:
            bool: True if position opened successfully, False otherwise
        """
        signal_id = signal.get('id', 'unknown')
        
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
                    return False
            except Exception as e:
                logger.error(f"Error validating signal #{signal_id}: {e}")
                return False
            
            symbol = validated_signal.symbol
            exchange = validated_signal.exchange
            
            # ✅ FIX: Check symbol filter (stop-list) BEFORE proceeding
            is_allowed, reason = self.symbol_filter.is_symbol_allowed(symbol)
            if not is_allowed:
                logger.info(
                    f"⏸️ Signal #{signal_id} skipped: {symbol} is blocked ({reason})"
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
                logger.error(f"Cannot get ticker for {symbol}")
                return False

            current_price = ticker.get('last', 0)
            if current_price is None or current_price <= 0:
                logger.error(f"Invalid price for {symbol}: {current_price}")
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
                return True
            else:
                logger.warning(f"❌ Signal #{signal_id} ({symbol}) - position_manager returned None")
                return False

        except Exception as e:
            logger.error(f"❌ Error executing signal #{signal_id}: {e}", exc_info=True)
            return False
    
    def get_stats(self) -> Dict:
        """Get processor statistics"""
        return {
            **self.stats,
            'websocket': self.ws_client.get_stats(),
            'buffer_size': len(self.ws_client.signal_buffer),
            'processed_waves_count': len(self.processed_waves)
        }