# 📋 ДЕТАЛЬНЫЙ ПЛАН ИСПРАВЛЕНИЯ ФИЛЬТРАЦИИ СИГНАЛОВ

**Дата**: 2025-11-01
**Приоритет**: 🔴 CRITICAL - прямое влияние на прибыль
**Оценка времени**: 8-12 часов
**Риск**: MEDIUM - изменение core логики обработки сигналов

---

## 🎯 ЦЕЛЬ ИЗМЕНЕНИЙ

### Текущее состояние (НЕПРАВИЛЬНО):
```
Получить сигналы → Отобрать N штук → Применить фильтры → Валидировать → Выполнить
                    ↑ ПРОБЛЕМА: берем первые попавшиеся
```

### Целевое состояние (ПРАВИЛЬНО):
```
Получить сигналы → Применить фильтры → Сортировать по score → Отобрать N лучших → Валидировать → Выполнить с retry
```

---

## 🏗️ АРХИТЕКТУРА РЕШЕНИЯ

### Новая структура данных для сигнала:
```python
@dataclass
class EnrichedSignal:
    """Сигнал с дополнительными метаданными для фильтрации"""
    # Original signal data
    signal_id: int
    symbol: str
    exchange: str
    side: str
    entry_price: float
    score_week: float
    score_month: float
    timestamp: datetime

    # Enriched metadata (populated during filtering)
    combined_score: float  # score_week + score_month
    open_interest_usdt: Optional[float] = None
    volume_1h_usdt: Optional[float] = None

    # Filter results
    passed_filters: bool = False
    filter_reason: Optional[str] = None
    filter_details: Dict[str, Any] = field(default_factory=dict)

    # Execution tracking
    validation_status: Optional[str] = None  # 'pending', 'passed', 'failed'
    execution_status: Optional[str] = None   # 'pending', 'executed', 'failed'
    execution_error: Optional[str] = None
```

### Новый класс для управления pipeline:
```python
class SignalPipeline:
    """
    Управляет полным pipeline обработки сигналов.
    Designed for future parallel processing.
    """

    def __init__(self):
        self.filter_executor = FilterExecutor()  # Применяет фильтры
        self.signal_validator = SignalValidator()  # Валидирует
        self.signal_executor = SignalExecutor()    # Выполняет

    async def process_wave(
        self,
        signals: List[Dict],
        exchange_params: Dict[str, Dict]
    ) -> Dict:
        """Main pipeline entry point"""

        # Step 1: Enrich all signals
        enriched_signals = await self._enrich_signals(signals)

        # Step 2: Apply filters to ALL signals
        filtered_signals = await self._apply_filters_batch(enriched_signals)

        # Step 3: Group by exchange and sort by score
        exchange_groups = self._group_and_sort(filtered_signals)

        # Step 4: Select best signals per exchange
        selected = self._select_top_signals(exchange_groups, exchange_params)

        # Step 5: Validate selected
        validated = await self._validate_batch(selected)

        # Step 6: Execute with retry logic
        results = await self._execute_with_retry(validated, exchange_params)

        return results
```

---

## 📝 PHASE 1: ПОДГОТОВКА И РЕФАКТОРИНГ (3 часа)

### 1.1 Создание новых структур данных

**Файл**: `core/models/signal_models.py` (НОВЫЙ)
```python
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
from decimal import Decimal
from enum import Enum

class FilterResult(Enum):
    PASSED = "passed"
    LOW_OI = "low_open_interest"
    LOW_VOLUME = "low_volume"
    DUPLICATE = "duplicate_position"
    OVERHEATED = "price_overheated"
    MARKET_CLOSED = "market_closed"

class ValidationStatus(Enum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"

class ExecutionStatus(Enum):
    PENDING = "pending"
    EXECUTED = "executed"
    FAILED = "failed"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    POSITION_SIZE_ERROR = "position_size_error"

@dataclass
class EnrichedSignal:
    # ... (как описано выше)

    def calculate_combined_score(self) -> float:
        """Calculate combined score for sorting"""
        self.combined_score = self.score_week + self.score_month
        return self.combined_score

    def to_dict(self) -> Dict:
        """Convert to dict for logging/storage"""
        return {
            'signal_id': self.signal_id,
            'symbol': self.symbol,
            'exchange': self.exchange,
            'combined_score': self.combined_score,
            'passed_filters': self.passed_filters,
            'filter_reason': self.filter_reason,
            'validation_status': self.validation_status,
            'execution_status': self.execution_status
        }
```

### 1.2 Создание FilterExecutor

**Файл**: `core/signal_processing/filter_executor.py` (НОВЫЙ)
```python
class FilterExecutor:
    """Applies all filters to signals BEFORE selection"""

    def __init__(self, config: TradingConfig):
        self.config = config
        self.min_oi = config.signal_min_open_interest_usdt
        self.min_volume = config.signal_min_volume_1h_usdt
        self.max_price_change = config.signal_max_price_change_5min_percent

        # Cache for API calls (OI, volume)
        self.oi_cache: Dict[str, Tuple[float, datetime]] = {}
        self.volume_cache: Dict[str, Tuple[float, datetime]] = {}
        self.cache_ttl = 60  # seconds

    async def apply_filters_batch(
        self,
        signals: List[EnrichedSignal],
        exchange_manager: ExchangeManager
    ) -> List[EnrichedSignal]:
        """
        Apply filters to ALL signals in parallel.
        Returns list with passed_filters flag set.
        """

        # Step 1: Fetch all OI and volume data in parallel
        await self._prefetch_market_data(signals, exchange_manager)

        # Step 2: Apply filters to each signal
        tasks = [
            self._apply_filters_single(signal, exchange_manager)
            for signal in signals
        ]

        # Process in batches to avoid overwhelming API
        batch_size = 10
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i+batch_size]
            await asyncio.gather(*batch)

        # Step 3: Mark duplicates
        self._mark_duplicate_positions(signals)

        return signals

    async def _prefetch_market_data(
        self,
        signals: List[EnrichedSignal],
        exchange_manager: ExchangeManager
    ):
        """Prefetch OI and volume for all signals to optimize API calls"""

        # Group by exchange for batch API calls
        by_exchange = defaultdict(list)
        for signal in signals:
            by_exchange[signal.exchange].append(signal.symbol)

        # Fetch in parallel per exchange
        tasks = []
        for exchange, symbols in by_exchange.items():
            tasks.append(self._fetch_exchange_data(exchange, symbols, exchange_manager))

        await asyncio.gather(*tasks)

    async def _apply_filters_single(
        self,
        signal: EnrichedSignal,
        exchange_manager: ExchangeManager
    ) -> None:
        """Apply all filters to a single signal"""

        # Get cached data
        oi = self._get_cached_oi(signal.symbol)
        volume = self._get_cached_volume(signal.symbol)

        signal.open_interest_usdt = oi
        signal.volume_1h_usdt = volume

        # Check OI filter
        if oi and oi < self.min_oi:
            signal.passed_filters = False
            signal.filter_reason = FilterResult.LOW_OI
            signal.filter_details = {
                'oi_usdt': oi,
                'min_required': self.min_oi
            }
            return

        # Check volume filter
        if volume and volume < self.min_volume:
            signal.passed_filters = False
            signal.filter_reason = FilterResult.LOW_VOLUME
            signal.filter_details = {
                'volume_1h_usdt': volume,
                'min_required': self.min_volume
            }
            return

        # Check price change filter
        price_change = await self._get_price_change_5min(
            signal.symbol, signal.exchange, exchange_manager
        )
        if price_change and abs(price_change) > self.max_price_change:
            signal.passed_filters = False
            signal.filter_reason = FilterResult.OVERHEATED
            signal.filter_details = {
                'price_change_5m': price_change,
                'max_allowed': self.max_price_change
            }
            return

        # All filters passed
        signal.passed_filters = True
        signal.filter_reason = FilterResult.PASSED
```

### 1.3 Создание SignalPipeline

**Файл**: `core/signal_processing/signal_pipeline.py` (НОВЫЙ)
```python
class SignalPipeline:
    """
    Main pipeline for signal processing.
    Designed for easy parallel processing in future.
    """

    def __init__(self, config: TradingConfig):
        self.config = config
        self.filter_executor = FilterExecutor(config)
        self.signal_validator = SignalValidator(config)
        self.signal_executor = SignalExecutor(config)

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
        exchange_managers: Dict[str, ExchangeManager],
        position_manager: PositionManager
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
            self.metrics['filter_rates'][signal.filter_reason.value] += 1

        # Step 3: Group by exchange and sort by score
        exchange_groups = self._group_by_exchange(filtered)

        for exchange_id, signals in exchange_groups.items():
            # Sort by combined score (highest first)
            signals.sort(key=lambda s: s.combined_score, reverse=True)
            logger.info(
                f"📊 Exchange {exchange_id}: {len(signals)} signals after filtering, "
                f"top score: {signals[0].combined_score if signals else 0}"
            )

        # Step 4: Select top signals per exchange
        selected = self._select_top_signals(exchange_groups, exchange_params)

        # Step 5: Validate selected signals
        validated = await self._validate_signals(selected, exchange_managers)
        self.metrics['validated'] = len([s for s in validated if s.validation_status == 'passed'])

        # Step 6: Execute with retry logic
        execution_results = await self._execute_with_retry(
            validated, exchange_params, exchange_managers, position_manager
        )

        self.metrics['executed'] = len([
            r for r in execution_results if r.get('success')
        ])

        # Step 7: Generate report
        return self._generate_report(
            enriched, filtered, selected, validated, execution_results
        )

    def _select_top_signals(
        self,
        exchange_groups: Dict[int, List[EnrichedSignal]],
        exchange_params: Dict[int, Dict]
    ) -> List[EnrichedSignal]:
        """
        Select top N signals per exchange based on score.
        """
        selected = []

        for exchange_id, signals in exchange_groups.items():
            params = exchange_params.get(exchange_id, {})
            max_trades = params.get('max_trades', 5)
            buffer_size = params.get('buffer_size', 10)

            # Take top signals by score
            needed = max_trades + buffer_size
            top_signals = signals[:needed]

            logger.info(
                f"📈 Exchange {exchange_id}: Selected {len(top_signals)}/{len(signals)} "
                f"top signals (target: {max_trades}, buffer: {buffer_size})"
            )

            selected.extend(top_signals)

        return selected

    async def _execute_with_retry(
        self,
        validated_signals: List[EnrichedSignal],
        exchange_params: Dict[int, Dict],
        exchange_managers: Dict[str, ExchangeManager],
        position_manager: PositionManager
    ) -> List[Dict]:
        """
        Execute signals with retry logic if target not reached.
        """
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

                # Execute signal
                try:
                    result = await position_manager.execute_signal({
                        'signal_id': signal.signal_id,
                        'symbol': signal.symbol,
                        'side': signal.side,
                        'entry_price': signal.entry_price
                    })

                    if result and result.get('success'):
                        executed += 1
                        signal.execution_status = ExecutionStatus.EXECUTED
                        logger.info(
                            f"✅ {exchange_name}: Position {executed}/{max_trades} opened"
                        )
                    else:
                        signal.execution_status = ExecutionStatus.FAILED
                        signal.execution_error = result.get('error', 'Unknown error')
                        logger.warning(
                            f"❌ {exchange_name}: Failed to open position: "
                            f"{signal.execution_error}"
                        )

                    results.append(result)

                    # Rate limiting
                    await asyncio.sleep(0.2)

                except Exception as e:
                    logger.error(f"❌ Exception executing signal: {e}")
                    signal.execution_status = ExecutionStatus.FAILED
                    signal.execution_error = str(e)

            logger.info(
                f"🎯 {exchange_name}: Execution complete - "
                f"{executed}/{max_trades} positions opened"
            )

        return results
```

---

## 📝 PHASE 2: ИНТЕГРАЦИЯ В СУЩЕСТВУЮЩИЙ КОД (3 часа)

### 2.1 Модификация signal_processor_websocket.py

**Изменения в `process_signals_per_exchange_with_logic()`**:

```python
async def process_signals_per_exchange_with_logic(
    self,
    signals: List[Dict],
    wave_timestamp: datetime
) -> Dict[str, Any]:
    """
    NEW: Use SignalPipeline for processing
    """

    # Initialize pipeline if not exists
    if not hasattr(self, 'signal_pipeline'):
        self.signal_pipeline = SignalPipeline(self.config)

    # Get exchange parameters
    exchange_params = {}
    for exchange_id in [1, 2]:  # Binance, Bybit
        params = await self._get_exchange_params(exchange_id)
        exchange_params[exchange_id] = params

    # Get exchange managers
    exchange_managers = {
        'binance': self.position_manager.exchange_managers.get('binance'),
        'bybit': self.position_manager.exchange_managers.get('bybit')
    }

    # Process through pipeline
    results = await self.signal_pipeline.process_wave(
        raw_signals=signals,
        exchange_params=exchange_params,
        exchange_managers=exchange_managers,
        position_manager=self.position_manager
    )

    # Log results
    logger.info(
        f"🌊 Wave complete: "
        f"{results['metrics']['executed']}/{results['metrics']['total_signals']} executed, "
        f"{results['metrics']['filtered_out']} filtered, "
        f"Filter rates: {dict(results['metrics']['filter_rates'])}"
    )

    return results
```

### 2.2 Удаление старой логики фильтрации

**В wave_signal_processor.py** - переместить фильтры в FilterExecutor:
- Удалить методы `_should_skip_signal()`, `_fetch_open_interest_usdt()`, `_fetch_1h_volume_usdt()`
- Логика переезжает в `FilterExecutor`

---

## 📝 PHASE 3: ТЕСТИРОВАНИЕ (2 часа)

### 3.1 Unit Tests

**Файл**: `tests/test_signal_pipeline.py` (НОВЫЙ)

```python
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime
from core.signal_processing.signal_pipeline import SignalPipeline
from core.models.signal_models import EnrichedSignal

class TestSignalPipeline:

    @pytest.fixture
    def pipeline(self):
        config = Mock()
        config.signal_min_open_interest_usdt = 500_000
        config.signal_min_volume_1h_usdt = 20_000
        return SignalPipeline(config)

    @pytest.fixture
    def sample_signals(self):
        """Create sample signals with various characteristics"""
        return [
            # Good signal - should pass all filters
            {
                'signal_id': 1,
                'symbol': 'BTCUSDT',
                'exchange': 'binance',
                'score_week': 80,
                'score_month': 75
            },
            # Low OI signal - should be filtered
            {
                'signal_id': 2,
                'symbol': 'SHITCOIN',
                'exchange': 'binance',
                'score_week': 90,
                'score_month': 85
            },
            # Low volume signal - should be filtered
            {
                'signal_id': 3,
                'symbol': 'LOWVOL',
                'exchange': 'bybit',
                'score_week': 70,
                'score_month': 65
            }
        ]

    @pytest.mark.asyncio
    async def test_filter_application(self, pipeline, sample_signals):
        """Test that filters are applied to ALL signals"""

        # Mock exchange data
        with patch.object(pipeline.filter_executor, '_get_cached_oi') as mock_oi:
            with patch.object(pipeline.filter_executor, '_get_cached_volume') as mock_vol:

                # Setup mock returns
                mock_oi.side_effect = [1_000_000, 100_000, 600_000]  # Low OI for signal 2
                mock_vol.side_effect = [100_000, 50_000, 10_000]  # Low volume for signal 3

                # Convert to enriched signals
                enriched = pipeline._create_enriched_signals(sample_signals)

                # Apply filters
                await pipeline.filter_executor.apply_filters_batch(
                    enriched, Mock()
                )

                # Check results
                assert enriched[0].passed_filters == True  # Good signal
                assert enriched[1].passed_filters == False  # Low OI
                assert enriched[1].filter_reason == FilterResult.LOW_OI
                assert enriched[2].passed_filters == False  # Low volume
                assert enriched[2].filter_reason == FilterResult.LOW_VOLUME

    @pytest.mark.asyncio
    async def test_signal_sorting_by_score(self, pipeline):
        """Test that signals are sorted by combined score"""

        signals = [
            EnrichedSignal(
                signal_id=1, symbol='A', exchange='binance',
                score_week=60, score_month=60, combined_score=120
            ),
            EnrichedSignal(
                signal_id=2, symbol='B', exchange='binance',
                score_week=80, score_month=70, combined_score=150
            ),
            EnrichedSignal(
                signal_id=3, symbol='C', exchange='binance',
                score_week=70, score_month=65, combined_score=135
            )
        ]

        # All passed filters
        for s in signals:
            s.passed_filters = True

        # Group and sort
        groups = pipeline._group_by_exchange(signals)

        # Check sorting
        binance_signals = groups[1]  # exchange_id=1 for binance
        assert binance_signals[0].signal_id == 2  # Highest score
        assert binance_signals[1].signal_id == 3  # Middle score
        assert binance_signals[2].signal_id == 1  # Lowest score

    @pytest.mark.asyncio
    async def test_retry_logic(self, pipeline):
        """Test that retry logic works when target not reached"""

        # Create 10 validated signals
        signals = [
            EnrichedSignal(
                signal_id=i,
                symbol=f'SYM{i}',
                exchange='binance',
                combined_score=100-i,
                validation_status='passed'
            )
            for i in range(10)
        ]

        # Mock position_manager that fails first 3 attempts
        position_manager = Mock()
        position_manager.execute_signal = AsyncMock()
        position_manager.execute_signal.side_effect = [
            None,  # Fail 1
            None,  # Fail 2
            None,  # Fail 3
            {'success': True, 'position_id': 1},  # Success 1
            {'success': True, 'position_id': 2},  # Success 2
            {'success': True, 'position_id': 3},  # Success 3
            {'success': True, 'position_id': 4},  # Success 4
        ]

        # Execute with target=4
        exchange_params = {1: {'max_trades': 4}}
        results = await pipeline._execute_with_retry(
            signals, exchange_params,
            {'binance': Mock()}, position_manager
        )

        # Should have tried 7 signals to get 4 successes
        assert position_manager.execute_signal.call_count == 7
        assert len([r for r in results if r and r.get('success')]) == 4
```

### 3.2 Integration Tests

**Файл**: `tests/integration/test_signal_processing_integration.py` (НОВЫЙ)

```python
class TestSignalProcessingIntegration:

    @pytest.mark.asyncio
    async def test_full_pipeline_with_filters(self):
        """Test complete pipeline from raw signals to execution"""

        # Create 50 test signals with various characteristics
        raw_signals = []
        for i in range(50):
            raw_signals.append({
                'id': i,
                'symbol': f'TOKEN{i}USDT',
                'exchange': 'binance' if i < 40 else 'bybit',
                'side': 'BUY' if i % 2 == 0 else 'SELL',
                'entry_price': 100 + i,
                'score_week': 50 + (i % 40),
                'score_month': 45 + (i % 35),
                'timestamp': datetime.now().isoformat()
            })

        # Setup pipeline with config
        config = TradingConfig()
        config.signal_min_open_interest_usdt = 500_000
        config.signal_min_volume_1h_usdt = 20_000

        pipeline = SignalPipeline(config)

        # Mock exchange managers with varying OI/volume
        exchange_manager = Mock()

        # 30% will fail OI filter
        # 20% will fail volume filter
        # 50% will pass

        # ... setup mocks ...

        # Process wave
        results = await pipeline.process_wave(
            raw_signals,
            {1: {'max_trades': 4}, 2: {'max_trades': 5}},
            {'binance': exchange_manager, 'bybit': exchange_manager},
            Mock()  # position_manager
        )

        # Verify results
        assert results['metrics']['total_signals'] == 50
        assert results['metrics']['filtered_out'] > 0
        assert results['metrics']['filter_rates']['low_open_interest'] > 0
        assert results['metrics']['filter_rates']['low_volume'] > 0
```

### 3.3 Monkey Testing

**Файл**: `tests/monkey/test_signal_chaos.py` (НОВЫЙ)

```python
class TestSignalChaos:
    """Chaos/monkey testing for signal processing"""

    @pytest.mark.asyncio
    async def test_random_filter_failures(self):
        """Test with random filter failures"""

        import random

        for iteration in range(100):
            # Generate random number of signals
            num_signals = random.randint(1, 100)

            # Random filter pass rate
            filter_pass_rate = random.random()

            # Random targets
            binance_target = random.randint(1, 10)
            bybit_target = random.randint(1, 10)

            # Create signals
            signals = self._generate_random_signals(num_signals)

            # Setup pipeline with random failures
            pipeline = self._setup_chaos_pipeline(filter_pass_rate)

            # Process and verify invariants
            results = await pipeline.process_wave(signals, ...)

            # Invariants that must always hold:
            assert results['metrics']['executed'] <= results['metrics']['validated']
            assert results['metrics']['validated'] <= results['metrics']['total_signals']
            assert results['metrics']['filtered_out'] + len(results['filtered_signals']) == num_signals

            # Target should be reached IF enough signals passed filters
            if results['filtered_count']['binance'] >= binance_target:
                assert results['executed']['binance'] == binance_target
```

---

## 📝 PHASE 4: МОНИТОРИНГ И МЕТРИКИ (1 час)

### 4.1 Добавление метрик

**Файл**: `core/signal_processing/metrics.py` (НОВЫЙ)

```python
class SignalMetrics:
    """Track metrics for signal processing pipeline"""

    def __init__(self):
        self.reset()

    def reset(self):
        self.wave_metrics = []
        self.filter_stats = defaultdict(lambda: {'count': 0, 'rate': 0.0})
        self.execution_stats = defaultdict(lambda: {'attempts': 0, 'success': 0})

    def record_wave(self, wave_result: Dict):
        """Record metrics from wave processing"""

        metrics = {
            'timestamp': datetime.now(),
            'total_signals': wave_result['metrics']['total_signals'],
            'filtered_out': wave_result['metrics']['filtered_out'],
            'filter_rate': wave_result['metrics']['filtered_out'] / wave_result['metrics']['total_signals'],
            'validated': wave_result['metrics']['validated'],
            'executed': wave_result['metrics']['executed'],
            'success_rate': wave_result['metrics']['executed'] / wave_result['metrics']['validated']
            if wave_result['metrics']['validated'] > 0 else 0
        }

        self.wave_metrics.append(metrics)

        # Update filter stats
        for reason, count in wave_result['metrics']['filter_rates'].items():
            self.filter_stats[reason]['count'] += count

        # Calculate rolling averages
        self._calculate_rolling_metrics()

    def _calculate_rolling_metrics(self):
        """Calculate rolling averages for adaptive buffer sizing"""

        if len(self.wave_metrics) >= 10:
            recent = self.wave_metrics[-10:]

            avg_filter_rate = sum(m['filter_rate'] for m in recent) / len(recent)
            avg_success_rate = sum(m['success_rate'] for m in recent) / len(recent)

            # Adaptive buffer recommendation
            if avg_filter_rate > 0.3:
                logger.warning(
                    f"⚠️ High filter rate: {avg_filter_rate:.1%} - "
                    f"consider increasing buffer size"
                )

            return {
                'avg_filter_rate': avg_filter_rate,
                'avg_success_rate': avg_success_rate,
                'recommended_buffer_multiplier': 1 + avg_filter_rate
            }

    def get_summary(self) -> Dict:
        """Get summary of metrics"""

        if not self.wave_metrics:
            return {}

        return {
            'waves_processed': len(self.wave_metrics),
            'total_signals': sum(m['total_signals'] for m in self.wave_metrics),
            'total_filtered': sum(m['filtered_out'] for m in self.wave_metrics),
            'total_executed': sum(m['executed'] for m in self.wave_metrics),
            'avg_filter_rate': sum(m['filter_rate'] for m in self.wave_metrics) / len(self.wave_metrics),
            'filter_reasons': dict(self.filter_stats),
            'last_10_waves': self.wave_metrics[-10:] if len(self.wave_metrics) >= 10 else self.wave_metrics
        }
```

### 4.2 Добавление логирования

**Структурированное логирование для анализа**:

```python
# В SignalPipeline
async def process_wave(self, ...):

    # Structured logging for analysis
    wave_id = f"wave_{datetime.now().timestamp()}"

    logger.info(f"🌊 [WAVE_START] {wave_id}: {len(raw_signals)} signals")

    # After filtering
    logger.info(
        f"📊 [WAVE_FILTER] {wave_id}: "
        f"passed={len(filtered)}, "
        f"filtered={len(filtered_out)}, "
        f"reasons={Counter(s.filter_reason for s in filtered_out)}"
    )

    # After selection
    logger.info(
        f"📈 [WAVE_SELECT] {wave_id}: "
        f"selected={len(selected)}, "
        f"by_exchange={Counter(s.exchange for s in selected)}"
    )

    # After execution
    logger.info(
        f"✅ [WAVE_COMPLETE] {wave_id}: "
        f"executed={executed}, "
        f"failed={failed}, "
        f"targets_reached={targets_reached}"
    )
```

---

## 📝 PHASE 5: ROLLOUT И GIT (1 час)

### 5.1 Git Strategy

```bash
# Create feature branch
git checkout -b feature/signal-filtering-fix

# Phase 1 commit - Data structures
git add core/models/signal_models.py
git commit -m "feat: add EnrichedSignal model and enums for signal processing

- Add EnrichedSignal dataclass with metadata tracking
- Add FilterResult, ValidationStatus, ExecutionStatus enums
- Prepare for new signal processing pipeline"

# Phase 2 commit - Core components
git add core/signal_processing/filter_executor.py
git add core/signal_processing/signal_pipeline.py
git commit -m "feat: implement new signal filtering pipeline

- Add FilterExecutor for batch filter application
- Add SignalPipeline for complete processing flow
- Filters now applied BEFORE signal selection
- Signals sorted by combined score"

# Phase 3 commit - Integration
git add core/signal_processor_websocket.py
git add core/wave_signal_processor.py
git commit -m "refactor: integrate new signal pipeline

- Replace old filtering logic with SignalPipeline
- Remove redundant filter methods from wave_signal_processor
- Fix issue where filters were applied after selection"

# Phase 4 commit - Tests
git add tests/test_signal_pipeline.py
git add tests/integration/test_signal_processing_integration.py
git add tests/monkey/test_signal_chaos.py
git commit -m "test: add comprehensive tests for signal pipeline

- Unit tests for filter application and sorting
- Integration tests for full pipeline
- Chaos testing for edge cases
- Test retry logic and target achievement"

# Phase 5 commit - Metrics
git add core/signal_processing/metrics.py
git commit -m "feat: add metrics tracking for signal pipeline

- Track filter rates and execution success
- Calculate rolling averages
- Adaptive buffer size recommendations"

# Push and create PR
git push origin feature/signal-filtering-fix
```

### 5.2 Rollout План

#### Stage 1: Dev Environment (День 1)
```bash
# Deploy to dev
git checkout feature/signal-filtering-fix
python -m pytest tests/ -v

# Run with test data
python scripts/test_signal_pipeline.py --dry-run
```

#### Stage 2: Staging (День 2-3)
```bash
# Deploy to staging with monitoring
ENVIRONMENT=staging python main.py

# Monitor metrics
tail -f logs/signal_pipeline.log | grep WAVE_
```

#### Stage 3: Production Canary (День 4)
```bash
# Deploy to 1 instance only
# Monitor for 24 hours
# Check metrics:
# - Filter rate
# - Target achievement rate
# - Execution success rate
```

#### Stage 4: Full Production (День 5)
```bash
# If canary successful, full rollout
git checkout main
git merge feature/signal-filtering-fix
git push origin main
```

---

## 🔄 ПОДГОТОВКА К ПАРАЛЛЕЛЬНОЙ ОБРАБОТКЕ

### Архитектурные решения для будущей параллелизации:

1. **Независимые компоненты**:
   - FilterExecutor - stateless, может работать параллельно
   - SignalValidator - stateless для каждого сигнала
   - SignalExecutor - требует семафор для rate limiting

2. **Разделение по exchange**:
   - Binance и Bybit могут обрабатываться параллельно
   - Каждый exchange имеет свой rate limit

3. **Async-first design**:
   - Все методы async/await
   - Использование asyncio.gather() для batch операций

4. **Подготовленные точки параллелизации**:
```python
# Легко преобразуется в параллельную обработку:
async def process_exchanges_parallel(self, ...):
    tasks = []
    for exchange in ['binance', 'bybit']:
        tasks.append(self.process_exchange(exchange, ...))

    results = await asyncio.gather(*tasks)
    return self.merge_results(results)
```

---

## 📊 ОЖИДАЕМЫЕ РЕЗУЛЬТАТЫ

### Метрики до исправления:
- Filter rate: 22.7% overall (55.6% Bybit)
- Target achievement: 88.9% (Binance 100%, Bybit 80%)
- Позиций упущено: ~1 на волну

### Метрики после исправления:
- Filter rate: тот же (но учтен в отборе)
- Target achievement: >95% (при достаточном количестве сигналов)
- Позиций упущено: 0

### ROI:
- Дополнительно ~1 позиция на волну
- ~20% увеличение позиций для Bybit
- Потенциально +15-20% к общей прибыли

---

## ⚠️ РИСКИ И МИТИГАЦИЯ

| Риск | Вероятность | Влияние | Митигация |
|------|------------|---------|-----------|
| Regression bugs | Medium | High | Comprehensive tests, staged rollout |
| API rate limits | Low | Medium | Batch operations, caching |
| Memory usage | Low | Low | Stream processing for large volumes |
| Wrong signal selection | Low | High | Sort by score, extensive testing |

---

## ✅ DEFINITION OF DONE

- [ ] Все тесты проходят (unit, integration, chaos)
- [ ] Filter rate metrics собираются
- [ ] Target achievement rate > 95%
- [ ] Логи структурированы для анализа
- [ ] Rollback план готов
- [ ] Documentation обновлена
- [ ] Code review пройден
- [ ] Staging тестирование 48 часов
- [ ] Production canary 24 часа успешно

---

**План готов к выполнению!**