# ДИАГНОСТИЧЕСКИЙ ОТЧЕТ: Protection Guard / Stop Loss Manager
**Дата:** 2025-10-14T20:12:50.065346+00:00
**Длительность:** 79 секунд (1.3 минут)

---

## EXECUTIVE SUMMARY

### Общая оценка: ✅ PASS

**Критические проблемы:** 0
**Высокий риск:** 0
**Средний/низкий риск:** 0

---

## МЕТРИКИ РАБОТЫ

### Активность Protection System
- **Проверок SL выполнено:** 2
- **Позиций проверено:** 28
- **Позиций с SL:** 28
- **Позиций без SL:** 0
- **SL ордеров обнаружено:** 28
- **SL создано:** 0
- **Ошибок создания SL:** 0
- **Ошибок API:** 0

### Производительность
- **Проверок в минуту:** 1.52
- **Среднее время между проверками:** 39.5с

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

✅ Критических проблем не обнаружено.

---

## СОБЫТИЯ МОНИТОРИНГА

Всего событий: 28

- **position_checked:** 28


---

## API CALLS ANALYSIS

Всего вызовов API: 4
Успешных: 4
Неудачных: 0

### Примеры вызовов (последние 5):

#### fetch_positions @ 2025-10-14T20:12:57.604714+00:00
- **Параметры:** `{'exchange': 'binance'}`
- **Статус:** ✅ Success
- **Ответ:** `Got 2 positions...`

#### fetch_positions @ 2025-10-14T20:12:58.576805+00:00
- **Параметры:** `{'exchange': 'bybit'}`
- **Статус:** ✅ Success
- **Ответ:** `Got 12 positions...`

#### fetch_positions @ 2025-10-14T20:13:33.241743+00:00
- **Параметры:** `{'exchange': 'binance'}`
- **Статус:** ✅ Success
- **Ответ:** `Got 2 positions...`

#### fetch_positions @ 2025-10-14T20:13:34.522471+00:00
- **Параметры:** `{'exchange': 'bybit'}`
- **Статус:** ✅ Success
- **Ответ:** `Got 12 positions...`


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
**Сгенерировано:** 2025-10-14T20:14:09.154125+00:00
**Версия скрипта:** 1.0
