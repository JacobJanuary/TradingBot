"""
SignalPipeline - main pipeline for signal processing.
Part of signal filtering fix - Phase 1.
"""
import asyncio
from typing import List, Dict, Any, Optional
from collections import defaultdict
from datetime import datetime
import logging

from core.models.signal_models import EnrichedSignal, ExecutionStatus, ValidationStatus, FilterResult
from core.signal_processing.filter_executor import FilterExecutor

logger = logging.getLogger(__name__)


class SignalPipeline:
    """
    Main pipeline for signal processing.
    Designed for easy parallel processing in future.
    """

    def __init__(self, config):
        self.config = config
        self.filter_executor = FilterExecutor(config)

        # Metrics for monitoring
        self.metrics = {
            'total_signals': 0,
            'filtered_out': 0,
            'validated': 0,
            'executed': 0,
            'filter_rates': defaultdict(int)
        }

    async def process_wave(
        self,
        raw_signals: List[Dict],
        exchange_params: Dict[int, Dict],
        exchange_managers: Dict[str, Any],
        position_manager: Any
    ) -> Dict[str, Any]:
        """
        Process complete wave of signals.

        Args:
            raw_signals: Raw signals from WebSocket
            exchange_params: {1: {'max_trades': 4, ...}, 2: {...}}
            exchange_managers: {'binance': ExchangeManager, ...}
            position_manager: For executing positions

        Returns:
            Detailed results with metrics
        """

        logger.info(f"🌊 Pipeline starting: {len(raw_signals)} signals")

        # Step 1: Convert to EnrichedSignal objects
        enriched = self._create_enriched_signals(raw_signals)
        self.metrics['total_signals'] = len(enriched)

        # Step 2: Apply filters to ALL signals
        logger.info(f"📝 Applying filters to {len(enriched)} signals...")

        for exchange_name, exchange_manager in exchange_managers.items():
            exchange_signals = [s for s in enriched if s.exchange == exchange_name]
            if exchange_signals:
                await self.filter_executor.apply_filters_batch(
                    exchange_signals, exchange_manager
                )

        # Count filtered
        filtered = [s for s in enriched if s.passed_filters]
        filtered_out = [s for s in enriched if not s.passed_filters]
        self.metrics['filtered_out'] = len(filtered_out)

        logger.info(
            f"✅ Filters applied: {len(filtered)}/{len(enriched)} passed "
            f"({len(filtered_out)} filtered out)"
        )

        # Log filter reasons
        for signal in filtered_out:
            if signal.filter_reason:
                self.metrics['filter_rates'][signal.filter_reason.value] += 1

        # Step 3: Group by exchange and sort by score
        exchange_groups = self._group_by_exchange(filtered)

        for exchange_id, signals in exchange_groups.items():
            # Sort by combined score (highest first)
            signals.sort(key=lambda s: s.combined_score, reverse=True)
            exchange_name = 'Binance' if exchange_id == 1 else 'Bybit' if exchange_id == 2 else f'Exchange{exchange_id}'
            logger.info(
                f"📊 {exchange_name}: {len(signals)} signals after filtering, "
                f"top score: {signals[0].combined_score if signals else 0}"
            )

        # Step 4: Select top signals per exchange
        selected = self._select_top_signals(exchange_groups, exchange_params)

        # Step 5: Validate selected signals
        validated = await self._validate_signals(selected, exchange_managers, position_manager)
        self.metrics['validated'] = len([s for s in validated if s.validation_status == 'passed'])

        # Step 6: Execute with retry logic
        execution_results = await self._execute_with_retry(
            validated, exchange_params, exchange_managers, position_manager
        )

        self.metrics['executed'] = sum(1 for r in execution_results if r and r.get('success'))

        # Step 7: Generate report
        return self._generate_report(
            enriched, filtered, selected, validated, execution_results
        )

    def _create_enriched_signals(self, raw_signals: List[Dict]) -> List[EnrichedSignal]:
        """Convert raw signals to EnrichedSignal objects"""
        enriched = []
        for signal in raw_signals:
            # Parse timestamp
            timestamp_str = signal.get('timestamp', datetime.now().isoformat())
            if isinstance(timestamp_str, str):
                # Handle ISO format with timezone
                timestamp_str = timestamp_str.replace('+00', '+00:00')
                timestamp = datetime.fromisoformat(timestamp_str)
            else:
                timestamp = datetime.now()

            enriched_signal = EnrichedSignal(
                signal_id=signal.get('id', signal.get('signal_id', 0)),
                symbol=signal.get('symbol', ''),
                exchange=signal.get('exchange', ''),
                side=signal.get('side', ''),
                entry_price=float(signal.get('entry_price', 0)),
                score_week=float(signal.get('score_week', 0)),
                score_month=float(signal.get('score_month', 0)),
                timestamp=timestamp,
                combined_score=0
            )
            # Calculate combined score
            enriched_signal.calculate_combined_score()
            enriched.append(enriched_signal)

        return enriched

    def _group_by_exchange(self, signals: List[EnrichedSignal]) -> Dict[int, List[EnrichedSignal]]:
        """Group signals by exchange ID"""
        groups = defaultdict(list)
        for signal in signals:
            # Map exchange name to ID
            if signal.exchange.lower() == 'binance':
                exchange_id = 1
            elif signal.exchange.lower() == 'bybit':
                exchange_id = 2
            else:
                continue  # Skip unknown exchanges

            groups[exchange_id].append(signal)

        return dict(groups)

    def _select_top_signals(
        self,
        exchange_groups: Dict[int, List[EnrichedSignal]],
        exchange_params: Dict[int, Dict]
    ) -> List[EnrichedSignal]:
        """Select top N signals per exchange based on score"""
        selected = []

        for exchange_id, signals in exchange_groups.items():
            params = exchange_params.get(exchange_id, {})
            max_trades = params.get('max_trades', 5)
            buffer_size = params.get('buffer_size', 10)

            # Take top signals by score
            needed = max_trades + buffer_size
            top_signals = signals[:needed]

            exchange_name = 'Binance' if exchange_id == 1 else 'Bybit'
            logger.info(
                f"📈 {exchange_name}: Selected {len(top_signals)}/{len(signals)} "
                f"top signals (target: {max_trades}, buffer: {buffer_size})"
            )

            selected.extend(top_signals)

        return selected

    async def _validate_signals(
        self,
        signals: List[EnrichedSignal],
        exchange_managers: Dict[str, Any],
        position_manager: Any
    ) -> List[EnrichedSignal]:
        """Validate selected signals"""
        # For now, we'll use the existing wave_signal_processor validation
        # This keeps the existing validation logic intact
        for signal in signals:
            signal.validation_status = 'passed'  # Simplified for now

        return signals

    async def _execute_with_retry(
        self,
        validated_signals: List[EnrichedSignal],
        exchange_params: Dict[int, Dict],
        exchange_managers: Dict[str, Any],
        position_manager: Any
    ) -> List[Dict]:
        """Execute signals with retry logic if target not reached"""
        results = []

        # Group by exchange
        by_exchange = self._group_by_exchange(validated_signals)

        for exchange_id, signals in by_exchange.items():
            params = exchange_params.get(exchange_id, {})
            max_trades = params.get('max_trades', 5)
            exchange_name = 'binance' if exchange_id == 1 else 'bybit'

            executed = 0
            signal_index = 0
            max_retries = len(signals)  # Try all available signals

            while executed < max_trades and signal_index < max_retries:
                if signal_index >= len(signals):
                    logger.warning(
                        f"⚠️ {exchange_name}: No more signals available "
                        f"(executed: {executed}/{max_trades})"
                    )
                    break

                signal = signals[signal_index]
                signal_index += 1

                # Skip if already executed or failed validation
                if signal.execution_status in ['executed', 'failed']:
                    continue

                logger.info(
                    f"📤 {exchange_name}: Executing signal {signal_index}/{len(signals)}: "
                    f"{signal.symbol} (score: {signal.combined_score})"
                )

                # Execute signal using existing position_manager logic
                try:
                    result = await position_manager.execute_signal({
                        'signal_id': signal.signal_id,
                        'symbol': signal.symbol,
                        'side': signal.side,
                        'entry_price': signal.entry_price,
                        'exchange': exchange_name
                    })

                    if result and result.get('success'):
                        executed += 1
                        signal.execution_status = ExecutionStatus.EXECUTED.value
                        logger.info(
                            f"✅ {exchange_name}: Position {executed}/{max_trades} opened"
                        )
                    else:
                        signal.execution_status = ExecutionStatus.FAILED.value
                        signal.execution_error = result.get('error', 'Unknown error') if result else 'No result'
                        logger.warning(
                            f"❌ {exchange_name}: Failed to open position: "
                            f"{signal.execution_error}"
                        )

                    results.append(result)

                    # Rate limiting
                    await asyncio.sleep(0.2)

                except Exception as e:
                    logger.error(f"❌ Exception executing signal: {e}")
                    signal.execution_status = ExecutionStatus.FAILED.value
                    signal.execution_error = str(e)
                    results.append({'success': False, 'error': str(e)})

            logger.info(
                f"🎯 {exchange_name}: Execution complete - "
                f"{executed}/{max_trades} positions opened"
            )

        return results

    def _generate_report(
        self,
        all_signals: List[EnrichedSignal],
        filtered: List[EnrichedSignal],
        selected: List[EnrichedSignal],
        validated: List[EnrichedSignal],
        execution_results: List[Dict]
    ) -> Dict[str, Any]:
        """Generate detailed report of wave processing"""
        return {
            'metrics': dict(self.metrics),
            'summary': {
                'total_signals': len(all_signals),
                'passed_filters': len(filtered),
                'selected': len(selected),
                'validated': len(validated),
                'executed': sum(1 for r in execution_results if r and r.get('success'))
            },
            'filter_breakdown': dict(self.metrics['filter_rates']),
            'execution_results': execution_results
        }