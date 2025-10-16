# План реализации исправлений Age Detector Module
## Вариант B: Упрощенная архитектура с централизованным управлением ордерами

**Дата создания:** 2025-10-15
**Статус:** ПЛАН - К ИСПОЛНЕНИЮ
**Стратегия:** Поэтапная реализация с тестированием после каждой фазы
**Git стратегия:** Отдельный коммит после каждой фазы

---

## 📋 Общая структура плана

**Принципы:**
- ✅ Один фикс = одна фаза
- ✅ Git commit после каждой успешной фазы
- ✅ Тестирование после каждой фазы
- ✅ Возможность отката на любом этапе
- ✅ Документирование результатов каждой фазы

**Всего фаз:** 8 (6 критических + 2 улучшения)

**Общее время:** 8-10 часов (включая тестирование)

---

## 🎯 ФАЗА 0: Подготовка и базовая линия

### Цель
Создать точку отсчета и подготовить окружение для безопасного внедрения исправлений.

### Задачи

#### 0.1 Создание feature-ветки
```bash
git checkout -b fix/age-detector-order-proliferation
```

#### 0.2 Создание baseline-документации
Создать файл `AGE_DETECTOR_BASELINE.md` с:
- Текущее состояние кода (хеши файлов)
- Snapshot конфигурации (.env параметры Age Detector)
- Последние метрики из логов (сколько ордеров создано за последний час)

#### 0.3 Backup текущих критических файлов
```bash
# Создать директорию для backup
mkdir -p backups/age_detector_fix_20251015/

# Скопировать файлы, которые будем менять
cp core/aged_position_manager.py backups/age_detector_fix_20251015/
cp core/exchange_manager_enhanced.py backups/age_detector_fix_20251015/
```

#### 0.4 Проверка окружения
- [ ] Убедиться, что testnet доступен и работает
- [ ] Проверить наличие тестовых позиций (или возможность их создать)
- [ ] Убедиться, что логирование включено
- [ ] Проверить, что скрипт `monitor_age_detector.py` запускается

#### 0.5 Запуск baseline-мониторинга (5 минут)
```bash
# В отдельном терминале запустить бота (если еще не запущен)
# python main.py

# Запустить короткий мониторинг для baseline
timeout 300 python monitor_age_detector.py logs/trading_bot.log
```

Сохранить результат в `baseline_metrics_age_detector.json`

### Git commit
```bash
git add backups/ AGE_DETECTOR_BASELINE.md baseline_metrics_age_detector.json
git commit -m "📊 Phase 0: Baseline for Age Detector fixes

- Created feature branch fix/age-detector-order-proliferation
- Backed up current implementation
- Documented baseline metrics
- Confirmed testnet availability

Related to: AGE_DETECTOR_AUDIT_REPORT_RU.md (Bug #1)"
```

### Критерии успеха
- ✅ Ветка создана
- ✅ Baseline-метрики собраны
- ✅ Backup файлов создан
- ✅ Окружение проверено

### Время
30 минут

---

## 🔴 ФАЗА 1: Создание унифицированного метода в EnhancedExchangeManager

### Цель
Реализовать централизованный метод `create_or_update_exit_order()` в EnhancedExchangeManager, который будет обрабатывать всю логику управления exit-ордерами.

### Задачи

#### 1.1 Добавить новый метод `create_or_update_exit_order()`

**Файл:** `core/exchange_manager_enhanced.py`

**Расположение:** После метода `create_limit_exit_order()` (после строки ~180)

**Что добавить:**
- Метод `create_or_update_exit_order()` с сигнатурой:
  ```python
  async def create_or_update_exit_order(
      self,
      symbol: str,
      side: str,
      amount: float,
      price: float,
      min_price_diff_pct: float = 0.5
  ) -> Optional[Dict]:
  ```

**Логика метода:**
1. Вызвать `_check_existing_exit_order(symbol, side, price)` - с передачей price!
2. Если существующий ордер найден:
   - Вычислить разницу в цене
   - Если < min_price_diff_pct: вернуть существующий с флагом `_was_updated=False`
   - Если >= min_price_diff_pct:
     - Отменить старый через `safe_cancel_with_verification()`
     - Ждать 0.5 сек
     - Создать новый через `create_limit_exit_order(..., check_duplicates=False)`
     - Установить флаг `_was_updated=True`
3. Если нет существующего:
   - Создать новый через `create_limit_exit_order(..., check_duplicates=True)`
   - Установить флаг `_was_updated=False`

**Важно:**
- Добавить подробное логирование каждого шага
- Добавить docstring с примерами использования
- Обработать все исключения

#### 1.2 Добавить unit-тест для нового метода

**Файл:** `tests/unit/test_exchange_manager_enhanced.py` (создать если нет)

**Тест-кейсы:**
- `test_create_or_update_exit_order_no_existing` - создание нового
- `test_create_or_update_exit_order_exists_price_ok` - существует, цена OK
- `test_create_or_update_exit_order_exists_price_changed` - существует, нужно обновить
- `test_create_or_update_exit_order_cancel_fails` - обработка ошибки отмены

#### 1.3 Запустить unit-тесты
```bash
pytest tests/unit/test_exchange_manager_enhanced.py -v
```

#### 1.4 Обновить статистику в EnhancedExchangeManager

Добавить в `self.stats`:
```python
'orders_updated_by_unified_method': 0,
'orders_created_by_unified_method': 0,
```

Инкрементировать в `create_or_update_exit_order()` соответственно.

### Git commit
```bash
git add core/exchange_manager_enhanced.py tests/unit/test_exchange_manager_enhanced.py
git commit -m "✨ Phase 1: Add create_or_update_exit_order() unified method

Implements centralized exit order management:
- Single method handles both creation and updates
- Automatic duplicate detection
- Proper price difference checking
- Returns _was_updated flag for statistics

Fixes: Bug #1 (Order Proliferation) - Part 1/2
Tests: Added unit tests for all scenarios

File: core/exchange_manager_enhanced.py
Related to: AGE_DETECTOR_AUDIT_REPORT_RU.md Section 7.1 (Variant B)"
```

### Тестирование фазы 1

**Цель:** Убедиться, что новый метод работает корректно изолированно.

**Шаги:**
1. Запустить все unit-тесты:
   ```bash
   pytest tests/unit/test_exchange_manager_enhanced.py -v
   ```

2. Проверить, что старые тесты не сломались:
   ```bash
   pytest tests/unit/ -v
   ```

3. Manual smoke test (опционально):
   ```python
   # В Python REPL
   from core.exchange_manager_enhanced import EnhancedExchangeManager
   # Создать instance с mock exchange
   # Вызвать create_or_update_exit_order()
   # Проверить возвращаемые значения
   ```

### Критерии успеха фазы 1
- ✅ Метод `create_or_update_exit_order()` добавлен
- ✅ Все unit-тесты проходят (зеленые)
- ✅ Docstring полный и понятный
- ✅ Логирование на каждом шаге
- ✅ Git commit создан

### Rollback plan
Если что-то пошло не так:
```bash
git reset --hard HEAD~1
git clean -fd
```

### Время
1.5 часа

---

## 🔴 ФАЗА 2: Рефакторинг AgedPositionManager для использования нового метода

### Цель
Заменить багованную логику управления ордерами в `aged_position_manager.py` на вызов единого метода `create_or_update_exit_order()`.

### Задачи

#### 2.1 Упростить метод `_update_single_exit_order()`

**Файл:** `core/aged_position_manager.py`

**Строки для замены:** 266-432 (весь метод `_update_single_exit_order`)

**Новая реализация:**
1. Оставить только основной путь через `EnhancedExchangeManager`
2. Удалить:
   - Ручной вызов `_check_existing_exit_order()` (строка 295)
   - Весь блок проверки `if existing:` (строки 299-344)
   - Блок `else:` для создания (строки 345-367)
   - Весь fallback-путь (строки 369-432)
3. Заменить на:
   - Один вызов `enhanced_manager.create_or_update_exit_order()`
   - Обработку возвращаемого значения
   - Обновление статистики на основе флага `_was_updated`

**Новая структура метода (~40 строк вместо 167):**
```
async def _update_single_exit_order(self, position, target_price, phase):
    try:
        # 1. Получить exchange и определить side
        # 2. Создать EnhancedExchangeManager
        # 3. Вызвать create_or_update_exit_order()
        # 4. Обработать результат
        # 5. Обновить self.managed_positions
        # 6. Обновить статистику (orders_created vs orders_updated)
    except ccxt.ExchangeError:
        # Обработка специфичных ошибок биржи
    except Exception:
        # Общая обработка ошибок
```

#### 2.2 Обновить обработку ошибок

Добавить специальную обработку для:
- Географических ограничений (код 170209)
- Ошибок точности цены
- Несуществующей позиции (код 110017, -2022)

Сохранять информацию о пропущенных символах в `self.managed_positions` с полем `skip_until`.

#### 2.3 Обновить логирование

Заменить логи:
- `"📝 Creating initial exit order"` → оставить (вызывается из нового метода)
- `"📊 Updating exit order"` → оставить (вызывается из нового метода)
- Удалить дублирующиеся логи

#### 2.4 Обновить статистику

В методе `get_statistics()` добавить:
```python
'orders_created_unified': self.stats['orders_created'],
'orders_updated_unified': self.stats['orders_updated'],
```

### Git commit
```bash
git add core/aged_position_manager.py
git commit -m "🔧 Phase 2: Refactor AgedPositionManager to use unified method

Simplified _update_single_exit_order():
- Replaced 167 lines with ~40 lines
- Removed manual duplicate checking
- Removed fallback path (dead code)
- Single call to create_or_update_exit_order()
- Improved error handling for geo restrictions

Fixes: Bug #1 (Order Proliferation) - Part 2/2
Fixes: Bug #2 (Double duplicate check)
Fixes: Bug #4 (Untested fallback path)

File: core/aged_position_manager.py (lines 266-432)
Related to: AGE_DETECTOR_AUDIT_REPORT_RU.md Section 7.1"
```

### Тестирование фазы 2

**Цель:** Убедиться, что Age Detector работает с новой логикой и НЕ создает множество ордеров.

#### 2.2.1 Static code check
```bash
# Проверить синтаксис
python -m py_compile core/aged_position_manager.py

# Проверить импорты
python -c "from core.aged_position_manager import AgedPositionManager; print('OK')"
```

#### 2.2.2 Unit-тесты
```bash
# Запустить тесты aged_position_manager
pytest tests/unit/test_aged_position_decimal_fix.py -v

# Если есть другие тесты для aged_position_manager
pytest tests/unit/ -k aged -v
```

#### 2.2.3 Integration test (testnet, 15 минут)

**Шаг 1:** Временно снизить `MAX_POSITION_AGE_HOURS` для быстрого тестирования:
```bash
# В .env
MAX_POSITION_AGE_HOURS=0.1  # 6 минут
```

**Шаг 2:** Запустить бота в testnet:
```bash
python main.py > test_phase2.log 2>&1 &
BOT_PID=$!
```

**Шаг 3:** В другом терминале запустить мониторинг:
```bash
python monitor_age_detector.py logs/trading_bot.log
```

**Шаг 4:** Через 15 минут остановить:
```bash
kill $BOT_PID
```

**Шаг 5:** Проверить результаты мониторинга:
```bash
# Открыть последний JSON отчет
ls -lt age_detector_diagnostic_*.json | head -1
```

**Критерии успеха:**
- ✅ `proliferation_issues` = [] (пустой массив)
- ✅ `duplicates_prevented` > 0 (дедупликация работает)
- ✅ Каждый символ имеет максимум 1-2 созданных ордера
- ✅ Нет ошибок типа "multiple orders for same symbol"

**Шаг 6:** Вернуть конфигурацию:
```bash
# В .env
MAX_POSITION_AGE_HOURS=3
```

#### 2.2.4 Проверка логов

```bash
# Проверить, что новые логи появляются
grep "create_or_update_exit_order" logs/trading_bot.log | tail -20

# Проверить отсутствие старых паттернов
grep "📝 Creating initial" logs/trading_bot.log | wc -l  # Должно быть мало
grep "Exit order already exists" logs/trading_bot.log | wc -l  # Должно быть > 0!
```

#### 2.2.5 Создать отчет о тестировании

**Файл:** `PHASE2_TEST_REPORT.md`

**Содержание:**
- Результаты unit-тестов
- Результаты integration-теста (JSON от монитора)
- Статистика из логов
- Выводы (прошла ли фаза успешно)

### Критерии успеха фазы 2
- ✅ Код упрощен (с ~167 строк до ~40)
- ✅ Все unit-тесты проходят
- ✅ Integration test: нет order proliferation
- ✅ Дедупликация работает (duplicates_prevented > 0)
- ✅ Git commit создан
- ✅ Отчет о тестировании создан

### Rollback plan
```bash
# Откатить оба коммита
git reset --hard HEAD~2
git clean -fd

# Или откатить только фазу 2
git reset --hard HEAD~1
git clean -fd
```

### Время
2 часа (включая 15 мин мониторинга)

---

## 🟡 ФАЗА 3: Улучшение инвалидации кэша при отмене ордеров

### Цель
Исправить Bug #3: гарантировать, что кэш ордеров инвалидируется немедленно после отмены, предотвращая использование устаревших данных.

### Задачи

#### 3.1 Улучшить метод `safe_cancel_with_verification()`

**Файл:** `core/exchange_manager_enhanced.py`

**Строки:** ~277-320

**Изменения:**
1. Добавить вызов `await self._invalidate_order_cache(symbol)` СРАЗУ после успешной отмены (после строки ~303)
2. Увеличить `await asyncio.sleep()` с текущего значения до 0.5 секунд
3. Добавить инвалидацию кэша также в блоках обработки исключений:
   - `except ccxt.OrderNotFound:` → добавить инвалидацию
   - `except Exception:` → добавить инвалидацию
4. Улучшить логирование для отладки проблем с кэшем

#### 3.2 Добавить метрику для отслеживания

В `self.stats` добавить:
```python
'cache_invalidations': 0,
'stale_cache_detections': 0,
```

Инкрементировать при каждой инвалидации.

#### 3.3 Добавить debug-логирование кэша (опционально)

При `LOG_LEVEL=DEBUG` логировать:
- Когда кэш инвалидируется
- Время жизни кэша
- Количество ордеров в кэше

### Git commit
```bash
git add core/exchange_manager_enhanced.py
git commit -m "🔧 Phase 3: Improve order cache invalidation timing

Enhanced safe_cancel_with_verification():
- Immediate cache invalidation after cancel
- Increased wait time to 0.5s (was 0.2s)
- Cache invalidation on all error paths
- Added cache metrics for monitoring

Fixes: Bug #3 (Cache invalidation race condition)

File: core/exchange_manager_enhanced.py (lines 277-320)
Related to: AGE_DETECTOR_AUDIT_REPORT_RU.md Section 7.1"
```

### Тестирование фазы 3

#### 3.1 Unit-тест для кэш-инвалидации

Добавить тест в `tests/unit/test_exchange_manager_enhanced.py`:
```python
async def test_safe_cancel_invalidates_cache():
    # Проверить, что _invalidate_order_cache() вызывается
    # после успешной отмены
    pass

async def test_safe_cancel_invalidates_cache_on_error():
    # Проверить, что кэш инвалидируется даже при ошибке
    pass
```

#### 3.2 Integration test (10 минут)

```bash
# Запустить бота
python main.py &

# Мониторить 10 минут
timeout 600 python monitor_age_detector.py logs/trading_bot.log

# Проверить метрики кэша
grep "cache_invalidations" logs/trading_bot.log
```

**Критерии:**
- ✅ Нет ошибок "order already cancelled"
- ✅ Метрика `cache_invalidations` растет
- ✅ Все еще нет order proliferation

### Критерии успеха фазы 3
- ✅ Кэш инвалидируется на всех путях
- ✅ Unit-тесты проходят
- ✅ Метрики кэша работают
- ✅ Git commit создан

### Время
1 час

---

## 🟡 ФАЗА 4: Обработка географических ограничений

### Цель
Исправить Bug #5 частично: добавить корректную обработку ошибок географических ограничений биржи, чтобы не спамить логи и не повторять попытки для заблокированных символов.

### Задачи

#### 4.1 Добавить обработку ExchangeError в process_aged_position()

**Файл:** `core/aged_position_manager.py`

**Метод:** `process_aged_position()` (строки ~134-203)

**Изменения:**
1. Обернуть вызов `_update_single_exit_order()` в `try-except`
2. Добавить специальную обработку для `ccxt.ExchangeError`:
   - Проверить код ошибки '170209' (China region)
   - Проверить код ошибки '170193' (Invalid price)
   - Для geo-restriction: сохранить в `managed_positions` с `skip_until = now + 24h`
   - Для price error: логировать WARNING и пропустить
3. Улучшить обработку других ошибок

#### 4.2 Добавить метод для проверки "skip_until"

Добавить вспомогательный метод:
```python
def _should_skip_position(self, position) -> bool:
    """Check if position should be skipped based on previous errors"""
    position_id = f"{position.symbol}_{position.exchange}"
    if position_id in self.managed_positions:
        skip_until = self.managed_positions[position_id].get('skip_until')
        if skip_until and datetime.now() < skip_until:
            return True
    return False
```

Вызывать в начале `process_aged_position()`.

#### 4.3 Добавить статистику

В `self.stats` добавить:
```python
'positions_skipped_geo_restricted': 0,
'positions_skipped_price_error': 0,
```

### Git commit
```bash
git add core/aged_position_manager.py
git commit -m "🛡️ Phase 4: Handle geographic restrictions gracefully

Added proper error handling:
- Detect geo-restricted symbols (error 170209)
- Skip geo-restricted symbols for 24h
- Handle price precision errors (error 170193)
- Statistics for skipped positions

Fixes: Bug #5 (Error handling) - Part 1/2

File: core/aged_position_manager.py
Related to: AGE_DETECTOR_AUDIT_REPORT_RU.md Section 7.1 Fix #3"
```

### Тестирование фазы 4

#### 4.1 Unit-тест

```python
async def test_process_aged_position_geo_restricted():
    # Mock exchange error 170209
    # Проверить, что позиция помечена skip_until
    # Проверить, что повторный вызов пропускает позицию
    pass
```

#### 4.2 Manual test (если есть geo-restricted символы)

Проверить логи для HNTUSDT или других заблокированных символов:
```bash
grep "geo.*restricted\|China region" logs/trading_bot.log
```

Должно быть:
- ✅ Одно сообщение об ошибке
- ✅ Не повторяется каждый цикл

### Критерии успеха фазы 4
- ✅ Geo-restricted символы обрабатываются корректно
- ✅ Skip-логика работает
- ✅ Нет спама в логах
- ✅ Git commit создан

### Время
1 час

---

## 🟢 ФАЗА 5: Добавление логики взятия прибыли (market close)

### Цель
Реализовать Improvement #1: немедленно закрывать устаревшие позиции market-ордером, если они в прибыли, вместо размещения limit-ордера.

### Задачи

#### 5.1 Добавить метод `_close_with_market_order()`

**Файл:** `core/aged_position_manager.py`

**Расположение:** После метода `_update_single_exit_order()`

**Реализация:**
```python
async def _close_with_market_order(self, position, current_price: float):
    """
    Закрыть позицию немедленно market-ордером

    Используется для устаревших позиций, которые находятся в прибыли
    """
    # 1. Получить exchange
    # 2. Определить order_side (opposite of position.side)
    # 3. Создать market order с reduceOnly=True
    # 4. Залогировать результат
    # 5. Обновить статистику
```

#### 5.2 Добавить проверку прибыльности в process_aged_position()

**Файл:** `core/aged_position_manager.py`

**Метод:** `process_aged_position()`

**Расположение:** После получения `current_price` (строка ~170), ПЕРЕД вызовом `_calculate_target_price()`

**Логика:**
1. Вычислить, находится ли позиция в прибыли:
   - Long: `current_price > entry_price * (1 + 0.002)` (> 0.2% прибыли)
   - Short: `current_price < entry_price * (0.998)`
2. Если в прибыли:
   - Залогировать "💰 Aged position profitable, closing with market order"
   - Вызвать `_close_with_market_order()`
   - Инкрементировать `self.stats['profitable_closes']`
   - Вернуться (не продолжать с limit-ордером)

#### 5.3 Добавить конфигурационный параметр

**Файл:** `config/settings.py`

Добавить в `TradingConfig`:
```python
aged_profitable_close_threshold_percent: Decimal = Decimal('0.2')  # Порог прибыли для market close
```

Загружать из `.env`:
```python
if val := os.getenv('AGED_PROFITABLE_CLOSE_THRESHOLD'):
    config.aged_profitable_close_threshold_percent = Decimal(val)
```

#### 5.4 Обновить статистику

В `self.stats` добавить:
```python
'profitable_closes': 0,
'market_orders_placed': 0,
```

### Git commit
```bash
git add core/aged_position_manager.py config/settings.py
git commit -m "✨ Phase 5: Add profit-taking logic for aged positions

Implemented immediate market close for profitable aged positions:
- Close with market order if profit > 0.2%
- New method: _close_with_market_order()
- Configurable profit threshold
- Statistics tracking

Implements: Improvement #1 (Profit-taking logic)

Files: core/aged_position_manager.py, config/settings.py
Related to: AGE_DETECTOR_AUDIT_REPORT_RU.md Section 7.2"
```

### Тестирование фазы 5

#### 5.1 Unit-тест

```python
async def test_close_with_market_order():
    # Проверить создание market ордера
    # Проверить reduceOnly=True
    # Проверить correct side
    pass

async def test_process_aged_position_profitable():
    # Mock profitable position
    # Проверить, что вызывается _close_with_market_order()
    # Проверить, что НЕ создается limit order
    pass
```

#### 5.2 Integration test

**Сложность:** Требует создания прибыльной позиции в testnet

**Альтернатива:** Manual verification через логи
```bash
# Искать в логах случаи profitable aged positions
grep "💰.*profitable" logs/trading_bot.log
```

### Критерии успеха фазы 5
- ✅ Метод `_close_with_market_order()` реализован
- ✅ Проверка прибыльности работает
- ✅ Market ордера создаются корректно
- ✅ Unit-тесты проходят
- ✅ Git commit создан

### Время
1.5 часа

---

## 🟢 ФАЗА 6: Добавление валидации состояния ордера

### Цель
Реализовать Improvement #2: проверять состояние ордера перед попыткой его отмены, чтобы избежать ошибок "order not found" и "already cancelled".

### Задачи

#### 6.1 Добавить метод `_validate_order_state()`

**Файл:** `core/exchange_manager_enhanced.py`

**Расположение:** После метода `safe_cancel_with_verification()`

**Реализация:**
```python
async def _validate_order_state(self, order_id: str, symbol: str) -> Optional[str]:
    """
    Проверить статус ордера перед модификацией

    Returns:
        str: Статус ордера ('open', 'new', 'partially_filled', etc.)
        None: Если ордер уже закрыт/отменен/не найден
    """
    # 1. Попытаться получить ордер
    # 2. Проверить статус
    # 3. Вернуть статус или None
```

#### 6.2 Интегрировать в `create_or_update_exit_order()`

**Перед отменой старого ордера:**
```python
# Перед вызовом safe_cancel_with_verification()
state = await self._validate_order_state(existing['id'], symbol)
if state and state not in ['closed', 'canceled', 'cancelled']:
    # Безопасно отменять
    await self.safe_cancel_with_verification(...)
else:
    # Ордер уже не активен, просто создать новый
    logger.info(f"Old order {existing['id']} no longer active")
```

#### 6.3 Обработать частично исполненные ордера

Если `state == 'partially_filled'`:
- Залогировать WARNING
- Отменить ордер (чтобы обновить оставшуюся часть)
- Пересчитать amount для нового ордера (использовать `remaining` вместо `amount`)

#### 6.4 Добавить статистику

```python
'partially_filled_orders_found': 0,
'already_cancelled_orders_skipped': 0,
```

### Git commit
```bash
git add core/exchange_manager_enhanced.py
git commit -m "🔍 Phase 6: Add order state validation before cancellation

Enhanced order management:
- Validate order state before cancel attempts
- Handle partially filled orders correctly
- Skip already cancelled/closed orders
- Detailed logging of order states

Implements: Improvement #2 (Order state validation)
Fixes: Bug #5 (Error handling) - Part 2/2

File: core/exchange_manager_enhanced.py
Related to: AGE_DETECTOR_AUDIT_REPORT_RU.md Section 7.2"
```

### Тестирование фазы 6

#### 6.1 Unit-тесты

```python
async def test_validate_order_state_open():
    # Order is open -> return 'open'
    pass

async def test_validate_order_state_cancelled():
    # Order is cancelled -> return None
    pass

async def test_validate_order_state_not_found():
    # Order not found -> return None
    pass

async def test_create_or_update_skips_cancelled_order():
    # If existing order is cancelled, should create new without cancel attempt
    pass
```

#### 6.2 Проверка логов

```bash
# Искать случаи пропуска отмены
grep "no longer active" logs/trading_bot.log

# Проверить отсутствие ошибок "order not found"
grep -i "order not found" logs/trading_bot.log
```

### Критерии успеха фазы 6
- ✅ Валидация состояния ордера работает
- ✅ Не пытаемся отменять уже отмененные ордера
- ✅ Частично исполненные ордера обрабатываются
- ✅ Unit-тесты проходят
- ✅ Git commit создан

### Время
1 час

---

## 🔵 ФАЗА 7: Добавление мониторинга множественных ордеров

### Цель
Реализовать Improvement #3: активный мониторинг для обнаружения множественных exit-ордеров на бирже (если баг все еще проявляется).

### Задачи

#### 7.1 Добавить метод `_detect_duplicate_orders()`

**Файл:** `core/aged_position_manager.py`

**Расположение:** После метода `get_statistics()`

**Реализация:**
```python
async def _detect_duplicate_orders(self) -> List[Dict]:
    """
    Активно проверять дублирующиеся exit-ордера на бирже

    Должно вызываться периодически (каждые 5 минут)

    Returns:
        List[Dict]: Список символов с множественными exit-ордерами
    """
    # 1. Для каждой биржи
    # 2. Для каждого активного символа (из managed_positions)
    # 3. Получить открытые ордера
    # 4. Фильтровать: reduceOnly=True, type='limit', НЕ stop loss
    # 5. Если > 1 ордера: добавить в список дубликатов
    # 6. Залогировать CRITICAL error если найдены
    # 7. Вернуть список
```

#### 7.2 Интегрировать в главный цикл

**Файл:** `main.py`

**В главном цикле (где вызывается `check_and_process_aged_positions()`):**

Добавить периодическую проверку (каждые 5 минут):
```python
# После вызова aged_position_manager.check_and_process_aged_positions()
if time.time() - last_duplicate_check > 300:  # 5 минут
    duplicates = await aged_position_manager._detect_duplicate_orders()
    if duplicates:
        logger.critical(f"🚨 DUPLICATE ORDERS DETECTED: {len(duplicates)} symbols affected!")
    last_duplicate_check = time.time()
```

#### 7.3 Добавить статистику и алертинг

```python
'duplicate_detection_runs': 0,
'symbols_with_duplicates': [],
'last_duplicate_check': None,
```

#### 7.4 Опциональное автоматическое исправление

Добавить параметр конфигурации:
```python
AGED_AUTO_CANCEL_DUPLICATES=false  # По умолчанию не трогаем
```

Если `true` и найдены дубликаты:
- Оставить ордер с лучшей ценой
- Отменить остальные
- Залогировать действие

### Git commit
```bash
git add core/aged_position_manager.py main.py config/settings.py
git commit -m "📊 Phase 7: Add duplicate orders monitoring

Implemented active duplicate detection:
- Periodic check every 5 minutes
- Detect multiple exit orders per symbol
- Critical alerts for duplicates
- Optional auto-cleanup (disabled by default)

Implements: Improvement #3 (Monitoring & Alerting)

Files: core/aged_position_manager.py, main.py
Related to: AGE_DETECTOR_AUDIT_REPORT_RU.md Section 7.2"
```

### Тестирование фазы 7

#### 7.1 Unit-тест

```python
async def test_detect_duplicate_orders_none():
    # No duplicates -> return []
    pass

async def test_detect_duplicate_orders_found():
    # Mock 2 exit orders for same symbol
    # Should return list with 1 item
    pass
```

#### 7.2 Integration test

Сложно тестировать без реальных дубликатов.

**Альтернатива:** Проверить, что метод вызывается:
```bash
grep "_detect_duplicate_orders" logs/trading_bot.log
```

### Критерии успеха фазы 7
- ✅ Метод обнаружения дубликатов реализован
- ✅ Интегрирован в главный цикл
- ✅ Алертинг работает
- ✅ Git commit создан

### Время
1 час

---

## 🎉 ФАЗА 8: Финальное тестирование и документация

### Цель
Провести комплексное тестирование всех исправлений вместе, создать итоговую документацию и подготовить к merge в main.

### Задачи

#### 8.1 Комплексное integration тестирование (2 часа)

**Подготовка:**
```bash
# Консервативные настройки для первого запуска
cat > .env.test << EOF
MAX_POSITION_AGE_HOURS=1
AGED_GRACE_PERIOD_HOURS=4
AGED_LOSS_STEP_PERCENT=0.3
AGED_MAX_LOSS_PERCENT=5.0
AGED_PROFITABLE_CLOSE_THRESHOLD=0.2
EOF
```

**Запуск:**
```bash
# Запустить бота в testnet
python main.py --testnet &
BOT_PID=$!

# Запустить расширенный мониторинг (2 часа)
timeout 7200 python monitor_age_detector.py logs/trading_bot.log

# Сохранить результат
mv age_detector_diagnostic_*.json phase8_final_test_results.json
```

**Что проверять:**
1. Order proliferation:
   - `proliferation_issues` должен быть пуст
   - Каждый символ: максимум 2-3 ордера за 2 часа (обновления)

2. Дедупликация:
   - `duplicates_prevented` > 0
   - "Exit order already exists" появляется в логах

3. Прибыльные позиции:
   - Если есть, должны закрываться market-ордером
   - `profitable_closes` > 0

4. Ошибки:
   - Нет необработанных исключений
   - Geo-restricted символы пропускаются корректно

#### 8.2 Анализ метрик

```bash
# Извлечь финальные статистики
grep "Aged positions processed" logs/trading_bot.log | tail -20

# Проверить статистику из самого модуля
python -c "
import asyncio
from core.aged_position_manager import AgedPositionManager
# ... load and print statistics
"
```

Создать файл `PHASE8_FINAL_METRICS.md` с:
- Количество обработанных позиций
- Созданных vs обновленных ордеров
- Предотвращенных дубликатов
- Profitable closes
- Geo-restricted skips

#### 8.3 Сравнение с baseline

**Создать файл:** `BEFORE_AFTER_COMPARISON.md`

| Метрика | До исправлений (Baseline) | После исправлений (Phase 8) | Улучшение |
|---------|---------------------------|------------------------------|-----------|
| Создано "initial" ордеров за час | ~300 | ~14 | -95% |
| Дубликатов предотвращено | 0 | >15 | ∞ |
| Множественных ордеров на символ | Да (30+) | Нет (0) | ✅ Исправлено |
| Обработано geo-restrictions | Спам в логах | Корректно пропущено | ✅ Улучшено |
| Profitable positions | Не обрабатывались | Market close | ✅ Добавлено |

#### 8.4 Обновление документации

**Файлы для обновления:**

1. **README.md** (если есть секция про Age Detector):
   - Добавить описание нового поведения
   - Обновить конфигурационные параметры

2. **Создать CHANGELOG_AGE_DETECTOR.md**:
   ```markdown
   # Age Detector Module - Changelog

   ## Version 2.0 - 2025-10-15

   ### Fixed
   - 🔴 [CRITICAL] Order proliferation bug - multiple orders no longer created
   - 🟡 Double duplicate checking removed
   - 🟡 Cache invalidation timing improved
   - 🟡 Geographic restrictions handled gracefully

   ### Added
   - ✨ Profit-taking logic (market close for profitable aged positions)
   - ✨ Order state validation before cancellation
   - ✨ Duplicate orders monitoring
   - ✨ Comprehensive error handling

   ### Changed
   - 🔧 Simplified order management logic (167 lines → 40 lines)
   - 🔧 Centralized order operations in EnhancedExchangeManager

   ### Metrics
   - Order creation reduced by 95%
   - Zero order proliferation detected in 2h test
   - Duplicate prevention now working (15+ prevented in test)
   ```

3. **Обновить AGE_DETECTOR_AUDIT_SUMMARY_RU.md**:
   - Добавить секцию "ИСПРАВЛЕНИЯ ПРИМЕНЕНЫ"
   - Обновить статус: ❌ → ✅
   - Ссылка на CHANGELOG

#### 8.5 Code review checklist

**Создать файл:** `PHASE8_CODE_REVIEW_CHECKLIST.md`

Проверить:
- [ ] Все TODO/FIXME комментарии удалены или обработаны
- [ ] Docstrings актуальны
- [ ] Типы аннотированы (где возможно)
- [ ] Нет dead code
- [ ] Логирование уровней корректно (DEBUG/INFO/WARNING/ERROR/CRITICAL)
- [ ] Нет hardcoded значений (всё через конфиг)
- [ ] Обработка исключений полная
- [ ] Unit-тесты покрывают новый код
- [ ] Нет секретов в коде

#### 8.6 Создание Pull Request описания

**Файл:** `PR_DESCRIPTION.md`

```markdown
# Fix: Age Detector Order Proliferation Bug

## Problem
Age Detector module was creating multiple limit exit orders for each position instead of updating a single order.

Evidence: 7,165 orders created in 23h vs expected ~14 (one per position).

## Solution
Implemented centralized order management through unified method `create_or_update_exit_order()`.

## Changes
- ✅ Phase 1: Added unified method in EnhancedExchangeManager
- ✅ Phase 2: Refactored AgedPositionManager (167→40 lines)
- ✅ Phase 3: Improved cache invalidation
- ✅ Phase 4: Handled geographic restrictions
- ✅ Phase 5: Added profit-taking logic
- ✅ Phase 6: Added order state validation
- ✅ Phase 7: Added duplicate monitoring
- ✅ Phase 8: Comprehensive testing

## Testing
- Unit tests: All passing ✅
- Integration test (2h): Zero proliferation detected ✅
- Duplicate prevention: Working (15+ prevented) ✅
- Performance: 95% reduction in order creation ✅

## Metrics
See: BEFORE_AFTER_COMPARISON.md

## Documentation
- CHANGELOG_AGE_DETECTOR.md
- PHASE8_FINAL_METRICS.md
- Updated audit report status

## Rollback Plan
All changes in feature branch `fix/age-detector-order-proliferation`
Each phase is a separate commit - can rollback to any phase.
```

### Git commits

```bash
# Сначала добавить все метрики и документацию
git add PHASE8_FINAL_METRICS.md BEFORE_AFTER_COMPARISON.md \
        CHANGELOG_AGE_DETECTOR.md PHASE8_CODE_REVIEW_CHECKLIST.md \
        PR_DESCRIPTION.md

git commit -m "📝 Phase 8: Final testing and documentation

Completed comprehensive testing:
- 2h integration test in testnet: PASSED
- Zero order proliferation detected
- Duplicate prevention working
- All metrics improved

Documentation:
- Before/After comparison
- Changelog created
- PR description prepared
- Code review checklist

Ready for merge to main.

Files: Multiple documentation files
Related to: AGE_DETECTOR_AUDIT_REPORT_RU.md (all sections)"

# Merge всех изменений в один squash commit (опционально)
git rebase -i HEAD~8  # Если хотим squash в 1 коммит

# Или оставить как есть - 8 отдельных коммитов для истории
```

### Критерии успеха фазы 8
- ✅ Integration test (2ч) пройден успешно
- ✅ Все метрики улучшены vs baseline
- ✅ Документация полная и актуальная
- ✅ Code review checklist выполнен
- ✅ PR description готов
- ✅ Все тесты проходят
- ✅ Git commits чистые и понятные

### Время
3 часа (включая 2ч мониторинга)

---

## 📦 ФАЗА 9: Merge и deployment

### Цель
Безопасно влить изменения в main и развернуть в production с мониторингом.

### Задачи

#### 9.1 Pre-merge проверки

```bash
# Убедиться что на актуальной версии main
git checkout main
git pull origin main

# Вернуться в feature branch
git checkout fix/age-detector-order-proliferation

# Rebase на актуальный main (если были другие изменения)
git rebase main

# Разрешить конфликты если есть

# Запустить ВСЕ тесты после rebase
pytest tests/ -v

# Проверить что всё работает
python -m py_compile core/*.py
```

#### 9.2 Создание Pull Request

**GitHub/GitLab:**
1. Push feature branch:
   ```bash
   git push origin fix/age-detector-order-proliferation
   ```

2. Создать PR через веб-интерфейс:
   - Title: "Fix: Age Detector Order Proliferation Bug"
   - Description: Скопировать из `PR_DESCRIPTION.md`
   - Labels: `bug`, `critical`, `tested`
   - Reviewers: Назначить ревьюеров

3. Приложить:
   - `BEFORE_AFTER_COMPARISON.md`
   - `CHANGELOG_AGE_DETECTOR.md`
   - Screenshots метрик (если есть)

#### 9.3 Code review процесс

Дождаться:
- [ ] Минимум 1 approval от reviewer
- [ ] Все CI/CD checks прошли (если настроены)
- [ ] Нет блокирующих комментариев

Исправить feedback если есть.

#### 9.4 Merge в main

**Стратегия merge:** Squash (рекомендуется) или Merge commit (если важна детальная история)

```bash
# После approval через веб-интерфейс
# ИЛИ локально:
git checkout main
git merge --squash fix/age-detector-order-proliferation
git commit -m "Fix: Age Detector order proliferation bug (#ISSUE_NUMBER)

- Unified order management method
- 95% reduction in order creation
- Duplicate prevention working
- Comprehensive testing passed

Fixes #ISSUE_NUMBER
See: CHANGELOG_AGE_DETECTOR.md"

git push origin main
```

#### 9.5 Deployment в production

**ВАЖНО:** Поэтапное развертывание!

##### 9.5.1 Pre-deployment checklist

- [ ] Backup production database
- [ ] Backup .env файла
- [ ] Создать rollback plan
- [ ] Уведомить команду о deployment
- [ ] Установить мониторинг

##### 9.5.2 Deployment steps

```bash
# На production сервере
cd /path/to/TradingBot

# Создать backup
./scripts/backup_before_deployment.sh

# Pull изменений
git fetch origin
git checkout main
git pull origin main

# Проверить .env конфигурацию
# Рекомендуется консервативные настройки первые 24ч:
cat >> .env << EOF
# Conservative settings for first 24h after Age Detector fix
MAX_POSITION_AGE_HOURS=6
AGED_GRACE_PERIOD_HOURS=12
AGED_LOSS_STEP_PERCENT=0.3
AGED_MAX_LOSS_PERCENT=5.0
AGED_PROFITABLE_CLOSE_THRESHOLD=0.2
EOF

# Restart сервиса
sudo systemctl restart trading-bot

# Проверить что запустился
sudo systemctl status trading-bot

# Начать мониторинг
tail -f logs/trading_bot.log | grep -i "aged\|exit order"
```

##### 9.5.3 Post-deployment мониторинг (24 часа)

**Первые 15 минут:**
```bash
# В отдельном терминале запустить монитор
python monitor_age_detector.py logs/trading_bot.log

# Ожидаемые результаты:
# - proliferation_issues = []
# - duplicates_prevented > 0
# - Нет критических ошибок
```

**Первые 2 часа:**
- Проверять логи каждые 30 минут
- Следить за метриками:
  ```bash
  grep "Aged positions processed" logs/trading_bot.log | tail -10
  ```
- Проверить отсутствие множественных ордеров на бирже вручную

**Первые 24 часа:**
- Мониторинг каждые 4 часа
- Сравнить с baseline метриками
- Собрать статистику

**Создать файл:** `PRODUCTION_DEPLOYMENT_LOG.md`
```markdown
# Production Deployment - Age Detector Fix

## Deployment Info
- Date: 2025-10-15
- Time: [ВРЕМЯ]
- Deployed by: [ИМЯ]
- Commit: [GIT HASH]

## Pre-deployment
- [x] Database backup created: backup_20251015.sql
- [x] .env backup created
- [x] Team notified

## Deployment
- [x] Code pulled from main
- [x] Service restarted
- [x] Initial monitoring started

## Monitoring Results

### T+15min
- proliferation_issues: []
- duplicates_prevented: 12
- errors: 0
- Status: ✅ GOOD

### T+2h
- positions_processed: 87
- orders_created: 14
- orders_updated: 23
- duplicates_prevented: 50
- Status: ✅ GOOD

### T+24h
- [TO BE FILLED]

## Issues Found
- None

## Rollback Required
- No
```

##### 9.5.4 Rollback plan (если что-то пошло не так)

```bash
# НЕМЕДЛЕННЫЙ ОТКАТ

# 1. Остановить бота
sudo systemctl stop trading-bot

# 2. Откатить код
git checkout [PREVIOUS_COMMIT_HASH]

# 3. Восстановить .env (если менялся)
cp .env.backup .env

# 4. Запустить
sudo systemctl start trading-bot

# 5. Уведомить команду
# 6. Создать post-mortem отчет
```

#### 9.6 Постепенное ужесточение параметров

После 24ч успешной работы с консервативными настройками:

```bash
# День 2-3: Средние настройки
MAX_POSITION_AGE_HOURS=4
AGED_GRACE_PERIOD_HOURS=10

# День 4-7: Стандартные настройки
MAX_POSITION_AGE_HOURS=3
AGED_GRACE_PERIOD_HOURS=8
AGED_LOSS_STEP_PERCENT=0.5
AGED_MAX_LOSS_PERCENT=10.0
```

Каждый раз:
- Restart сервиса
- Мониторинг 2 часа
- Проверка метрик

### Git tag

После успешного deployment:
```bash
git tag -a v2.0.0-age-detector-fix -m "Age Detector order proliferation fix deployed

- Zero proliferation in 24h production test
- Duplicate prevention working
- All metrics improved

Deployed: 2025-10-15
See: CHANGELOG_AGE_DETECTOR.md"

git push origin v2.0.0-age-detector-fix
```

### Критерии успеха фазы 9
- ✅ PR создан и approved
- ✅ Merged в main
- ✅ Deployed в production
- ✅ 24h мониторинг прошел успешно
- ✅ Метрики подтверждают исправление
- ✅ Tag создан

### Время
1 час (deployment) + 24 часа (мониторинг)

---

## 📊 Суммарная таблица всех фаз

| Фаза | Название | Время | Статус | Git Commit |
|------|----------|-------|--------|------------|
| 0 | Подготовка и baseline | 30 мин | ⏳ Pending | ✅ |
| 1 | Унифицированный метод в EnhancedExchangeManager | 1.5 ч | ⏳ Pending | ✅ |
| 2 | Рефакторинг AgedPositionManager | 2 ч | ⏳ Pending | ✅ |
| 3 | Улучшение кэш-инвалидации | 1 ч | ⏳ Pending | ✅ |
| 4 | Обработка geo-ограничений | 1 ч | ⏳ Pending | ✅ |
| 5 | Логика взятия прибыли | 1.5 ч | ⏳ Pending | ✅ |
| 6 | Валидация состояния ордера | 1 ч | ⏳ Pending | ✅ |
| 7 | Мониторинг дубликатов | 1 ч | ⏳ Pending | ✅ |
| 8 | Финальное тестирование | 3 ч | ⏳ Pending | ✅ |
| 9 | Merge и deployment | 1 ч + 24ч | ⏳ Pending | ✅ |

**Итого:** ~12 часов активной работы + 24 часа мониторинга

---

## 🎯 Критерии полного успеха проекта

### Технические критерии
- ✅ Order proliferation = 0 (нет множественных ордеров)
- ✅ Duplicate prevention работает (метрика > 0)
- ✅ Все unit-тесты проходят
- ✅ Integration test 2ч прошел успешно
- ✅ Production deployment успешен
- ✅ 24ч production мониторинг без проблем

### Метрики улучшения
- ✅ Создание ордеров сократилось на 95%
- ✅ "Exit order already exists" появляется в логах
- ✅ Нет ошибок "multiple orders for symbol"
- ✅ Geo-restricted символы обрабатываются без спама
- ✅ Profitable positions закрываются market-ордером

### Документация
- ✅ CHANGELOG создан
- ✅ Audit report обновлен (статус исправлений)
- ✅ Before/After сравнение задокументировано
- ✅ PR description полный
- ✅ Production deployment log заполнен

### Процесс
- ✅ Каждая фаза имеет отдельный git commit
- ✅ Тестирование после каждой фазы
- ✅ Возможность отката на любом этапе
- ✅ Code review выполнен
- ✅ Team notified о deployment

---

## 📝 Tracking прогресса

**Создать файл:** `IMPLEMENTATION_PROGRESS.md`

Обновлять после каждой фазы:

```markdown
# Age Detector Fix - Implementation Progress

Last updated: [ДАТА ВРЕМЯ]

## Phase Status

- [x] Phase 0: Baseline ✅ Completed 2025-10-15 10:00
- [ ] Phase 1: Unified method ⏳ In Progress
- [ ] Phase 2: Refactor AgedPositionManager
- [ ] Phase 3: Cache invalidation
- [ ] Phase 4: Geo restrictions
- [ ] Phase 5: Profit taking
- [ ] Phase 6: Order validation
- [ ] Phase 7: Duplicate monitoring
- [ ] Phase 8: Final testing
- [ ] Phase 9: Deployment

## Current Phase Details

### Phase 1: Unified Method
- Started: 2025-10-15 10:30
- Expected completion: 2025-10-15 12:00
- Status: Writing create_or_update_exit_order() method
- Blockers: None
- Next step: Add unit tests

## Issues Log

(Empty - no issues yet)

## Notes

- Using testnet for all testing
- Conservative config for first deployment
- Team notified about planned deployment
```

---

## 🚨 Важные напоминания

### Перед началом каждой фазы
1. ✅ Убедиться, что предыдущая фаза завершена успешно
2. ✅ Проверить, что все тесты проходят
3. ✅ Создать git commit предыдущей фазы
4. ✅ Обновить `IMPLEMENTATION_PROGRESS.md`

### Во время фазы
1. ✅ Делать частые локальные коммиты (можно squash позже)
2. ✅ Тестировать изменения по мере написания
3. ✅ Документировать неожиданные проблемы
4. ✅ Не переходить к следующей фазе при проблемах

### После каждой фазы
1. ✅ Запустить все тесты
2. ✅ Проверить, что ничего не сломалось
3. ✅ Создать чистый git commit с правильным сообщением
4. ✅ Обновить progress tracker
5. ✅ Сделать short break перед следующей фазой

### При обнаружении проблемы
1. 🛑 STOP - не продолжать дальше
2. 📝 Задокументировать проблему
3. 🔍 Исследовать причину
4. 🔧 Исправить
5. ✅ Перетестировать
6. ➡️ Только тогда продолжить

---

## 📞 Контакты и эскалация

**Если возникли проблемы:**

1. **Технические вопросы:** См. `AGE_DETECTOR_AUDIT_REPORT_RU.md`
2. **Проблемы с тестами:** Проверить `IMPLEMENTATION_PROGRESS.md` → Issues Log
3. **Production проблемы:** Немедленный rollback → Post-mortem

---

**КОНЕЦ ПЛАНА**

Этот план готов к исполнению. Начинайте с Фазы 0.

Удачи! 🚀
