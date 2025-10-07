import asyncio
import logging
import os
from typing import Dict, List, Optional
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from config.settings import TradingConfig
from database.repository import Repository as TradingRepository
from core.position_manager import PositionManager, PositionRequest
from core.wave_signal_processor import WaveSignalProcessor
from core.symbol_filter import SymbolFilter
from websocket.event_router import EventRouter
from models.validation import TradingSignal, validate_signal, OrderSide

logger = logging.getLogger(__name__)


class SignalProcessor:
    """
    Process trading signals from database
    Handles signal filtering, validation, and execution
    
    TEST_MODE support:
    - Set TEST_MODE=true in environment to read from test.scoring_history
    - Uses fas.scoring_history by default (production)
    """

    def __init__(self,
                 config: TradingConfig,
                 repository: TradingRepository,
                 position_manager: PositionManager,
                 event_router: EventRouter):
        """Initialize signal processor"""
        self.config = config
        self.repository = repository
        self.position_manager = position_manager
        self.event_router = event_router
        
        # TEST MODE support: Read from test.scoring_history instead of fas.scoring_history
        self.test_mode = os.getenv('TEST_MODE', 'false').lower() in ('true', '1', 'yes')
        self.signal_table = 'test.scoring_history' if self.test_mode else 'fas.scoring_history'
        
        if self.test_mode:
            logger.warning("="*80)
            logger.warning("🧪 TEST MODE ENABLED - Reading signals from test.scoring_history")
            logger.warning("="*80)
        
        # Wave processor for duplicate handling
        self.wave_processor = WaveSignalProcessor(config, position_manager)

        # Symbol filter for centralized filtering
        self.symbol_filter = SymbolFilter(config)

        # Processing state
        self.processing_signals = set()
        self.failed_signals = set()
        self.stop_list = set()  # Keep for backward compatibility, but use symbol_filter
        self.processed_waves = {}  # Track signals per wave {timestamp: {signal_ids, count, first_seen}}

        # Wave timing configuration from environment variables
        # All defaults configured in .env file - NO MAGIC NUMBERS IN CODE!
        wave_minutes_str = os.getenv('WAVE_CHECK_MINUTES')
        if not wave_minutes_str:
            raise ValueError("WAVE_CHECK_MINUTES must be set in .env file")
        self.wave_check_minutes = sorted([int(m.strip()) for m in wave_minutes_str.split(',')])  # CRITICAL: Sort for correct next-wave logic
        
        wave_duration = os.getenv('WAVE_CHECK_DURATION_SECONDS')
        if not wave_duration:
            raise ValueError("WAVE_CHECK_DURATION_SECONDS must be set in .env file")
        self.wave_check_duration = int(wave_duration)
        
        wave_interval = os.getenv('WAVE_CHECK_INTERVAL_SECONDS')
        if not wave_interval:
            raise ValueError("WAVE_CHECK_INTERVAL_SECONDS must be set in .env file")
        self.wave_check_interval = int(wave_interval)

        # Signal processing limits
        self.signal_time_window = config.signal_time_window_minutes
        self.max_trades_per_window = config.max_trades_per_15min
        
        wave_cleanup = os.getenv('WAVE_CLEANUP_HOURS')
        if not wave_cleanup:
            raise ValueError("WAVE_CLEANUP_HOURS must be set in .env file")
        self.wave_cleanup_hours = int(wave_cleanup)

        # Statistics
        self.stats = {
            'signals_received': 0,
            'signals_processed': 0,
            'signals_executed': 0,
            'signals_rejected': 0,
            'signals_failed': 0,
            'last_check': None,
            'waves_detected': 0,
            'current_wave': None
        }

        # Running state
        self.running = False
        self._process_task = None

        logger.info(f"SignalProcessor initialized with wave checks at minutes: {self.wave_check_minutes}")

    def add_to_stop_list(self, symbols: List[str]):
        """Add symbols to stop list - now uses SymbolFilter"""
        # Keep backward compatibility
        self.stop_list.update(symbols)
        # Also add to symbol filter
        self.symbol_filter.add_to_stoplist(symbols)
        logger.info(f"Added {len(symbols)} symbols to stop list")

    async def start(self):
        """Start signal processing loop"""
        if self.running:
            logger.warning("SignalProcessor already running")
            return

        self.running = True
        self._process_task = asyncio.create_task(self._process_loop())
        logger.info("SignalProcessor started")

    async def stop(self):
        """Stop signal processing"""
        self.running = False

        if self._process_task:
            self._process_task.cancel()
            try:
                await self._process_task
            except asyncio.CancelledError:
                pass

        logger.info("SignalProcessor stopped")

    async def _process_loop(self):
        """Main processing loop with wave detection"""
        logger.info("Signal processing loop started with wave detection")

        while self.running:
            try:
                # Wait for the next wave check time
                await self._wait_for_next_wave_check()

                if not self.running:
                    break

                # Detect and process wave
                wave_detected = await self._detect_and_process_wave()

                if wave_detected:
                    logger.info(f"✅ Wave processing completed at {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")
                else:
                    logger.debug(f"No wave detected at {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")

                # Clean up old wave data periodically
                await self._cleanup_old_waves()

                # Update stats
                self.stats['last_check'] = datetime.now(timezone.utc)

            except Exception as e:
                logger.error(f"Error in signal processing loop: {e}", exc_info=True)
                await asyncio.sleep(10)

    async def _wait_for_next_wave_check(self):
        """Wait until the next wave check time (04, 18, 33, 48) in UTC"""
        now = datetime.now(timezone.utc)
        current_minute = now.minute

        # Find the next check minute
        next_check_minute = None
        for check_minute in self.wave_check_minutes:
            if current_minute < check_minute:
                next_check_minute = check_minute
                break

        # If no check minute found in current hour, use first one of next hour
        if next_check_minute is None:
            next_check_minute = self.wave_check_minutes[0]
            next_check_time = now.replace(minute=next_check_minute, second=0, microsecond=0)
            next_check_time += timedelta(hours=1)
        else:
            next_check_time = now.replace(minute=next_check_minute, second=0, microsecond=0)

        # Calculate wait time
        wait_seconds = (next_check_time - now).total_seconds()

        if wait_seconds > 0:
            logger.info(f"⏰ Waiting {wait_seconds:.0f}s until next wave check at {next_check_time.strftime('%H:%M UTC')}")
            await asyncio.sleep(wait_seconds)

    async def _detect_and_process_wave(self) -> bool:
        """
        Detect new wave and process signals
        Returns True if wave was detected and processed
        """
        logger.info(f"🔍 Starting wave detection at {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")

        # Calculate expected wave timestamp (15 minutes before current check)
        now = datetime.now(timezone.utc)
        current_minute = now.minute

        # Determine which 15-minute candle we're checking for
        # UPDATED: 07 -> 45 (previous hour), 22 -> 00, 37 -> 15, 52 -> 30
        # Signals created at xx:05, xx:20, xx:35, xx:50 → Check at xx:07, xx:22, xx:37, xx:52
        if current_minute in [7, 8, 9]:
            wave_minute = 45
            wave_time = now.replace(minute=wave_minute, second=0, microsecond=0) - timedelta(hours=1)
        elif current_minute in [22, 23, 24]:
            wave_minute = 0
            wave_time = now.replace(minute=wave_minute, second=0, microsecond=0)
        elif current_minute in [37, 38, 39]:
            wave_minute = 15
            wave_time = now.replace(minute=wave_minute, second=0, microsecond=0)
        elif current_minute in [52, 53, 54]:
            wave_minute = 30
            wave_time = now.replace(minute=wave_minute, second=0, microsecond=0)
        else:
            logger.warning(f"Unexpected minute for wave check: {current_minute}")
            return False

        wave_timestamp = wave_time.isoformat()
        logger.info(f"Looking for signals with timestamp: {wave_timestamp}")

        # Check if we already processed this wave
        if wave_timestamp in self.processed_waves:
            logger.info(f"Wave {wave_timestamp} already processed ({self.processed_waves[wave_timestamp]['count']} signals)")
            return False

        # Try to detect wave for up to 120 seconds
        detection_start = datetime.now(timezone.utc)
        signals_found = []

        while (datetime.now(timezone.utc) - detection_start).total_seconds() < self.wave_check_duration:
            # Fetch signals for this specific wave timestamp
            signals = await self._fetch_wave_signals(wave_time)

            if signals:
                signals_found = signals
                logger.info(f"🌊 Wave detected! Found {len(signals)} signals for timestamp {wave_timestamp}")
                break

            # Wait before next check
            await asyncio.sleep(self.wave_check_interval)

        if not signals_found:
            logger.info(f"No wave detected after {self.wave_check_duration}s of checking")
            return False

        # Initialize wave tracking
        self.processed_waves[wave_timestamp] = {
            'signal_ids': set(),
            'count': 0,
            'first_seen': datetime.now(timezone.utc)
        }
        self.stats['waves_detected'] += 1
        self.stats['current_wave'] = wave_timestamp

        # Process signals using WaveSignalProcessor with smart duplicate handling
        logger.info(f"Processing wave with smart duplicate handling (buffer: +{self.wave_processor.buffer_percent}%)")

        # Use wave processor to handle duplicates and get final signals
        result = await self.wave_processor.process_wave_signals(signals_found, wave_timestamp)

        # Extract successful signals for execution
        final_signals = result.get('successful', [])
        failed_signals = result.get('failed', [])
        skipped_signals = result.get('skipped', [])

        # CRITICAL FIX 2: Limit execution to MAX_TRADES_PER_15MIN
        # Buffer helps get enough signals after filtering, but we only execute MAX
        if len(final_signals) > self.max_trades_per_window:
            original_count = len(final_signals)
            final_signals = final_signals[:self.max_trades_per_window]
            logger.info(
                f"🎯 EXECUTION LIMITED: {original_count} -> {len(final_signals)} "
                f"(max_trades_per_15min={self.max_trades_per_window})"
            )

        logger.info(
            f"Wave processing results: "
            f"✅ {len(final_signals)} to execute, "
            f"❌ {len(failed_signals)} failed, "
            f"⏭️ {len(skipped_signals)} skipped "
            f"(from {len(signals_found)} total signals)"
        )

        # Execute successful signals
        for idx, signal_result in enumerate(final_signals):
            if not self.running:
                break

            # Extract the original signal data from the result
            signal = signal_result.get('signal_data') if isinstance(signal_result, dict) else signal_result

            logger.info(f"Executing signal {idx+1}/{len(final_signals)}")
            await self._process_signal(signal)
            self.processed_waves[wave_timestamp]['count'] += 1

            # Delay between signals
            if len(final_signals) > 1:
                await asyncio.sleep(1)

        # Log wave completion
        logger.info(
            f"Wave {wave_timestamp} complete:\n"
            f"  • Total signals found: {len(signals_found)}\n"
            f"  • Successfully executed: {len(final_signals)}\n"
            f"  • Failed: {len(failed_signals)}\n"
            f"  • Skipped (duplicates): {len(skipped_signals)}\n"
            f"  • Success rate: {result.get('success_rate', 0):.1%}"
        )
        return True

    async def _fetch_wave_signals(self, wave_time: datetime) -> List[Dict]:
        """
        Fetch signals for a specific wave timestamp
        Supports TEST_MODE: reads from test.scoring_history or fas.scoring_history
        """
        try:
            # Different queries for test mode vs production
            if self.test_mode:
                # TEST MODE: Simplified query for test.scoring_history
                # test.scoring_history has exchange field directly (no JOIN needed)
                # Note: test mode uses same parameters as production for consistency
                # Generate random LONG/SHORT for each signal (50/50)
                query = f"""
                    SELECT
                        id,
                        symbol,
                        exchange,
                        CASE WHEN random() < 0.5 THEN 'SHORT' ELSE 'LONG' END as action,
                        score as score_week,
                        score as score_month,
                        created_at,
                        timestamp,
                        true as is_active
                    FROM {self.signal_table}
                    WHERE timestamp = $1
                        AND score >= $2
                        AND score >= $3
                        AND NOT processed
                    ORDER BY score DESC
                    LIMIT $4;
                """
            else:
                # PRODUCTION MODE: Query for fas.scoring_history with trading_pairs join
                # The timestamp field in fas.scoring_history represents the candle start time
                # Join with trading_pairs to get exchange info (exchange_id=1 is Binance, =2 is Bybit)
                # CRITICAL: Filter by created_at to get FRESH signals only (not older than 1 hour)
                query = f"""
                    SELECT
                        sc.id,
                        sc.pair_symbol as symbol,
                        CASE
                            WHEN tp.exchange_id::integer = 1 THEN 'binance'  -- CAST to INTEGER for comparison
                            WHEN tp.exchange_id::integer = 2 THEN 'bybit'    -- CAST to INTEGER for comparison
                            ELSE 'unknown'
                        END as exchange,
                        sc.recommended_action as action,
                        sc.score_week,
                        sc.score_month,
                        sc.created_at,
                        sc.timestamp,
                        sc.is_active
                    FROM {self.signal_table} sc
                    JOIN public.trading_pairs tp ON sc.trading_pair_id::integer = tp.id  -- EXPLICIT CAST to INTEGER
                    WHERE sc.timestamp = $1
                        AND sc.score_week >= $2
                        AND sc.score_month >= $3
                        AND sc.is_active = true
                        AND sc.recommended_action IN ('BUY', 'SELL', 'LONG', 'SHORT')
                        AND NOT EXISTS (
                            SELECT 1 FROM trading_bot.processed_signals ps
                            WHERE ps.signal_id = sc.id::varchar  -- CAST id to match signal_id type if needed
                        )
                    ORDER BY
                        GREATEST(sc.score_week, sc.score_month) DESC,
                        sc.score_week DESC,
                        sc.score_month DESC
                    LIMIT $4;
                """

            async with self.repository.pool.acquire() as conn:
                # Use buffer size from wave processor
                buffer_size = self.wave_processor.buffer_size
                
                # CRITICAL FIX: PostgreSQL с timezone 'Etc/UTC' правильно интерпретирует datetime с tzinfo=UTC
                # AsyncPG автоматически конвертирует в правильный формат для БД
                # НЕ удаляем tzinfo! Иначе PostgreSQL интерпретирует как локальное время!
                
                # DEBUG: Log what we're querying
                logger.debug(f"Querying DB with wave_time: {wave_time} (UTC aware)")
                
                signals = await conn.fetch(
                    query,
                    wave_time,  # Use UTC-aware datetime directly
                    float(self.config.min_score_week),
                    float(self.config.min_score_month),
                    buffer_size  # Fetch with buffer for duplicate replacement
                )
                
                # DEBUG: Log to understand timezone issue
                if signals:
                    first_signal = signals[0]
                    db_timestamp = first_signal.get('timestamp')
                    logger.info(f"🔍 DEBUG TIMEZONE: DB returned {len(signals)} signals")
                    logger.info(f"   First signal timestamp: {db_timestamp} (type: {type(db_timestamp).__name__})")
                    logger.info(f"   Queried with: {wave_time} (UTC aware)")
                    logger.info(f"   Current UTC: {datetime.now(timezone.utc)}")

            # CRITICAL FIX 1: Apply STOPLIST_SYMBOLS filtering in wave mode
            # Convert to list of dicts for filtering
            raw_signals = [dict(s) for s in signals]

            # Apply symbol filtering (same as in _fetch_signals)
            filtered_signals = []
            for signal in raw_signals:
                symbol = signal.get('symbol', '')
                is_allowed, reason = self.symbol_filter.is_symbol_allowed(symbol)
                if not is_allowed:
                    logger.debug(f"Wave signal for {symbol} filtered: {reason}")
                    continue
                filtered_signals.append(signal)

            logger.info(
                f"Wave signals after stoplist filtering: {len(filtered_signals)} "
                f"(filtered {len(raw_signals) - len(filtered_signals)} stoplist symbols)"
            )

            return filtered_signals

        except Exception as e:
            logger.error(f"Error fetching wave signals: {e}", exc_info=True)
            return []

    async def _fetch_signals(self) -> List[Dict]:
        """Fetch new signals from database"""
        try:
            logger.info(f"Fetching signals with params: week>={self.config.min_score_week}, month>={self.config.min_score_month}, window={self.signal_time_window}min")

            signals = await self.repository.get_unprocessed_signals(
                min_score_week=float(self.config.min_score_week),
                min_score_month=float(self.config.min_score_month),
                time_window_minutes=self.signal_time_window,
                limit=self.max_trades_per_window
            )

            logger.info(f"Fetched {len(signals)} signals from database")
            self.stats['signals_received'] += len(signals)

            # Filter out processed and failed signals
            filtered_signals = []
            for signal in signals:
                signal_id = signal['id']

                if signal_id in self.processing_signals:
                    continue
                if signal_id in self.failed_signals:
                    continue
                # Check if symbol is allowed (centralized filtering)
                symbol = signal.get('symbol', '')
                is_allowed, reason = self.symbol_filter.is_symbol_allowed(symbol)
                if not is_allowed:
                    logger.debug(f"Signal {signal_id} for {symbol} filtered: {reason}")
                    continue

                # Check if position already exists
                if symbol in self.position_manager.positions:
                    logger.debug(f"Position already exists for {symbol}")
                    continue

                # Add to filtered signals
                filtered_signals.append(signal)

            logger.info(f"After filtering: {len(filtered_signals)} signals to process")
            return filtered_signals

        except Exception as e:
            logger.error(f"Error fetching signals: {e}", exc_info=True)
            import traceback
            traceback.print_exc()
            return []

    async def _process_signal(self, signal: Dict):
        """Process individual signal with validation"""
        signal_id = signal['id']

        # Log raw signal for debugging
        logger.debug(f"Raw signal data: {signal}")

        # Check if action is present
        if not signal.get('action'):
            logger.warning(f"Signal #{signal_id} has no action field, skipping")
            self.stats['signals_rejected'] += 1
            return

        # Validate signal data using pydantic
        try:
            validated_signal = validate_signal(signal)
            if not validated_signal:
                logger.warning(f"Signal #{signal_id} failed validation. Raw data: {signal}")
                self.stats['signals_rejected'] += 1
                self.processing_signals.discard(signal_id)
                await self.repository.mark_signal_processed(signal_id)
                return
        except Exception as e:
            logger.error(f"Error validating signal #{signal_id}: {e}")
            self.stats['signals_rejected'] += 1
            return
        
        symbol = validated_signal.symbol
        exchange = validated_signal.exchange
        
        # Mark as processing
        self.processing_signals.add(signal_id)

        try:
            logger.info(
                f"Processing signal #{signal_id}: {symbol} on {exchange} "
                f"(week: {validated_signal.score_week}, month: {validated_signal.score_month})"
            )

            # Emit signal received event
            await self.event_router.emit('signal.received', {
                'signal_id': signal_id,
                'symbol': symbol,
                'exchange': exchange,
                'action': validated_signal.action.value
            })

            # Additional validation
            if not await self._validate_signal(signal):
                self.stats['signals_rejected'] += 1
                await self.repository.mark_signal_processed(signal_id)
                return

            # Get current price (for validation)
            exchange_manager = self.position_manager.exchanges.get(exchange)
            if not exchange_manager:
                logger.error(f"Exchange {exchange} not available")
                self.failed_signals.add(signal_id)
                self.stats['signals_failed'] += 1
                return

            ticker = await exchange_manager.fetch_ticker(symbol)
            if not ticker:
                logger.error(f"Cannot get ticker for {symbol}")
                self.failed_signals.add(signal_id)
                self.stats['signals_failed'] += 1
                return

            current_price = ticker.get('last', 0)
            if current_price is None or current_price <= 0:
                logger.error(f"Invalid price for {symbol}: {current_price}")
                self.failed_signals.add(signal_id)
                self.stats['signals_failed'] += 1
                return

            # Use validated signal action
            if validated_signal.action in [OrderSide.BUY, OrderSide.LONG]:
                side = 'long'
            elif validated_signal.action in [OrderSide.SELL, OrderSide.SHORT]:
                side = 'short'
            else:
                logger.error(f"Invalid signal action: {validated_signal.action}")
                self.failed_signals.add(signal_id)
                return
            
            # Create position request with validated data
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
                logger.info(f"✅ Signal #{signal_id} executed successfully")
                self.stats['signals_executed'] += 1

                # Emit position opened event
                await self.event_router.emit('position.opened', {
                    'signal_id': signal_id,
                    'symbol': symbol,
                    'exchange': exchange,
                    'side': position.side,
                    'quantity': position.quantity,
                    'entry_price': position.entry_price
                })
            else:
                logger.warning(f"Failed to execute signal #{signal_id}")
                self.failed_signals.add(signal_id)
                self.stats['signals_failed'] += 1

            # Mark signal as processed and track in wave
            await self.repository.mark_signal_processed(signal_id)
            self.stats['signals_processed'] += 1
            
            # Track successful processing in wave using timestamp field
            wave_timestamp = self._get_wave_timestamp(signal.get('timestamp', signal['created_at']))
            if wave_timestamp in self.processed_waves:
                self.processed_waves[wave_timestamp]['signal_ids'].add(signal_id)
                self.processed_waves[wave_timestamp]['count'] += 1
                logger.info(f"Wave {wave_timestamp}: {self.processed_waves[wave_timestamp]['count']}/{self.max_trades_per_window} signals processed")

        except Exception as e:
            logger.error(f"Error processing signal {signal_id}: {e}", exc_info=True)
            self.failed_signals.add(signal_id)
            self.stats['signals_failed'] += 1

            # Mark as processed to avoid retry
            try:
                await self.repository.mark_signal_processed(signal_id)
                # Also track failed signals in wave count using timestamp field
                wave_timestamp = self._get_wave_timestamp(signal.get('timestamp', signal['created_at']))
                if wave_timestamp in self.processed_waves:
                    self.processed_waves[wave_timestamp]['signal_ids'].add(signal_id)
                    self.processed_waves[wave_timestamp]['count'] += 1
            except Exception as e:
                logger.warning(f"Failed to mark signal {signal_id} as processed: {e}")

        finally:
            self.processing_signals.discard(signal_id)

    async def _validate_signal(self, signal: Dict) -> bool:
        """
        Validate signal before execution

        Checks:
        - Signal age
        - Score thresholds
        - Symbol validity
        - Exchange availability
        """

        # Check signal age
        # CRITICAL: Use 'timestamp' field (wave time in UTC), not 'created_at' (record creation time)
        signal_time = signal.get('timestamp') or signal.get('created_at')
        if isinstance(signal_time, str):
            signal_time = datetime.fromisoformat(signal_time)

        # Always use UTC for consistency
        now = datetime.now(timezone.utc)
        if signal_time.tzinfo is None:
            # If signal_time is naive, assume it's UTC
            signal_time = signal_time.replace(tzinfo=timezone.utc)
            
        age_minutes = (now - signal_time).total_seconds() / 60

        if age_minutes > self.signal_time_window:
            logger.warning(
                f"Signal #{signal['id']} too old: {age_minutes:.1f} minutes"
            )
            return False

        # Validate scores
        score_week = signal.get('score_week', 0)
        score_month = signal.get('score_month', 0)

        if score_week < float(self.config.min_score_week):
            logger.warning(
                f"Signal #{signal['id']} score_week {score_week} "
                f"below threshold {self.config.min_score_week}"
            )
            return False

        if score_month < float(self.config.min_score_month):
            logger.warning(
                f"Signal #{signal['id']} score_month {score_month} "
                f"below threshold {self.config.min_score_month}"
            )
            return False

        # Validate action - check both possible field names
        action = signal.get('signal_type') or signal.get('recommended_action')
        if action not in ['BUY', 'SELL', 'LONG', 'SHORT']:
            logger.warning(f"Invalid action for signal #{signal['id']}: {action}")
            return False

        return True
    
    def _get_wave_timestamp(self, signal_time: datetime) -> str:
        """
        Get the 15-minute wave timestamp for a signal
        Rounds down to nearest 15-minute mark
        """
        if isinstance(signal_time, str):
            signal_time = datetime.fromisoformat(signal_time)
        
        # Round down to 15-minute mark
        minute = signal_time.minute
        rounded_minute = (minute // 15) * 15
        
        wave_time = signal_time.replace(
            minute=rounded_minute,
            second=0,
            microsecond=0
        )
        
        return wave_time.isoformat()
    
    async def _cleanup_old_waves(self):
        """Clean up old wave tracking data"""
        now = datetime.now(timezone.utc)
        cutoff = timedelta(hours=self.wave_cleanup_hours)
        
        waves_to_remove = []
        for wave_timestamp, wave_data in self.processed_waves.items():
            if now - wave_data['first_seen'] > cutoff:
                waves_to_remove.append(wave_timestamp)
        
        for wave_timestamp in waves_to_remove:
            del self.processed_waves[wave_timestamp]
            logger.debug(f"Cleaned up old wave data: {wave_timestamp}")

    def get_stats(self) -> Dict:
        """Get processor statistics"""
        wave_stats = {}
        for wave_timestamp, wave_data in self.processed_waves.items():
            wave_stats[wave_timestamp] = {
                'count': wave_data['count'],
                'limit': self.max_trades_per_window,
                'signal_ids': len(wave_data['signal_ids']),
                'first_seen': wave_data['first_seen'].isoformat()
            }

        # Get symbol filter statistics
        filter_stats = self.symbol_filter.get_statistics()

        return {
            **self.stats,
            'processing_count': len(self.processing_signals),
            'failed_count': len(self.failed_signals),
            'stop_list_size': filter_stats['stoplist_count'],  # Use filter stats
            'symbols_filtered': filter_stats,  # Full filter statistics
            'active_waves': wave_stats,
            'next_check_minute': self.wave_check_minutes
        }