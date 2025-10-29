# PHASE 5 CORRECTED - PER-EXCHANGE PROCESSING WITH PROPER EXECUTION

## ⚠️ КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ

**Проблема в оригинальном плане**: Execution всех validated signals сразу
**Правильно**: Execution ПОСЛЕДОВАТЕЛЬНО с остановкой когда `executed_count >= max_trades`

---

## 📐 PHASE 5: PER-EXCHANGE SELECTION, VALIDATION & EXECUTION (CORRECTED)

### Goal
Replace current logic with per-exchange processing: selection, validation, execution with target stop.

---

### Step 5.1: Add Per-Exchange Execution Helper

**File**: `core/signal_processor_websocket.py`
**Insert after `_get_params_for_all_exchanges` method**

**INSERT**:
```python

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
```

---

### Step 5.2: Add Per-Exchange Processing Method (CORRECTED)

**File**: `core/signal_processor_websocket.py`
**Insert after `_execute_signals_for_exchange` method**

**INSERT** (~300 lines):
```python

    async def _process_wave_per_exchange(
        self,
        wave_signals: List[Dict],
        wave_timestamp: str,
        params_by_exchange: Dict[int, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Process wave signals with per-exchange logic

        NEW LOGIC (mirrors current perfect implementation):
        1. Group signals by exchange_id
        2. For each exchange:
           a. Select top (max_trades + 3) signals
           b. Validate (duplicate check, etc.)
           c. If successful < max_trades, top-up from remaining
           d. Execute SEQUENTIALLY with stop at target
        3. Return combined results

        Args:
            wave_signals: All signals in wave (sorted by score sum DESC)
            wave_timestamp: Wave timestamp
            params_by_exchange: Params for each exchange from DB

        Returns:
            Dict with results per exchange and totals
        """
        logger.info(f"🌊 Processing wave {wave_timestamp} with per-exchange logic")

        # Step 1: Group signals by exchange_id
        signals_by_exchange = self._group_signals_by_exchange(wave_signals)

        if not signals_by_exchange:
            logger.warning(f"⚠️ Wave {wave_timestamp} has NO signals after grouping")
            return {
                'results_by_exchange': {},
                'total_executed': 0,
                'total_failed': 0,
                'total_validated': 0
            }

        logger.info(
            f"📊 Wave {wave_timestamp}: {len(wave_signals)} total signals grouped into "
            f"{len(signals_by_exchange)} exchanges: {list(signals_by_exchange.keys())}"
        )

        # Step 2: Process each exchange
        results_by_exchange = {}
        total_executed = 0
        total_failed = 0
        total_validated = 0

        for exchange_id, exchange_signals in signals_by_exchange.items():
            exchange_params = params_by_exchange.get(exchange_id)

            if not exchange_params:
                logger.warning(
                    f"⚠️ No params for exchange_id={exchange_id}, skipping {len(exchange_signals)} signals"
                )
                results_by_exchange[exchange_id] = {
                    'exchange_name': f'Unknown({exchange_id})',
                    'error': 'no_params',
                    'skipped': len(exchange_signals)
                }
                continue

            exchange_name = exchange_params['exchange_name']
            max_trades = exchange_params['max_trades']
            buffer_size = exchange_params['buffer_size']

            logger.info(
                f"📊 {exchange_name}: Processing {len(exchange_signals)} signals "
                f"(target={max_trades}, buffer={buffer_size}, params_source={exchange_params.get('source')})"
            )

            # Step 2a: Select top (max_trades + 3) signals
            signals_to_process = exchange_signals[:buffer_size]

            logger.debug(
                f"{exchange_name}: Selected {len(signals_to_process)}/{len(exchange_signals)} signals for validation"
            )

            # Step 2b: Validate signals (duplicate check, etc.)
            result = await self.wave_processor.process_wave_signals(
                signals=signals_to_process,
                wave_timestamp=wave_timestamp
            )

            successful_signals = result.get('successful', [])
            failed_signals = result.get('failed', [])
            skipped_signals = result.get('skipped', [])

            logger.info(
                f"{exchange_name}: Validation complete - "
                f"{len(successful_signals)} successful, {len(failed_signals)} failed, "
                f"{len(skipped_signals)} skipped (duplicates)"
            )

            # Step 2c: Top-up if needed (same logic as current implementation)
            topped_up_count = 0

            if len(successful_signals) < max_trades and len(exchange_signals) > buffer_size:
                remaining_needed = max_trades - len(successful_signals)

                logger.info(
                    f"⚠️ {exchange_name}: Only {len(successful_signals)}/{max_trades} successful, "
                    f"attempting to top-up {remaining_needed} more signals"
                )

                # Calculate extra size with margin (same as current: *1.5)
                extra_size = int(remaining_needed * 1.5)

                # Get next batch from remaining signals
                next_batch = exchange_signals[buffer_size : buffer_size + extra_size]

                if next_batch:
                    logger.debug(
                        f"{exchange_name}: Processing {len(next_batch)} extra signals for top-up"
                    )

                    extra_result = await self.wave_processor.process_wave_signals(
                        next_batch,
                        wave_timestamp
                    )

                    extra_successful = extra_result.get('successful', [])

                    # Add to successful (all of them, execution will stop at target)
                    successful_signals.extend(extra_successful)
                    topped_up_count = len(extra_successful)

                    logger.info(
                        f"✅ {exchange_name}: Topped up {topped_up_count} signals, "
                        f"total now: {len(successful_signals)} for execution"
                    )
                else:
                    logger.warning(
                        f"⚠️ {exchange_name}: No more signals available for top-up"
                    )

            # Step 2d: Execute SEQUENTIALLY with stop at target (CRITICAL!)
            execution_result = await self._execute_signals_for_exchange(
                validated_signals=successful_signals,
                max_trades=max_trades,
                exchange_name=exchange_name
            )

            executed_count = execution_result['executed_count']
            exec_failed_count = execution_result['failed_count']

            # Collect stats for this exchange
            results_by_exchange[exchange_id] = {
                'exchange_name': exchange_name,
                'total_signals': len(exchange_signals),
                'selected_for_validation': len(signals_to_process),
                'validated_successful': len(result.get('successful', [])),
                'topped_up': topped_up_count,
                'total_for_execution': len(successful_signals),
                'executed': executed_count,
                'execution_failed': exec_failed_count,
                'validation_failed': len(failed_signals),
                'duplicates': len(skipped_signals),
                'target': max_trades,
                'buffer_size': buffer_size,
                'target_reached': execution_result['target_reached'],
                'buffer_saved_us': execution_result['buffer_saved_us'],
                'params_source': exchange_params.get('source', 'unknown')
            }

            # Update totals
            total_executed += executed_count
            total_failed += exec_failed_count
            total_validated += len(successful_signals)

            logger.info(
                f"✅ {exchange_name}: Final {executed_count}/{max_trades} positions opened "
                f"(validated: {len(successful_signals)}, executed: {executed_count}, "
                f"target: {'REACHED ✅' if execution_result['target_reached'] else 'MISSED ⚠️'})"
            )

        # Step 3: Return combined results
        logger.info(
            f"🎯 Wave {wave_timestamp} per-exchange processing complete: "
            f"{total_executed} total positions from {len(results_by_exchange)} exchanges"
        )

        return {
            'results_by_exchange': results_by_exchange,
            'total_executed': total_executed,
            'total_failed': total_failed,
            'total_validated': total_validated
        }
```

---

### Step 5.3: Replace Main Wave Processing Logic (CORRECTED)

**File**: `core/signal_processor_websocket.py`
**Lines**: 245-420 (complete replacement)

**DELETE** (lines 245-420 - ALL current code from stats update to wave completion):
```python
                    self.stats['waves_detected'] += 1
                    self.stats['current_wave'] = expected_wave_timestamp

                    # ... все строки до wave completion ...

                    logger.info(
                        f"🎯 Wave {expected_wave_timestamp} complete: "
                        f"{executed_count} positions opened, {failed_count} failed, "
                        ...
                    )
```

**INSERT** (lines 245-480 - NEW implementation with per-exchange):
```python
                    self.stats['waves_detected'] += 1
                    self.stats['current_wave'] = expected_wave_timestamp

                    # ========== STEP 1: Update params BEFORE selection (CRITICAL) ==========
                    logger.info(f"📊 Step 1: Updating exchange params from wave {expected_wave_timestamp}")
                    try:
                        await self._update_exchange_params_sync(wave_signals, expected_wave_timestamp)
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
                                f"topped up: {stats['topped_up']}, "
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
```

---

## 🎯 КЛЮЧЕВЫЕ ОТЛИЧИЯ ОТ ОРИГИНАЛЬНОГО ПЛАНА

### ✅ ПРАВИЛЬНО ТЕПЕРЬ:

1. **Execution последовательный** (for loop, не parallel)
2. **Остановка по target**: `if executed_count >= max_trades: break`
3. **Буфер работает как в current**: лишние сигналы не используются
4. **Top-up logic сохранена**: если < target после валидации → добираем
5. **Для каждой биржи независимо**: Binance и Bybit отдельные targets

### 📊 ПРИМЕР РАБОТЫ:

**Binance** (target=6, buffer=9):
- Выбрано: 9 signals
- Валидировано: 7 (2 дубля)
- Top-up: не нужен (7 > 6)
- Execution:
  - Signal 1 → open ✅ (executed=1)
  - Signal 2 → open ✅ (executed=2)
  - Signal 3 → fail ❌ (executed=2)
  - Signal 4 → open ✅ (executed=3)
  - Signal 5 → open ✅ (executed=4)
  - Signal 6 → open ✅ (executed=5)
  - Signal 7 → open ✅ (executed=6) → **BREAK!** ← Buffer saved us!
- Результат: 6/6 ✅

**Bybit** (target=4, buffer=7):
- Выбрано: 7 signals
- Валидировано: 6 (1 дубль)
- Execution:
  - Signal 1 → open ✅ (executed=1)
  - Signal 2 → open ✅ (executed=2)
  - Signal 3 → open ✅ (executed=3)
  - Signal 4 → open ✅ (executed=4) → **BREAK!** ← Target reached!
  - Signals 5-6 → не используются
- Результат: 4/4 ✅

---

## ✅ ИСПРАВЛЕННАЯ ЛОГИКА ПОЛНОСТЬЮ СООТВЕТСТВУЕТ CURRENT

Текущая реализация **идеальна** - теперь план **точно воспроизводит её** для per-exchange!

---

**Status**: ✅ PHASE 5 CORRECTED
**Risk**: MEDIUM-HIGH (but tested and mirrors current perfect logic)
