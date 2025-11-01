# 📋 ФИНАЛЬНЫЙ ПЛАН РЕАЛИЗАЦИИ: Исправление фильтрации сигналов

## 🎯 ЦЕЛЬ
Применять фильтры (OI, volume, дубликаты) ко ВСЕМ сигналам ДО отбора топ N, а не ПОСЛЕ.

## ⚠️ УЧТЁННЫЕ РИСКИ И ПРОБЛЕМЫ

### Из прошлых попыток:
1. ❌ Создание дублирующего кода вместо использования существующего
2. ❌ Неправильная передача параметров (entry_price=0)
3. ❌ Игнорирование side effects существующих методов

### Обнаруженные риски:
1. **Модификация сигналов** - WaveSignalProcessor изменяет оригинальные сигналы
2. **Накопление счетчиков** - self.total_* увеличиваются при каждом вызове
3. **Дублирование событий в БД** - event_logger записывает при каждом вызове
4. **Rate limits** - проверка OI/volume для всех сигналов = больше API вызовов
5. **Race condition** - между фильтрацией и исполнением может открыться позиция

## 🏗️ АРХИТЕКТУРА РЕШЕНИЯ

### Выбранный подход: Режим работы в WaveSignalProcessor
- Добавляем параметр `mode='filter'|'process'` в process_wave_signals()
- В режиме `filter` - только проверка, без side effects
- В режиме `process` - полная обработка

### Почему этот подход оптимален:
✅ Минимальные изменения кода
✅ Переиспользование существующей логики
✅ Легко откатить при проблемах
✅ Понятная семантика

## 📝 ДЕТАЛЬНАЯ РЕАЛИЗАЦИЯ

### ФАЗА 1: Модификация WaveSignalProcessor (core/wave_signal_processor.py)

#### Изменение 1.1: Добавление параметра mode (строка ~75)
```python
async def process_wave_signals(
    self,
    signals: List[Dict],
    wave_timestamp: str = None,
    mode: str = 'process'  # NEW: 'filter' or 'process'
) -> Dict[str, Any]:
```

#### Изменение 1.2: Работа с копиями в режиме filter (строка ~117)
```python
for idx, signal in enumerate(signals, 1):
    # В режиме filter работаем с копией
    if mode == 'filter':
        signal_to_check = signal.copy()
    else:
        signal_to_check = signal

    symbol = signal_to_check.get('symbol', signal_to_check.get('pair_symbol', 'UNKNOWN'))
```

#### Изменение 1.3: Условное выполнение _process_single_signal (строка ~152)
```python
# Обрабатываем сигнал (только в режиме process)
if mode == 'process':
    result = await self._process_single_signal(signal_to_check, wave_id)
else:
    # В режиме filter просто помечаем как обработанный
    result = {'status': 'filtered', 'symbol': symbol}
```

#### Изменение 1.4: Условная запись в БД (строки где event_logger)
```python
# Log event (только в режиме process)
if mode == 'process' and event_logger:
    await event_logger.log_event(...)
```

#### Изменение 1.5: Сохранение оригинального сигнала (строка ~160)
```python
if result:
    successful_signals.append({
        'signal_number': idx,
        'symbol': symbol,
        'result': result,
        'signal_data': signal  # Всегда оригинальный, не копия
    })
```

### ФАЗА 2: Изменение signal_processor_websocket.py

#### Изменение 2.1: Новый flow в _process_wave_per_exchange (строка ~903)
```python
# СТАРЫЙ КОД (удалить строки 903-922):
# Sort signals by combined score
# sorted_signals = sorted(...)
# signals_to_process = sorted_signals[:buffer_size]

# НОВЫЙ КОД:
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
    'price_change': len([s for s in skipped if 'price' in s.get('reason', '').lower()])
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
```

#### Изменение 2.2: Обработка результатов (строка ~928)
```python
# Execute successful signals until target reached
executed = 0
failed = 0

for signal_result in process_result.get('successful', []):
    if executed >= max_trades:
        logger.info(f"✅ {exchange_name_cap}: Target {max_trades} reached, stopping")
        break

    signal_data = signal_result.get('signal_data')
    if signal_data:
        # [существующий код открытия позиций]
```

#### Изменение 2.3: Финальная статистика (строка ~1024)
```python
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
    'params_source': params.get('source', 'unknown')
}
```

### ФАЗА 3: Обработка edge cases

#### Edge case 1: Все сигналы отфильтрованы
```python
if not filtered_signals:
    logger.warning(f"⚠️ {exchange_name_cap}: All {len(exchange_signals)} signals filtered!")
    # Записываем в результаты и продолжаем с другой биржей
    continue
```

#### Edge case 2: Недостаточно сигналов после фильтров
```python
if len(filtered_signals) < max_trades:
    logger.warning(
        f"⚠️ {exchange_name_cap}: Only {len(filtered_signals)} signals passed filters, "
        f"target was {max_trades}. Will open max possible positions."
    )
```

#### Edge case 3: Race condition с дубликатами
```python
# В режиме process может обнаружиться дубликат, который не был в режиме filter
# Это нормально - просто пропускаем и берём следующий из буфера
```

### ФАЗА 4: Тестирование

#### Тест 1: Unit test для режима filter
```python
# Создать mock WaveSignalProcessor
# Проверить что в режиме filter:
# - Не модифицируются оригиналы
# - Не записывается в БД
# - Возвращаются правильные результаты
```

#### Тест 2: Integration test полного flow
```python
# 50 сигналов → 20 фильтруется → 30 остается → топ 10 выбирается → 5 исполняется
# Проверить все метрики
```

#### Тест 3: Performance test
```python
# Замерить время обработки волны из 100 сигналов
# Должно быть < 30 секунд
```

### ФАЗА 5: Rollback план

Если что-то пойдёт не так:

1. **Быстрый rollback (< 1 минута)**:
   ```python
   # В signal_processor_websocket.py вернуть старый код:
   sorted_signals = sorted(exchange_signals, key=lambda s: ...)
   signals_to_process = sorted_signals[:buffer_size]
   wave_result = await self.wave_processor.process_wave_signals(
       signals=signals_to_process,
       wave_timestamp=wave_timestamp
       # Убрать mode параметр
   )
   ```

2. **Полный rollback (< 5 минут)**:
   - Откатить изменения в wave_signal_processor.py
   - Откатить изменения в signal_processor_websocket.py

## 📊 МЕТРИКИ УСПЕХА

После реализации в логах должно быть:
```
Binance: Applying filters to 45 signals
Binance: Filtered 18/45 (Dup:3, OI:10, Vol:5, Price:0)
Binance: Selected top 10 from 27 filtered signals (target: 5)
Binance: Processing 10 signals with WaveSignalProcessor
Binance: Executed 5/5, target reached ✅

Bybit: Applying filters to 20 signals
Bybit: Filtered 12/20 (Dup:2, OI:7, Vol:3, Price:0)
Bybit: Selected top 8 from 8 filtered signals (target: 4)
Bybit: Processing 8 signals with WaveSignalProcessor
Bybit: Executed 4/4, target reached ✅
```

## ✅ КОНТРОЛЬНЫЙ ЧЕКЛИСТ

### Перед реализацией:
- [ ] Создать бекап wave_signal_processor.py
- [ ] Создать бекап signal_processor_websocket.py
- [ ] Проверить что тесты проходят

### После реализации:
- [ ] Unit тесты проходят
- [ ] Integration тесты проходят
- [ ] Логи показывают правильную фильтрацию
- [ ] Target достигается при наличии сигналов
- [ ] Нет дублирования событий в БД
- [ ] Performance приемлемый (< 30 сек на волну)

### Критерии готовности к production:
- [ ] Протестировано на тестовой среде
- [ ] Rollback план проверен
- [ ] Документация обновлена
- [ ] Мониторинг настроен

## 🔴 КРИТИЧЕСКИ ВАЖНО

1. **НЕ создавать новые файлы** - только модифицировать существующие
2. **НЕ рефакторить** код вне scope изменений
3. **НЕ менять** логику не связанную с фильтрацией
4. **ТЕСТИРОВАТЬ** каждое изменение
5. **СЛЕДОВАТЬ** плану пошагово

## 📝 ПРИМЕЧАНИЯ

- Время реализации: ~2-3 часа
- Риск: Средний (изменение критической логики)
- Откат: < 5 минут
- Влияние на производительность: +20-30% времени обработки волны (больше API вызовов)