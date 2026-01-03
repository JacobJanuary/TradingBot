"""
Wave Signal Processor with Smart Duplicate Handling
Implements buffered signal selection with automatic replacement
"""
import logging
from typing import Dict, List, Optional, Set, Union, Any
from datetime import datetime, timezone
from dataclasses import dataclass
import ccxt

logger = logging.getLogger(__name__)


@dataclass
class WaveProcessingStats:
    """Statistics for wave processing"""
    total_signals: int = 0
    signals_with_buffer: int = 0
    duplicates_filtered: int = 0
    buffer_replacements: int = 0
    final_signals: int = 0
    buffer_exhausted: bool = False
    processing_time_ms: float = 0


class WaveSignalProcessor:
    """
    Advanced wave processor with intelligent duplicate replacement.

    Features:
    - Buffer strategy: takes MAX + 33% signals
    - Smart replacement: uses buffer signals when duplicates found
    - Duplicate prevention: one position per symbol
    - Metrics tracking: detailed statistics
    """

    def __init__(self, config, position_manager):
        """
        Initialize wave processor.

        Args:
            config: Trading configuration
            position_manager: Position manager instance
        """
        self.config = config
        self.position_manager = position_manager

        # Wave parameters
        self.max_trades_per_wave = int(getattr(config, 'max_trades_per_15min', 10))
        self.duplicate_check_enabled = getattr(config, 'duplicate_check_enabled', True)

        # Buffer size for logging (aligns with per-exchange logic)
        self.buffer_size = self.max_trades_per_wave + self.config.signal_buffer_fixed

        # Statistics
        self.wave_stats = {}  # {timestamp: WaveProcessingStats}
        self.total_duplicates_filtered = 0
        self.total_buffer_replacements = 0

        # New filter statistics
        self.total_filtered_low_oi = 0
        self.total_filtered_low_volume = 0
        self.total_filtered_price_change = 0

        logger.info(
            f"WaveSignalProcessor initialized: "
            f"max_trades={self.max_trades_per_wave}, "
            f"buffer_size={self.buffer_size} (+{self.config.signal_buffer_fixed}), "
            f"duplicate_check={self.duplicate_check_enabled}, "
            f"filters=[OI:{getattr(config, 'signal_filter_oi_enabled', True)}, "
            f"Volume:{getattr(config, 'signal_filter_volume_enabled', True)}, "
            f"PriceChange:{getattr(config, 'signal_filter_price_change_enabled', True)}]"
        )

    async def process_wave_signals(
        self,
        signals: List[Dict],
        wave_timestamp: str = None,
        mode: str = 'process'  # NEW: 'filter' or 'process'
    ) -> Dict[str, Any]:
        """
        Обрабатывает волну сигналов с graceful degradation.

        Один неверный символ НЕ останавливает обработку всей волны.

        Args:
            signals: Список сигналов для обработки
            wave_timestamp: Timestamp волны

        Returns:
            dict: {
                'successful': [...],
                'failed': [...],
                'skipped': [...],
                'total_signals': int,
                'processed': int,
                'success_rate': float
            }

        Based on: Freqtrade freqtradebot.py process() method
        """
        # Инициализация результатов
        successful_signals = []
        failed_signals = []
        skipped_symbols = []
        insufficient_funds_hit = False  # Track if InsufficientFunds occurred

        # Сохраняем текущий режим для использования в методах
        self._current_mode = mode

        start_time = datetime.now(timezone.utc)
        wave_id = wave_timestamp or start_time.isoformat()

        logger.info(
            f"🌊 Starting wave processing: {len(signals)} signals at "
            f"timestamp {wave_id}"
        )

        # ✅ ГЛАВНОЕ ИЗМЕНЕНИЕ: используем try-except с continue
        # Based on: Freqtrade pattern for batch processing
        for idx, signal in enumerate(signals, 1):
            # В режиме filter работаем с копией чтобы не модифицировать оригинал
            if mode == 'filter':
                signal_to_check = signal.copy()
            else:
                signal_to_check = signal

            symbol = signal_to_check.get('symbol', signal_to_check.get('pair_symbol', 'UNKNOWN'))

            try:
                logger.debug(f"Processing signal {idx}/{len(signals)}: {symbol}")

                # Проверяем на дубликаты
                is_duplicate, reason = await self._is_duplicate(signal_to_check, wave_id)

                # ✅ Обрабатываем результат проверки позиции
                # Если вернулся dict с ошибкой - символ невалидный
                if isinstance(is_duplicate, dict) and 'error' in is_duplicate:
                    logger.warning(
                        f"⚠️ Skipping signal {idx} ({symbol}): "
                        f"{is_duplicate['error']} - {is_duplicate['message']}"
                    )
                    failed_signals.append({
                        'signal_number': idx,
                        'symbol': symbol,
                        'error_type': is_duplicate['error'],
                        'message': is_duplicate['message'],
                        'retryable': is_duplicate.get('retryable', False),
                        'signal_data': signal
                    })
                    continue  # ✅ Продолжаем со следующим сигналом

                # Если дубликат - пропускаем
                if is_duplicate:
                    logger.info(f"⏭️ Signal {idx} ({symbol}) is duplicate: {reason}")
                    skipped_symbols.append({
                        'symbol': symbol,
                        'reason': reason
                    })
                    continue  # ✅ Продолжаем со следующим сигналом

                # Обрабатываем сигнал (только в режиме process)
                if mode == 'process':
                    result = await self._process_single_signal(signal_to_check, wave_id)
                else:
                    # В режиме filter просто помечаем как прошедший фильтры
                    result = {'status': 'filtered', 'symbol': symbol}

                if result:
                    successful_signals.append({
                        'signal_number': idx,
                        'symbol': symbol,
                        'result': result,
                        'signal_data': signal  # Всегда оригинальный, не копия
                    })
                    logger.info(f"✅ Signal {idx} ({symbol}) processed successfully")
                else:
                    logger.warning(f"⚠️ Signal {idx} ({symbol}) processing returned None")
                    failed_signals.append({
                        'signal_number': idx,
                        'symbol': symbol,
                        'error_type': 'processing_failed',
                        'message': 'Processing returned None/False',
                        'retryable': False
                    })

            except ccxt.BadSymbol as e:
                # Не должно попасть сюда (обрабатывается в position_manager)
                # но на всякий случай ловим
                logger.error(f"❌ BadSymbol leaked to processor for {symbol}: {e}")
                failed_signals.append({
                    'signal_number': idx,
                    'symbol': symbol,
                    'error_type': 'bad_symbol_leaked',
                    'message': str(e),
                    'retryable': False
                })
                continue  # ✅ Продолжаем с остальными

            except ccxt.InsufficientFunds as e:
                # Недостаточно средств - останавливаем весь batch
                logger.error(f"💰 Insufficient funds at signal {idx} ({symbol}): {e}")
                failed_signals.append({
                    'signal_number': idx,
                    'symbol': symbol,
                    'error_type': 'insufficient_funds',
                    'message': str(e),
                    'retryable': False
                })
                insufficient_funds_hit = True  # Set flag for caller
                break  # ❌ Останавливаем - средства кончились

            except Exception as e:
                # Неожиданные ошибки - логируем и продолжаем
                logger.error(
                    f"❌ Unexpected error processing signal {idx} ({symbol}): {e}",
                    exc_info=True
                )
                failed_signals.append({
                    'signal_number': idx,
                    'symbol': symbol,
                    'error_type': 'unexpected_error',
                    'message': str(e),
                    'retryable': False
                })
                continue  # ✅ Продолжаем с остальными сигналами

        # Формируем итоговый результат
        result = {
            'successful': successful_signals,
            'failed': failed_signals,
            'skipped': skipped_symbols,
            'total_signals': len(signals),
            'processed': len(successful_signals),
            'failed_count': len(failed_signals),
            'skipped_count': len(skipped_symbols),
            'success_rate': len(successful_signals) / len(signals) if signals else 0,
            'insufficient_funds': insufficient_funds_hit  # Flag for iterative loop control
        }

        # Детальное логирование результатов
        processing_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        logger.info(
            f"🌊 Wave processing complete in {processing_time:.0f}ms: "
            f"✅ {result['processed']} successful, "
            f"❌ {result['failed_count']} failed, "
            f"⏭️ {result['skipped_count']} skipped, "
            f"📊 Success rate: {result['success_rate']:.1%}"
        )

        # Логируем детали неудачных
        if failed_signals:
            logger.warning(f"Failed signals breakdown:")
            for failed in failed_signals:
                logger.warning(
                    f"  - Signal #{failed['signal_number']} ({failed['symbol']}): "
                    f"{failed['error_type']} - {failed['message']}"
                )

        return result

    async def _is_duplicate(self, signal: Dict, wave_timestamp: str) -> tuple:
        """
        Проверяет является ли сигнал дубликатом.

        Returns:
            tuple: (is_duplicate: Union[bool, dict], reason: str)
                - Если bool: True/False - результат проверки
                - Если dict: error object с деталями ошибки
        """
        symbol = signal.get('symbol', signal.get('pair_symbol', ''))
        # КРИТИЧНО: Извлекаем биржу из сигнала!
        exchange = signal.get('exchange', signal.get('exchange_name', ''))

        try:
            # Проверяем наличие открытой позиции НА КОНКРЕТНОЙ БИРЖЕ
            if exchange:
                has_position = await self.position_manager.has_open_position(symbol, exchange)
            else:
                # Если биржа не указана - проверяем на всех (для обратной совместимости)
                logger.warning(f"Exchange not specified for signal {symbol}, checking all exchanges")
                has_position = await self.position_manager.has_open_position(symbol)

            # ✅ КРИТИЧНО: Обрабатываем error object
            if isinstance(has_position, dict) and 'error' in has_position:
                # Возвращаем error object наверх
                return has_position, ""

            # Если позиция есть - это дубликат
            if has_position:
                return True, "Position already exists"

            # ========== НОВАЯ ПРОВЕРКА: Минимальная стоимость позиции ==========

            # Get exchange manager
            exchange_manager = self.position_manager.exchanges.get(exchange)
            if not exchange_manager:
                logger.warning(f"Exchange {exchange} not available for {symbol}")
                return {
                    'error': 'exchange_not_available',
                    'symbol': symbol,
                    'exchange': exchange,
                    'message': f"Exchange {exchange} not available",
                    'retryable': False
                }, ""

            # Get exchange-specific symbol format
            exchange_symbol = exchange_manager.find_exchange_symbol(symbol)
            if not exchange_symbol:
                logger.debug(f"Symbol {symbol} not found on {exchange}")
                return True, f"Symbol {symbol} not found on {exchange}"

            # Get market data
            market = exchange_manager.markets.get(exchange_symbol)
            if not market:
                logger.debug(f"Market data not available for {symbol}")
                return True, f"Market data not available for {symbol}"

            # Get current price
            ticker = await exchange_manager.fetch_ticker(symbol)
            if not ticker:
                logger.debug(f"Ticker not available for {symbol}")
                return True, f"Ticker not available for {symbol}"

            # DEFENSIVE FIX 2025-10-29: Convert ticker price to float explicitly
            # Some exchanges return prices as strings, causing type errors in calculations
            price_raw = ticker.get('last') or ticker.get('close', 0)
            try:
                current_price = float(price_raw)
            except (ValueError, TypeError) as e:
                logger.debug(f"Invalid price format for {symbol}: {price_raw} ({type(price_raw).__name__}), error: {e}")
                return True, f"Invalid price for {symbol}"

            if not current_price or current_price <= 0:
                logger.debug(f"Invalid price for {symbol}: {current_price}")
                return True, f"Invalid price for {symbol}"

            # Get position size from config
            position_size_usd = float(self.config.position_size_usd)

            # Calculate notional value
            quantity = position_size_usd / current_price
            notional_value = quantity * current_price  # Should equal position_size_usd

            # Get minimum cost using 3-step approach
            min_cost = await self._get_minimum_cost(
                market=market,
                exchange_name=exchange,
                symbol=symbol,
                current_price=current_price
            )

            # Validate against minimum
            if notional_value < min_cost:
                logger.info(
                    f"⏭️ Signal skipped: {symbol} minimum notional ${min_cost:.2f} "
                    f"> position size ${position_size_usd:.2f} on {exchange}"
                )

                # Log event to database
                from core.event_logger import get_event_logger, EventType
                event_logger = get_event_logger()
                if event_logger:
                    # Determine source of min_cost for logging
                    source = 'unknown'
                    if market.get('limits', {}).get('cost', {}).get('min'):
                        source = 'ccxt_standard'
                    elif exchange == 'bybit' and market.get('info', {}).get('lotSizeFilter', {}).get('minNotionalValue'):
                        source = 'bybit_raw_api'
                    else:
                        source = 'fallback_10usd'

                    # Log event (только в режиме process)
                    if getattr(self, '_current_mode', 'process') == 'process':
                        await event_logger.log_event(
                            EventType.SIGNAL_FILTERED,
                            {
                                'signal_id': signal.get('id'),
                                'symbol': symbol,
                                'exchange': exchange,
                                'filter_reason': 'below_minimum_notional',
                                'position_size_usd': position_size_usd,
                                'notional_value': float(notional_value),
                                'min_cost_required': float(min_cost),
                                'current_price': float(current_price),
                                'quantity': float(quantity),
                                'min_cost_source': source
                            },
                            symbol=symbol,
                            exchange=exchange,
                            severity='INFO'
                        )

                return True, f"Position size (${position_size_usd:.2f}) below exchange minimum (${min_cost:.2f})"

            # ========== NEW FILTERS: OI, Volume, Price Change ==========

            # Extract signal timestamp and direction for new filters
            signal_timestamp_str = signal.get('timestamp') or signal.get('created_at')
            direction = signal.get('recommended_action') or signal.get('signal_type') or signal.get('action')

            if signal_timestamp_str and direction:
                try:
                    # CRITICAL FIX 2025-10-29: Ensure timestamp is string before calling .replace()
                    # If signal['timestamp'] is already datetime object, convert to ISO string first
                    if isinstance(signal_timestamp_str, datetime):
                        signal_timestamp_str = signal_timestamp_str.isoformat()
                    elif not isinstance(signal_timestamp_str, str):
                        # Convert any other type (int, float, etc.) to string
                        signal_timestamp_str = str(signal_timestamp_str)

                    # Parse timestamp
                    signal_timestamp = datetime.fromisoformat(signal_timestamp_str.replace('+00', '+00:00'))

                    # Filter 1: Open Interest >= 1M USDT
                    if getattr(self.config, 'signal_filter_oi_enabled', True):
                        oi_usdt = await self._fetch_open_interest_usdt(
                            exchange_manager, symbol, exchange, current_price
                        )
                        min_oi = float(getattr(self.config, 'signal_min_open_interest_usdt', 1_000_000))

                        if oi_usdt is not None and oi_usdt < min_oi:
                            logger.info(
                                f"⏭️ Signal skipped: {symbol} OI ${oi_usdt:,.0f} < ${min_oi:,} on {exchange}"
                            )

                            # Log event (только в режиме process)
                            from core.event_logger import get_event_logger, EventType
                            event_logger = get_event_logger()
                            if event_logger and getattr(self, '_current_mode', 'process') == 'process':
                                await event_logger.log_event(
                                    EventType.SIGNAL_FILTERED,
                                    {
                                        'signal_id': signal.get('id'),
                                        'symbol': symbol,
                                        'exchange': exchange,
                                        'filter_reason': 'low_open_interest',
                                        'open_interest_usdt': float(oi_usdt),
                                        'min_oi_required': float(min_oi)
                                    },
                                    symbol=symbol,
                                    exchange=exchange,
                                    severity='INFO'
                                )

                            self.total_filtered_low_oi = getattr(self, 'total_filtered_low_oi', 0) + 1
                            return True, f"OI ${oi_usdt:,.0f} below minimum ${min_oi:,}"

                    # Filter 2: 1h Volume >= 50k USDT
                    if getattr(self.config, 'signal_filter_volume_enabled', True):
                        volume_1h_usdt = await self._fetch_1h_volume_usdt(
                            exchange_manager, symbol, signal_timestamp
                        )
                        min_volume = float(getattr(self.config, 'signal_min_volume_1h_usdt', 50_000))

                        if volume_1h_usdt is not None and volume_1h_usdt < min_volume:
                            logger.info(
                                f"⏭️ Signal skipped: {symbol} 1h volume ${volume_1h_usdt:,.0f} < ${min_volume:,} on {exchange}"
                            )

                            # Log event (только в режиме process)
                            from core.event_logger import get_event_logger, EventType
                            event_logger = get_event_logger()
                            if event_logger and getattr(self, '_current_mode', 'process') == 'process':
                                await event_logger.log_event(
                                    EventType.SIGNAL_FILTERED,
                                    {
                                        'signal_id': signal.get('id'),
                                        'symbol': symbol,
                                        'exchange': exchange,
                                        'filter_reason': 'low_volume',
                                        'volume_1h_usdt': float(volume_1h_usdt),
                                        'min_volume_required': float(min_volume)
                                    },
                                    symbol=symbol,
                                    exchange=exchange,
                                    severity='INFO'
                                )

                            self.total_filtered_low_volume = getattr(self, 'total_filtered_low_volume', 0) + 1
                            return True, f"1h volume ${volume_1h_usdt:,.0f} below minimum ${min_volume:,}"

                    # Filter 3: Price Change Check (5min and 15min)
                    if getattr(self.config, 'signal_filter_price_change_enabled', True):
                        price_at_signal, price_5min_before, price_15min_before = await self._fetch_price_change_data(
                            exchange_manager, symbol, signal_timestamp
                        )
                        max_change_5m = float(getattr(self.config, 'signal_max_price_change_5min_percent', 4.0))
                        max_change_15m = max_change_5m * 2.0  # 15min threshold is double the 5min one

                        # Check 1: 5-minute change
                        if price_at_signal and price_5min_before and price_5min_before > 0:
                            price_change_5m_percent = ((price_at_signal - price_5min_before) / price_5min_before) * 100
                            
                            should_filter_5m = False
                            reason_5m = ""
                            
                            if direction == 'BUY' and price_change_5m_percent > max_change_5m:
                                should_filter_5m = True
                                reason_5m = f"overheated 5m (BUY after +{price_change_5m_percent:.2f}% rise)"
                            elif direction == 'SELL' and price_change_5m_percent < -max_change_5m:
                                should_filter_5m = True
                                reason_5m = f"oversold 5m (SELL after {price_change_5m_percent:.2f}% drop)"

                            if should_filter_5m:
                                logger.info(
                                    f"⏭️ Signal skipped: {symbol} {reason_5m} on {exchange}"
                                )
                                
                                # Log event
                                from core.event_logger import get_event_logger, EventType
                                event_logger = get_event_logger()
                                if event_logger and getattr(self, '_current_mode', 'process') == 'process':
                                    await event_logger.log_event(
                                        EventType.SIGNAL_FILTERED,
                                        {
                                            'signal_id': signal.get('id'),
                                            'symbol': symbol,
                                            'exchange': exchange,
                                            'filter_reason': 'price_overheated_5m' if direction == 'BUY' else 'price_oversold_5m',
                                            'direction': direction,
                                            'price_change_5min_percent': float(price_change_5m_percent),
                                            'max_change_allowed': float(max_change_5m),
                                            'price_at_signal': float(price_at_signal),
                                            'price_5min_before': float(price_5min_before)
                                        },
                                        symbol=symbol,
                                        exchange=exchange,
                                        severity='INFO'
                                    )
                                
                                self.total_filtered_price_change = getattr(self, 'total_filtered_price_change', 0) + 1
                                return True, reason_5m

                        # Check 2: 15-minute change
                        if price_at_signal and price_15min_before and price_15min_before > 0:
                            price_change_15m_percent = ((price_at_signal - price_15min_before) / price_15min_before) * 100
                            
                            should_filter_15m = False
                            reason_15m = ""
                            
                            if direction == 'BUY' and price_change_15m_percent > max_change_15m:
                                should_filter_15m = True
                                reason_15m = f"overheated 15m (BUY after +{price_change_15m_percent:.2f}% rise)"
                            elif direction == 'SELL' and price_change_15m_percent < -max_change_15m:
                                should_filter_15m = True
                                reason_15m = f"oversold 15m (SELL after {price_change_15m_percent:.2f}% drop)"

                            if should_filter_15m:
                                logger.info(
                                    f"⏭️ Signal skipped: {symbol} {reason_15m} on {exchange}"
                                )
                                
                                # Log event
                                from core.event_logger import get_event_logger, EventType
                                event_logger = get_event_logger()
                                if event_logger and getattr(self, '_current_mode', 'process') == 'process':
                                    await event_logger.log_event(
                                        EventType.SIGNAL_FILTERED,
                                        {
                                            'signal_id': signal.get('id'),
                                            'symbol': symbol,
                                            'exchange': exchange,
                                            'filter_reason': 'price_overheated_15m' if direction == 'BUY' else 'price_oversold_15m',
                                            'direction': direction,
                                            'price_change_15min_percent': float(price_change_15m_percent),
                                            'max_change_allowed': float(max_change_15m),
                                            'price_at_signal': float(price_at_signal),
                                            'price_15min_before': float(price_15min_before)
                                        },
                                        symbol=symbol,
                                        exchange=exchange,
                                        severity='INFO'
                                    )
                                
                                self.total_filtered_price_change = getattr(self, 'total_filtered_price_change', 0) + 1
                                return True, reason_15m

                except Exception as e:
                    logger.warning(f"Error applying new filters to {symbol}: {e}", exc_info=True)
                    # Don't filter on error - graceful degradation

            # All checks passed
            return False, ""

        except Exception as e:
            logger.error(f"Error in _is_duplicate for {symbol}: {e}", exc_info=True)
            # Возвращаем error object
            return {
                'error': 'duplicate_check_failed',
                'symbol': symbol,
                'message': str(e),
                'retryable': False
            }, ""

    async def _process_single_signal(self, signal: Dict, wave_timestamp: str) -> Optional[Dict]:
        """
        Обрабатывает один сигнал.
        
        Args:
            signal: Сигнал для обработки
            wave_timestamp: Timestamp волны
        
        Returns:
            Dict с результатом обработки или None если не удалось
        """
        try:
            # Extract action from signal
            action = signal.get('signal_type') or signal.get('recommended_action') or signal.get('action')
            symbol = signal.get('symbol', signal.get('pair_symbol', ''))

            # Ensure action is set for downstream processing
            if action and not signal.get('action'):
                signal['action'] = action
                logger.debug(f"Signal #{signal.get('id', 'unknown')} action set to: {action}")

            # Ensure signal_type is set for validation
            if action and not signal.get('signal_type'):
                signal['signal_type'] = action
            
            # Direct processing (SMART_ENTRY removed 2026-01-03)
            return {
                'symbol': symbol,
                'action': action,
                'processed_at': wave_timestamp,
                'status': 'processed'
            }
        
        except Exception as e:
            logger.error(f"Error processing single signal: {e}", exc_info=True)
            return None

    async def _get_minimum_cost(
        self,
        market: Dict,
        exchange_name: str,
        symbol: str,
        current_price: float
    ) -> float:
        """
        Get minimum notional cost for a symbol (3-step approach).

        Step 1: Try CCXT standard (works for Binance, most exchanges)
        Step 2: Try exchange-specific parsing (Bybit)
        Step 3: Fallback to safe absolute minimum ($10)

        Args:
            market: Market data from exchange
            exchange_name: Exchange name (e.g., 'bybit', 'binance')
            symbol: Trading symbol
            current_price: Current market price

        Returns:
            Minimum cost in USD
        """
        # Step 1: Try CCXT standard
        cost_min = market.get('limits', {}).get('cost', {}).get('min')
        if cost_min and cost_min > 0:
            logger.debug(f"{symbol}: Using CCXT cost.min = ${cost_min}")
            return float(cost_min)

        # Step 2: Try Bybit-specific parsing
        if exchange_name == 'bybit':
            info = market.get('info', {})
            lot_size_filter = info.get('lotSizeFilter', {})
            min_notional_str = lot_size_filter.get('minNotionalValue')

            if min_notional_str:
                try:
                    min_notional = float(min_notional_str)
                    logger.debug(
                        f"{symbol}: Using Bybit minNotionalValue = ${min_notional} "
                        f"(parsed from info.lotSizeFilter)"
                    )
                    return min_notional
                except (ValueError, TypeError) as e:
                    logger.warning(
                        f"{symbol}: Could not parse Bybit minNotionalValue '{min_notional_str}': {e}"
                    )

        # Step 3: Fallback to absolute minimum
        logger.warning(
            f"{symbol}: No min_cost from exchange, using fallback $10.00"
        )
        return 10.0

    async def _fetch_open_interest_usdt(
        self,
        exchange_manager,
        symbol: str,
        exchange_name: str,
        current_price: float
    ) -> Optional[float]:
        """
        Получить Open Interest в USDT для проверки ликвидности.

        Использует 5 методов в порядке fallback:
        1. fetch_open_interest() → openInterestValue
        2. fetch_open_interest() → quoteVolume
        3. fetch_open_interest() → openInterestAmount * markPrice
        4. fetch_ticker() → info.openInterest * last_price (Binance)
        5. fetch_ticker() → info.openInterestValue (Bybit)

        Args:
            exchange_manager: Exchange manager instance
            symbol: Trading symbol
            exchange_name: Exchange name
            current_price: Current price for fallback conversion

        Returns:
            Open Interest in USDT or None if not available
        """
        try:
            # FIX 2025-10-29: Bybit-specific handling
            # CCXT fetch_open_interest() returns openInterestValue=None for Bybit
            # Use ticker['info']['openInterest'] instead
            if exchange_name.lower() == 'bybit':
                try:
                    ticker = await exchange_manager.fetch_ticker(symbol)
                    if ticker and ticker.get('info'):
                        oi_contracts = float(ticker['info'].get('openInterest', 0))
                        if oi_contracts and current_price:
                            oi_usd = oi_contracts * current_price
                            logger.debug(
                                f"Bybit OI: {symbol} - contracts: {oi_contracts:,.2f}, "
                                f"price: ${current_price:,.2f}, USD: ${oi_usd:,.0f}"
                            )
                            return oi_usd
                except Exception as e:
                    logger.debug(f"Bybit OI fetch failed for {symbol}: {e}")
                    # Fall through to generic methods below
                    pass
            # Method 1-3: Try fetch_open_interest
            try:
                oi_data = await exchange_manager.exchange.fetch_open_interest(
                    exchange_manager.find_exchange_symbol(symbol)
                )

                if oi_data:
                    # Method 1: openInterestValue (already in USDT)
                    if 'openInterestValue' in oi_data and oi_data['openInterestValue'] is not None:
                        return float(oi_data['openInterestValue'])

                    # Method 2: quoteVolume
                    if 'quoteVolume' in oi_data and oi_data['quoteVolume'] is not None:
                        return float(oi_data['quoteVolume'])

                    # Method 3: openInterestAmount * markPrice
                    if 'openInterestAmount' in oi_data and oi_data['openInterestAmount'] is not None:
                        amount = float(oi_data['openInterestAmount'])
                        if 'info' in oi_data and oi_data['info']:
                            mark_price = oi_data['info'].get('markPrice') or oi_data['info'].get('lastPrice')
                            if mark_price:
                                return amount * float(mark_price)
                        # Fallback: use current_price
                        return amount * current_price
            except Exception:
                pass  # Try next method

            # Method 4-5: Try fetch_ticker
            try:
                ticker = await exchange_manager.fetch_ticker(symbol)
                if ticker and ticker.get('info'):
                    info = ticker['info']

                    # Method 4: Binance - openInterest * last_price
                    if 'openInterest' in info and info['openInterest']:
                        oi_amount = float(info['openInterest'])
                        price = ticker.get('last') or current_price
                        return oi_amount * price

                    # Method 5: Bybit - openInterestValue
                    if 'openInterestValue' in info and info['openInterestValue']:
                        return float(info['openInterestValue'])
            except Exception:
                pass

            return None

        except Exception as e:
            logger.debug(f"Could not fetch OI for {symbol}: {e}")
            return None

    async def _fetch_1h_volume_usdt(
        self,
        exchange_manager,
        symbol: str,
        signal_timestamp: datetime
    ) -> Optional[float]:
        """
        Получить объем торгов за 1 час ПЕРЕД сигналом в USDT.
        
        CRITICAL FIX 2025-11-30: Fetch PREVIOUS complete hour, not current incomplete hour.
        
        Example:
            Signal at 14:37:22
            - Current hour: 14:00-14:59 (only 37 minutes, INCOMPLETE)
            - Previous hour: 13:00-13:59 (full 60 minutes, COMPLETE) ✅
        
        We check the PREVIOUS hour's volume to ensure we have a full 60 minutes of data.

        Args:
            exchange_manager: Exchange manager instance
            symbol: Trading symbol
            signal_timestamp: Timestamp сигнала

        Returns:
            1h volume in USDT or None if not available
        """
        try:
            from datetime import timedelta
            
            # Round timestamp down to hour boundary
            hour_start = signal_timestamp.replace(minute=0, second=0, microsecond=0)
            
            # CRITICAL FIX: Subtract 1 hour to get PREVIOUS COMPLETE hour
            # If signal is at 14:37, we want 13:00-13:59 candle (complete), not 14:00-14:37 (incomplete)
            prev_hour_start = hour_start - timedelta(hours=1)
            ts_ms = int(prev_hour_start.timestamp() * 1000)

            # Fetch 1h candle from PREVIOUS hour (complete data)
            ohlcv = await exchange_manager.exchange.fetch_ohlcv(
                exchange_manager.find_exchange_symbol(symbol),
                timeframe='1h',
                since=ts_ms,
                limit=1
            )

            if not ohlcv or len(ohlcv) == 0:
                return None

            candle = ohlcv[0]
            # [timestamp, open, high, low, close, volume]
            base_volume = candle[5]
            close_price = candle[4]

            # Convert to USDT
            volume_usdt = base_volume * close_price
            return volume_usdt

        except Exception as e:
            logger.debug(f"Could not fetch 1h volume for {symbol}: {e}")
            return None

    async def _fetch_price_change_data(
        self,
        exchange_manager,
        symbol: str,
        signal_timestamp: datetime
    ) -> tuple:
        """
        Fetch price data for 5min and 15min change calculations.
        Optimized to use a single API call.

        Args:
            exchange_manager: Exchange manager instance
            symbol: Trading symbol
            signal_timestamp: Timestamp of the signal

        Returns:
            tuple: (price_at_signal, price_5min_before, price_15min_before)
                   Returns (None, None, None) if data unavailable
        """
        try:
            exchange_symbol = exchange_manager.find_exchange_symbol(symbol)
            
            # We need data from 15 mins before up to signal time
            # Fetch 20 mins to be safe and ensure we find the candles
            from datetime import timedelta
            
            ts_signal_ms = int(signal_timestamp.timestamp() * 1000)
            ts_start_ms = ts_signal_ms - (20 * 60 * 1000)  # 20 mins before signal
            
            # Fetch 1m candles
            # Limit 30 should cover 20 mins + some buffer
            ohlcv = await exchange_manager.exchange.fetch_ohlcv(
                exchange_symbol,
                timeframe='1m',
                since=ts_start_ms,
                limit=30
            )

            if not ohlcv:
                return None, None, None

            # Helper to find closest candle price
            def get_price_at_time(target_ts_ms, candles):
                # Find candle with timestamp closest to target
                # Candle timestamp is usually open time
                closest = min(candles, key=lambda x: abs(x[0] - target_ts_ms))
                
                # Check if it's within reasonable range (e.g. 2 mins)
                if abs(closest[0] - target_ts_ms) > (2 * 60 * 1000):
                    return None
                return closest[4]  # close price

            price_at_signal = get_price_at_time(ts_signal_ms, ohlcv)
            
            ts_5min_before_ms = ts_signal_ms - (5 * 60 * 1000)
            price_5min_before = get_price_at_time(ts_5min_before_ms, ohlcv)
            
            ts_15min_before_ms = ts_signal_ms - (15 * 60 * 1000)
            price_15min_before = get_price_at_time(ts_15min_before_ms, ohlcv)

            return price_at_signal, price_5min_before, price_15min_before

        except Exception as e:
            logger.debug(f"Could not fetch price change data for {symbol}: {e}")
            return None, None, None

    async def _get_open_positions(self) -> List[Dict]:
        """Get all open positions with details."""

        try:
            # Get from position manager
            positions = []

            # Check local tracking
            for symbol, position_state in self.position_manager.positions.items():
                positions.append({
                    'symbol': symbol,
                    'side': position_state.side,
                    'exchange': position_state.exchange,
                    'entry_price': position_state.entry_price,
                    'quantity': position_state.quantity,
                    'status': 'open'
                })

            return positions

        except Exception as e:
            logger.error(f"Error getting open positions: {e}")
            return []

    def get_statistics(self) -> Dict:
        """Get processing statistics."""

        recent_waves = list(self.wave_stats.items())[-10:]  # Last 10 waves

        if recent_waves:
            avg_duplicates = sum(s.duplicates_filtered for _, s in recent_waves) / len(recent_waves)
            avg_replacements = sum(s.buffer_replacements for _, s in recent_waves) / len(recent_waves)
            buffer_exhausted_count = sum(1 for _, s in recent_waves if s.buffer_exhausted)
        else:
            avg_duplicates = 0
            avg_replacements = 0
            buffer_exhausted_count = 0

        return {
            'buffer_config': {
                'max_trades_per_wave': self.max_trades_per_wave,
                'buffer_fixed': self.config.signal_buffer_fixed,
                'buffer_size': self.buffer_size
            },
            'total_stats': {
                'duplicates_filtered': self.total_duplicates_filtered,
                'buffer_replacements': self.total_buffer_replacements,
                'waves_processed': len(self.wave_stats),
                'filtered_low_oi': self.total_filtered_low_oi,
                'filtered_low_volume': self.total_filtered_low_volume,
                'filtered_price_change': self.total_filtered_price_change
            },
            'recent_stats': {
                'avg_duplicates_per_wave': avg_duplicates,
                'avg_replacements_per_wave': avg_replacements,
                'buffer_exhausted_count': buffer_exhausted_count,
                'sample_size': len(recent_waves)
            }
        }

    def reset_statistics(self):
        """Reset all statistics."""
        self.wave_stats.clear()
        self.total_duplicates_filtered = 0
        self.total_buffer_replacements = 0
        self.total_filtered_low_oi = 0
        self.total_filtered_low_volume = 0
        self.total_filtered_price_change = 0
        logger.info("Wave processor statistics reset")