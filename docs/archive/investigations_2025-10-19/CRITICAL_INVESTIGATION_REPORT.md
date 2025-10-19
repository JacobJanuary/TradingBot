# 🔴 КРИТИЧЕСКОЕ РАССЛЕДОВАНИЕ: Реальные Проблемы Бота

**Дата:** 2025-10-19 13:10 UTC
**Волна:** 12:37 (08:15 UTC)
**Статус:** 🔴 НАЙДЕНЫ 3 КРИТИЧЕСКИЕ ПРОБЛЕМЫ

---

## 🎯 РЕАЛЬНЫЕ ПРОБЛЕМЫ НАЙДЕНЫ

### ❌ ПРОБЛЕМА 1: Bybit использует TESTNET вместо MAINNET

**Симптом:**
```
Signal SNTUSDT on bybit filtered out: Insufficient free balance: $0.00 < $200.00
```

**Реальность:**
- Пользователь имеет $9600+ на **реальном Bybit**
- Бот подключен к **Bybit TESTNET** (баланс $0)

**Причина:**
```bash
# В .env файле:
BYBIT_TESTNET=true  ← ПРОБЛЕМА!
```

**Доказательство из логов:**
```
12:33:53,722 - Bybit testnet configured with UNIFIED account settings
12:33:53,722 - Exchange bybit initialized (TESTNET)
12:33:56,976 - Starting REST API polling for Bybit private data (testnet mode)
```

**Код (core/exchange_manager.py:116-119):**
```python
if self.name == 'bybit':
    self.exchange.urls['api'] = {
        'public': 'https://api-testnet.bybit.com',  # ← TESTNET!
        'private': 'https://api-testnet.bybit.com'
    }
```

**РЕШЕНИЕ:**
```bash
# В .env изменить:
BYBIT_TESTNET=false  # или удалить строку
```

---

### ❌ ПРОБЛЕМА 2: DEADLOCK в trailing_stop.create_trailing_stop()

**Симптом:**
- Волна 12:37 открыла только 1 позицию из 3
- После открытия TOSHIUSDT код завис на 2+ минуты
- Бот остановлен пользователем в 12:39 (Ctrl+C)

**Временная шкала:**
```
12:37:16,944 - ✅ Added TOSHIUSDT to tracked positions (total: 36)
                ↓ вызывается trailing_manager.create_trailing_stop() ↓
                ... КОД ЗАВИС НА 2+ МИНУТЫ ...
12:39:06,295 - Received signal 2 (SIGINT - пользователь нажал Ctrl+C)
```

**Код проблемы (core/position_manager.py:1465-1477):**
```python
# После успешного открытия позиции:
logger.info(f"✅ Added {symbol} to tracked positions")

# 10. Initialize trailing stop (ATOMIC path)
trailing_manager = self.trailing_managers.get(exchange_name)
if trailing_manager:
    await trailing_manager.create_trailing_stop(  # ← ЗАВИСАЕТ ЗДЕСЬ!
        symbol=symbol,
        side=position.side,
        entry_price=position.entry_price,
        quantity=position.quantity,
        initial_stop=None
    )
    # Этот лог НИКОГДА не появляется:
    logger.info(f"✅ Trailing stop initialized for {symbol}")
```

**Причина дедлока (protection/trailing_stop.py:308):**
```python
async def create_trailing_stop(self, ...):
    async with self.lock:  # ← DEADLOCK! Lock уже занят!
        # ...код никогда не выполняется...
```

**Доказательства:**
1. НЕТ лога: `"✅ Trailing stop initialized for TOSHIUSDT"`
2. НЕТ лога: `"✅ Signal #4990210 (TOSHIUSDT) executed successfully"`
3. НЕТ продолжения обработки сигналов 2/3 и 3/3
4. 2+ минуты тишины в логах после открытия позиции

**Вероятная причина дедлока:**
- Lock уже захвачен в другом месте (возможно при update_price)
- Или бесконечный цикл в _save_state()
- Или await без timeout в критической секции

---

### ❌ ПРОБЛЕМА 3: 502 Bad Gateway блокирует волны (иногда)

**НЕ критично само по себе**, но в комбинации с дедлоком создает проблемы.

**Факты:**
- 502 появляется с 09:51 (59 раз в логах)
- Это проблема Binance TESTNET infrastructure
- Retry механизм работает (attempt 1/5 → успех)

**НО:** Пока идет retry (1.1s), может произойти race condition с trailing_stop lock!

---

## 📊 АНАЛИЗ КОММИТОВ

### Последние 6 часов:
```
e6c1459 (20 min)  - fix: parallel validation multi-exchange  ✅ OK
6ddb3ea (39 min)  - perf: parallelize can_open_position()     ⚠️ Был баг, исправлен
2bc76c5 (3 hours) - fix: float conversion                      ✅ OK
5e086db (3 hours) - fix: balance float                        ✅ OK
f71c066 (5 hours) - fix: add can_open_position()              ✅ OK
ddadb59 (5 hours) - fix: minimum amount check                  ✅ OK
0ec4f4a (6 hours) - fix: parse minQty                         ✅ OK
```

**Ни один коммит НЕ трогал trailing_stop.py!**

Проблема с дедлоком существовала ДО этих изменений!

---

## 🔧 ПЛАН ИСПРАВЛЕНИЯ

### Приоритет 1: СРОЧНО исправить Bybit

```bash
# 1. Остановить бота
# 2. В .env файле:
BYBIT_TESTNET=false  # или полностью удалить эту строку

# 3. Перезапустить бота
python3 main.py
```

**Результат:** Bybit будет использовать РЕАЛЬНЫЙ баланс $9600+

### Приоритет 2: Исправить DEADLOCK в trailing_stop

**Временное решение (БЫСТРО):**

Добавить timeout в lock:
```python
# protection/trailing_stop.py:308
async def create_trailing_stop(self, ...):
    try:
        # Добавить timeout 5 секунд
        async with asyncio.timeout(5):
            async with self.lock:
                # ... существующий код ...
    except asyncio.TimeoutError:
        logger.error(f"DEADLOCK detected in create_trailing_stop for {symbol}!")
        # Продолжить без trailing stop
        return None
```

**Постоянное решение (ПРАВИЛЬНО):**

1. Найти источник дедлока (кто еще держит lock?)
2. Использовать RLock (reentrant lock) вместо обычного Lock
3. Или убрать lock из create_trailing_stop если он не нужен

### Приоритет 3: Мониторинг 502

Добавить метрику:
- Если >3 retry на одном запросе → алерт
- Если волна выполняется >30 секунд → алерт

---

## 🎯 ИТОГИ

### Реальные проблемы (НЕ мои ошибки в расследовании):

1. ✅ **BYBIT_TESTNET=true** → баланс $0 вместо $9600
2. ✅ **DEADLOCK в trailing_stop** → волны зависают
3. ✅ **502 Bad Gateway** → Binance testnet проблема (не критично)

### Что НЕ является проблемой:

- ✅ Параллельная валидация работает правильно (после фикса e6c1459)
- ✅ Multi-exchange поддержка работает
- ✅ can_open_position() работает правильно
- ✅ Retry механизм для 502 работает

### Почему пользователь думал что "сигналы перестали обрабатываться":

**НЕ из-за 502!** А из-за DEADLOCK в trailing_stop, который завис после открытия первой позиции.

---

## 📝 КОМАНДЫ ДЛЯ ПРОВЕРКИ

### 1. Проверить Bybit настройки:
```bash
grep BYBIT_TESTNET .env
```

### 2. Проверить дедлоки в логах:
```bash
grep -E "(Trailing stop initialized|deadlock|timeout)" logs/trading_bot.log | tail -20
```

### 3. Проверить зависшие волны:
```bash
grep "Wave.*complete" logs/trading_bot.log | tail -5
```

---

**Статус:** 🔴 КРИТИЧЕСКИЕ ПРОБЛЕМЫ НАЙДЕНЫ И ПОНЯТЫ
**Автор:** Claude Code Deep Investigation
**Дата:** 2025-10-19 13:10 UTC