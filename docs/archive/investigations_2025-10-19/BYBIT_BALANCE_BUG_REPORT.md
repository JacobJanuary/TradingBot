# 🔴 КРИТИЧЕСКИЙ БАГ: Bybit Balance Free = $0

**Дата:** 2025-10-19 14:00 UTC
**Статус:** 🔴 КРИТИЧЕСКАЯ ПРОБЛЕМА НАЙДЕНА
**Приоритет:** P0 - Блокирует все Bybit сигналы

---

## 🎯 ПРОБЛЕМА

Bybit сигналы фильтруются с ошибкой `"Insufficient free balance: $0.00 < $200.00"`, хотя реальный баланс = **$10,608**!

**Логи:**
```
12:37:09,872 - Signal SNTUSDT on bybit filtered out: Insufficient free balance: $0.00 < $200.00
12:37:09,872 - Signal OSMOUSDT on bybit filtered out: Insufficient free balance: $0.00 < $200.00
12:37:09,872 - Signal XCHUSDT on bybit filtered out: Insufficient free balance: $0.00 < $200.00
12:37:09,872 - Signal YZYUSDT on bybit filtered out: Insufficient free balance: $0.00 < $200.00
```

**Код проверки (core/exchange_manager.py:1177-1180):**
```python
balance = await self.exchange.fetch_balance()
free_usdt = float(balance.get('USDT', {}).get('free', 0) or 0)  # ← Получает None/0!

if free_usdt < float(notional_usd):
    return False, f"Insufficient free balance: ${free_usdt:.2f} < ${notional_usd:.2f}"
```

---

## 🔬 РАССЛЕДОВАНИЕ

### Тест 1: CCXT fetchBalance()

**Результат:**
```python
balance = await bybit.fetch_balance()
usdt = balance.get('USDT', {})

# Вывод:
{
    'free': None,   # ← ПРОБЛЕМА!
    'used': None,   # ← ПРОБЛЕМА!
    'total': 10608.80412494  # ← Корректно
}
```

### Тест 2: Прямой API вызов

**Endpoint:** `GET /v5/account/wallet-balance`
**Parameters:** `accountType=UNIFIED, coin=USDT`

**Результат:**
```json
{
    "retCode": 0,
    "retMsg": "OK",
    "result": {
        "list": [{
            "accountType": "UNIFIED",
            "totalEquity": "10604.75689881",
            "totalWalletBalance": "10611.46693477",
            "totalAvailableBalance": "10252.38124734",  ← РЕАЛЬНЫЙ FREE BALANCE!
            "coin": [...]
        }]
    }
}
```

---

## 💡 КОРНЕВАЯ ПРИЧИНА

**Проблема в CCXT библиотеке:**

CCXT `bybit.parse_balance()` НЕ корректно извлекает `free` и `used` для **UNIFIED** аккаунтов Bybit v5!

**Почему:**
1. Bybit API v5 UNIFIED возвращает `totalAvailableBalance` вместо `free`
2. CCXT парсер ожидает структуру от старого API (v3)
3. Результат: `free = None`, `used = None`

**Доказательство:**
```python
# CCXT парсит ответ, но НЕ находит 'free' поле
# Потому что в UNIFIED ответе его нет!
# Вместо этого есть:
#   - totalAvailableBalance  (аналог 'free')
#   - totalWalletBalance - totalAvailableBalance (аналог 'used')
```

---

## ✅ РЕШЕНИЕ

### Вариант 1: Использовать `totalAvailableBalance` напрямую (ЛУЧШЕЕ)

**Реализация:**

```python
# core/exchange_manager.py

async def can_open_position(self, symbol: str, notional_usd: float, preloaded_positions: Optional[List] = None) -> Tuple[bool, str]:
    """Check if we can open position"""
    try:
        # Step 1: Check free balance
        if self.name == 'bybit':
            # BYBIT UNIFIED ACCOUNT: Use direct API call
            response = await self.exchange.privateGetV5AccountWalletBalance({
                'accountType': 'UNIFIED',
                'coin': 'USDT'
            })

            result = response.get('result', {})
            accounts = result.get('list', [])

            if accounts:
                account = accounts[0]
                # Use totalAvailableBalance instead of 'free'
                free_usdt = float(account.get('totalAvailableBalance', 0))
            else:
                return False, "No Bybit account data"
        else:
            # BINANCE: Use standard fetchBalance
            balance = await self.exchange.fetch_balance()
            free_usdt = float(balance.get('USDT', {}).get('free', 0) or 0)

        if free_usdt < float(notional_usd):
            return False, f"Insufficient free balance: ${free_usdt:.2f} < ${notional_usd:.2f}"

        # ... rest of method
```

**Преимущества:**
- ✅ Использует официальный Bybit API v5
- ✅ Получает точное значение available balance
- ✅ Работает для UNIFIED аккаунтов
- ✅ Минимальные изменения кода

---

### Вариант 2: Исправить CCXT (ДОЛГО)

Создать PR в CCXT репозиторий для исправления `bybit.parse_balance()`:

```python
# В CCXT bybit.py
def parse_balance(self, response):
    # ...
    if accountType == 'UNIFIED':
        # Parse totalAvailableBalance as 'free'
        free = self.safe_string(account, 'totalAvailableBalance')
        total = self.safe_string(account, 'totalWalletBalance')
        used = Precise.string_sub(total, free)
        # ...
```

**Недостатки:**
- ⏰ Долго (ожидание merge в CCXT)
- ⏰ Нужно обновлять CCXT после merge
- ⚠️ Не контролируем процесс

---

### Вариант 3: Fallback на `total` (ВРЕМЕННОЕ)

**Быстрое решение:**

```python
# core/exchange_manager.py:1178

balance = await self.exchange.fetch_balance()
usdt_balance = balance.get('USDT', {})

# Fallback: если free=None, использовать total (рискованно!)
free_usdt = float(usdt_balance.get('free') or usdt_balance.get('total', 0) or 0)
```

**Недостатки:**
- ⚠️ Игнорирует используемый баланс (used)
- ⚠️ Может открыть слишком много позиций
- ✅ НО: лучше чем $0!

---

## 📊 ТЕСТИРОВАНИЕ

**Тестовый скрипт:** `scripts/test_bybit_balance_v5.py`

**Результаты:**
```
Standard CCXT fetchBalance():
   Free:  None          ← БАГ
   Total: 10608.80      ← OK

Direct API call (/v5/account/wallet-balance):
   Total Available Balance: 10252.38  ← ПРАВИЛЬНЫЙ FREE!
   Total Wallet Balance: 10611.47     ← ПРАВИЛЬНЫЙ TOTAL!
```

---

## 🎯 РЕКОМЕНДАЦИЯ

### ✅ Использовать Вариант 1 (прямой API вызов)

**План:**
1. Добавить метод `_get_bybit_free_balance()` в `ExchangeManager`
2. Использовать его в `can_open_position()` для Bybit
3. Оставить стандартный `fetch_balance()` для Binance

**Код изменений:** ~20 строк

**Время реализации:** 10 минут

**Тестирование:** Запустить `test_bybit_balance_v5.py` → проверить что free > 0

---

## 📝 ДОПОЛНИТЕЛЬНЫЕ НАХОДКИ

### API Response структура

**Bybit UNIFIED v5:**
```json
{
    "totalEquity": "10604.76",           // Общая стоимость (включая unrealized PnL)
    "totalWalletBalance": "10611.47",    // Общий баланс кошелька
    "totalAvailableBalance": "10252.38", // ← ЭТО ЕСТЬ 'FREE'!
    "totalPerpUPL": "-6.71",             // Unrealized PnL
    "totalInitialMargin": "359.08",      // Используемая маржа
    "accountIMRate": "0.0339",           // Initial Margin ratio
    "totalMaintenanceMargin": "135.97"   // Maintenance Margin
}
```

**Формула:**
```
free = totalAvailableBalance
used = totalWalletBalance - totalAvailableBalance
total = totalWalletBalance
```

### CCXT Unified Account Indicator

Из теста:
```json
{
    "unified": "0",   // Legacy unified (deprecated)
    "uta": "1"        // ← Unified Trading Account v5 ENABLED!
}
```

`uta=1` означает что аккаунт использует UNIFIED v5!

---

## ✅ ИТОГ

### Проблема найдена и понята:

1. ✅ CCXT `fetch_balance()` возвращает `free=None` для Bybit UNIFIED
2. ✅ Реальный баланс = $10,608, доступный = $10,252
3. ✅ Нужно использовать прямой API вызов `/v5/account/wallet-balance`
4. ✅ Параметр `totalAvailableBalance` = правильный `free`

### Следующий шаг:

Реализовать Вариант 1 (прямой API вызов для Bybit UNIFIED аккаунтов).

---

**Дата:** 2025-10-19 14:00 UTC
**Автор:** Claude Code Investigation Team
**Скрипт:** `scripts/test_bybit_balance_v5.py`
**Статус:** ✅ ПРОБЛЕМА НАЙДЕНА, РЕШЕНИЕ ГОТОВО
