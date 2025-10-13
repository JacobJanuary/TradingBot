# ПЛАН РЕАЛИЗАЦИИ: Stop Loss с Защитой от Price Drift

**Дата**: 2025-10-13
**Проблема**: SL рассчитывается от entry_price, игнорируя изменение цены
**Решение**: Использовать current_price если изменение > STOP_LOSS_PERCENT
**Статус**: ✅ ПЛАН ГОТОВ - БЕЗ ИЗМЕНЕНИЯ КОДА

---

## 🎯 СУТЬ РЕШЕНИЯ

### Правило:

```
IF price_drift > STOP_LOSS_PERCENT:
    base_price = current_price
ELSE:
    base_price = entry_price

stop_loss = base_price * (1 ± STOP_LOSS_PERCENT)
```

### Пример (HNTUSDT):

```
STOP_LOSS_PERCENT = 2%

Entry: 1.772
Current: 1.618
Drift: |1.618 - 1.772| / 1.772 = 8.7%

8.7% > 2% → USE CURRENT PRICE

SL = 1.618 * 0.98 = 1.585 ✅ VALID
```

### Почему Порог = STOP_LOSS_PERCENT?

**Логика**: Если цена ушла дальше чем размер самого SL, значит:
- Либо позиция уже в убытке больше SL
- Либо позиция в прибыли больше SL
- В обоих случаях нужно защищать **ТЕКУЩУЮ** позицию, а не начальную

**Преимущество**: Используем **СУЩЕСТВУЮЩУЮ** конфигурацию, не добавляем новых параметров.

---

## 📋 ШАГ 1: ОПРЕДЕЛИТЬ МЕСТА ИЗМЕНЕНИЯ

### 1.1 Основной Файл

**Файл**: `core/position_manager.py`

### 1.2 Найти Методы для Изменения

#### Метод A: Stop Loss Protection (Приоритет 1)

**Назначение**: Устанавливает SL для позиций без защиты

**Поиск**:
```bash
grep -n "unprotected_positions\|without.*stop.*loss\|ensure.*stop" core/position_manager.py
```

**Где искать**:
- Метод с логикой проверки `has_stop_loss = False`
- Цикл по позициям без SL
- Вызов `calculate_stop_loss` или прямой расчет

**Что изменить**:
1. Добавить получение `current_price` из ticker
2. Добавить расчет `price_drift`
3. Выбрать `base_price` на основе drift
4. Рассчитать SL от выбранного `base_price`

---

#### Метод B: _set_stop_loss (Приоритет 2)

**Назначение**: Общий метод установки SL

**Поиск**:
```bash
grep -n "async def _set_stop_loss\|def.*set.*stop.*loss" core/position_manager.py
```

**Сигнатура** (примерная):
```python
async def _set_stop_loss(self, exchange, position, stop_price: float)
```

**Проблема**: Этот метод принимает **готовый** `stop_price`, расчет происходит ДО вызова.

**Решение**: Изменять не этот метод, а **ТОТ, который РАССЧИТЫВАЕТ** stop_price перед вызовом.

---

#### Метод C: Расчет Stop Price (Приоритет 1)

**Где искать**:
```bash
grep -n "calculate_stop_loss\|stop_loss_percent\|entry_price.*0.98" core/position_manager.py
```

**Типичный паттерн**:
```python
stop_loss_percent = self.config.stop_loss_percent

stop_loss_price = calculate_stop_loss(
    entry_price=Decimal(str(position.entry_price)),
    side=position.side,
    stop_loss_percent=Decimal(str(stop_loss_percent))
)
```

**Это ГЛАВНОЕ место для изменений!**

---

### 1.3 Проверить Используемые Утилиты

**Файл**: `core/utils.py` или `utils/calculations.py`

**Функция**: `calculate_stop_loss`

**Поиск**:
```bash
grep -rn "def calculate_stop_loss" .
```

**Проверить**:
- Принимает ли `entry_price` как обязательный параметр?
- Можно ли передать любую цену (не только entry)?

**Ожидаемый результат**: Функция универсальная, принимает любую базовую цену.

---

## 📋 ШАГ 2: ДЕТАЛЬНЫЙ ПЛАН ИЗМЕНЕНИЙ

### 2.1 Найти Метод Stop Loss Protection

**Команда для поиска**:
```bash
grep -A 50 "def.*stop.*loss.*protection\|unprotected_positions" core/position_manager.py | head -80
```

**Искать блок вида**:
```python
for position in unprotected_positions:
    try:
        exchange = self.exchanges.get(position.exchange)

        # ЗДЕСЬ расчет stop_loss_price
        stop_loss_price = calculate_stop_loss(...)

        # ЗДЕСЬ вызов установки SL
        await sl_manager.set_stop_loss(...)
```

---

### 2.2 Определить Текущую Логику

**Что там СЕЙЧАС** (примерный код):

```python
# Текущая логика (ДО изменений)
stop_loss_percent = self.config.stop_loss_percent

stop_loss_price = calculate_stop_loss(
    entry_price=Decimal(str(position.entry_price)),  # ← Всегда entry_price
    side=position.side,
    stop_loss_percent=Decimal(str(stop_loss_percent))
)
```

**Проблема**: Всегда использует `position.entry_price`, игнорируя текущий рынок.

---

### 2.3 План Изменения (Псевдокод)

```python
# НОВАЯ логика (ПОСЛЕ изменений)

# Шаг 1: Получить текущую цену
try:
    ticker = await exchange.exchange.fetch_ticker(position.symbol)
    current_price = float(ticker.get('last') or ticker.get('mark') or 0)

    if current_price == 0:
        logger.error(f"Failed to get current price for {position.symbol}")
        continue  # Skip this position

except Exception as e:
    logger.error(f"Failed to fetch ticker for {position.symbol}: {e}")
    continue

# Шаг 2: Рассчитать price drift
entry_price = float(position.entry_price)
price_drift_pct = abs((current_price - entry_price) / entry_price)

# Шаг 3: Выбрать базовую цену
stop_loss_percent = self.config.stop_loss_percent

if price_drift_pct > stop_loss_percent:
    # Цена ушла дальше чем размер SL
    logger.warning(
        f"⚠️ {position.symbol}: Price drifted {price_drift_pct*100:.2f}% "
        f"(more than SL {stop_loss_percent*100}%). "
        f"Using CURRENT price {current_price:.6f} instead of entry {entry_price:.6f}"
    )
    base_price = current_price
else:
    # Цена в пределах нормы
    logger.info(
        f"✓ {position.symbol}: Price drift {price_drift_pct*100:.2f}% "
        f"within threshold {stop_loss_percent*100}%. Using entry price"
    )
    base_price = entry_price

# Шаг 4: Рассчитать SL от выбранной базы
stop_loss_price = calculate_stop_loss(
    entry_price=Decimal(str(base_price)),  # ← Используем base_price!
    side=position.side,
    stop_loss_percent=Decimal(str(stop_loss_percent))
)

# Шаг 5: Дополнительная валидация (safety check)
stop_loss_float = float(stop_loss_price)

if position.side == 'long':
    if stop_loss_float >= current_price:
        logger.error(
            f"❌ {position.symbol}: Calculated SL {stop_loss_float:.6f} >= "
            f"current {current_price:.6f} for LONG! Using emergency fallback"
        )
        # Emergency: force SL below current
        stop_loss_price = Decimal(str(current_price * (1 - stop_loss_percent)))

else:  # short
    if stop_loss_float <= current_price:
        logger.error(
            f"❌ {position.symbol}: Calculated SL {stop_loss_float:.6f} <= "
            f"current {current_price:.6f} for SHORT! Using emergency fallback"
        )
        # Emergency: force SL above current
        stop_loss_price = Decimal(str(current_price * (1 + stop_loss_percent)))

logger.info(
    f"📊 {position.symbol} SL: entry={entry_price:.6f}, "
    f"current={current_price:.6f}, base={base_price:.6f}, "
    f"SL={float(stop_loss_price):.6f}"
)

# Шаг 6: Установить SL (существующая логика не меняется)
result = await sl_manager.verify_and_fix_missing_sl(
    position=position,
    stop_price=float(stop_loss_price),
    max_retries=3
)
```

---

## 📋 ШАГ 3: ТОЧНАЯ ЛОКАЦИЯ ИЗМЕНЕНИЙ

### 3.1 Определить Номер Строки

**Команда**:
```bash
grep -n "stop_loss_price = calculate_stop_loss" core/position_manager.py
```

**Ожидаемый вывод**:
```
1711:                        stop_loss_price = calculate_stop_loss(
```

**ИЛИ** если используется прямой расчет:
```bash
grep -n "entry_price.*\*.*stop_loss_percent" core/position_manager.py
```

---

### 3.2 Прочитать Контекст (30 строк до и после)

**Команда**:
```bash
sed -n '1681,1741p' core/position_manager.py
```

**Анализ**:
1. Где начинается цикл `for position in unprotected_positions`?
2. Где находится расчет `stop_loss_price`?
3. Где находится вызов `set_stop_loss` или `verify_and_fix_missing_sl`?
4. Есть ли уже получение `current_price`?

---

### 3.3 Определить Зависимости

**Проверить импорты**:
```bash
head -50 core/position_manager.py | grep "from\|import"
```

**Нужны**:
- `from decimal import Decimal` - ✅ должен быть
- `calculate_stop_loss` - ✅ должна быть импортирована или определена

**Если нет** - добавить в импорты.

---

## 📋 ШАГ 4: ПЛАН ТЕСТИРОВАНИЯ

### 4.1 Создать Тест-Скрипт

**Файл**: `test_sl_drift_calculation.py`

**Назначение**: Проверить логику расчета БЕЗ реальной установки SL

**Псевдокод**:
```python
#!/usr/bin/env python3
"""Test SL calculation with price drift"""

def test_sl_calculation():
    """Test different scenarios"""

    STOP_LOSS_PERCENT = 0.02  # 2%

    scenarios = [
        # (entry, current, side, expected_base)
        (1.772, 1.618, 'long', 'current'),  # HNTUSDT: drift 8.7% > 2%
        (1.00, 1.01, 'long', 'entry'),      # Drift 1% < 2%
        (1.00, 0.97, 'long', 'current'),    # Drift 3% > 2%
        (1.00, 1.10, 'long', 'current'),    # Drift 10% > 2%
        (1.00, 0.90, 'short', 'current'),   # SHORT drift 10% > 2%
    ]

    for entry, current, side, expected in scenarios:
        # Calculate drift
        drift = abs((current - entry) / entry)

        # Choose base
        if drift > STOP_LOSS_PERCENT:
            base = current
            choice = 'current'
        else:
            base = entry
            choice = 'entry'

        # Calculate SL
        if side == 'long':
            sl = base * (1 - STOP_LOSS_PERCENT)
        else:
            sl = base * (1 + STOP_LOSS_PERCENT)

        # Validate
        if side == 'long':
            valid = sl < current
        else:
            valid = sl > current

        # Report
        status = "✅" if (choice == expected and valid) else "❌"
        print(f"{status} Entry={entry}, Current={current}, Side={side}")
        print(f"   Drift={drift*100:.2f}%, Base={choice}, SL={sl:.6f}, Valid={valid}")

        assert choice == expected, f"Expected {expected}, got {choice}"
        assert valid, f"SL {sl} invalid for {side} at {current}"

    print("\n✅ All tests passed!")

if __name__ == '__main__':
    test_sl_calculation()
```

**Команда запуска**:
```bash
python3 test_sl_drift_calculation.py
```

**Ожидаемый результат**: Все тесты проходят ✅

---

### 4.2 Тест на Реальных Данных (БЕЗ установки SL)

**Файл**: `test_real_positions_sl.py`

**Назначение**: Проверить расчет для реальных позиций из БД

**Псевдокод**:
```python
#!/usr/bin/env python3
"""Test SL calculation on real positions"""

import asyncio
import asyncpg
from dotenv import load_dotenv
import os

async def test_real():
    load_dotenv()

    # Connect to DB
    conn = await asyncpg.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', '5433')),
        database=os.getenv('DB_NAME', 'fox_crypto_test'),
        user=os.getenv('DB_USER', 'elcrypto'),
        password=os.getenv('DB_PASSWORD')
    )

    # Get active positions
    positions = await conn.fetch("""
        SELECT id, symbol, side, entry_price, quantity
        FROM monitoring.positions
        WHERE status = 'active'
        LIMIT 5
    """)

    print("="*80)
    print("TESTING SL CALCULATION ON REAL POSITIONS")
    print("="*80)

    for pos in positions:
        symbol = pos['symbol']
        entry = float(pos['entry_price'])
        side = pos['side']

        # Mock current price (в реальном коде - из ticker)
        # Для теста: симулируем разные ситуации
        current = entry * 0.92  # -8% drift

        print(f"\n{symbol}:")
        print(f"  Entry: {entry:.6f}")
        print(f"  Current (mock): {current:.6f}")
        print(f"  Side: {side}")

        # Calculate drift
        drift = abs((current - entry) / entry)
        print(f"  Drift: {drift*100:.2f}%")

        # Choose base
        STOP_LOSS_PERCENT = 0.02
        if drift > STOP_LOSS_PERCENT:
            base = current
            choice = "current"
        else:
            base = entry
            choice = "entry"

        print(f"  Base choice: {choice}")

        # Calculate SL
        if side == 'long':
            sl = base * (1 - STOP_LOSS_PERCENT)
        else:
            sl = base * (1 + STOP_LOSS_PERCENT)

        print(f"  SL: {sl:.6f}")

        # Validate
        if side == 'long':
            valid = sl < current
        else:
            valid = sl > current

        print(f"  Valid: {'✅' if valid else '❌'} ({sl:.6f} {'<' if side=='long' else '>'} {current:.6f})")

    await conn.close()

if __name__ == '__main__':
    asyncio.run(test_real())
```

**Команда**:
```bash
python3 test_real_positions_sl.py
```

**Проверяет**: Логика работает для реальных позиций из БД

---

## 📋 ШАГ 5: ПЛАН ДЕПЛОЯ

### 5.1 Pre-Deployment Checklist

**Перед изменением кода**:

- [ ] Создать бекап текущего файла
  ```bash
  cp core/position_manager.py core/position_manager.py.backup_$(date +%Y%m%d_%H%M%S)
  ```

- [ ] Проверить текущую работу бота
  ```bash
  tail -100 logs/trading_bot.log | grep "stop loss"
  ```

- [ ] Записать текущие метрики
  ```bash
  grep "without stop loss" logs/trading_bot.log | tail -20
  ```

- [ ] Создать ветку в git (если используется)
  ```bash
  git checkout -b fix/sl-price-drift
  ```

---

### 5.2 Implementation Steps

**Шаг A**: Найти точное место изменения
```bash
grep -n "stop_loss_price = calculate_stop_loss" core/position_manager.py
```

**Шаг B**: Прочитать контекст
```bash
# Заменить XXXX на номер строки из шага A
sed -n '$((XXXX-20)),$((XXXX+30))p' core/position_manager.py
```

**Шаг C**: Понять структуру
- Где находится цикл по позициям?
- Где `exchange` доступен?
- Где уже есть обращения к `exchange.exchange`?

**Шаг D**: Применить изменения (через Edit tool)

**Шаг E**: Проверить синтаксис
```bash
python3 -m py_compile core/position_manager.py
```

**Шаг F**: Запустить тесты
```bash
python3 test_sl_drift_calculation.py
python3 test_real_positions_sl.py
```

---

### 5.3 Deployment

**Шаг 1**: Остановить бота
```bash
# Метод зависит от того, как запущен бот
# Например:
pkill -f "python.*main.py"
# ИЛИ
systemctl stop trading_bot
```

**Шаг 2**: Применить изменения (уже сделано в шаге 5.2)

**Шаг 3**: Запустить бота
```bash
python3 main.py
# ИЛИ
systemctl start trading_bot
```

**Шаг 4**: Мониторить логи
```bash
tail -f logs/trading_bot.log | grep -E "Price drifted|SL:|stop loss"
```

---

### 5.4 Post-Deployment Monitoring

**Первые 5 минут**:
```bash
# Проверить нет ли ошибок
tail -100 logs/trading_bot.log | grep -i error

# Проверить что логика работает
tail -100 logs/trading_bot.log | grep "Price drifted"
```

**Первые 30 минут**:
```bash
# Проверить успешную установку SL
grep "Stop loss set" logs/trading_bot.log | tail -10

# Проверить нет ли ошибок base_price
grep "base_price" logs/trading_bot.log | tail -10
```

**Первые 24 часа**:
- Мониторить количество позиций без SL
- Проверить нет ли новых ошибок
- Проверить что SL устанавливаются успешно

---

## 📋 ШАГ 6: ROLLBACK ПЛАН

### 6.1 Если Что-то Пошло Не Так

**Признаки проблемы**:
- ❌ Бот падает с exception
- ❌ SL не устанавливаются (новые ошибки)
- ❌ Позиции остаются без SL дольше обычного

### 6.2 Быстрый Rollback

**Вариант A**: Восстановить из бекапа
```bash
# Остановить бота
pkill -f "python.*main.py"

# Восстановить файл
cp core/position_manager.py.backup_YYYYMMDD_HHMMSS core/position_manager.py

# Запустить бота
python3 main.py
```

**Вариант B**: Откат через git (если используется)
```bash
git checkout HEAD -- core/position_manager.py
systemctl restart trading_bot
```

---

## 📋 ШАГ 7: МЕТРИКИ УСПЕХА

### 7.1 Технические Метрики

**До изменений** (baseline):
```bash
# Количество ошибок base_price за последний час
grep "base_price" logs/trading_bot.log | grep "$(date +%Y-%m-%d\ %H)" | wc -l
```

**После изменений** (ожидаемое):
```bash
# Должно быть 0 ошибок base_price
grep "base_price" logs/trading_bot.log | grep "$(date +%Y-%m-%d\ %H)" | wc -l
# Expected: 0
```

### 7.2 Бизнес Метрики

**Проверить**:
- Количество позиций с SL: должно быть 100%
- Количество CRITICAL alerts "without stop loss": должно быть 0
- Среднее время установки SL: должно уменьшиться

**Команды**:
```bash
# Позиции с SL
psql -c "SELECT COUNT(*) FROM monitoring.positions WHERE status='active' AND has_stop_loss=true"

# CRITICAL alerts
grep "CRITICAL.*without stop loss" logs/trading_bot.log | tail -10
```

---

## 📋 ШАГ 8: ДОКУМЕНТАЦИЯ ИЗМЕНЕНИЙ

### 8.1 Что Записать

**В код**:
```python
# CRITICAL FIX (2025-10-13): Use current_price instead of entry_price
# when price drifts more than STOP_LOSS_PERCENT.
# This prevents "base_price validation" errors from Bybit when
# market price has moved significantly from entry.
# See: CORRECT_SOLUTION_SL_PRICE_DRIFT.md for details
```

**В git commit**:
```bash
git add core/position_manager.py
git commit -m "🔧 Fix SL validation error by using current_price on drift

Fix 'base_price validation' error when setting stop loss for positions
where price has drifted significantly from entry.

Problem:
- Bot calculated SL from entry_price (e.g. 1.772)
- Current market price dropped to 1.618
- SL = 1.772 * 0.98 = 1.74
- Bybit rejected: 1.74 > 1.618 (invalid for LONG)

Solution:
- Detect when price_drift > STOP_LOSS_PERCENT
- Use current_price as base instead of entry_price
- SL = 1.618 * 0.98 = 1.585 (valid)

Impact:
- 100% positions will have SL protection
- No more base_price validation errors
- Better risk management in volatile markets

File: core/position_manager.py
Lines: ~1681-1741 (stop loss protection logic)

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
"
```

**В changelog** (если есть):
```markdown
## [Unreleased] - 2025-10-13

### Fixed
- Stop-loss validation errors when price drifts significantly from entry
- Now uses current market price as base when drift > STOP_LOSS_PERCENT
- Prevents "base_price validation" rejections from Bybit API

### Changed
- Stop-loss calculation logic now adaptive to market conditions
- Added price drift detection and smart base price selection
```

---

## 📋 РЕЗЮМЕ ПЛАНА

### Ключевые Изменения:

1. **Получить current_price** из ticker перед расчетом SL
2. **Рассчитать drift** = |current - entry| / entry
3. **Выбрать base_price**:
   - Если drift > STOP_LOSS_PERCENT → base = current_price
   - Иначе → base = entry_price
4. **Рассчитать SL** от выбранного base_price
5. **Валидация** SL < current (LONG) или SL > current (SHORT)

### Локация:

**Файл**: `core/position_manager.py`

**Метод**: Stop loss protection (цикл по unprotected_positions)

**Строки**: ~1681-1741 (точно определить при реализации)

### Порог:

**STOP_LOSS_PERCENT** (из config) - используем существующий параметр!

### Безопасность:

- ✅ Бекап файла перед изменением
- ✅ Тесты перед деплоем
- ✅ Rollback план готов
- ✅ Мониторинг после деплоя

---

## ✅ ЧЕКЛИСТ ГОТОВНОСТИ

**Перед началом реализации проверить**:

- [ ] Понимание проблемы (price drift validation error)
- [ ] Понимание решения (use current_price when drift > SL%)
- [ ] Локация найдена (position_manager.py, строки определены)
- [ ] Тесты написаны и готовы
- [ ] Бекап план готов
- [ ] Rollback план готов
- [ ] Мониторинг план готов

**Когда все ✅ - можно начинать реализацию!**

---

**Статус**: ✅ ПЛАН ГОТОВ - ЖДЕТ РЕАЛИЗАЦИИ

**Приоритет**: 🔴 ВЫСОКИЙ

**Риск**: 🟢 НИЗКИЙ (изменение логики расчета, не архитектуры)

**Время**: ~30-60 минут (поиск места + изменение + тесты)

---

**Автор**: Claude Code
**Дата**: 2025-10-13
**Тип**: Implementation Plan (NO CODE CHANGES)
