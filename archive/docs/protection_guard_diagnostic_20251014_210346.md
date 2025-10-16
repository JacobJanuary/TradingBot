# ДИАГНОСТИЧЕСКИЙ ОТЧЕТ: Protection Guard / Stop Loss Manager
**Дата:** 2025-10-14T21:03:46.783628+00:00
**Длительность:** 155 секунд (2.6 минут)

---

## EXECUTIVE SUMMARY

### Общая оценка: ✅ PASS

**Критические проблемы:** 0
**Высокий риск:** 4
**Средний/низкий риск:** 0

---

## МЕТРИКИ РАБОТЫ

### Активность Protection System
- **Проверок SL выполнено:** 4
- **Позиций проверено:** 60
- **Позиций с SL:** 56
- **Позиций без SL:** 4
- **SL ордеров обнаружено:** 56
- **SL создано:** 0
- **Ошибок создания SL:** 0
- **Ошибок API:** 0

### Производительность
- **Проверок в минуту:** 1.55
- **Среднее время между проверками:** 38.8с

---

## КЛЮЧЕВЫЕ НАХОДКИ

### Архитектура системы

**ФАКТ 1:** Protection Guard (`protection/position_guard.py`) НЕ ИСПОЛЬЗУЕТСЯ в production
- ❌ PositionGuard не инициализируется в `main.py`
- ❌ Нет интеграции с Position Manager
- ✅ Но код PositionGuard существует и выглядит функционально

**ФАКТ 2:** Реальная защита реализована в `core/stop_loss_manager.py`
- ✅ StopLossManager используется в position_manager.py
- ✅ Проверка SL происходит каждые **120 секунд** (2 минуты)
- ✅ Вызывается через `check_positions_protection()` в periodic sync

**ФАКТ 3:** Метод проверки SL
```python
# Файл: core/stop_loss_manager.py:43
async def has_stop_loss(symbol: str) -> Tuple[bool, Optional[str]]:
    # ПРИОРИТЕТ 1: Position-attached SL (для Bybit через position.info.stopLoss)
    # ПРИОРИТЕТ 2: Conditional stop orders (через fetch_open_orders)
```

### API Методы

**Для получения позиций:**
- Bybit: `exchange.fetch_positions(params={'category': 'linear'})`
- Проверка: `float(pos.get('contracts', 0)) > 0`

**Для проверки SL:**
- Bybit position-attached: `pos.get('info', {}).get('stopLoss', '0')`
- Bybit stop orders: `exchange.fetch_open_orders(symbol, params={'category': 'linear', 'orderFilter': 'StopOrder'})`
- Generic: `exchange.fetch_open_orders(symbol)`

**Для установки SL:**
- Используется `_set_bybit_stop_loss` или `_set_generic_stop_loss`
- Метод: `setTradingStop` для Bybit position-attached SL
- Fallback: conditional stop orders

---

## КРИТИЧЕСКИЕ ПРОБЛЕМЫ

### ❌ ПРОБЛЕМА #1: Position HNT/USDT:USDT without Stop Loss
**Серьезность:** HIGH
**Описание:** Position HNT/USDT:USDT on bybit (long 59.88) has no stop loss protection
**Доказательства:**
```json
{
  "exchange": "bybit",
  "symbol": "HNT/USDT:USDT",
  "side": "long",
  "contracts": 59.88,
  "entry_price": "1.772732"
}
```
**Время обнаружения:** 2025-10-14T21:04:00.288157+00:00

---

### ❌ ПРОБЛЕМА #2: Position HNT/USDT:USDT without Stop Loss
**Серьезность:** HIGH
**Описание:** Position HNT/USDT:USDT on bybit (long 59.88) has no stop loss protection
**Доказательства:**
```json
{
  "exchange": "bybit",
  "symbol": "HNT/USDT:USDT",
  "side": "long",
  "contracts": 59.88,
  "entry_price": "1.772732"
}
```
**Время обнаружения:** 2025-10-14T21:04:37.268390+00:00

---

### ❌ ПРОБЛЕМА #3: Position HNT/USDT:USDT without Stop Loss
**Серьезность:** HIGH
**Описание:** Position HNT/USDT:USDT on bybit (long 59.88) has no stop loss protection
**Доказательства:**
```json
{
  "exchange": "bybit",
  "symbol": "HNT/USDT:USDT",
  "side": "long",
  "contracts": 59.88,
  "entry_price": "1.772732"
}
```
**Время обнаружения:** 2025-10-14T21:05:14.357724+00:00

---

### ❌ ПРОБЛЕМА #4: Position HNT/USDT:USDT without Stop Loss
**Серьезность:** HIGH
**Описание:** Position HNT/USDT:USDT on bybit (long 59.88) has no stop loss protection
**Доказательства:**
```json
{
  "exchange": "bybit",
  "symbol": "HNT/USDT:USDT",
  "side": "long",
  "contracts": 59.88,
  "entry_price": "1.772732"
}
```
**Время обнаружения:** 2025-10-14T21:05:51.614811+00:00

---

## СОБЫТИЯ МОНИТОРИНГА

Всего событий: 60

- **position_checked:** 60


---

## API CALLS ANALYSIS

Всего вызовов API: 8
Успешных: 8
Неудачных: 0

### Примеры вызовов (последние 5):

#### fetch_positions @ 2025-10-14T21:04:32.160723+00:00
- **Параметры:** `{'exchange': 'bybit'}`
- **Статус:** ✅ Success
- **Ответ:** `Got 13 positions...`

#### fetch_positions @ 2025-10-14T21:05:08.012785+00:00
- **Параметры:** `{'exchange': 'binance'}`
- **Статус:** ✅ Success
- **Ответ:** `Got 2 positions...`

#### fetch_positions @ 2025-10-14T21:05:09.398569+00:00
- **Параметры:** `{'exchange': 'bybit'}`
- **Статус:** ✅ Success
- **Ответ:** `Got 13 positions...`

#### fetch_positions @ 2025-10-14T21:05:44.951116+00:00
- **Параметры:** `{'exchange': 'binance'}`
- **Статус:** ✅ Success
- **Ответ:** `Got 2 positions...`

#### fetch_positions @ 2025-10-14T21:05:46.221045+00:00
- **Параметры:** `{'exchange': 'bybit'}`
- **Статус:** ✅ Success
- **Ответ:** `Got 13 positions...`


---

## РЕЗУЛЬТАТЫ ВАЛИДАЦИИ

| # | Проверка | Статус | Комментарий |
|---|----------|--------|-------------|
| 1 | Position Guard интегрирован в main.py | ❌ | НЕ используется |
| 2 | StopLossManager используется | ✅ | Корректно |
| 3 | Периодическая проверка SL настроена | ✅ | Каждые 120 сек |
| 4 | API метод для позиций корректен | ✅ | fetch_positions |
| 5 | Проверка position.info.stopLoss (Bybit) | ✅ | Корректно |
| 6 | Проверка stop orders (fallback) | ✅ | Корректно |
| 7 | Логика установки SL корректна | ⚠️ | Требует проверки |
| 8 | Обработка ошибок API | ✅ | Присутствует |
| 9 | Retry logic для SL | ✅ | max_retries=3 |
| 10 | Логирование событий | ✅ | Event logger |

---

## РЕКОМЕНДАЦИИ

### Критически важно (исправить немедленно):

- ✅ Критических проблем не обнаружено


### Улучшения:
- [ ] Интегрировать PositionGuard в main.py для продвинутой защиты
- [ ] Добавить метрики производительности Protection System
- [ ] Настроить алерты на отсутствие SL более 5 минут
- [ ] Добавить unit-тесты для StopLossManager

---

## ЗАКЛЮЧЕНИЕ

Система защиты позиций работает корректно. Критических проблем не обнаружено.

**Следующие шаги:**
1. Исправить критические проблемы
2. Провести повторное тестирование
3. Мониторинг в production

---
**Сгенерировано:** 2025-10-14T21:06:22.122591+00:00
**Версия скрипта:** 1.0
