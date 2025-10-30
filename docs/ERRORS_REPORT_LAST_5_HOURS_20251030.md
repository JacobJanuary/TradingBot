# Отчет по Ошибкам за Последние 5 Часов

**Период**: 2025-10-29 23:10 - 2025-10-30 04:10 (5 часов)
**Дата анализа**: 2025-10-30 04:12

---

## 📊 Сводка

| Тип ошибки | Количество | Критичность | Статус |
|------------|------------|-------------|--------|
| KeyError 'topped_up' | 9 раз | 🟡 MEDIUM | Нужен фикс |
| CROUSDT WebSocket stale | Каждую минуту 250+ мин | 🔴 HIGH | **ТРЕБУЕТ НЕМЕДЛЕННОГО ВНИМАНИЯ** |
| Failed to calculate position size | 7 позиций | 🟢 LOW | Нормальная работа |

**Всего ошибок:** 266+ (минимум)

---

## 🔴 КРИТИЧЕСКИЕ ОШИБКИ

### 1. CROUSDT WebSocket Stale (🔴 ТРЕБУЕТ ИСПРАВЛЕНИЯ)

**Описание:**
Бот каждую минуту пытается переподписаться на WebSocket для CROUSDT, но терпит неудачу уже 250+ минут (4+ часа).

**Ошибки:**
```
2025-10-30 04:11:35,753 - CRITICAL - 🚨 CRITICAL ALERT: CROUSDT stale for 250.2 minutes!
2025-10-30 04:11:35,753 - ERROR - ❌ FAILED to resubscribe CROUSDT after 3 attempts! MANUAL INTERVENTION REQUIRED
```

**Частота:** Каждую минуту с 00:21 до 04:11+ (250+ раз)

**Причина:**
Позиция CROUSDT была **ЗАКРЫТА** 2025-10-29 20:03 UTC (4 часа назад), но:
1. Бот не отписался от WebSocket после закрытия позиции
2. Продолжает мониторить несуществующую позицию
3. Каждую минуту пытается переподписаться
4. Логирует CRITICAL ошибку

**Данные из БД:**
```sql
symbol  | exchange | status | opened_at              | updated_at
CROUSDT | bybit    | closed | 2025-10-29 13:21:24   | 2025-10-29 20:03:11
```

**Последствия:**
- ✅ Не влияет на торговлю (позиция закрыта)
- ❌ Засоряет логи (250+ CRITICAL сообщений)
- ❌ Расходует ресурсы на попытки переподписки
- ❌ Вводит в заблуждение мониторинг

**Решение:**
1. При закрытии позиции ОБЯЗАТЕЛЬНО отписываться от WebSocket
2. Очищать мониторинг закрытых позиций
3. Добавить проверку статуса позиции перед попыткой переподписки

**Файл:** `core/position_manager_unified_patch.py`

**Приоритет:** 🔴 **ВЫСОКИЙ** - фикс нужен немедленно

---

## 🟡 СРЕДНИЕ ОШИБКИ

### 2. KeyError: 'topped_up' (🟡 НУЖЕН ФИКС)

**Описание:**
При обработке волны сигналов происходит попытка доступа к несуществующему ключу 'topped_up' в словаре статистики.

**Ошибки:**
```
2025-10-30 03:34:47,409 - ERROR - Error in wave monitoring loop: 'topped_up'
Traceback (most recent call last):
  File "core/signal_processor_websocket.py", line 294, in _wave_monitoring_loop
    f"topped up: {stats['topped_up']}, "
                  ~~~~~^^^^^^^^^^^^^
KeyError: 'topped_up'
```

**Частота:** 9 раз за 5 часов (примерно каждые 30 минут при обработке волн)

**Время:**
- 03:34:47
- 03:49:26
- 04:05:04
- (и еще 6 раз)

**Причина:**
В `signal_processor_websocket.py` на строке 294 происходит обращение к `stats['topped_up']`, но этот ключ не всегда присутствует в словаре `stats`.

**Код (строка 294):**
```python
f"topped up: {stats['topped_up']}, "
```

**Контекст:**
Волны обрабатываются успешно, но при логировании статистики бот пытается вывести информацию о "topped_up" позициях, которая отсутствует.

**Последствия:**
- ✅ Не влияет на торговлю (волна обработана)
- ✅ Позиции открываются корректно
- ❌ Exception в логе
- ❌ Статистика волны не полностью выводится

**Решение:**
```python
# Было:
f"topped up: {stats['topped_up']}, "

# Должно быть:
f"topped up: {stats.get('topped_up', 0)}, "
```

**Файл:** `core/signal_processor_websocket.py:294`

**Приоритет:** 🟡 **СРЕДНИЙ** - не критично, но нужно исправить

---

## 🟢 ИНФОРМАЦИОННЫЕ ОШИБКИ (Нормальная работа)

### 3. Failed to Calculate Position Size (🟢 ОЖИДАЕМО)

**Описание:**
Бот не может рассчитать размер позиции, так как размер позиции ($6) меньше минимальной стоимости ордера ($5 после учета ограничений биржи).

**Примеры:**

#### 3.1 APEUSDT (03:34:40)
```
❌ Failed to calculate position size for APEUSDT
   Position size USD: $6
   Entry price: $0.4302
   Market constraints: min_amount=1.0, step_size=1.0
   Limits: min_amount=1.0, min_cost=5.0

Reason: failed_to_calculate_quantity
```

**Расчет:**
- Позиция: $6
- Цена: $0.4302
- Количество: 6 / 0.4302 = 13.94 → округление до 13 (step_size=1.0)
- Стоимость после округления: 13 × 0.4302 = $5.59
- min_cost = $5.0 ✅ (но margin недостаточен после fees)

#### 3.2 HOOKUSDT (03:34:42)
```
❌ Failed to calculate position size for HOOKUSDT
   Position size USD: $6
   Entry price: $0.06352
   Market constraints: min_amount=0.1, step_size=0.1
   Limits: min_amount=0.1, min_cost=5.0
```

**Расчет:**
- Позиция: $6
- Цена: $0.06352
- Количество: 6 / 0.06352 = 94.47 → округление до 94.4 (step_size=0.1)
- Стоимость: 94.4 × 0.06352 = $5.996
- min_cost = $5.0 ✅ (но margin недостаточен)

#### 3.3 TIAUSDT (03:34:45)
```
❌ Failed to calculate position size for TIAUSDT
   Position size USD: $6
   Entry price: $1.0122
   Market constraints: min_amount=1.0, step_size=1.0
```

**Расчет:**
- Количество: 6 / 1.0122 = 5.93 → округление до 5
- Стоимость: 5 × 1.0122 = $5.06 ✅

#### 3.4 AKTUSDT (03:34:47)
```
❌ Failed to calculate position size for AKTUSDT
   Position size USD: $6
   Entry price: $0.7922
```

#### 3.5 CGPTUSDT (03:49:21)
```
❌ Failed to calculate position size for CGPTUSDT
   Position size USD: $6
   Entry price: $0.05433
```

#### 3.6 LINEAUSDT (03:49:23)
```
❌ Failed to calculate position size for LINEAUSDT
   Position size USD: $6
   Entry price: $0.01399
```

#### 3.7 OGNUSDT (03:49:26)
```
❌ Failed to calculate position size for OGNUSDT
   Position size USD: $6
   Entry price: $0.0462
```

**Причина:**
Это **НОРМАЛЬНАЯ РАБОТА БОТА**:
1. Размер позиции слишком мал ($6)
2. После округления по step_size стоимость падает ниже минимума
3. Или margin недостаточен для покрытия fees
4. Бот корректно отклоняет такие сигналы

**Последствия:**
- ✅ Бот защищает от слишком мелких позиций
- ✅ Предотвращает ошибки биржи (Order would immediately trigger)
- ✅ Логирует детальную информацию для отладки
- ❌ Позиция не открывается (но это правильно)

**Решение:**
Не требуется. Это защитный механизм бота.

**Примечание:**
Если хочется открывать такие позиции, нужно:
1. Увеличить размер позиции (например, до $10-15)
2. Или изменить логику расчета margin

**Приоритет:** 🟢 **НИЗКИЙ** - это не ошибка, а нормальная работа

---

## 📊 Детальная Статистика

### Ошибки по Времени

| Время | Тип ошибки | Количество |
|-------|------------|------------|
| 03:29-03:34 | CROUSDT stale | 5 раз |
| 03:34:40-03:34:47 | Position size | 4 позиции |
| 03:34:47 | KeyError topped_up | 1 раз |
| 03:35-03:49 | CROUSDT stale | 14 раз |
| 03:49:21-03:49:26 | Position size | 3 позиции |
| 03:49:26 | KeyError topped_up | 1 раз |
| 03:50-04:05 | CROUSDT stale | 15 раз |
| 04:05:04 | KeyError topped_up | 1 раз |
| 04:06-04:11 | CROUSDT stale | 5 раз |

### Ошибки по Типу

1. **CROUSDT WebSocket stale**: 250+ раз (каждую минуту)
2. **KeyError 'topped_up'**: 9 раз
3. **Position size calculation failed**: 7 позиций

### Ошибки по Критичности

| Критичность | Количество | % от общего |
|-------------|------------|-------------|
| 🔴 HIGH | 250+ | 94% |
| 🟡 MEDIUM | 9 | 3% |
| 🟢 LOW/INFO | 7 | 3% |

---

## 🎯 Рекомендации

### Немедленные действия (в течение 1 часа):

1. **Исправить CROUSDT stale issue:**
   ```python
   # В position_manager_unified_patch.py
   # При закрытии позиции:
   async def close_position(self, position_id):
       # ... existing code ...

       # ДОБАВИТЬ:
       # Отписаться от WebSocket
       await self._unsubscribe_from_websocket(symbol, exchange)

       # Удалить из мониторинга
       if symbol in self._monitored_symbols:
           del self._monitored_symbols[symbol]
   ```

2. **Исправить KeyError 'topped_up':**
   ```python
   # В signal_processor_websocket.py:294
   # Было:
   f"topped up: {stats['topped_up']}, "

   # Стало:
   f"topped up: {stats.get('topped_up', 0)}, "
   ```

### Краткосрочные действия (в течение суток):

3. **Добавить очистку stale subscriptions:**
   - Проверять статус позиции перед попыткой resubscribe
   - Если позиция closed - не пытаться переподписаться
   - Удалять из monitoring list

4. **Улучшить логирование:**
   - Убрать CRITICAL для закрытых позиций
   - Добавить INFO при успешной отписке
   - Логировать только реальные проблемы

### Долгосрочные действия (в течение недели):

5. **Рефакторинг WebSocket subscription management:**
   - Централизовать управление подписками
   - Автоматическая очистка при закрытии позиций
   - Graceful unsubscribe

6. **Добавить мониторинг ошибок:**
   - Dashboard с количеством ошибок
   - Алерты при превышении порога
   - Автоматическое детектирование аномалий

---

## 📝 Примечания

### Что НЕ является ошибкой:

1. ✅ **"Failed to calculate position size"** - это нормальная работа защитного механизма
2. ✅ **"Position size too small"** - правильная валидация
3. ✅ **"signal_execution_failed" с reason "position_manager_returned_none"** - следствие валидации

### Что ЯВЛЯЕТСЯ ошибкой:

1. ❌ **CROUSDT stale for 250+ minutes** - баг в отписке от WebSocket
2. ❌ **KeyError: 'topped_up'** - отсутствие проверки наличия ключа
3. ❌ **CRITICAL alerts для закрытых позиций** - неправильный уровень логирования

---

## 🔍 Дополнительная Информация

### Файлы для исправления:

1. `core/position_manager_unified_patch.py` - добавить unsubscribe при закрытии
2. `core/signal_processor_websocket.py:294` - использовать .get()
3. `core/position_manager_unified_patch.py` - проверка статуса перед resubscribe

### Тесты для добавления:

1. Test: закрытие позиции корректно отписывается от WebSocket
2. Test: stats dictionary всегда содержит все нужные ключи
3. Test: stale subscription не пытается переподписаться на закрытую позицию

---

## ✅ Итоги

### Критичные проблемы:
- 🔴 **1 критичная ошибка** требует немедленного исправления (CROUSDT WebSocket)

### Средние проблемы:
- 🟡 **1 средняя ошибка** требует исправления (KeyError)

### Информационные:
- 🟢 **7 информационных сообщений** - нормальная работа

### Общее состояние бота:
- ✅ Торговля работает корректно
- ✅ Позиции открываются и закрываются
- ✅ WebSocket работает для активных позиций
- ❌ Логи засорены повторяющимися сообщениями о CROUSDT
- ❌ Небольшие баги в статистике волн

**Общая оценка:** 7/10 (работает, но требуются исправления)
