# ПЛАН УДАЛЕНИЯ MAX_ACCOUNT_UTILIZATION_PERCENT

**Дата**: 2025-10-27
**Цель**: Полностью удалить функционал проверки safe account utilization из системы
**Причина**: Проверка блокирует открытие позиций даже при достаточных средствах. Пользователь хочет полностью убрать это ограничение

---

## 📋 EXECUTIVE SUMMARY

### Что будет удалено?
**Step 4: Conservative utilization check** в методе `ExchangeManager.can_open_position()`

### Текущее поведение:
```python
# Блокирует открытие позиции если:
utilization = (total_notional + new_position) / total_balance
if utilization > MAX_ACCOUNT_UTILIZATION_PERCENT:
    return False, "Would exceed safe utilization: 104.1% > 100%"
```

### После удаления:
- Step 4 полностью удален
- Остаются только проверки биржи (Step 1-3)
- Никаких искусственных ограничений на утилизацию счета

---

## 🔍 FORENSIC INVESTIGATION - ПОЛНЫЕ РЕЗУЛЬТАТЫ

### 1. Определение константы

**Файл**: `config/settings.py`

**Строка 45** (в классе TradingConfig):
```python
max_account_utilization_percent: Decimal = Decimal('100')
```

**Строки 208-209** (чтение из .env):
```python
if val := os.getenv('MAX_ACCOUNT_UTILIZATION_PERCENT'):
    config.max_account_utilization_percent = Decimal(val)
```

---

### 2. Использование в проверке

**Файл**: `core/exchange_manager.py`

**Метод**: `can_open_position()`
**Строки**: 1526-1531

**Полный контекст** (строки 1459-1537):
```python
async def can_open_position(self, symbol: str, notional_usd: float, preloaded_positions: Optional[List] = None) -> Tuple[bool, str]:
    """
    Check if we can open a new position without exceeding limits

    Steps:
    - Step 1: Check free balance
    - Step 1.5: Check minimum active balance reserve
    - Step 2: Get total current notional
    - Step 3: Check maxNotionalValue (Binance specific)
    - Step 4: Conservative utilization check ⚠️ ЭТОТ УДАЛЯЕМ
    """
    try:
        # Step 1: Check free balance
        free_usdt = await self._get_free_balance_usdt()
        total_usdt = await self._get_total_balance_usdt()

        if free_usdt < float(notional_usd):
            return False, f"Insufficient free balance: ${free_usdt:.2f} < ${notional_usd:.2f}"

        # Step 1.5: Check minimum active balance (reserve after opening position)
        remaining_balance = free_usdt - float(notional_usd)
        min_active_balance = float(config.safety.MINIMUM_ACTIVE_BALANCE_USD)

        if remaining_balance < min_active_balance:
            return False, (
                f"Insufficient free balance on {self.name}: "
                f"Opening ${notional_usd:.2f} position would leave ${remaining_balance:.2f}, "
                f"minimum required: ${min_active_balance:.2f}"
            )

        # Step 2: Get total current notional
        if preloaded_positions is not None:
            positions = preloaded_positions
        else:
            positions = await self.exchange.fetch_positions()
        total_notional = sum(abs(float(p.get('notional', 0)))
                            for p in positions if float(p.get('contracts', 0)) > 0)

        # Step 3: Check maxNotionalValue (Binance specific)
        if self.name == 'binance':
            try:
                exchange_symbol = self.find_exchange_symbol(symbol)
                symbol_clean = exchange_symbol.replace('/USDT:USDT', 'USDT')

                position_risk = await self.exchange.fapiPrivateV2GetPositionRisk({
                    'symbol': symbol_clean
                })

                for risk in position_risk:
                    if risk.get('symbol') == symbol_clean:
                        max_notional_str = risk.get('maxNotionalValue', 'INF')
                        if max_notional_str != 'INF':
                            max_notional = float(max_notional_str)

                            # FIX BUG #2: Ignore maxNotional = 0
                            if max_notional > 0:
                                new_total = total_notional + float(notional_usd)

                                if new_total > max_notional:
                                    return False, f"Would exceed max notional: ${new_total:.2f} > ${max_notional:.2f}"
                        break
            except Exception as e:
                # Log warning but don't block
                logger.warning(f"Could not check maxNotionalValue for {symbol}: {e}")

        # ⚠️ Step 4: Conservative utilization check - УДАЛИТЬ ЭТО!
        if total_usdt > 0:
            utilization = (total_notional + float(notional_usd)) / total_usdt
            max_util = float(config.trading.max_account_utilization_percent) / 100
            if utilization > max_util:
                return False, f"Would exceed safe utilization: {utilization*100:.1f}% > {max_util*100:.0f}%"

        return True, "OK"

    except Exception as e:
        logger.error(f"Error checking if can open position for {symbol}: {e}")
        return False, f"Validation error: {e}"
```

---

### 3. Переменная окружения

**Файл**: `.env`

**Строка 38**:
```bash
MAX_ACCOUNT_UTILIZATION_PERCENT=100  # Max % of total balance to use (prevents over-leveraging)
```

---

### 4. Вызовы can_open_position()

**НЕ ТРЕБУЮТ ИЗМЕНЕНИЙ** - эти вызовы останутся как есть:

#### Вызов 1: `core/position_manager.py:1828`
```python
# Check if we can afford this position (margin/leverage validation)
can_open, reason = await exchange.can_open_position(symbol, size_usd)
if not can_open:
    logger.warning(f"Cannot open {symbol} position: {reason}")
    return None
```

#### Вызов 2: `core/signal_processor_websocket.py:331`
```python
if exchange_manager:
    preloaded_positions = preloaded_positions_by_exchange.get(exchange_name, [])
    validation_tasks.append(
        exchange_manager.can_open_position(symbol, size_usd, preloaded_positions=preloaded_positions)
    )
```

---

### 5. Тестовые скрипты

**Файл**: `scripts/test_fix_margin_check.py`

**Строки 112-115**:
```python
MAX_UTILIZATION = 0.80  # Don't use more than 80% of total balance

if utilization_after > MAX_UTILIZATION:
    result['reason'] = f"Would exceed safe utilization: {utilization_after*100:.1f}% > {MAX_UTILIZATION*100:.1f}%"
    return result
```

**Статус**: Deprecated тестовый скрипт с hardcoded 80%
**Рекомендация**: Либо удалить скрипт, либо удалить Step 4 из скрипта

---

### 6. Тесты

**Результат поиска**: НЕТ юнит-тестов для MAX_ACCOUNT_UTILIZATION_PERCENT

**Проверенные файлы**:
- `tests/integration/test_bug2_max_notional_zero.py` - тестирует maxNotionalValue (Step 3), НЕ утилизацию (Step 4)
- Другие тесты `can_open_position` не найдены

**Вывод**: Удаление Step 4 НЕ сломает существующие тесты

---

### 7. Документация

**Файлы с упоминаниями** (информационно, не требуют изменений):
- `docs/new_errors/POSITION_OPENING_RESTRICTIONS_AUDIT.md` - описание проверки
- `docs/archive/investigations_2025-10-19/FINAL_FIX_PLAN_PHASES_2_3.md` - старые планы
- `docs/archive/investigations_2025-10-19/IMPLEMENTATION_PLAN_WAVE_ERRORS.md` - старые планы
- `docs/archive/investigations_2025-10-19/CACHE_RISK_ANALYSIS.md` - анализ
- `docs/new_errors/DEEP_WAVE_ERROR_INVESTIGATION_20251026.md` - логи с блокировками
- `docs/new_errors/ERRORS_POST_RESTART_20251026_2139.md` - логи с блокировками

---

## 🎯 ПЛАН УДАЛЕНИЯ

### GOLDEN RULE
- ❌ НЕ РЕФАКТОРЬ остальной код
- ❌ НЕ УЛУЧШАЙ структуру
- ❌ НЕ МЕНЯЙ Step 1, Step 2, Step 3
- ✅ ТОЛЬКО удалить Step 4 и связанную конфигурацию

---

### Изменение 1: Удалить Step 4 из can_open_position()

**Файл**: `core/exchange_manager.py`

**Удалить строки 1526-1531**:
```python
# УДАЛИТЬ ЭТО:
# Step 4: Conservative utilization check
if total_usdt > 0:
    utilization = (total_notional + float(notional_usd)) / total_usdt
    max_util = float(config.trading.max_account_utilization_percent) / 100
    if utilization > max_util:
        return False, f"Would exceed safe utilization: {utilization*100:.1f}% > {max_util*100:.0f}%"
```

**После удаления** (строки 1526-1533):
```python
# Step 3 заканчивается на строке 1524
            except Exception as e:
                # Log warning but don't block
                logger.warning(f"Could not check maxNotionalValue for {symbol}: {e}")

        return True, "OK"

    except Exception as e:
        logger.error(f"Error checking if can open position for {symbol}: {e}")
        return False, f"Validation error: {e}"
```

**Обновить docstring** (строки 1460-1470):
```python
"""
Check if we can open a new position without exceeding limits

Args:
    symbol: Trading symbol
    notional_usd: Position size in USD
    preloaded_positions: Optional pre-fetched positions list (for parallel validation)

Returns:
    (can_open, reason)

Steps:
    1. Check free balance
    1.5. Check minimum active balance reserve
    2. Get total current notional
    3. Check maxNotionalValue (Binance specific)
"""
```

---

### Изменение 2: Удалить из config/settings.py

**Файл**: `config/settings.py`

**Удалить строку 45** (в классе TradingConfig):
```python
# УДАЛИТЬ:
max_account_utilization_percent: Decimal = Decimal('100')
```

**Удалить строки 208-209** (в методе from_env):
```python
# УДАЛИТЬ:
if val := os.getenv('MAX_ACCOUNT_UTILIZATION_PERCENT'):
    config.max_account_utilization_percent = Decimal(val)
```

---

### Изменение 3: Удалить из .env

**Файл**: `.env`

**Удалить строку 38**:
```bash
# УДАЛИТЬ:
MAX_ACCOUNT_UTILIZATION_PERCENT=100  # Max % of total balance to use (prevents over-leveraging)
```

---

### Изменение 4: Обновить тестовый скрипт (опционально)

**Файл**: `scripts/test_fix_margin_check.py`

**Вариант A**: Удалить весь скрипт (если deprecated)

**Вариант B**: Удалить Step 4 из скрипта (строки 109-116):
```python
# УДАЛИТЬ:
# Step 4: Conservative check - ensure we don't use too much of total balance
utilization_after = (total_notional + notional_usd) / total_usdt if total_usdt > 0 else 0

MAX_UTILIZATION = 0.80  # Don't use more than 80% of total balance

if utilization_after > MAX_UTILIZATION:
    result['reason'] = f"Would exceed safe utilization: {utilization_after*100:.1f}% > {MAX_UTILIZATION*100:.1f}%"
    return result
```

**Рекомендация**: Вариант A (удалить скрипт) - он устарел

---

## ✅ VERIFICATION PLAN

### 1. Code Review Checklist

После удаления проверить:

```bash
# 1. Убедиться что MAX_ACCOUNT_UTILIZATION не осталось в коде
grep -rn "MAX_ACCOUNT_UTILIZATION" --include="*.py" core/ config/

# 2. Убедиться что safe_utilization проверки удалены
grep -rn "safe_utilization" --include="*.py" core/

# 3. Убедиться что max_account_utilization_percent удалено из settings
grep -rn "max_account_utilization_percent" config/settings.py

# 4. Проверить что .env очищен
grep "MAX_ACCOUNT_UTILIZATION" .env
```

**Ожидаемый результат**: Все команды должны вернуть 0 результатов (или только в docs/)

---

### 2. Functional Testing

**Тест 1**: Позиция с утилизацией >100% должна открываться
```python
# Сценарий:
# - Total balance: $10,000
# - Current notional: $8,000
# - New position: $5,000
# - Utilization after: 130% (было бы заблокировано до удаления)

# До удаления:
can_open = False
reason = "Would exceed safe utilization: 130.0% > 100%"

# После удаления:
can_open = True  # Если достаточно free balance
reason = "OK"
```

**Тест 2**: Step 1-3 все еще работают
- Step 1: Insufficient free balance - блокирует
- Step 1.5: Minimum active balance - блокирует
- Step 2: (no blocking, just calculation)
- Step 3: maxNotionalValue - блокирует (Binance only)

---

### 3. Integration Testing

**Проверить реальный сценарий** из логов:

```
2025-10-27 03:05:32,200 - Cannot open COOKUSDT position: Would exceed safe utilization: 104.1% > 100%
```

**После удаления** эта позиция должна открываться (если достаточно free_usdt и не блокируют Step 1-3).

---

## 🚨 POTENTIAL RISKS

### Risk 1: Overleveraging
**Описание**: Без Step 4 система может использовать >100% баланса (через leverage)

**Пример**:
- Total balance: $10,000
- Leverage: 10x
- Max notional: $100,000
- System может открыть позиции на $100k (1000% утилизации)

**Mitigation**:
- Step 1.5 (MINIMUM_ACTIVE_BALANCE_USD) защищает от полного обнуления баланса
- Step 3 (maxNotionalValue) ограничивает по Binance API
- Пользователь сам управляет риском через размер позиций

**Severity**: MEDIUM
**User Acceptance**: Пользователь явно запросил удаление этой защиты

---

### Risk 2: Liquidation Risk
**Описание**: Высокая утилизация увеличивает риск ликвидации

**Mitigation**:
- Trailing stops защищают прибыльные позиции
- Stop-loss защищает от больших убытков
- Пользователь сам управляет риском

**Severity**: MEDIUM
**User Acceptance**: Пользователь принимает риск

---

### Risk 3: No Tests Will Break
**Описание**: Нет юнит-тестов для этой проверки

**Validation**: Ручное тестирование в production

**Severity**: LOW
**Mitigation**: Мониторинг логов после развертывания

---

## 📦 GIT STRATEGY

### Commit Message

```bash
git add core/exchange_manager.py config/settings.py .env
git commit -m "feat(risk): remove MAX_ACCOUNT_UTILIZATION_PERCENT restriction

Remove Step 4 (safe utilization check) from can_open_position().
Allow positions to be opened without artificial utilization limits.

Changes:
- Remove Step 4 from ExchangeManager.can_open_position()
- Remove max_account_utilization_percent from TradingConfig
- Remove MAX_ACCOUNT_UTILIZATION_PERCENT from .env
- Update docstring to reflect removed step

Remaining protections:
- Step 1: Free balance check (exchange limit)
- Step 1.5: Minimum active balance reserve
- Step 3: maxNotionalValue check (Binance API limit)

User explicitly requested removal of this bot-imposed restriction.
System will rely on exchange limits and user risk management.

Related: POSITION_OPENING_RESTRICTIONS_AUDIT.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Optional: Clean up test script

```bash
git rm scripts/test_fix_margin_check.py
git commit -m "chore: remove deprecated test_fix_margin_check.py script

Script contained hardcoded 80% utilization check which is being removed.
Script is deprecated and no longer needed.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## 📊 IMPACT SUMMARY

### What Changes
- ❌ Step 4 "Conservative utilization check" - **REMOVED**
- ❌ MAX_ACCOUNT_UTILIZATION_PERCENT config - **REMOVED**
- ❌ max_account_utilization_percent setting - **REMOVED**

### What Stays
- ✅ Step 1: Free balance check
- ✅ Step 1.5: Minimum active balance reserve
- ✅ Step 2: Total notional calculation
- ✅ Step 3: maxNotionalValue check (Binance)
- ✅ All other position opening restrictions (MAX_POSITIONS, MAX_EXPOSURE_USD, etc.)

### Lines Changed
- `core/exchange_manager.py`: -6 lines (удалить Step 4), ~2 lines (обновить docstring)
- `config/settings.py`: -1 line (переменная), -2 lines (чтение из env)
- `.env`: -1 line

**Total**: ~12 lines removed

---

## 🎬 IMPLEMENTATION STEPS

1. ✅ **Расследование завершено** (этот документ)
2. ⏳ **Ожидание подтверждения пользователя**
3. 🔄 **Реализация согласно плану**:
   - Изменение 1: `core/exchange_manager.py`
   - Изменение 2: `config/settings.py`
   - Изменение 3: `.env`
   - Изменение 4: `scripts/test_fix_margin_check.py` (опционально)
4. ✅ **Верификация** (grep проверки)
5. 🧪 **Тестирование** (см. Verification Plan)
6. 📝 **Git commit**
7. 🚀 **Push**
8. 👁️ **Мониторинг** логов после деплоя

---

## 📝 FINAL NOTES

### История изменений
1. **Первая версия**: Hardcoded 80% утилизация
2. **Первое улучшение**: Сделали конфигурируемым через MAX_ACCOUNT_UTILIZATION_PERCENT
3. **Финальное решение**: Полное удаление проверки по запросу пользователя

### Логи до удаления
```
2025-10-27 03:05:32 - Cannot open COOKUSDT: Would exceed safe utilization: 104.1% > 100%
2025-10-26 21:49:33 - Cannot open COMPUSDT: Would exceed safe utilization: 83.0% > 80%
2025-10-26 21:49:36 - Cannot open SNXUSDT: Would exceed safe utilization: 83.0% > 80%
```

### Ожидаемый результат
После удаления эти позиции будут открываться (если проходят Step 1-3).

---

**Конец плана**
