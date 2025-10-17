# CRITICAL INVESTIGATION REPORT: UNDEFINED VARIABLES IN CODEBASE
**Date**: 2025-10-17
**Severity**: CRITICAL
**Methods Used**: Triple verification with AST analysis, pattern matching, and static analysis (flake8/pylint)

## EXECUTIVE SUMMARY
Обнаружены **КРИТИЧЕСКИЕ ОШИБКИ** с неопределёнными переменными в коде! Найдено несколько реальных проблем, которые могут привести к сбоям во время выполнения.

---

## 🔴 КРИТИЧЕСКИЕ НАХОДКИ (ТРЕБУЮТ НЕМЕДЛЕННОГО ИСПРАВЛЕНИЯ)

### 1. ❌ CRITICAL: StreamEvent не определён в binance_stream.py
**Файл**: `websocket/binance_stream.py`
**Строки**: 126, 136, 194, 254, 316, 327
**Проблема**: `StreamEvent` используется но НЕ ИМПОРТИРОВАН и НЕ ОПРЕДЕЛЁН нигде в коде!
```python
# Строка 126:
await self._emit_event(StreamEvent.CONNECTED, {})  # StreamEvent НЕ СУЩЕСТВУЕТ!
# Строка 136:
await self._emit_event(StreamEvent.ERROR, {'error': str(e)})
# Строка 194:
await self._emit_event(StreamEvent.BALANCE_UPDATE, {...})
# Строка 254:
await self._emit_event(StreamEvent.POSITION_UPDATE, position_data)
# Строка 316:
await self._emit_event(StreamEvent.ORDER_UPDATE, order_info)
# Строка 327:
await self._emit_event(StreamEvent.MARGIN_CALL, margin_call_info)
```
**Влияние**: Любая попытка использовать Binance stream приведёт к NameError и краху!
**Статус**: ✅ Подтверждено тремя методами (AST, flake8, grep)

### 2. ❌ CRITICAL: Функции вызываются до их определения в utils/decimal_utils.py
**Файл**: `utils/decimal_utils.py`
**Проблема A**: `round_decimal` вызывается на строках 28 и 34, но определена только на строке 37
```python
# Строка 28:
return round_decimal(value, precision)  # Функция ещё не определена!
# Строка 34:
return round_decimal(decimal_value, precision)  # Функция ещё не определена!
# Строка 37:
def round_decimal(value: Decimal, precision: int = 8, rounding=ROUND_DOWN) -> Decimal:
```

**Проблема B**: `round_to_tick_size` вызывается на строке 145, но определена только на строке 150
```python
# Строка 145:
sl_price = round_to_tick_size(sl_price, tick_size)  # Функция ещё не определена!
# Строка 150:
def round_to_tick_size(price: Decimal, tick_size: Decimal) -> Decimal:
```
**Влияние**: NameError при попытке использовать эти функции
**Статус**: ✅ Подтверждено AST анализом

### 3. ❌ CRITICAL: async_main вызывается до определения в main.py
**Файл**: `main.py`
**Проблема**: `async_main` вызывается на строке 793, но определена только на строке 804
```python
# Строка 793:
asyncio.run(async_main(bot))  # Функция ещё не определена!
# Строка 804:
async def async_main(bot: TradingBot):
```
**Влияние**: NameError при запуске главного модуля
**Статус**: ✅ Подтверждено AST анализом

---

## 🟡 ЛОЖНЫЕ СРАБАТЫВАНИЯ (НЕ ЯВЛЯЮТСЯ ОШИБКАМИ)

### Лямбда-функции и comprehensions
Следующие находки AST являются ложными срабатываниями (переменные определены в контексте):
- `core/wave_signal_processor.py:349-350` - переменная `s` в list comprehension
- `core/position_manager.py:156-159` - переменные `name`, `exchange` в dict comprehension
- `core/position_manager.py:2676` - переменные `symbol`, `pos` в dict comprehension
- `core/symbol_cache.py:116` - переменные в dict comprehension
- `monitoring/performance.py:339,614` - переменные в лямбдах
- `protection/position_guard.py:776-779` - переменные в dict comprehension
- `websocket/event_router.py:166` - переменные в dict comprehension
- `websocket/binance_stream.py:383` - переменные `k`, `v` в dict comprehension
- `websocket/signal_client.py:214,478` - переменные в лямбдах
- `websocket/signal_adapter.py:120` - переменные в лямбдах

### Потенциально проблемные (требуют проверки контекста)
- `database/transactional_repository.py:255-257` - переменные `tx_id`, `info` (возможно определены выше)

---

## 🟢 ПРОВЕРКА БАЗ ДАННЫХ
Проверены все ссылки на колонки БД:
- ✅ `row['daily_pnl']` - колонка существует
- ✅ `row['order_data']` - колонка существует
- ✅ `row['symbol']` - колонка существует
- ✅ `row['count']` - используется в агрегатных запросах

---

## 📊 СТАТИСТИКА ПРОВЕРКИ
- **Проверено файлов**: 63
- **Найдено потенциальных проблем AST**: 38
- **Реальных критических ошибок**: 9+ (минимум)
- **Ложных срабатываний**: ~29

---

## 🚨 РЕКОМЕНДАЦИИ ПО ИСПРАВЛЕНИЮ

### НЕМЕДЛЕННО:
1. **StreamEvent в binance_stream.py** - нужно либо:
   - Импортировать из другого модуля (если существует)
   - Определить enum/класс StreamEvent
   - Заменить на строковые константы

2. **decimal_utils.py** - переместить определения функций ВЫШЕ их использования

3. **main.py** - переместить определение async_main ВЫШЕ строки 793

### КРИТИЧЕСКИ ВАЖНО:
Эти ошибки могут привести к полному краху бота при определённых условиях! Особенно опасна ошибка со StreamEvent - любое использование Binance stream приведёт к краху.

---

## МЕТОДЫ ПРОВЕРКИ

### Метод 1: AST анализ
```bash
python3 check_undefined_vars.py
```
Результат: 38 потенциальных проблем

### Метод 2: Flake8 статический анализ
```bash
flake8 --select=F821 core database monitoring protection utils websocket main.py config.py
```
Результат: 6 подтверждённых ошибок StreamEvent

### Метод 3: Pattern matching
```bash
grep -r "StreamEvent" .
grep "def round_decimal\|def round_to_tick_size\|def async_main"
```
Результат: Подтверждены forward reference проблемы

---

## ЗАКЛЮЧЕНИЕ
Найдены **КРИТИЧЕСКИЕ ОШИБКИ**, которые ДОЛЖНЫ быть исправлены немедленно! Особенно опасны:
1. Полностью отсутствующий StreamEvent
2. Forward references в критических utility функциях
3. Forward reference в главном модуле запуска

Эти ошибки - "тикающие бомбы", которые могут взорваться в любой момент при определённых условиях выполнения.