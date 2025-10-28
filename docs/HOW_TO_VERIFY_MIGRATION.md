# Как Отследить Что Бот Использует Правильные Параметры из БД

**Вопрос**: Как отследить что бот реально использует правильные параметры из базы? Это будет видно в логах? Как отследить что TS правильно мониторит активации для каждой из позиции на правильных уровнях?

**Ответ**: Да! У нас есть 3 способа проверки.

---

## ✅ Способ 1: Автоматическая Проверка (Рекомендуется)

### Скрипт Проверки БД и Состояния

```bash
python tools/verify_params_migration.py
```

**Что проверяет**:
- ✅ monitoring.params содержит разные значения для Binance и Bybit
- ✅ monitoring.positions имеет колонки trailing_activation_percent и trailing_callback_percent
- ✅ Активные позиции сохранили trailing params
- ✅ Показывает .env config для сравнения

**Вывод**:
```
📊 STEP 1: Checking monitoring.params (per-exchange parameters)
+----+----------+---------+-----------------+---------------+
| ID | Exchange | SL %    | TS Activation % | TS Callback % |
+====+==========+=========+=================+===============+
| 1  | binance  | 4.0000% | 2.0000%         | 0.5000%       |
| 2  | bybit    | 6.0000% | 2.5000%         | 0.5000%       |
+----+----------+---------+-----------------+---------------+

✅ CONFIRMED: Different SL% - Binance: 4.0000% vs Bybit: 6.0000%
✅ CONFIRMED: Different TS Activation% - Binance: 2.0000% vs Bybit: 2.5000%
```

**Что искать**:
- ✅ "✅ CONFIRMED: Different SL%" - значит per-exchange параметры есть
- ✅ "✅ CONFIRMED: Different TS Activation%" - значит trailing params разные
- ❌ "No data in monitoring.params" - ПРОБЛЕМА! БД не заполнена

---

## ✅ Способ 2: Мониторинг Активаций в Реальном Времени

### Скрипт Живого Мониторинга TS

```bash
python tools/monitor_ts_activations.py
```

**Что показывает** (обновляется каждые 5 секунд):
- 🔴 Текущая цена vs цена активации
- 🔴 Расстояние до активации (%)
- 🔴 **ОТКУДА ВЗЯТЫ ПАРАМЕТРЫ** (DB vs .env)

**Вывод**:
```
📊 Exchange: BINANCE
   DB Params: activation=2.0%, callback=0.5%

+----------+------+---------------+------------------+----------------+---------------------+
| Symbol   | Side | Current Price | Activation Price | Distance       | Activation % Source |
+==========+======+===============+==================+================+=====================+
| BTCUSDT  | LONG | 67891.23      | 69249.05         | ⚪ 2.00%       | ✅ DB (2.0%)        |
| ETHUSDT  | LONG | 3298.45       | 3310.58          | 🟡 0.37%       | ✅ DB (2.0%)        |
+----------+------+---------------+------------------+----------------+---------------------+

📊 Exchange: BYBIT
   DB Params: activation=2.5%, callback=0.5%

+----------+------+---------------+------------------+----------------+---------------------+
| Symbol   | Side | Current Price | Activation Price | Distance       | Activation % Source |
+==========+======+===============+==================+================+=====================+
| SOLUSDT  | LONG | 145.80        | 146.06           | 🔥 0.18%       | ✅ DB (2.5%)        |
+----------+------+---------------+------------------+----------------+---------------------+
```

**КРИТИЧЕСКИ ВАЖНО**:
- ✅ **"✅ DB (2.0%)"** - ПРАВИЛЬНО! Бот использует параметры из monitoring.params
- ✅ **"📌 Position (2.0%)"** - ОК! Бот использует per-position параметры (Variant B)
- ❌ **"⚠️  Config (3.0%)"** - ПЛОХО! Бот использует .env fallback (миграция НЕ работает!)

**Обрати внимание**:
- Binance positions должны показывать: **2.0%** activation
- Bybit positions должны показывать: **2.5%** activation
- Если все показывают одинаковые значения (например, 3.0%) → бот использует .env → ПРОБЛЕМА!

---

## ✅ Способ 3: Проверка Логов

### Логи При Открытии Позиции

**Команда**:
```bash
tail -f logs/bot.log | grep "📊 Using trailing"
```

**ПРАВИЛЬНЫЙ вывод** (когда открывается Binance позиция):
```
2025-10-28 15:30:45 [DEBUG] 📊 Using trailing_activation_filter from DB for binance: 2.0%
2025-10-28 15:30:45 [DEBUG] 📊 Using trailing_distance_filter from DB for binance: 0.5%
```

**ПРАВИЛЬНЫЙ вывод** (когда открывается Bybit позиция):
```
2025-10-28 15:30:50 [DEBUG] 📊 Using trailing_activation_filter from DB for bybit: 2.5%
2025-10-28 15:30:50 [DEBUG] 📊 Using trailing_distance_filter from DB for bybit: 0.5%
```

**🔴 RED FLAG** (миграция НЕ работает):
```
2025-10-28 15:30:45 [WARNING] ⚠️  trailing_activation_filter not in DB for binance, using .env fallback: 3.0%
```

Если видишь это WARNING → значит:
- ❌ monitoring.params пустая или NULL
- ❌ Бот использует старые параметры из .env
- ❌ Миграция провалилась

---

### Логи При Создании Trailing Stop

**Команда**:
```bash
tail -f logs/bot.log | grep "Using per-position trailing params"
```

**ПРАВИЛЬНЫЙ вывод**:
```
2025-10-28 15:30:46 [DEBUG] 📊 BTCUSDT: Using per-position trailing params: activation=2.0%, callback=0.5%
2025-10-28 15:30:51 [DEBUG] 📊 SOLUSDT: Using per-position trailing params: activation=2.5%, callback=0.5%
```

**🔴 RED FLAG**:
```
2025-10-28 15:30:46 [DEBUG] 📊 BTCUSDT: Using config trailing params (fallback): activation=3.0%, callback=1.0%
```

Если видишь "Using config trailing params (fallback)" → значит:
- ❌ Позиция не сохранила trailing params в БД
- ❌ create_trailing_stop() не получил position_params
- ❌ TS использует старую логику (.env)

---

## 🎯 Краткий Чеклист

### ✅ Миграция РАБОТАЕТ если:

1. **В БД**:
   ```bash
   python tools/verify_params_migration.py
   ```
   - ✅ Показывает РАЗНЫЕ значения для Binance и Bybit
   - ✅ Новые позиции имеют non-NULL trailing params

2. **В Логах**:
   ```bash
   grep "📊 Using trailing_activation_filter from DB" logs/bot.log
   ```
   - ✅ Видишь "from DB for binance: 2.0%"
   - ✅ Видишь "from DB for bybit: 2.5%" (РАЗНЫЕ!)
   - ❌ НЕ видишь "using .env fallback"

3. **В Мониторинге**:
   ```bash
   python tools/monitor_ts_activations.py
   ```
   - ✅ Все позиции показывают "✅ DB (X%)"
   - ✅ Binance: 2.0%, Bybit: 2.5% (РАЗНЫЕ!)

---

### ❌ Миграция НЕ РАБОТАЕТ если:

1. **В Логах видишь**:
   - ❌ "⚠️  trailing_activation_filter not in DB, using .env fallback"
   - ❌ "Using config trailing params (fallback)"
   - ❌ Одинаковые проценты для Binance и Bybit

2. **В Мониторинге видишь**:
   - ❌ "⚠️  Config (3.0%)" вместо "✅ DB (2.0%)"
   - ❌ Все позиции показывают одинаковые значения

3. **В БД**:
   - ❌ monitoring.params пустая
   - ❌ Новые позиции имеют NULL trailing params

---

## 📝 Пример: Как Проверить После Деплоя

### Шаг 1: Проверь БД
```bash
python tools/verify_params_migration.py
```
Должен показать РАЗНЫЕ значения для Binance (2.0%) и Bybit (2.5%)

### Шаг 2: Запусти Мониторинг
```bash
python tools/monitor_ts_activations.py
```
Оставь работать в отдельном терминале. Следи за колонкой "Activation % Source".

### Шаг 3: Открой Позицию
Когда придет сигнал и откроется позиция, проверь логи:
```bash
tail -n 100 logs/bot.log | grep "📊 Using trailing"
```

### Шаг 4: Проверь Результат
Должен увидеть:
```
📊 Using trailing_activation_filter from DB for binance: 2.0%
📊 BTCUSDT: Using per-position trailing params: activation=2.0%, callback=0.5%
```

Если видишь "using .env fallback" или "Using config trailing params" → ПРОБЛЕМА!

---

## 🚨 Что Делать Если Видишь Проблему?

### Проблема: "trailing_activation_filter not in DB"

**Причина**: monitoring.params пустая

**Решение**:
```sql
-- Проверь monitoring.params
SELECT * FROM monitoring.params;

-- Если пустая, вручную заполни:
INSERT INTO monitoring.params (exchange_id, trailing_activation_filter, trailing_distance_filter, stop_loss_filter, max_trades_filter)
VALUES
    (1, 2.0, 0.5, 4.0, 6),  -- Binance
    (2, 2.5, 0.5, 6.0, 4)   -- Bybit
ON CONFLICT (exchange_id) DO UPDATE SET
    trailing_activation_filter = EXCLUDED.trailing_activation_filter,
    trailing_distance_filter = EXCLUDED.trailing_distance_filter;
```

---

## 📚 Дополнительная Документация

**Полный guide**: `docs/PARAMS_MIGRATION_VERIFICATION_GUIDE.md`
- Детальные SQL запросы
- Troubleshooting
- Test scenarios

**План миграции**: `docs/SL_TS_PARAMS_MIGRATION_ULTRA_DETAILED_PLAN.md`
- Архитектура
- Все изменения кода
- Rollback procedures

---

**ИТОГ**: У тебя есть **3 инструмента** для проверки:
1. 🔧 **verify_params_migration.py** - проверка БД и состояния
2. 📊 **monitor_ts_activations.py** - живой мониторинг TS (видно откуда параметры!)
3. 📝 **Логи** - grep по паттернам выше

Все логи уже добавлены в код, инструменты готовы к использованию!
