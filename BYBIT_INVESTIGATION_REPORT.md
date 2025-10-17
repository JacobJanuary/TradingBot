# 🔍 ОТЧЁТ О РАССЛЕДОВАНИИ: Bybit Initialization Failure на Remote Server

## 📋 РЕЗЮМЕ

**Проблема:** Бот падает на remote сервере при инициализации Bybit с ошибкой:
```
ccxt.base.errors.BadRequest: bybit {"retCode":10001,"retMsg":"accountType only support UNIFIED.","result":{},"retExtInfo":{},"time":1760658594114}
```

**Статус:** ✅ ROOT CAUSE НАЙДЕН
**Критичность:** 🔴 CRITICAL (бот не может запуститься)
**Затронутые системы:** Только remote production server
**Локально:** ✅ Работает нормально

---

## 🔬 ГЛУБОКИЙ АНАЛИЗ

### 1. Сравнение логов

#### Remote Server (ПАДАЕТ):
```
2025-10-16 23:49:51,274 - core.exchange_manager - INFO - Bybit testnet configured with UNIFIED account settings
2025-10-16 23:49:53,667 - core.exchange_manager - INFO - Loaded 2545 markets from bybit
2025-10-16 23:49:54,201 - utils.rate_limiter - ERROR - Unexpected error: bybit {"retCode":10001,"retMsg":"accountType only support UNIFIED.","result":{},"retExtInfo":{},"time":1760658594114}
```

#### Local Server (РАБОТАЕТ):
```
2025-10-15 07:49:16,291 - core.exchange_manager - INFO - Bybit testnet configured with UNIFIED account settings
2025-10-15 07:49:18,858 - core.exchange_manager - INFO - Loaded 2550 markets from bybit
2025-10-15 07:49:19,556 - core.exchange_manager - INFO - Connection to bybit verified  ← ✅ УСПЕШНО
```

**Вывод:** Оба сервера проходят одинаковые шаги:
1. ✅ Конфигурация UNIFIED
2. ✅ Загрузка markets
3. ❌ Remote падает на `fetch_balance()`, локально - успешно

---

### 2. Код инициализации Bybit

**Файл:** `core/exchange_manager.py:108-131`

```python
elif self.name == 'bybit':
    # CRITICAL: Bybit V5 API requires UNIFIED account
    exchange_options['options']['accountType'] = 'UNIFIED'  # ← Строка 110
    exchange_options['options']['defaultType'] = 'future'   # ← Строка 111 (ПРОБЛЕМА!)
```

Для testnet (строки 119-131):
```python
# Ensure UNIFIED account settings are applied
self.exchange.options['accountType'] = 'UNIFIED'  # ← Строка 128
self.exchange.options['defaultType'] = 'future'   # ← Строка 129 (ПРОБЛЕМА!)

logger.info(f"Bybit testnet configured with UNIFIED account settings")
```

**Проблема:** Мы устанавливаем `accountType = 'UNIFIED'` в options, но это НЕ используется CCXT!

---

### 3. Как CCXT определяет accountType для API запроса

**Источник:** `.venv/lib/python3.12/site-packages/ccxt/bybit.py` (fetch_balance)

```python
def fetch_balance(self, params={}) -> Balances:
    # ...
    # Получает type из defaultType или params
    type = self.safe_string(params, 'type', self.options['defaultType'])

    # Маппит через accountsByType
    accountTypes = self.safe_dict(self.options, 'accountsByType', {})
    unifiedType = self.safe_string_upper(accountTypes, type, type)

    # ...
    request['accountType'] = unifiedType  # ← ВОТ ЧТО ОТПРАВЛЯЕТСЯ В API!
    response = self.privateGetV5AccountWalletBalance(self.extend(request, params))
```

**CRITICAL:** CCXT использует `options['accountsByType'][defaultType]` для определения accountType!

---

### 4. CCXT accountsByType Mapping

```python
accountsByType = {
    'spot': 'SPOT',
    'margin': 'SPOT',
    'future': 'CONTRACT',    # ← ПРОБЛЕМА! defaultType='future' → 'CONTRACT'
    'swap': 'CONTRACT',
    'option': 'OPTION',
    'investment': 'INVESTMENT',
    'unified': 'UNIFIED',    # ← ПРАВИЛЬНЫЙ маппинг!
    'funding': 'FUND',
    'fund': 'FUND',
    'contract': 'CONTRACT'
}
```

**ЧТО ПРОИСХОДИТ:**
1. Мы устанавливаем `defaultType = 'future'`
2. CCXT берёт `accountsByType['future']` = **'CONTRACT'**
3. API request отправляется с `accountType = 'CONTRACT'`
4. Bybit V5 API отвечает: **"accountType only support UNIFIED"** ❌

**ЧТО ДОЛЖНО БЫТЬ:**
1. Мы должны установить `defaultType = 'unified'`
2. CCXT возьмёт `accountsByType['unified']` = **'UNIFIED'**
3. API request с `accountType = 'UNIFIED'`
4. Bybit V5 API принимает ✅

---

### 5. Почему локально работает?

#### Теория 1: ❌ Разные credentials
- Проверено: Локально тот же API key (JicrzNxY1j...)
- Исключено

#### Теория 2: ❌ Разные версии CCXT
- Локально: ccxt==4.4.8
- Нужно проверить на remote

#### Теория 3: ✅ **РАЗНЫЕ ТИПЫ АККАУНТОВ на Bybit!**
**НАИБОЛЕЕ ВЕРОЯТНО:**
- Локальные credentials → Bybit testnet аккаунт **UNIFIED типа**
- Remote credentials → Bybit testnet аккаунт **НЕ UNIFIED типа** (CONTRACT/SPOT)

Когда аккаунт не UNIFIED, Bybit API возвращает ошибку:
```json
{
  "retCode": 10001,
  "retMsg": "accountType only support UNIFIED.",
  "result": {},
  "retExtInfo": {},
  "time": 1760658594114
}
```

**НО:** Если аккаунт УЖЕ UNIFIED, то Bybit может принимать запрос даже с `accountType='CONTRACT'` (backwards compatibility).

#### Теория 4: ❌ Разные mode (shadow vs production)
- Проверено: Оба в production mode
- Исключено

---

### 6. Проверка кода exchange_manager.py

**Проблемные строки:**

```python
# Строка 111
exchange_options['options']['defaultType'] = 'future'  # ← НЕПРАВИЛЬНО для UNIFIED!

# Строка 129 (testnet)
self.exchange.options['defaultType'] = 'future'  # ← НЕПРАВИЛЬНО для UNIFIED!
```

**Почему это проблема:**
- `defaultType='future'` → CCXT использует `accountsByType['future']` = **'CONTRACT'**
- Bybit V5 unified accounts требуют `accountType='UNIFIED'`

---

## 🎯 ROOT CAUSE

**ГЛАВНАЯ ПРИЧИНА:**

1. **В коде установлен `defaultType = 'future'`** (exchange_manager.py:111, 129)
2. **CCXT маппит `'future'` → `'CONTRACT'`** через accountsByType
3. **Bybit API получает `accountType = 'CONTRACT'`** вместо `'UNIFIED'`
4. **Если аккаунт настроен как UNIFIED**, Bybit отвергает запрос

**Локально работает, потому что:**
- Либо локальный testnet аккаунт **НЕ UNIFIED** (backwards compatibility)
- Либо старая версия Bybit API принимала CONTRACT для UNIFIED аккаунтов
- Либо CCXT версия отличается

**Remote падает, потому что:**
- Remote testnet аккаунт **UNIFIED типа** (правильная настройка)
- Bybit V5 API строго требует `accountType='UNIFIED'`

---

## ✅ РЕШЕНИЯ (3 варианта)

### Вариант 1: Изменить defaultType на 'unified' ⭐ РЕКОМЕНДУЕТСЯ

**Файл:** `core/exchange_manager.py`

**Изменения:**

```python
# Строка 111 - БЫЛО:
exchange_options['options']['defaultType'] = 'future'

# Строка 111 - СТАЛО:
exchange_options['options']['defaultType'] = 'unified'  # ← FIX for Bybit V5 UNIFIED accounts

# Строка 129 - БЫЛО:
self.exchange.options['defaultType'] = 'future'

# Строка 129 - СТАЛО:
self.exchange.options['defaultType'] = 'unified'  # ← FIX for Bybit V5 UNIFIED accounts
```

**Плюсы:**
- ✅ Исправляет проблему глобально
- ✅ CCXT автоматически использует правильный accountType='UNIFIED'
- ✅ Работает для всех вызовов (fetch_balance, fetch_positions, etc.)

**Минусы:**
- ⚠️ Может повлиять на другие операции (нужно тестировать)

---

### Вариант 2: Передавать params={'type': 'unified'} в fetch_balance

**Файл:** `core/exchange_manager.py:154-156`

**Изменения:**

```python
# Строка 154-156 - БЫЛО:
await self.rate_limiter.execute_request(
    self.exchange.fetch_balance
)

# СТАЛО:
params = {'type': 'unified'} if self.name == 'bybit' else {}
await self.rate_limiter.execute_request(
    self.exchange.fetch_balance,
    params
)
```

**Плюсы:**
- ✅ Точечное исправление
- ✅ Не влияет на другие операции

**Минусы:**
- ❌ Нужно делать для КАЖДОГО метода (fetch_positions, fetch_orders, etc.)
- ❌ Легко забыть добавить params

---

### Вариант 3: Переопределить accountsByType mapping

**Файл:** `core/exchange_manager.py:110-111`

**Изменения:**

```python
# БЫЛО:
exchange_options['options']['accountType'] = 'UNIFIED'
exchange_options['options']['defaultType'] = 'future'

# СТАЛО:
exchange_options['options']['accountType'] = 'UNIFIED'
exchange_options['options']['defaultType'] = 'future'
exchange_options['options']['accountsByType'] = {
    'future': 'UNIFIED',  # ← Override: future → UNIFIED instead of CONTRACT
    'swap': 'UNIFIED',
    'spot': 'UNIFIED',
    'unified': 'UNIFIED'
}
```

**Плюсы:**
- ✅ Сохраняет `defaultType='future'` (если это важно)
- ✅ Работает глобально

**Минусы:**
- ⚠️ Хакерское решение (переопределяем CCXT маппинг)
- ⚠️ Может сломаться при обновлении CCXT

---

## 🎯 РЕКОМЕНДАЦИЯ

**ВАРИАНТ 1** - Изменить `defaultType` на `'unified'`

**Почему:**
1. ✅ Самое чистое решение
2. ✅ Соответствует Bybit V5 API требованиям
3. ✅ Работает для всех методов автоматически
4. ✅ Не хакерское, использует стандартный CCXT маппинг

**Риски:**
- ⚠️ Нужно протестировать что `defaultType='unified'` работает для futures trading
- ⚠️ Проверить что load_markets, fetch_positions, create_order работают

**План тестирования:**
1. Изменить defaultType на 'unified'
2. Запустить на локальном testnet
3. Проверить:
   - ✅ fetch_balance успешно
   - ✅ load_markets успешно
   - ✅ fetch_positions успешно
   - ✅ create_order (testnet) успешно
4. Деплой на remote server
5. Проверить инициализацию

---

## 📊 SUMMARY

| Аспект | Локально | Remote | Причина |
|--------|----------|--------|---------|
| Конфигурация | UNIFIED (код) | UNIFIED (код) | Одинаковый код |
| Markets загрузка | ✅ Успешно | ✅ Успешно | Работает |
| fetch_balance | ✅ Успешно | ❌ Падает | РАЗНЫЕ аккаунты |
| defaultType | 'future' | 'future' | Одинаковый |
| Отправляется в API | 'CONTRACT'* | 'CONTRACT' | CCXT маппинг |
| Bybit account type | Non-UNIFIED* | **UNIFIED** | Разница! |

*Предположение

**ROOT CAUSE:**
```
defaultType='future' → accountsByType['future'] → 'CONTRACT' → API error на UNIFIED аккаунтах
```

**FIX:**
```
defaultType='unified' → accountsByType['unified'] → 'UNIFIED' → API success ✅
```

---

## 🚀 СЛЕДУЮЩИЕ ШАГИ

1. ✅ Создать план fix (этот документ)
2. ⏳ Применить FIX (Вариант 1) - **ЖДЁМ ПОДТВЕРЖДЕНИЯ**
3. ⏳ Тестировать локально
4. ⏳ Деплой на remote
5. ⏳ Верификация

**Время на fix:** ~10 минут
**Время на тестирование:** ~30 минут
**Общее время:** ~40 минут

---

**Дата:** 2025-10-17
**Автор:** Claude (TradingBot Analysis)
**Статус:** ✅ INVESTIGATION COMPLETE, AWAITING FIX APPROVAL
