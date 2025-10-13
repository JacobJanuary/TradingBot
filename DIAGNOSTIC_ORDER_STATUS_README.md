# 🔬 Диагностический скрипт: Real Order Status Analysis

**Файл:** `diagnose_real_order_status.py`

**Цель:** Найти 100% причину ошибки "Entry order failed: unknown"

---

## 🎯 Что делает скрипт

Создает **РЕАЛЬНЫЕ market orders** для проблемных символов и анализирует:

1. ✅ Какой статус возвращает биржа СРАЗУ после создания
2. ✅ Какой статус после fetch_order (через 1 сек)
3. ✅ Как ExchangeResponseAdapter нормализует статусы
4. ✅ Примет ли бот этот ордер или отклонит
5. ✅ Полную структуру raw_order от биржи

**Проблемные символы:**
- `SUNDOG/USDT:USDT` - вызвал "Entry order failed: unknown" (2025-10-12 05:51:20)
- `XCH/USDT:USDT` - возможно та же проблема

---

## ⚠️ ВАЖНО

### Скрипт создает РЕАЛЬНЫЕ ордера!

- ✅ Минимальные суммы (~$1-2 за ордер)
- ✅ Позиции сразу закрываются автоматически
- ✅ Работает на testnet (если включен в конфиге)
- ✅ Требует подтверждение перед каждым ордером

**Убедитесь:**
- [ ] У вас есть баланс USDT (~$5-10 достаточно)
- [ ] Вы работаете на testnet (или согласны потратить $2-4 на production)
- [ ] Вы понимаете что создаются реальные ордера

---

## 🚀 Как использовать

### Шаг 1: Запустить скрипт

```bash
python3 diagnose_real_order_status.py
```

### Шаг 2: Подтвердить каждый тест

Для каждого символа скрипт покажет:
```
⚠️  ВНИМАНИЕ!
Будет создан РЕАЛЬНЫЙ market order:
  Symbol: SUNDOG/USDT:USDT
  Side: SELL (short)
  Amount: 4000
  Cost: ~$2.00

Позиция будет сразу закрыта после анализа статуса.

Создать этот ордер? (yes/no):
```

Введите `yes` для подтверждения или `no` для пропуска.

### Шаг 3: Анализировать результаты

Скрипт покажет:

**ДЛЯ КАЖДОГО ОРДЕРА:**
```
🔍 RAW ORDER STRUCTURE:
{
  "id": "...",
  "status": "...",          ← Важно!
  "info": {
    "orderStatus": "..."    ← Критически важно!
  }
}

🔄 NORMALIZED ORDER:
  status: unknown            ← Если 'unknown' - нашли проблему!
  is_filled: False           ← Бот отклонит такой ордер

📊 СРАВНЕНИЕ:
  IMMEDIATE (сразу):
    info.orderStatus: Created    ← НАЙДЕНО!
    normalized: unknown          ← Проблема
    Бот примет: НЕТ             ← Root cause!

  AFTER FETCH (через 1 сек):
    info.orderStatus: Filled
    normalized: closed
    Бот примет: ДА
```

**ФИНАЛЬНЫЙ ОТЧЕТ:**
```
🔍 КЛЮЧЕВЫЕ НАХОДКИ:

1. RAW СТАТУСЫ (order['status']):
   Immediate: {'closed', 'Created'}
   After fetch: {'closed'}

2. INFO СТАТУСЫ (order['info']['orderStatus']):
   Immediate: {'Created', 'Filled'}  ← НАШЛИ 'Created'!
   After fetch: {'Filled'}

3. ПРОБЛЕМНЫЕ СТАТУСЫ (бот отклонит):
   SUNDOG/USDT:USDT: normalized='unknown'
     → info.orderStatus был: 'Created'  ← ROOT CAUSE!
     → НЕ в status_map → стал 'unknown'

💡 РЕКОМЕНДАЦИИ:

Добавить в status_map:
  'Created': 'open',
```

### Шаг 4: Проверить сохраненные данные

Скрипт сохранит полные данные в JSON:
```
💾 Данные сохранены в: diagnostic_order_status_20251012_060000.json
```

---

## 📊 Что анализируется

### 1. Immediate response (сразу после create_market_order)

```python
raw_order = await exchange.create_market_order(...)

# Что смотрим:
- raw_order['status']           # ccxt статус
- raw_order['info']['orderStatus']  # Bybit статус
- normalized.status             # Как нормализовалось
- is_order_filled()            # Примет ли бот
```

### 2. After fetch (через 1 секунду)

```python
await asyncio.sleep(1.0)
raw_order = await exchange.fetch_order(order_id, symbol)

# Статус мог измениться:
# Created → Filled
```

### 3. Normalization mapping

Проверяет как status_map обрабатывает статусы:
```python
status_map = {
    'Filled': 'closed',
    'PartiallyFilled': 'open',
    'New': 'open',
    'Cancelled': 'canceled',
    'Rejected': 'canceled',
}

# Если статус НЕ в мапе → 'unknown'
```

---

## 🔍 Ожидаемый результат

### Сценарий A: Находим 'Created'

```
INFO СТАТУСЫ immediate: {'Created'}
ПРОБЛЕМА: 'Created' НЕ в status_map → 'unknown'

РЕШЕНИЕ:
Добавить в exchange_response_adapter.py:
  'Created': 'open',
```

### Сценарий B: Находим другой статус

```
INFO СТАТУСЫ immediate: {'Triggered'}
ПРОБЛЕМА: 'Triggered' НЕ в status_map → 'unknown'

РЕШЕНИЕ:
Добавить:
  'Triggered': 'open',
```

### Сценарий C: Статус в мапе, но другая проблема

```
INFO СТАТУСЫ immediate: {'Filled'}
normalized status: 'closed'
is_filled: True

Бот должен был принять!
→ Проблема в другом месте (race condition, timing, etc.)
```

---

## 📁 Выходные файлы

### JSON файл с полными данными

Содержит:
- Полную структуру raw_order (immediate)
- Полную структуру raw_order (after fetch)
- Все извлеченные статусы
- Результаты нормализации
- Результаты is_order_filled()

**Использование:**
```bash
# Посмотреть результаты
cat diagnostic_order_status_*.json | jq '.'

# Найти все статусы
cat diagnostic_order_status_*.json | jq '.[].immediate.info_status'
```

---

## 🛡️ Безопасность

### Что делается для безопасности:

1. ✅ **Минимальные суммы:** ~$1-2 за ордер
2. ✅ **Автоматическое закрытие:** Позиции закрываются сразу
3. ✅ **Подтверждение:** Требует 'yes' для каждого ордера
4. ✅ **Обработка ошибок:** Ловит InsufficientFunds, InvalidOrder
5. ✅ **Graceful exit:** Ctrl+C безопасно прерывает

### Возможные ошибки:

**Недостаточно баланса:**
```
❌ Недостаточно средств: InsufficientFunds
→ Пополните баланс USDT
```

**Символ не найден:**
```
❌ Символ не найден на бирже
→ Проверьте доступность символа
```

**Минимальный лимит:**
```
❌ Неверный ордер: The number of contracts exceeds minimum limit
→ Автоматически пересчитает количество
```

---

## 🎯 План действий после диагностики

### 1. Запустить диагностику

```bash
python3 diagnose_real_order_status.py
```

### 2. Найти проблемный статус

Смотрим в выводе:
```
INFO СТАТУСЫ immediate: {'Created'}  ← НАШЛИ!
```

### 3. Применить решение

Добавить найденный статус в `core/exchange_response_adapter.py`:

```python
status_map = {
    'Filled': 'closed',
    'PartiallyFilled': 'open',
    'New': 'open',
    'Created': 'open',  # ← ДОБАВИТЬ НАЙДЕННЫЙ
    'Cancelled': 'canceled',
    'Rejected': 'canceled',
}
```

### 4. Проверить исправление

Запустить бота и убедиться что ошибка больше не повторяется.

---

## 💡 Дополнительные возможности

### Добавить свои символы для теста

Отредактировать в скрипте:
```python
problem_symbols = [
    'SUNDOG/USDT:USDT',
    'XCH/USDT:USDT',
    'YOUR/SYMBOL:USDT',  # Добавить свой
]
```

### Изменить задержку между тестами

```python
await asyncio.sleep(3)  # Изменить на нужное значение
```

### Тестировать на production

Изменить в config:
```python
testnet: False  # В конфиге для Bybit
```

---

## ✅ Checklist перед запуском

- [ ] Проверил что работает на testnet (или согласен на production)
- [ ] Есть баланс USDT (~$5-10)
- [ ] Понимаю что создаются реальные ордера
- [ ] Готов подтвердить каждый тест
- [ ] Буду анализировать вывод

---

## 📞 Что делать с результатами

### Если нашли проблемный статус:

1. Скопировать статус из вывода
2. Добавить в status_map
3. Протестировать
4. Закоммитить изменения

### Если все статусы в мапе:

1. Проблема в другом месте
2. Проверить race condition
3. Проверить timing между create и fetch
4. Добавить дополнительное логирование

### В любом случае:

1. Сохранить JSON файл
2. Создать отчет с находками
3. Обновить INVESTIGATION_ENTRY_ORDER_UNKNOWN_STATUS.md

---

**Автор:** Claude Code
**Дата:** 2025-10-12
**Статус:** ✅ Готов к использованию
**Риск:** НИЗКИЙ (тестовые ордера на минимальные суммы)
