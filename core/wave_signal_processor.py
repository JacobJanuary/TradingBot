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

        logger.info(
            f"WaveSignalProcessor initialized: "
            f"max_trades={self.max_trades_per_wave}, "
            f"buffer_size={self.buffer_size} (+{self.config.signal_buffer_fixed}), "
            f"duplicate_check={self.duplicate_check_enabled}"
        )

    async def process_wave_signals(
        self,
        signals: List[Dict],
        wave_timestamp: str = None
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

        start_time = datetime.now(timezone.utc)
        wave_id = wave_timestamp or start_time.isoformat()

        logger.info(
            f"🌊 Starting wave processing: {len(signals)} signals at "
            f"timestamp {wave_id}"
        )

        # ✅ ГЛАВНОЕ ИЗМЕНЕНИЕ: используем try-except с continue
        # Based on: Freqtrade pattern for batch processing
        for idx, signal in enumerate(signals, 1):
            symbol = signal.get('symbol', signal.get('pair_symbol', 'UNKNOWN'))

            try:
                logger.debug(f"Processing signal {idx}/{len(signals)}: {symbol}")

                # Проверяем на дубликаты
                is_duplicate, reason = await self._is_duplicate(signal, wave_id)

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

                # Обрабатываем сигнал
                result = await self._process_single_signal(signal, wave_id)

                if result:
                    successful_signals.append({
                        'signal_number': idx,
                        'symbol': symbol,
                        'result': result,
                        'signal_data': signal  # Добавляем оригинальный сигнал для последующего исполнения
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
            'success_rate': len(successful_signals) / len(signals) if signals else 0
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

            current_price = ticker.get('last') or ticker.get('close', 0)
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
            # FIX: 2025-10-03 - CRITICAL: Modify original signal to ensure SignalProcessor gets correct action
            # Используем ту же логику что в SignalProcessor (signal_type или recommended_action)
            action = signal.get('signal_type') or signal.get('recommended_action') or signal.get('action')

            # CRITICAL FIX: Modify the original signal so SignalProcessor gets the correct action
            if action and not signal.get('action'):
                signal['action'] = action
                logger.debug(f"Signal #{signal.get('id', 'unknown')} action set to: {action}")

            # Also ensure signal_type is set for SignalProcessor validation
            if action and not signal.get('signal_type'):
                signal['signal_type'] = action

            # Return processing result
            return {
                'symbol': signal.get('symbol', signal.get('pair_symbol', '')),
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
                'waves_processed': len(self.wave_stats)
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
        logger.info("Wave processor statistics reset")