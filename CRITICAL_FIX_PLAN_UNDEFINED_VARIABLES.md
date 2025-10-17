# ДЕТАЛЬНЫЙ ПЛАН ИСПРАВЛЕНИЯ КРИТИЧЕСКИХ ОШИБОК С НЕОПРЕДЕЛЁННЫМИ ПЕРЕМЕННЫМИ

**Дата**: 2025-10-17
**Критичность**: МАКСИМАЛЬНАЯ
**Принцип**: "If it ain't broke, don't fix it" - минимальные хирургические изменения

---

## 🔴 ОШИБКА #1: StreamEvent и _emit_event НЕ СУЩЕСТВУЮТ

### Глубокое расследование:
1. **Файл**: `websocket/binance_stream.py`
2. **Проблема**:
   - `StreamEvent` используется 6 раз (строки 126, 136, 194, 254, 316, 327)
   - `_emit_event` метод тоже НЕ СУЩЕСТВУЕТ в классе!
   - Ни StreamEvent, ни _emit_event не определены нигде в коде
3. **Зависимости**:
   - Используется в `main.py` (строка 179) при создании BinancePrivateStream
   - Критично для работы с Binance
4. **Последствия**:
   - NameError при любой попытке подключения к Binance WebSocket
   - Полный крах бота при работе с Binance

### План исправления:
```python
# ВАРИАНТ 1: Добавить в начало binance_stream.py (РЕКОМЕНДУЕТСЯ)
from enum import Enum

class StreamEvent(Enum):
    """WebSocket stream events"""
    CONNECTED = "connected"
    ERROR = "error"
    BALANCE_UPDATE = "balance_update"
    POSITION_UPDATE = "position_update"
    ORDER_UPDATE = "order_update"
    MARGIN_CALL = "margin_call"

# И добавить метод _emit_event в класс BinancePrivateStream:
async def _emit_event(self, event: StreamEvent, data: Dict):
    """Emit event to handler"""
    if self.event_handler:
        await self.event_handler(event.value, data)
```

### План тестирования:
1. **Unit тест**: Создать mock WebSocket и проверить вызов событий
2. **Integration тест**: Подключиться к testnet Binance
3. **Проверка**: `python3 -c "from websocket.binance_stream import BinancePrivateStream, StreamEvent"`
4. **Runtime тест**: Запустить бот с Binance в тестовом режиме

---

## 🔴 ОШИБКА #2: Forward References в decimal_utils.py

### Глубокое расследование:
1. **Файл**: `utils/decimal_utils.py`
2. **Проблемы**:
   - `round_decimal` вызывается на строках 28, 34 до определения на строке 37
   - `round_to_tick_size` вызывается на строке 145 до определения на строке 150
3. **Зависимости**:
   - Импортируется в `core/position_manager.py`
   - Импортируется в `core/exchange_manager.py`
   - Импортируется в `core/exchange_manager_enhanced.py`
4. **Последствия**:
   - NameError при вызове `to_decimal()`
   - NameError при вызове `calculate_stop_loss()` с tick_size

### План исправления:
```python
# ПРОСТОЕ РЕШЕНИЕ: Переместить функции в правильный порядок
# 1. Переместить round_decimal() ПЕРЕД to_decimal() (перед строкой 13)
# 2. Переместить round_to_tick_size() ПЕРЕД calculate_stop_loss() (перед строкой 118)
```

### Детальные шаги:
1. Вырезать строки 37-53 (функция round_decimal)
2. Вставить после строки 11 (перед to_decimal)
3. Вырезать строки 150-164 (функция round_to_tick_size)
4. Вставить перед строкой 118 (перед calculate_stop_loss)

### План тестирования:
1. **Import тест**: `python3 -c "from utils.decimal_utils import *"`
2. **Unit тесты**:
   ```python
   from utils.decimal_utils import to_decimal, calculate_stop_loss
   assert to_decimal("100.5", 2)
   assert calculate_stop_loss(Decimal("100"), "long", Decimal("5"), Decimal("0.01"))
   ```
3. **Integration**: Запустить position_manager тесты

---

## 🔴 ОШИБКА #3: Forward Reference в main.py

### Глубокое расследование:
1. **Файл**: `main.py`
2. **Проблема**: `async_main` вызывается на строке 793, определена на строке 804
3. **Зависимости**: Это точка входа в приложение
4. **Последствия**: NameError при запуске бота

### План исправления:
```python
# ПРОСТОЕ РЕШЕНИЕ: Переместить определение async_main ПЕРЕД main()
# Вырезать строки 804-808 и вставить перед строкой 695 (перед def main())
```

### Детальные шаги:
1. Вырезать строки 804-808 (функция async_main)
2. Вставить перед строкой 695 (перед функцией main)

### План тестирования:
1. **Syntax check**: `python3 -m py_compile main.py`
2. **Dry run**: `python3 main.py --help`
3. **Test mode**: Запустить с тестовой конфигурацией

---

## 📋 ПОРЯДОК ИСПРАВЛЕНИЯ (КРИТИЧЕСКИ ВАЖНО!)

### Последовательность:
1. **ПЕРВЫМ**: Исправить `decimal_utils.py` (наименьший риск, не ломает ничего)
2. **ВТОРЫМ**: Исправить `main.py` (простое перемещение функции)
3. **ТРЕТЬИМ**: Исправить `binance_stream.py` (самое сложное, требует добавления кода)

### Проверка после КАЖДОГО исправления:
```bash
# После decimal_utils.py:
python3 -c "from utils.decimal_utils import *; print('✅ decimal_utils OK')"

# После main.py:
python3 -m py_compile main.py && echo "✅ main.py OK"

# После binance_stream.py:
python3 -c "from websocket.binance_stream import BinancePrivateStream, StreamEvent; print('✅ binance_stream OK')"
```

---

## ⚠️ РИСКИ И МЕРЫ ПРЕДОСТОРОЖНОСТИ

### Риски:
1. **decimal_utils.py**: Минимальный риск, простое перемещение
2. **main.py**: Минимальный риск, простое перемещение
3. **binance_stream.py**: ВЫСОКИЙ РИСК - добавление нового кода

### Меры предосторожности:
1. **Бэкап перед каждым изменением**:
   ```bash
   cp utils/decimal_utils.py utils/decimal_utils.py.backup_$(date +%Y%m%d_%H%M%S)
   cp main.py main.py.backup_$(date +%Y%m%d_%H%M%S)
   cp websocket/binance_stream.py websocket/binance_stream.py.backup_$(date +%Y%m%d_%H%M%S)
   ```

2. **Проверка зависимостей**:
   ```bash
   # Проверить что никто не использует неопределённые функции напрямую
   grep -r "round_decimal\|round_to_tick_size\|async_main" --include="*.py"
   ```

3. **Остановить бот перед исправлениями**:
   ```bash
   pkill -f "python.*main.py"
   ```

---

## 🧪 ПОЛНЫЙ ПЛАН ТЕСТИРОВАНИЯ

### 1. Pre-fix тестирование (подтвердить ошибки):
```python
# Тест 1: Подтвердить ошибку в decimal_utils
try:
    from utils.decimal_utils import to_decimal
    to_decimal("100")  # Должен упасть с NameError
except NameError as e:
    print(f"✅ Confirmed: {e}")

# Тест 2: Подтвердить ошибку в binance_stream
try:
    from websocket.binance_stream import BinancePrivateStream
    # Создать экземпляр и вызвать connect
except NameError as e:
    print(f"✅ Confirmed: {e}")
```

### 2. Post-fix тестирование:
```python
# Тест 1: decimal_utils
from decimal import Decimal
from utils.decimal_utils import to_decimal, calculate_stop_loss, round_to_tick_size
assert to_decimal("100.123456", 4) == Decimal("100.1234")
assert calculate_stop_loss(Decimal("100"), "long", Decimal("5"), Decimal("0.01"))
print("✅ decimal_utils works!")

# Тест 2: main.py
import main  # Не должно быть ошибок импорта
print("✅ main.py imports successfully!")

# Тест 3: binance_stream
from websocket.binance_stream import BinancePrivateStream, StreamEvent
assert StreamEvent.CONNECTED.value == "connected"
print("✅ binance_stream works!")
```

### 3. Integration тестирование:
```bash
# Запустить бот в тестовом режиме на 1 минуту
timeout 60 python3 main.py --test-mode

# Проверить логи на наличие NameError
grep -i "nameerror\|undefined" logs/*.log
```

---

## 📊 МЕТРИКИ УСПЕХА

1. **Нет NameError в логах**: `grep -c NameError logs/*.log` должен вернуть 0
2. **Успешный импорт всех модулей**: Все import тесты проходят
3. **Бот запускается без ошибок**: `python3 main.py` не падает сразу
4. **WebSocket подключается**: Binance stream подключается без ошибок

---

## 🔄 ROLLBACK ПЛАН

Если что-то пойдёт не так:
```bash
# Восстановить оригиналы
mv utils/decimal_utils.py.backup_* utils/decimal_utils.py
mv main.py.backup_* main.py
mv websocket/binance_stream.py.backup_* websocket/binance_stream.py

# Перезапустить бот
python3 main.py
```

---

## ЗАКЛЮЧЕНИЕ

**КРИТИЧЕСКИ ВАЖНО**:
1. Делать исправления ПО ОДНОМУ
2. Тестировать после КАЖДОГО исправления
3. Делать бэкапы ПЕРЕД изменениями
4. НЕ РЕФАКТОРИТЬ - только минимальные изменения для исправления ошибок

Эти ошибки ДОЛЖНЫ быть исправлены немедленно, так как они могут привести к полному краху бота в любой момент!