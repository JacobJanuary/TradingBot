# 🔧 FIX: Signal Filtering Logic

## ❌ ПРОБЛЕМА

**Было:**
Bridge получал сигналы от WebSocket и выбирал топ-7 (buffer_size=7) БЕЗ фильтрации по score thresholds.

```python
# СТАРАЯ ЛОГИКА (НЕПРАВИЛЬНАЯ)
def select_top_signals(signals, wave_timestamp):
    buffer_size = 7
    top_signals = signals[:buffer_size]  # ❌ Берём топ-7 БЕЗ фильтрации!
    return top_signals
```

**Последствия:**
- Если в топ-7 попадали сигналы с `score_week < score_week_filter`, они всё равно публиковались в Redis
- Freqtrade потом фильтровал их в стратегии, но это неэффективно
- Могли быть пропущены сигналы с хорошими scores, которые были на позициях 8-10

---

## ✅ РЕШЕНИЕ

**Стало:**
Bridge СНАЧАЛА фильтрует по `score_week_filter` и `score_month_filter`, ПОТОМ берёт топ-7.

```python
# НОВАЯ ЛОГИКА (ПРАВИЛЬНАЯ)
def select_top_signals(signals, wave_timestamp):
    # STEP 1: Фильтрация по score thresholds
    score_week_filter = signals[0].get('score_week_filter')
    score_month_filter = signals[0].get('score_month_filter')

    filtered_signals = []
    for signal in signals:
        if (signal['score_week'] >= score_week_filter and
            signal['score_month'] >= score_month_filter):
            filtered_signals.append(signal)

    # STEP 2: Взять топ-7 из ОТФИЛЬТРОВАННЫХ
    buffer_size = 7
    top_signals = filtered_signals[:buffer_size]  # ✅ Топ-7 из отфильтрованных!
    return top_signals
```

---

## 📊 ПРИМЕР

### До исправления:

**Входящие сигналы (отсортированы по score_week DESC):**
```
1. BTC/USDT    - score_week=95, score_month=90  ✅ (топ-1)
2. ETH/USDT    - score_week=88, score_month=85  ✅ (топ-2)
3. SOL/USDT    - score_week=82, score_month=78  ✅ (топ-3)
4. AVAX/USDT   - score_week=75, score_month=70  ✅ (топ-4)
5. LINK/USDT   - score_week=68, score_month=65  ✅ (топ-5)
6. UNI/USDT    - score_week=55, score_month=50  ✅ (топ-6)
7. AAVE/USDT   - score_week=48, score_month=45  ✅ (топ-7) ❌ НЕ ПРОХОДИТ ФИЛЬТР!
8. DOT/USDT    - score_week=72, score_month=88  ❌ Пропущен (позиция 8)
```

**Фильтры:** `score_week_filter=50`, `score_month_filter=50`

**Проблема:**
- AAVE (топ-7) НЕ проходит `score_week_filter=50` (48 < 50)
- DOT (позиция 8) ПРОХОДИТ оба фильтра, но не попал в топ-7

**Результат:** В Redis попал AAVE вместо DOT ❌

---

### После исправления:

**Шаг 1: Фильтрация**
```
1. BTC/USDT    - score_week=95, score_month=90  ✅ Прошёл
2. ETH/USDT    - score_week=88, score_month=85  ✅ Прошёл
3. SOL/USDT    - score_week=82, score_month=78  ✅ Прошёл
4. AVAX/USDT   - score_week=75, score_month=70  ✅ Прошёл
5. LINK/USDT   - score_week=68, score_month=65  ✅ Прошёл
6. UNI/USDT    - score_week=55, score_month=50  ✅ Прошёл
7. AAVE/USDT   - score_week=48, score_month=45  ❌ Отфильтрован (48 < 50)
8. DOT/USDT    - score_week=72, score_month=88  ✅ Прошёл
```

**Шаг 2: Топ-7 из отфильтрованных**
```
1. BTC/USDT    - score_week=95
2. ETH/USDT    - score_week=88
3. SOL/USDT    - score_week=82
4. AVAX/USDT   - score_week=75
5. DOT/USDT    - score_week=72  ← ✅ Теперь попал в топ-7!
6. LINK/USDT   - score_week=68
7. UNI/USDT    - score_week=55
```

**Результат:** В Redis попал DOT вместо AAVE ✅

---

## 🔍 ГДЕ ИЗМЕНЕНИЯ

**Файл:** `/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/freqtrade_integration/bridge/wave_detector.py`

**Метод:** `select_top_signals()`

**Строки:** ~304-373

**Коммит:** 2025-10-21 - Added score filtering BEFORE top-N selection

---

## 📋 ЛОГИРОВАНИЕ

**Новые логи в Bridge:**

```log
INFO - 📊 Score filtering: 45/77 signals passed (score_week>=50.0, score_month>=50.0)
DEBUG - Filtered out XRP/USDT: score_week=48.0 (need 50.0), score_month=45.0 (need 50.0)
INFO - 📊 Wave 2025-10-21T18:00:00+00:00: 45 total signals, selected top 7 (buffer=7) for up wave
```

**Что видно:**
- `45/77 signals passed` - из 77 сигналов прошли фильтр только 45
- `Filtered out XRP/USDT` - конкретные отфильтрованные сигналы (DEBUG level)
- `selected top 7` - из 45 отфильтрованных взяты топ-7

---

## ✅ ПРОВЕРКА РАБОТЫ

### Мониторинг Bridge логов:

```bash
tail -f /Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/freqtrade_integration/bridge/bridge.log | grep -E "(Score filtering|Filtered out|Wave.*total)"
```

### Ожидаемый вывод при следующей волне:

```
2025-10-21 18:05:22 - INFO - 📊 Score filtering: X/Y signals passed (score_week>=Z, score_month>=W)
2025-10-21 18:05:22 - INFO - 📊 Wave 2025-10-21T18:00:00+00:00: X total signals, selected top 7 (buffer=7) for up wave
```

Где:
- `Y` = общее количество сигналов от WebSocket
- `X` = количество прошедших фильтр
- `Z`, `W` = значения фильтров из сигналов

---

## 🎯 ИТОГО

**До:**
1. Получили 77 сигналов
2. Взяли топ-7
3. Результат: могли попасть сигналы с низкими scores

**После:**
1. Получили 77 сигналов
2. Отфильтровали по `score_week_filter` и `score_month_filter`
3. Из отфильтрованных взяли топ-7
4. Результат: только лучшие сигналы, прошедшие фильтры ✅

---

**Дата:** 2025-10-21
**Автор:** Claude Code
**Статус:** ✅ ИСПРАВЛЕНО
