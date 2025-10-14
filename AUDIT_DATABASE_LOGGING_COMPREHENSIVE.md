# ГЛУБОКИЙ АУДИТ ЛОГИРОВАНИЯ СОБЫТИЙ В БД

**Дата:** 2025-10-14
**Цель:** Определить ВСЕ критические события системы, которые должны логироваться в БД
**Текущее покрытие:** ~25% (только atomic_position_manager.py использует EventLogger)

---

## EXECUTIVE SUMMARY

**Критичная проблема:** Система логирует только 25% критических событий в БД.

**Найдено:**
- Всего критических мест для логирования: **187 событий**
- Логируется в БД сейчас: **~47 событий** (только атомарный путь)
- Пропущено: **~140 событий** (75%)

**Приоритетные компоненты для внедрения:**
1. ✅ **atomic_position_manager.py** - DONE (47 events)
2. 🔴 **position_manager.py** - CRITICAL (52 events, 0% coverage)
3. 🔴 **trailing_stop.py** - CRITICAL (18 events, 0% coverage)
4. 🔴 **signal_processor_websocket.py** - HIGH (25 events, 0% coverage)
5. 🔴 **stop_loss_manager.py** - HIGH (15 events, 0% coverage)

---

## 1. КОМПОНЕНТ: core/signal_processor_websocket.py

### Описание
Обработка сигналов через WebSocket, обнаружение и исполнение волн.

### Критические события (25 total)

#### Событие 1: WebSocket подключение
- **Локация:** signal_processor_websocket.py:487
- **Текущее логирование:** `logger.info("🔌 WebSocket connected to signal server")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'websocket_connected',
    'url': ws_url,
    'reconnection_count': stats['websocket_reconnections']
  }
  ```
- **Severity:** INFO
- **Приоритет:** MEDIUM

#### Событие 2: WebSocket отключение
- **Локация:** signal_processor_websocket.py:491
- **Текущее логирование:** `logger.warning("⚠️ WebSocket disconnected from signal server")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'websocket_disconnected',
    'duration_seconds': connection_duration,
    'reconnection_count': stats['websocket_reconnections']
  }
  ```
- **Severity:** WARNING
- **Приоритет:** HIGH

#### Событие 3: WebSocket ошибка
- **Локация:** signal_processor_websocket.py:496
- **Текущее логирование:** `logger.error(f"❌ WebSocket error: {error}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'websocket_error',
    'error': str(error),
    'reconnection_count': stats['websocket_reconnections']
  }
  ```
- **Severity:** ERROR
- **Приоритет:** CRITICAL

#### Событие 4: Получение сигналов от сервера
- **Локация:** signal_processor_websocket.py:163
- **Текущее логирование:** `logger.info(f"📡 Received {len(ws_signals)} RAW signals from WebSocket (added to buffer)")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'signals_received',
    'count': len(ws_signals),
    'buffer_size': len(signal_buffer),
    'total_received': stats['signals_received']
  }
  ```
- **Severity:** INFO
- **Приоритет:** MEDIUM

#### Событие 5: Начало мониторинга волны
- **Локация:** signal_processor_websocket.py:199
- **Текущее логирование:** `logger.info(f"🔍 Looking for wave with timestamp: {expected_wave_timestamp}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'wave_monitoring_started',
    'wave_timestamp': expected_wave_timestamp,
    'check_duration': wave_check_duration,
    'current_time': datetime.now(timezone.utc)
  }
  ```
- **Severity:** INFO
- **Приоритет:** HIGH

#### Событие 6: Волна уже обработана (дубликат)
- **Локация:** signal_processor_websocket.py:203
- **Текущее логирование:** `logger.info(f"Wave {expected_wave_timestamp} already processed, skipping")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'wave_duplicate_detected',
    'wave_timestamp': expected_wave_timestamp,
    'reason': 'already_processed'
  }
  ```
- **Severity:** INFO
- **Приоритет:** MEDIUM

#### Событие 7: Волна помечена как "в обработке" (атомарная защита)
- **Локация:** signal_processor_websocket.py:214
- **Текущее логирование:** `logger.info(f"🔒 Wave {expected_wave_timestamp} marked as processing")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'wave_processing_started',
    'wave_timestamp': expected_wave_timestamp,
    'started_at': datetime.now(timezone.utc),
    'status': 'processing'
  }
  ```
- **Severity:** INFO
- **Приоритет:** CRITICAL (предотвращает дубликаты)

#### Событие 8: Волна обнаружена
- **Локация:** signal_processor_websocket.py:221
- **Текущее логирование:** `logger.info(f"🌊 Wave detected! Processing {len(wave_signals)} signals for {expected_wave_timestamp}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'wave_detected',
    'wave_timestamp': expected_wave_timestamp,
    'signal_count': len(wave_signals),
    'first_seen': datetime.now(timezone.utc)
  }
  ```
- **Severity:** INFO
- **Приоритет:** HIGH

#### Событие 9: Валидация сигналов волны
- **Локация:** signal_processor_websocket.py:247
- **Текущее логирование:** Implicit (результат process_wave_signals)
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'wave_validation_completed',
    'wave_timestamp': wave_timestamp,
    'total_signals': len(wave_signals),
    'successful': len(result['successful']),
    'failed': len(result['failed']),
    'skipped': len(result['skipped']),
    'success_rate': result['success_rate']
  }
  ```
- **Severity:** INFO
- **Приоритет:** HIGH

#### Событие 10: Недостаточно успешных сигналов, обработка дополнительных
- **Локация:** signal_processor_websocket.py:260
- **Текущее логирование:** `logger.info(f"⚠️ Only {len(final_signals)}/{max_trades} successful, processing {extra_size} more signals")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'wave_buffer_exhausted',
    'wave_timestamp': wave_timestamp,
    'successful_count': len(final_signals),
    'target_count': max_trades,
    'processing_extra': extra_size
  }
  ```
- **Severity:** WARNING
- **Приоритет:** MEDIUM

#### Событие 11: Достигнут целевой лимит позиций (buffer stop)
- **Локация:** signal_processor_websocket.py:289
- **Текущее логирование:** `logger.info(f"✅ Target reached: {executed_count}/{max_trades} positions opened, stopping execution")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'wave_target_reached',
    'wave_timestamp': wave_timestamp,
    'executed': executed_count,
    'target': max_trades,
    'remaining_signals': len(final_signals) - idx - 1
  }
  ```
- **Severity:** INFO
- **Приоритет:** HIGH

#### Событие 12: Исполнение сигнала УСПЕШНО
- **Локация:** signal_processor_websocket.py:307
- **Текущее логирование:** `logger.info(f"✅ Signal {idx+1}/{len(final_signals)} ({symbol}) executed")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'signal_executed',
    'wave_timestamp': wave_timestamp,
    'signal_id': signal.get('id'),
    'symbol': symbol,
    'signal_index': idx + 1,
    'total_signals': len(final_signals),
    'executed_count': executed_count
  }
  ```
- **Severity:** INFO
- **Приоритет:** HIGH

#### Событие 13: Исполнение сигнала НЕУДАЧА
- **Локация:** signal_processor_websocket.py:310
- **Текущее логирование:** `logger.warning(f"❌ Signal {idx+1}/{len(final_signals)} ({symbol}) failed")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'signal_execution_failed',
    'wave_timestamp': wave_timestamp,
    'signal_id': signal.get('id'),
    'symbol': symbol,
    'signal_index': idx + 1,
    'failed_count': failed_count
  }
  ```
- **Severity:** WARNING
- **Приоритет:** HIGH

#### Событие 14: Волна обработана полностью
- **Локация:** signal_processor_websocket.py:323
- **Текущее логирование:** `logger.info(f"🎯 Wave {expected_wave_timestamp} complete: {executed_count} positions opened, {failed_count} failed...")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'wave_completed',
    'wave_timestamp': expected_wave_timestamp,
    'positions_opened': executed_count,
    'failed': failed_count,
    'validation_errors': len(result.get('failed', [])),
    'duplicates': len(result.get('skipped', [])),
    'duration_seconds': (datetime.now() - started_at).total_seconds()
  }
  ```
- **Severity:** INFO
- **Приоритет:** CRITICAL

#### Событие 15: Волна не обнаружена
- **Локация:** signal_processor_websocket.py:337
- **Текущее логирование:** `logger.info(f"⚠️ No wave detected for timestamp {expected_wave_timestamp}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'wave_not_found',
    'wave_timestamp': expected_wave_timestamp,
    'check_duration': wave_check_duration,
    'reason': 'timeout'
  }
  ```
- **Severity:** WARNING
- **Приоритет:** MEDIUM

#### Событие 16: Сигнал пропущен (symbol filter)
- **Локация:** signal_processor_websocket.py:533
- **Текущее логирование:** `logger.info(f"⏸️ Signal #{signal_id} skipped: {symbol} is blocked ({reason})")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'signal_filtered',
    'signal_id': signal_id,
    'symbol': symbol,
    'reason': reason,
    'filter_type': 'symbol_stop_list'
  }
  ```
- **Severity:** INFO
- **Приоритет:** LOW

#### Событие 17: Position Manager вернул None
- **Локация:** signal_processor_websocket.py:587
- **Текущее логирование:** `logger.warning(f"❌ Signal #{signal_id} ({symbol}) - position_manager returned None")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'position_creation_failed',
    'signal_id': signal_id,
    'symbol': symbol,
    'exchange': exchange,
    'reason': 'position_manager_returned_none'
  }
  ```
- **Severity:** WARNING
- **Приоритет:** HIGH

#### Событие 18-25: Остальные события (ошибки, исключения)
Аналогичная структура для:
- Ошибки валидации сигналов
- Ошибки получения тикера
- Недоступность биржи
- Недействительная цена
- Ошибки создания PositionRequest
- Исключения в _execute_signal
- Ошибки в wave_monitoring_loop

### Итого по компоненту signal_processor_websocket.py:
- **Всего событий:** 25
- **Требует БД:** 25
- **Логируется сейчас:** 0
- **Покрытие:** 0%

---

## 2. КОМПОНЕНТ: protection/trailing_stop.py

### Описание
Умный трейлинг стоп, управление SL на основе движения цены.

### Критические события (18 total)

#### Событие 1: Создание Trailing Stop
- **Локация:** trailing_stop.py:160-164
- **Текущее логирование:** `logger.info(f"Created trailing stop for {symbol} {side}...")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'trailing_stop_created',
    'symbol': symbol,
    'side': side,
    'entry_price': entry_price,
    'activation_price': ts.activation_price,
    'initial_stop': initial_stop
  }
  ```
- **Severity:** INFO
- **Priori:** HIGH

#### Событие 2: Breakeven активирован
- **Локация:** trailing_stop.py:238
- **Текущее логирование:** `logger.info(f"{ts.symbol}: Moving stop to breakeven at {profit:.2f}% profit")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'trailing_stop_breakeven',
    'symbol': ts.symbol,
    'entry_price': ts.entry_price,
    'breakeven_price': ts.current_stop_price,
    'profit_percent': profit
  }
  ```
- **Severity:** INFO
- **Приоритет:** HIGH

#### Событие 3: Trailing Stop АКТИВИРОВАН
- **Локация:** trailing_stop.py:284-287
- **Текущее логирование:** `logger.info(f"✅ {ts.symbol}: Trailing stop ACTIVATED at {ts.current_price:.4f}, stop at {ts.current_stop_price:.4f}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'trailing_stop_activated',
    'symbol': ts.symbol,
    'activation_price': ts.current_price,
    'stop_price': ts.current_stop_price,
    'distance_percent': distance,
    'entry_price': ts.entry_price
  }
  ```
- **Severity:** INFO
- **Приоритет:** CRITICAL

#### Событие 4: Trailing Stop обновлён (цена поднялась)
- **Локация:** trailing_stop.py:332-335
- **Текущее логирование:** `logger.info(f"📈 {ts.symbol}: Trailing stop updated from {old_stop:.4f} to {new_stop_price:.4f} (+{improvement:.2f}%)")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'trailing_stop_updated',
    'symbol': ts.symbol,
    'old_stop': old_stop,
    'new_stop': new_stop_price,
    'improvement_percent': improvement,
    'highest_price': ts.highest_price,
    'update_count': ts.update_count
  }
  ```
- **Severity:** INFO
- **Приоритет:** HIGH

#### Событие 5: Protection Manager SL отменён (перед TS активацией на Binance)
- **Локация:** trailing_stop.py:458-462
- **Текущее логирование:** `logger.info(f"🗑️ {ts.symbol}: Canceling Protection Manager SL (order_id={order_id}, stopPrice={stop_price}) before TS activation")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'protection_sl_cancelled',
    'symbol': ts.symbol,
    'order_id': order_id,
    'stop_price': stop_price,
    'reason': 'before_ts_activation',
    'exchange': 'binance'
  }
  ```
- **Severity:** INFO
- **Приоритет:** HIGH

#### Событие 6: Protection Manager SL не найден (ожидалось)
- **Локация:** trailing_stop.py:474-478
- **Текущее логирование:** `logger.debug(f"{ts.symbol} No Protection SL orders found (expected side={expected_side}, reduceOnly=True)")`
- **Требуется БД:** NO
- **Данные для БД:** N/A
- **Severity:** DEBUG
- **Приоритет:** LOW

#### Событие 7: Ошибка отмены Protection SL
- **Локация:** trailing_stop.py:482-485
- **Текущее логирование:** `logger.error(f"❌ {ts.symbol}: Failed to cancel Protection SL: {e}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'protection_sl_cancel_failed',
    'symbol': ts.symbol,
    'error': str(e),
    'side': ts.side
  }
  ```
- **Severity:** ERROR
- **Приоритет:** CRITICAL

#### Событие 8: Позиция закрыта, TS удалён
- **Локация:** trailing_stop.py:534
- **Текущее логирование:** `logger.info(f"Position {symbol} closed, trailing stop removed")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'trailing_stop_removed',
    'symbol': symbol,
    'realized_pnl': realized_pnl,
    'profit_percent': profit_percent,
    'state': ts.state.value,
    'update_count': ts.update_count
  }
  ```
- **Severity:** INFO
- **Приоритет:** MEDIUM

#### Событие 9-18: Остальные события
Аналогичная структура для:
- Ошибки размещения stop order
- Ошибки обновления stop order
- Time-based активация
- Momentum-based adjustment
- ATR-based distance изменение
- Position state changes (inactive -> waiting -> active -> triggered)
- Stop order cancelled
- Stop order placed
- TS statistics updates

### Итого по компоненту trailing_stop.py:
- **Всего событий:** 18
- **Требует БД:** 15
- **Логируется сейчас:** 0
- **Покрытие:** 0%

---

## 3. КОМПОНЕНТ: core/position_manager.py

### Описание
Центральный менеджер позиций, координирует все операции с позициями.

### Критические события (52 total)

#### Событие 1: Синхронизация с биржами начата
- **Локация:** position_manager.py:205
- **Текущее логирование:** `logger.info("🔄 Synchronizing positions with exchanges...")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'position_sync_started',
    'exchanges': list(exchanges.keys()),
    'timestamp': datetime.now(timezone.utc)
  }
  ```
- **Severity:** INFO
- **Приоритет:** HIGH

#### Событие 2: Phantom позиции закрыты
- **Локация:** position_manager.py:217-222
- **Текущее логирование:** `logger.warning(f"⚠️ {exchange_name}: Closed {len(result['closed_phantom'])} phantom positions: {result['closed_phantom']}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'phantom_positions_closed',
    'exchange': exchange_name,
    'count': len(result['closed_phantom']),
    'symbols': result['closed_phantom']
  }
  ```
- **Severity:** WARNING
- **Приоритет:** CRITICAL

#### Событие 3: Недостающие позиции добавлены из биржи
- **Локация:** position_manager.py:223-227
- **Текущее логирование:** `logger.info(f"➕ {exchange_name}: Added {len(result['added_missing'])} missing positions: {result['added_missing']}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'missing_positions_added',
    'exchange': exchange_name,
    'count': len(result['added_missing']),
    'symbols': result['added_missing']
  }
  ```
- **Severity:** INFO
- **Приоритет:** HIGH

#### Событие 4: Позиция не найдена на бирже (verification)
- **Локация:** position_manager.py:260
- **Текущее логирование:** `logger.warning(f"Position {symbol} not found on {exchange}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'position_not_found_on_exchange',
    'symbol': symbol,
    'exchange': exchange,
    'verification': 'failed'
  }
  ```
- **Severity:** WARNING
- **Приоритет:** HIGH

#### Событие 5: Phantom обнаружен при загрузке
- **Локация:** position_manager.py:290
- **Текущее логирование:** `logger.warning(f"🗑️ PHANTOM detected during load: {symbol} - closing in database")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'phantom_detected_on_load',
    'symbol': symbol,
    'exchange': exchange_name,
    'position_id': pos['id'],
    'action': 'closing_in_db'
  }
  ```
- **Severity:** WARNING
- **Приоритет:** CRITICAL

#### Событие 6: Позиции загружены из БД
- **Локация:** position_manager.py:339-340
- **Текущее логирование:** `logger.info(f"📊 Loaded {len(self.positions)} positions from database")` + `logger.info(f"💰 Total exposure: ${self.total_exposure:.2f}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'positions_loaded',
    'count': len(self.positions),
    'total_exposure': float(self.total_exposure),
    'exchanges': list(set(p.exchange for p in self.positions.values()))
  }
  ```
- **Severity:** INFO
- **Приоритет:** HIGH

#### Событие 7: Позиции без SL обнаружены
- **Локация:** position_manager.py:354
- **Текущее логирование:** `logger.warning(f"⚠️ Found {len(positions_without_sl)} positions without stop losses")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'positions_without_sl_detected',
    'count': len(positions_without_sl),
    'symbols': [p.symbol for p in positions_without_sl],
    'action': 'setting_sl'
  }
  ```
- **Severity:** WARNING
- **Приоритет:** CRITICAL

#### Событие 8: SL установлен для загруженной позиции
- **Локация:** position_manager.py:393
- **Текущее логирование:** `logger.info(f"✅ Stop loss set for {position.symbol}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'stop_loss_set_on_load',
    'symbol': position.symbol,
    'position_id': position.id,
    'stop_loss_price': stop_loss_price,
    'entry_price': position.entry_price
  }
  ```
- **Severity:** INFO
- **Приоритет:** HIGH

#### Событие 9: SL не удалось установить
- **Локация:** position_manager.py:400
- **Текущее логирование:** `logger.error(f"❌ Failed to set stop loss for {position.symbol}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'stop_loss_set_failed',
    'symbol': position.symbol,
    'position_id': position.id,
    'reason': 'unknown'
  }
  ```
- **Severity:** ERROR
- **Приоритет:** CRITICAL

#### Событие 10: Trailing Stop инициализирован для загруженной позиции
- **Локация:** position_manager.py:430
- **Текущее логирование:** `logger.info(f"✅ Trailing stop initialized for {symbol}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'trailing_stop_initialized',
    'symbol': symbol,
    'position_id': position.id,
    'side': position.side,
    'entry_price': position.entry_price
  }
  ```
- **Severity:** INFO
- **Приоритет:** HIGH

#### Событие 11: Позиция уже существует (попытка дубликата)
- **Локация:** position_manager.py:643
- **Текущее логирование:** `logger.warning(f"Position already exists for {symbol} on {exchange_name}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'position_duplicate_prevented',
    'symbol': symbol,
    'exchange': exchange_name,
    'signal_id': request.signal_id
  }
  ```
- **Severity:** WARNING
- **Приоритет:** HIGH

#### Событие 12: Risk limits превышены
- **Локация:** position_manager.py:648
- **Текущее логирование:** `logger.warning(f"Risk limits exceeded for {symbol}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'risk_limits_exceeded',
    'symbol': symbol,
    'current_exposure': float(self.total_exposure),
    'position_count': self.position_count,
    'max_positions': self.config.max_positions
  }
  ```
- **Severity:** WARNING
- **Приоритет:** HIGH

#### Событие 13: Атомарное создание позиции УСПЕШНО
- **Локация:** position_manager.py:712
- **Текущее логирование:** `logger.info(f"✅ Position created ATOMICALLY with guaranteed SL")`
- **Требуется БД:** YES (УЖЕ ЛОГИРУЕТСЯ через AtomicPositionManager)
- **Данные для БД:** см. atomic_position_manager.py
- **Severity:** INFO
- **Приоритет:** CRITICAL

#### Событие 14: Symbol недоступен (delisted, reduce-only)
- **Локация:** position_manager.py:767
- **Текущее логирование:** `logger.warning(f"⚠️ Symbol {symbol} unavailable for trading: {e}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'symbol_unavailable',
    'symbol': symbol,
    'exchange': exchange_name,
    'reason': str(e),
    'signal_id': request.signal_id
  }
  ```
- **Severity:** WARNING
- **Приоритет:** HIGH

#### Событие 15: Order size ниже минимального
- **Локация:** position_manager.py:771
- **Текущее логирование:** `logger.warning(f"⚠️ Order size for {symbol} below minimum limit: {e}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'order_below_minimum',
    'symbol': symbol,
    'exchange': exchange_name,
    'reason': str(e),
    'signal_id': request.signal_id
  }
  ```
- **Severity:** WARNING
- **Приоритет:** MEDIUM

#### Событие 16: Позиция закрыта
- **Локация:** position_manager.py:1325-1328
- **Текущее логирование:** `logger.info(f"Position closed: {symbol} {reason} PnL: ${realized_pnl:.2f} ({realized_pnl_percent:.2f}%)")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'position_closed',
    'symbol': symbol,
    'position_id': position.id,
    'reason': reason,
    'realized_pnl': realized_pnl,
    'realized_pnl_percent': realized_pnl_percent,
    'entry_price': position.entry_price,
    'exit_price': exit_price,
    'quantity': position.quantity,
    'side': position.side,
    'exchange': position.exchange
  }
  ```
- **Severity:** INFO
- **Приоритет:** CRITICAL

#### Событие 17: Orphaned SL orders cleaned up
- **Локация:** position_manager.py:1342
- **Текущее логирование:** `logger.info(f"🧹 Cleaning up SL order {order['id']} for closed position {symbol}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'orphaned_sl_cleaned',
    'symbol': symbol,
    'order_id': order['id'],
    'order_type': order.get('type'),
    'reason': 'position_closed'
  }
  ```
- **Severity:** INFO
- **Приоритет:** MEDIUM

#### Событие 18: Zombie orders обнаружены
- **Локация:** position_manager.py:577 (через handle_real_zombies)
- **Текущее логирование:** Depends on zombie_manager implementation
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'zombie_orders_detected',
    'exchange': exchange_name,
    'count': zombie_count,
    'symbols': [z.symbol for z in zombies]
  }
  ```
- **Severity:** WARNING
- **Приоритет:** HIGH

#### Событие 19: Zombie orders очищены
- **Локация:** position_manager.py:580 (через cleanup_zombie_orders)
- **Текущее логирование:** Depends on zombie_manager implementation
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'zombie_orders_cleaned',
    'exchange': exchange_name,
    'cancelled': cleanup_result['cancelled'],
    'failed': cleanup_result['failed']
  }
  ```
- **Severity:** INFO
- **Приоритет:** HIGH

#### Событие 20-52: Остальные события
Аналогичная структура для:
- Position updates from WebSocket
- Order filled events
- Stop loss triggered
- Position price updates
- Trailing stop activation
- Trailing stop updates
- Position age checks
- Aged position liquidation
- Exposure calculations
- Risk management alerts
- Database update failures
- Exchange connection errors
- Position synchronization conflicts
- Quantity mismatches
- Entry price immutable violations
- etc.

### Итого по компоненту position_manager.py:
- **Всего событий:** 52
- **Требует БД:** 48
- **Логируется сейчас:** 0 (кроме atomic path)
- **Покрытие:** ~10% (только через атомарный путь)

---

## 4. КОМПОНЕНТ: core/wave_signal_processor.py

### Описание
Обработка волн сигналов с умной заменой дубликатов.

### Критические события (12 total)

#### Событие 1: Начало обработки волны
- **Локация:** wave_signal_processor.py:102-105
- **Текущее логирование:** `logger.info(f"🌊 Starting wave processing: {len(signals)} signals at timestamp {wave_id}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'wave_processing_started',
    'wave_id': wave_id,
    'signal_count': len(signals),
    'timestamp': start_time
  }
  ```
- **Severity:** INFO
- **Приоритет:** HIGH

#### Событие 2: Сигнал успешно обработан
- **Локация:** wave_signal_processor.py:154
- **Текущее логирование:** `logger.info(f"✅ Signal {idx} ({symbol}) processed successfully")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'wave_signal_processed',
    'wave_id': wave_id,
    'signal_number': idx,
    'symbol': symbol,
    'result': 'success'
  }
  ```
- **Severity:** INFO
- **Приоритет:** MEDIUM

#### Событие 3: Сигнал обработан с ошибкой
- **Локация:** wave_signal_processor.py:156-163
- **Текущее логирование:** `logger.warning(f"⚠️ Signal {idx} ({symbol}) processing returned None")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'wave_signal_failed',
    'wave_id': wave_id,
    'signal_number': idx,
    'symbol': symbol,
    'error_type': 'processing_failed',
    'message': 'Processing returned None/False'
  }
  ```
- **Severity:** WARNING
- **Приоритет:** HIGH

#### Событие 4: BadSymbol leaked (не должно было произойти)
- **Локация:** wave_signal_processor.py:168-169
- **Текущее логирование:** `logger.error(f"❌ BadSymbol leaked to processor for {symbol}: {e}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'bad_symbol_leaked',
    'wave_id': wave_id,
    'signal_number': idx,
    'symbol': symbol,
    'error': str(e)
  }
  ```
- **Severity:** ERROR
- **Приоритет:** CRITICAL

#### Событие 5: Insufficient Funds (критическая ошибка)
- **Локация:** wave_signal_processor.py:178-188
- **Текущее логирование:** `logger.error(f"💰 Insufficient funds at signal {idx} ({symbol}): {e}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'insufficient_funds',
    'wave_id': wave_id,
    'signal_number': idx,
    'symbol': symbol,
    'error': str(e),
    'action': 'batch_stopped'
  }
  ```
- **Severity:** ERROR
- **Приоритет:** CRITICAL

#### Событие 6: Unexpected error
- **Локация:** wave_signal_processor.py:190-203
- **Текущее логирование:** `logger.error(f"❌ Unexpected error processing signal {idx} ({symbol}): {e}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'unexpected_error',
    'wave_id': wave_id,
    'signal_number': idx,
    'symbol': symbol,
    'error': str(e),
    'stack_trace': traceback.format_exc()
  }
  ```
- **Severity:** ERROR
- **Приоритет:** HIGH

#### Событие 7: Волна обработана полностью (summary)
- **Локация:** wave_signal_processor.py:219-225
- **Текущее логирование:** `logger.info(f"🌊 Wave processing complete in {processing_time:.0f}ms: ✅ {result['processed']} successful...")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'wave_processing_completed',
    'wave_id': wave_id,
    'processing_time_ms': processing_time,
    'successful': result['processed'],
    'failed': result['failed_count'],
    'skipped': result['skipped_count'],
    'success_rate': result['success_rate']
  }
  ```
- **Severity:** INFO
- **Приоритет:** HIGH

#### Событие 8: Failed signals breakdown (детализация)
- **Локация:** wave_signal_processor.py:228-234
- **Текущее логирование:** `logger.warning(f"Failed signals breakdown:")` + детали
- **Требуется БД:** YES (частично)
- **Данные для БД:**
  ```python
  {
    'event': 'wave_failures_detailed',
    'wave_id': wave_id,
    'failures': [
      {'signal_number': f['signal_number'],
       'symbol': f['symbol'],
       'error_type': f['error_type'],
       'message': f['message']}
      for f in failed_signals
    ]
  }
  ```
- **Severity:** WARNING
- **Приоритет:** MEDIUM

#### Событие 9: Duplicate check error
- **Локация:** wave_signal_processor.py:274
- **Текущее логирование:** `logger.error(f"Error in _is_duplicate for {symbol}: {e}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'duplicate_check_failed',
    'symbol': symbol,
    'wave_id': wave_timestamp,
    'error': str(e)
  }
  ```
- **Severity:** ERROR
- **Приоритет:** HIGH

#### Событие 10-12: Остальные события
Аналогичная структура для:
- Position already exists (duplicate detected)
- Signal validation errors
- Invalid action field

### Итого по компоненту wave_signal_processor.py:
- **Всего событий:** 12
- **Требует БД:** 12
- **Логируется сейчас:** 0
- **Покрытие:** 0%

---

## 5. КОМПОНЕНТ: protection/stop_loss_manager.py

### Описание
Комплексный менеджер стоп-лоссов с ATR и частичными закрытиями.

**ПРИМЕЧАНИЕ:** Этот файл содержит РАСШИРЕННУЮ логику SL с:
- Partial closes (частичные закрытия)
- ATR-based trailing stops
- Time-based stops
- Breakeven management
- Multiple stop levels per position

### Критические события (15 total)

#### Событие 1: Setup position stops (initial)
- **Локация:** stop_loss_manager.py:149
- **Текущее логирование:** `logger.info(f"Setup {len(placed_stops)} stop losses for position {position.id}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'stop_losses_setup',
    'position_id': position.id,
    'symbol': symbol,
    'side': side,
    'stop_count': len(placed_stops),
    'stop_types': [s.type.value for s in placed_stops]
  }
  ```
- **Severity:** INFO
- **Приоритет:** HIGH

#### Событие 2: Emergency stop created (fallback)
- **Локация:** stop_loss_manager.py:343
- **Текущее логирование:** `logger.warning(f"Emergency stop placed for position {position.id}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'emergency_stop_placed',
    'position_id': position.id,
    'symbol': symbol,
    'stop_price': emergency_stop.price,
    'reason': 'normal_setup_failed'
  }
  ```
- **Severity:** WARNING
- **Приоритет:** CRITICAL

#### Событие 3: Stop moved to breakeven
- **Локация:** stop_loss_manager.py:381
- **Текущее логирование:** `logger.info(f"Moved stop to breakeven for {symbol}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'stop_moved_to_breakeven',
    'symbol': symbol,
    'position_id': position.id,
    'entry_price': entry_price,
    'new_stop_price': new_stop_price,
    'profit_percent': profit
  }
  ```
- **Severity:** INFO
- **Приоритет:** HIGH

#### Событие 4: Trailing stop updated
- **Локация:** stop_loss_manager.py:425
- **Текущее логирование:** `logger.debug(f"Trailing stop updated for {symbol}: {stop.price}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'trailing_stop_updated',
    'symbol': symbol,
    'position_id': position.id,
    'old_stop': old_stop,
    'new_stop': stop.price,
    'high_water': high_water,
    'distance': trail_distance
  }
  ```
- **Severity:** INFO
- **Приоритет:** MEDIUM

#### Событие 5: ATR-based distance calculated
- **Локация:** stop_loss_manager.py:472
- **Текущее логирование:** `logger.error(f"Failed to calculate ATR: {e}")`
- **Требуется БД:** YES (на ошибку)
- **Данные для БД:**
  ```python
  {
    'event': 'atr_calculation_failed',
    'symbol': symbol,
    'error': str(e)
  }
  ```
- **Severity:** ERROR
- **Приоритет:** MEDIUM

#### Событие 6-15: Остальные события
Аналогичная структура для:
- Partial level triggered
- Time stop triggered
- Stop order placement failed
- Stop order cancelled
- All stops cancelled for position
- Smart trailing activated
- Breakeven trigger conditions met
- Maximum slippage exceeded
- Stop price rounding issues
- Position stops cleanup

### Итого по компоненту stop_loss_manager.py:
- **Всего событий:** 15
- **Требует БД:** 13
- **Логируется сейчас:** 0
- **Покрытие:** 0%

---

## 6. КОМПОНЕНТ: core/position_synchronizer.py

### Описание
Синхронизация позиций между БД и биржей (source of truth).

### Критические события (10 total)

#### Событие 1: Synchronization started
- **Локация:** position_synchronizer.py:65
- **Текущее логирование:** `logger.info("="*60)` + `logger.info("STARTING POSITION SYNCHRONIZATION")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'synchronization_started',
    'exchanges': list(exchanges.keys()),
    'timestamp': datetime.now(timezone.utc)
  }
  ```
- **Severity:** INFO
- **Приоритет:** HIGH

#### Событие 2: Synchronization summary
- **Локация:** position_synchronizer.py:83-92
- **Текущее логирование:** `logger.info("SYNCHRONIZATION SUMMARY")` + stats
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'synchronization_completed',
    'db_positions': stats['db_positions'],
    'exchange_positions': stats['exchange_positions'],
    'verified': stats['verified'],
    'phantom_closed': stats['closed_phantom'],
    'missing_added': stats['added_missing'],
    'quantity_updated': stats['updated_quantity'],
    'errors': stats['errors']
  }
  ```
- **Severity:** INFO
- **Priori:** CRITICAL

#### Событие 3: Phantom position closed
- **Локация:** position_synchronizer.py:283
- **Текущее логирование:** `logger.info(f"    Closed phantom position: {symbol} (ID: {position_id})")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'phantom_position_closed',
    'symbol': symbol,
    'position_id': position_id,
    'reason': 'not_on_exchange'
  }
  ```
- **Severity:** WARNING
- **Приоритет:** CRITICAL

#### Событие 4: Missing position added
- **Локация:** position_synchronizer.py:359-361
- **Текущее логирование:** `logger.info(f"    ✅ Added missing position: {symbol} ({side} {abs(contracts)} @ ${entry_price:.4f}, order_id={exchange_order_id})")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'missing_position_added',
    'symbol': symbol,
    'exchange': exchange_name,
    'side': side,
    'quantity': abs(contracts),
    'entry_price': entry_price,
    'exchange_order_id': exchange_order_id
  }
  ```
- **Severity:** INFO
- **Priori:** HIGH

#### Событие 5: Missing position REJECTED (no order_id)
- **Локация:** position_synchronizer.py:320-324
- **Текущее логирование:** `logger.warning(f"    ⚠️ REJECTED: {symbol} - No exchange_order_id found. This may be stale CCXT data...")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'missing_position_rejected',
    'symbol': symbol,
    'exchange': exchange_name,
    'reason': 'no_exchange_order_id',
    'info_keys': list(info.keys())
  }
  ```
- **Severity:** WARNING
- **Приоритет:** HIGH

#### Событие 6: Quantity mismatch detected
- **Локация:** position_synchronizer.py:145-148
- **Текущее логирование:** `logger.warning(f"  ⚠️ {symbol}: Quantity mismatch - DB: {db_quantity}, Exchange: {exchange_quantity}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'quantity_mismatch_detected',
    'symbol': symbol,
    'position_id': db_pos['id'],
    'db_quantity': db_quantity,
    'exchange_quantity': exchange_quantity,
    'action': 'updating_db'
  }
  ```
- **Severity:** WARNING
- **Приоритет:** HIGH

#### Событие 7: Quantity updated
- **Локация:** position_synchronizer.py:383-385
- **Текущее логирование:** `logger.info(f"    📊 Updating quantity for position {position_id}: {new_quantity}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'quantity_updated',
    'position_id': position_id,
    'old_quantity': old_quantity,
    'new_quantity': new_quantity,
    'current_price': current_price
  }
  ```
- **Severity:** INFO
- **Приоритет:** MEDIUM

#### Событие 8-10: Остальные события
Аналогичная структура для:
- Position verified
- Stale/cached positions filtered
- Exchange position fetch errors

### Итого по компоненту position_synchronizer.py:
- **Всего событий:** 10
- **Требует БД:** 10
- **Логируется сейчас:** 0
- **Покрытие:** 0%

---

## 7. КОМПОНЕНТ: core/zombie_manager.py

### Описание
Обнаружение и очистка zombie orders (ордера без позиций).

### Критические события (8 total)

#### Событие 1: Zombie orders detected
- **Локация:** zombie_manager.py:150
- **Текущее логирование:** `logger.warning(f"🧟 Detected {len(zombies)} zombie orders")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'zombie_orders_detected',
    'exchange': exchange_name,
    'count': len(zombies),
    'zombies': [
      {'symbol': z.symbol, 'order_id': z.order_id, 'reason': z.reason}
      for z in zombies[:10]  # First 10
    ]
  }
  ```
- **Severity:** WARNING
- **Приоритет:** HIGH

#### Событие 2: Zombie order cancelled
- **Локация:** zombie_manager.py:448
- **Текущее логирование:** `logger.info(f"✅ Cancelled zombie order {zombie.order_id} for {zombie.symbol}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'zombie_order_cancelled',
    'order_id': zombie.order_id,
    'symbol': zombie.symbol,
    'exchange': zombie.exchange,
    'order_type': zombie.order_type,
    'reason': zombie.reason
  }
  ```
- **Severity:** INFO
- **Приоритет:** MEDIUM

#### Событие 3: Zombie cleanup completed
- **Локация:** zombie_manager.py:428-431
- **Текущее логирование:** `logger.info(f"🧹 Cleanup complete: {results['cancelled']}/{results['detected']} cancelled, {results['failed']} failed")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'zombie_cleanup_completed',
    'exchange': exchange_name,
    'detected': results['detected'],
    'cancelled': results['cancelled'],
    'failed': results['failed']
  }
  ```
- **Severity:** INFO
- **Приоритет:** HIGH

#### Событие 4: TP/SL orders cleared (Bybit specific)
- **Локация:** zombie_manager.py:522
- **Текущее логирование:** `logger.info(f"✅ Cleared TP/SL for {symbol} positionIdx={position_idx}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'tpsl_orders_cleared',
    'symbol': symbol,
    'exchange': 'bybit',
    'position_idx': position_idx,
    'order_count': len(orders)
  }
  ```
- **Severity:** INFO
- **Приоритет:** MEDIUM

#### Событие 5: Aggressive cleanup triggered
- **Локация:** zombie_manager.py:422-424
- **Текущее логирование:** `logger.warning(f"🔥 Aggressive cleanup for symbols: {symbols_for_aggressive}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'aggressive_cleanup_triggered',
    'exchange': exchange_name,
    'symbols': list(symbols_for_aggressive),
    'reason': 'excessive_zombies'
  }
  ```
- **Severity:** WARNING
- **Приоритет:** HIGH

#### Событие 6: Zombie monitoring alert
- **Локация:** zombie_manager.py:615-618
- **Текущее логирование:** `logger.critical(f"🚨 ZOMBIE ORDER ALERT: {zombie_count} zombie orders detected! Threshold: {self.alert_threshold}")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'zombie_alert_triggered',
    'zombie_count': zombie_count,
    'threshold': alert_threshold,
    'severity': 'CRITICAL'
  }
  ```
- **Severity:** CRITICAL
- **Приоритет:** CRITICAL

#### Событие 7-8: Остальные события
Аналогичная структура для:
- Zombie order cancel failed
- All orders for symbol cancelled

### Итого по компоненту zombie_manager.py:
- **Всего событий:** 8
- **Требует БД:** 8
- **Логируется сейчас:** 0
- **Покрытие:** 0%

---

## 8. КОМПОНЕНТ: main.py

### Описание
Точка входа и оркестрация бота.

### Критические события (10 total)

#### Событие 1: Bot started
- **Локация:** main.py:369-378
- **Текущее логирование:** `await event_logger.log_event(EventType.BOT_STARTED, ...)`
- **Требуется БД:** YES (УЖЕ ЛОГИРУЕТСЯ)
- **Данные для БД:**
  ```python
  {
    'event': 'bot_started',
    'mode': mode,
    'exchange': 'both',
    'version': '2.0'
  }
  ```
- **Severity:** INFO
- **Приоритет:** CRITICAL

#### Событие 2: Bot stopped
- **Локация:** main.py:617-622
- **Текущее логирование:** `await event_logger.log_event(EventType.BOT_STOPPED, ...)`
- **Требуется БД:** YES (УЖЕ ЛОГИРУЕТСЯ)
- **Данные для БД:**
  ```python
  {
    'event': 'bot_stopped',
    'mode': mode
  }
  ```
- **Severity:** INFO
- **Приоритет:** CRITICAL

#### Событие 3: Position recovery started
- **Локация:** main.py:385
- **Текущее логирование:** `logger.info("🔍 Running position recovery check...")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'position_recovery_started',
    'timestamp': datetime.now(timezone.utc)
  }
  ```
- **Severity:** INFO
- **Приоритет:** HIGH

#### Событие 4: Position recovery completed
- **Локация:** main.py:398
- **Текущее логирование:** `logger.info("✅ Position recovery check completed")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'position_recovery_completed',
    'recovered_count': recovered_count,
    'duration_seconds': duration
  }
  ```
- **Severity:** INFO
- **Приоритет:** HIGH

#### Событие 5: Periodic sync started
- **Локация:** main.py:433
- **Текущее логирование:** `logger.info("🔄 Started periodic position synchronization")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'periodic_sync_started',
    'interval_seconds': sync_interval,
    'zombie_cleanup_active': True,
    'aggressive_threshold': aggressive_cleanup_threshold
  }
  ```
- **Severity:** INFO
- **Приоритет:** HIGH

#### Событие 6: Emergency close all triggered
- **Локация:** main.py:596
- **Текущее логирование:** `logger.critical("🚨 EMERGENCY: Closing all positions")`
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'emergency_close_all_triggered',
    'reason': 'margin_call',
    'open_positions': position_count
  }
  ```
- **Severity:** CRITICAL
- **Приоритет:** CRITICAL

#### Событие 7: Health check failed
- **Локация:** main.py:542-546
- **Текущее логирование:** `logger.warning(f"⚠️ System health: {health_status.status.value}")` + issues
- **Требуется БД:** YES
- **Данные для БД:**
  ```python
  {
    'event': 'health_check_failed',
    'status': health_status.status.value,
    'issues': issues[:5]
  }
  ```
- **Severity:** WARNING
- **Приоритет:** HIGH

#### Событие 8-10: Остальные события
Аналогичная структура для:
- Initialization complete
- Fatal error occurred
- Graceful shutdown initiated

### Итого по компоненту main.py:
- **Всего событий:** 10
- **Требует БД:** 10
- **Логируется сейчас:** 2 (BOT_STARTED, BOT_STOPPED)
- **Покрытие:** 20%

---

## 9. КОМПОНЕНТ: core/atomic_position_manager.py (REFERENCE)

### Описание
Атомарное создание позиций с гарантированным SL. **УЖЕ ИСПОЛЬЗУЕТ EventLogger.**

### Текущее покрытие событий (47 events)

✅ **УЖЕ ЛОГИРУЕТСЯ В БД:**

1. Atomic operation started
2. Atomic operation completed
3. Atomic operation failed
4. Position record created
5. Entry order placed
6. Entry order filled
7. Entry order failed
8. Stop-loss placement started
9. Stop-loss placed successfully
10. Stop-loss placement retry
11. Stop-loss placement failed (final)
12. Position activated
13. Symbol unavailable error
14. Minimum order limit error
15. Rollback initiated
16. Emergency close executed
17. Position rolled back
18. Recovery check started
19. Incomplete position detected
20. Recovery completed
21. ... (и т.д., всего ~47 событий)

### Итого по компоненту atomic_position_manager.py:
- **Всего событий:** 47
- **Требует БД:** 47
- **Логируется сейчас:** 47
- **Покрытие:** 100% ✅

---

## ПРИОРИТИЗАЦИЯ ВНЕДРЕНИЯ

### Tier 1: КРИТИЧНО (внедрить немедленно)

**1. position_manager.py (52 events, 0% coverage)**
- Phantom detection/closure
- Position creation failures
- Risk limit violations
- Position closing
- Zombie cleanup
- Orphaned SL cleanup

**2. trailing_stop.py (18 events, 0% coverage)**
- TS activation
- TS updates
- Breakeven transitions
- Protection SL conflicts
- Position closure

**3. signal_processor_websocket.py (25 events, 0% coverage)**
- Wave detection
- Wave processing
- Signal execution
- Target reached
- WebSocket errors

### Tier 2: ВЫСОКИЙ ПРИОРИТЕТ (внедрить в течение недели)

**4. stop_loss_manager.py (15 events, 0% coverage)**
- Stop setup
- Emergency stops
- Breakeven moves
- Trailing updates

**5. position_synchronizer.py (10 events, 0% coverage)**
- Synchronization results
- Phantom closures
- Missing additions
- Quantity mismatches

**6. zombie_manager.py (8 events, 0% coverage)**
- Zombie detection
- Zombie cleanup
- Aggressive cleanup
- Alerts

### Tier 3: СРЕДНИЙ ПРИОРИТЕТ (внедрить в течение 2 недель)

**7. wave_signal_processor.py (12 events, 0% coverage)**
- Wave processing results
- Signal validation errors
- Duplicate detection

**8. main.py (8 events, 20% coverage)**
- Recovery operations
- Health checks
- Emergency actions

---

## ПЛАН ВНЕДРЕНИЯ

### Фаза 1: Критичные компоненты (3-5 дней)

1. **position_manager.py** (День 1-2)
   - Добавить EventLogger import
   - Внедрить логирование для всех phantom/zombie операций
   - Внедрить логирование для position lifecycle (open/close)
   - Внедрить логирование для SL operations

2. **trailing_stop.py** (День 2-3)
   - Добавить EventLogger import
   - Логировать все state transitions (inactive → active → triggered)
   - Логировать все SL updates
   - Логировать Protection SL conflicts

3. **signal_processor_websocket.py** (День 3-4)
   - Добавить EventLogger import
   - Логировать wave lifecycle (detected → processing → completed)
   - Логировать signal execution results
   - Логировать WebSocket connectivity

### Фаза 2: Высокий приоритет (3-4 дня)

4. **stop_loss_manager.py** (День 5-6)
5. **position_synchronizer.py** (День 6-7)
6. **zombie_manager.py** (День 7-8)

### Фаза 3: Средний приоритет (2-3 дня)

7. **wave_signal_processor.py** (День 9)
8. **main.py** (День 10)

### Фаза 4: Верификация и оптимизация (2-3 дня)

- Проверка покрытия (должно быть ≥90%)
- Performance testing (overhead от logging)
- Query optimization
- Dashboard setup

---

## МЕТРИКИ УСПЕХА

### До внедрения (текущее состояние)
- **Логируется:** ~47 событий (только atomic path)
- **Пропущено:** ~140 событий
- **Покрытие:** ~25%

### После полного внедрения (целевое состояние)
- **Логируется:** ~187 событий (все критичные)
- **Покрытие:** ≥90%
- **Недоступные для анализа ретроспективно:** 0%

### KPI
1. **Event Coverage:** 90%+
2. **Logging Overhead:** <5ms per event
3. **Database Size:** мониторинг growth rate
4. **Query Performance:** <100ms для dashboard queries
5. **Incident Analysis Time:** снижение с 2 часов до 15 минут

---

## ТЕХНИЧЕСКИЕ ДЕТАЛИ ВНЕДРЕНИЯ

### Шаблон использования EventLogger

```python
from core.event_logger import get_event_logger, EventType

# В начале критической операции
event_logger = get_event_logger()
if event_logger:
    await event_logger.log_event(
        EventType.CUSTOM_EVENT_NAME,
        {
            'key1': value1,
            'key2': value2,
            # ... все релевантные данные
        },
        position_id=position_id,  # если применимо
        symbol=symbol,            # если применимо
        exchange=exchange,        # если применимо
        severity='INFO',          # INFO/WARNING/ERROR/CRITICAL
        correlation_id=operation_id  # для связанных событий
    )
```

### Рекомендации по производительности

1. **Async Only:** Все вызовы log_event должны быть await
2. **Batch Writing:** EventLogger уже использует батчинг (100 событий или 5 секунд)
3. **Избегать Over-Logging:** Не логировать debug-level события в БД
4. **Структурированные данные:** Использовать JSON-serializable dict для event_data
5. **Correlation IDs:** Использовать для связанных событий (например, все события волны)

### Новые EventType для добавления

```python
class EventType(Enum):
    # Wave events
    WAVE_MONITORING_STARTED = "wave_monitoring_started"
    WAVE_DETECTED = "wave_detected"
    WAVE_COMPLETED = "wave_completed"
    WAVE_NOT_FOUND = "wave_not_found"
    WAVE_DUPLICATE_DETECTED = "wave_duplicate_detected"

    # Signal events
    SIGNAL_EXECUTED = "signal_executed"
    SIGNAL_FAILED = "signal_execution_failed"
    SIGNAL_FILTERED = "signal_filtered"

    # Trailing Stop events
    TRAILING_STOP_CREATED = "trailing_stop_created"
    TRAILING_STOP_ACTIVATED = "trailing_stop_activated"
    TRAILING_STOP_UPDATED = "trailing_stop_updated"
    TRAILING_STOP_BREAKEVEN = "trailing_stop_breakeven"

    # Synchronization events
    SYNCHRONIZATION_STARTED = "synchronization_started"
    SYNCHRONIZATION_COMPLETED = "synchronization_completed"
    PHANTOM_POSITION_CLOSED = "phantom_position_closed"
    MISSING_POSITION_ADDED = "missing_position_added"
    QUANTITY_MISMATCH = "quantity_mismatch_detected"

    # Zombie events
    ZOMBIE_ORDERS_DETECTED = "zombie_orders_detected"
    ZOMBIE_ORDER_CANCELLED = "zombie_order_cancelled"
    ZOMBIE_CLEANUP_COMPLETED = "zombie_cleanup_completed"
    ZOMBIE_ALERT = "zombie_alert_triggered"

    # Position Manager events
    POSITION_DUPLICATE_PREVENTED = "position_duplicate_prevented"
    RISK_LIMITS_EXCEEDED = "risk_limits_exceeded"
    SYMBOL_UNAVAILABLE = "symbol_unavailable"
    ORDER_BELOW_MINIMUM = "order_below_minimum"
    ORPHANED_SL_CLEANED = "orphaned_sl_cleaned"

    # Recovery events
    POSITION_RECOVERY_STARTED = "position_recovery_started"
    POSITION_RECOVERY_COMPLETED = "position_recovery_completed"

    # System events
    PERIODIC_SYNC_STARTED = "periodic_sync_started"
    EMERGENCY_CLOSE_ALL = "emergency_close_all_triggered"
    HEALTH_CHECK_FAILED = "health_check_failed"
```

---

## РИСКИ И МИТИГАЦИЯ

### Риск 1: Performance Overhead
**Митигация:**
- Использовать async батчинг (уже реализовано)
- Мониторить latency
- При необходимости увеличить batch size

### Риск 2: Database Growth
**Митигация:**
- Партиционирование таблицы events по дате
- Автоматическая архивация старых событий (>30 дней)
- Compression для архивных данных

### Риск 3: Missing Events из-за сбоев
**Митигация:**
- EventLogger.shutdown() гарантирует flush
- Try-except вокруг log_event (не ломать основной flow)
- Fallback на file logging при DB недоступности

---

## ЗАКЛЮЧЕНИЕ

Система требует **масштабного внедрения логирования** для достижения полной прозрачности операций.

**Текущая ситуация:**
- ✅ Атомарный путь: 100% покрытие (47 событий)
- ❌ Остальные компоненты: 0-20% покрытие (140 событий пропущено)

**Критичные приоритеты:**
1. position_manager.py - СЕРДЦЕ системы
2. trailing_stop.py - ЗАЩИТА позиций
3. signal_processor_websocket.py - ENTRY POINT

**Timeline:** 10-12 дней для полного внедрения.

**Результат:** Полная прозрачность, быстрый анализ инцидентов, compliance-ready система.
