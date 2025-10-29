# CRITICAL BUG: Bybit Free Balance Calculation - MINIMUM_ACTIVE_BALANCE_USD не работает

**Дата**: 2025-10-27
**Severity**: CRITICAL
**Impact**: MINIMUM_ACTIVE_BALANCE_USD защита не работает для Bybit, баланс упал до $3.36 вместо минимума $10

---

## 📊 FORENSIC INVESTIGATION - РЕЗУЛЬТАТЫ ТЕСТА

### Реальные данные с Bybit UNIFIED аккаунта:

```
ACCOUNT-LEVEL BALANCES:
totalEquity             : $51.1991 (total account value)
totalWalletBalance      : $51.2329 (wallet balance)
totalMarginBalance      : $0.0000 (пустая строка "" - НЕ ИСПОЛЬЗУЕТСЯ!)
totalInitialMargin      : $0.0000 (пустая строка "")
totalAvailableBalance   : $0.0000 (пустая строка "" - НЕ ИСПОЛЬЗУЕТСЯ!)

COIN-LEVEL BALANCES (USDT):
walletBalance           : $50.7894 (USDT wallet)
locked                  : $0.0000 (locked by spot orders)
totalPositionIM         : $47.4198 (margin used in positions!)
```

### Текущий код (НЕПРАВИЛЬНО):
```python
free_balance = walletBalance - locked
free_balance = $50.7894 - $0.00 = $50.7894  ← ОШИБКА!
```

### Правильный расчет:
```python
free_balance = walletBalance - totalPositionIM
free_balance = $50.7894 - $47.4198 = $3.3696  ← ПРАВИЛЬНО!
```

### Пользователь видит:
```
Available Balance: 3.3670 USDT  ← Почти точно!
```

---

## 🔍 ROOT CAUSE ANALYSIS

### Проблема #1: Неправильная формула

**Текущий код** (`core/exchange_manager.py:270-272`):
```python
wallet_balance = float(coin_data.get('walletBalance', 0) or 0)
locked = float(coin_data.get('locked', 0) or 0)
free_balance = wallet_balance - locked  # ❌ НЕПРАВИЛЬНО!
```

**Что не учитывается:**
- `totalPositionIM` - Initial Margin занятый в открытых позициях
- Это КРИТИЧЕСКОЕ упущение для futures/margin trading!

### Проблема #2: totalAvailableBalance не работает для UNIFIED

**Из теста:**
```
totalAvailableBalance: $0.0000
```

**Причина:**
Bybit API возвращает **пустую строку ""** для `totalAvailableBalance` на некоторых UNIFIED аккаунтах.

**Из комментария в коде** (line 264):
```python
# FIX: totalAvailableBalance is often empty string "" for UNIFIED accounts
```

Этот комментарий был для другого поля, но проблема та же!

### Проблема #3: Coin-level данные ИМЕЮТ правильную информацию

**Coin-level поля (USDT):**
- ✅ `walletBalance` - есть ($50.7894)
- ✅ `totalPositionIM` - есть ($47.4198)
- ✅ Формула работает: $50.7894 - $47.4198 = $3.3696

---

## 💥 IMPACT ANALYSIS

### Сценарий который произошел:

1. **Баланс:** $50.79 USDT total
2. **В позициях:** $47.42 margin (несколько открытых позиций)
3. **Реально доступно:** $3.37 USDT

**Текущий код думает:**
```python
free_balance = $50.79
remaining_after_$6_position = $44.79
MINIMUM_ACTIVE_BALANCE = $10.00

Check: $44.79 >= $10.00? YES ✅ PASS (НЕПРАВИЛЬНО!)
Position opened → баланс падает до $3.37 ❌
```

**Правильно должно быть:**
```python
free_balance = $3.37
remaining_after_$6_position = -$2.63
MINIMUM_ACTIVE_BALANCE = $10.00

Check: -$2.63 >= $10.00? NO ❌ FAIL (ПРАВИЛЬНО!)
Position NOT opened → защита работает
```

### Real-world последствия:

```
2025-10-27: Available Balance 3.3670 USDT
```

- ❌ Баланс упал ниже $10 минимума
- ❌ Нет запаса для комиссий
- ❌ Риск ликвидации при малых движениях
- ❌ Невозможность открывать новые позиции

---

## 🎯 SOLUTION

### Правильная формула для Bybit UNIFIED:

```python
free_balance = walletBalance - totalPositionIM
```

**Объяснение:**
- `walletBalance` - весь USDT баланс
- `totalPositionIM` - margin занятый в позициях
- Разница = доступно для новых позиций

---

## 📝 DETAILED FIX PLAN

### Изменение: `core/exchange_manager.py`

**Файл:** `core/exchange_manager.py`
**Метод:** `_get_free_balance_usdt()`
**Строки:** 263-274

#### До (НЕПРАВИЛЬНО):

```python
# FIX: totalAvailableBalance is often empty string "" for UNIFIED accounts
# Use coin[].walletBalance instead
coins = account.get('coin', [])
for coin_data in coins:
    if coin_data.get('coin') == 'USDT':
        # walletBalance - locked = available for new positions
        wallet_balance = float(coin_data.get('walletBalance', 0) or 0)
        locked = float(coin_data.get('locked', 0) or 0)
        free_balance = wallet_balance - locked  # ❌ НЕПРАВИЛЬНО!
        logger.debug(f"Bybit USDT: wallet={wallet_balance:.2f}, locked={locked:.2f}, free={free_balance:.2f}")
        return free_balance
```

#### После (ПРАВИЛЬНО):

```python
# FIX: For UNIFIED accounts, must account for margin used in positions
# totalAvailableBalance often returns empty string ""
# Correct formula: walletBalance - totalPositionIM
coins = account.get('coin', [])
for coin_data in coins:
    if coin_data.get('coin') == 'USDT':
        wallet_balance = float(coin_data.get('walletBalance', 0) or 0)
        total_position_im = float(coin_data.get('totalPositionIM', 0) or 0)

        # Free balance = wallet - margin used in positions
        free_balance = wallet_balance - total_position_im

        logger.debug(
            f"Bybit USDT: wallet={wallet_balance:.2f}, "
            f"positionIM={total_position_im:.2f}, "
            f"free={free_balance:.2f}"
        )
        return free_balance
```

#### Изменения:
1. ❌ Удалить: `locked = float(coin_data.get('locked', 0) or 0)`
2. ✅ Добавить: `total_position_im = float(coin_data.get('totalPositionIM', 0) or 0)`
3. ✅ Изменить формулу: `free_balance = wallet_balance - total_position_im`
4. ✅ Обновить debug log

**Lines changed:** ~6 lines
**Complexity:** LOW (простая замена формулы)

---

## ✅ VERIFICATION PLAN

### Test 1: Запустить тестовый скрипт

```bash
python tests/manual/test_bybit_free_balance_bug.py
```

**Ожидаемый результат:**
```
_get_free_balance_usdt() returns: $3.3696
✅ Matches correct calculation (walletBalance - totalPositionIM)
```

### Test 2: Проверить MINIMUM_ACTIVE_BALANCE_USD

**Сценарий:**
```python
free_balance = $3.37
position_size = $6.00
remaining = $3.37 - $6.00 = -$2.63
min_active = $10.00

Check: -$2.63 >= $10.00? NO ❌
Result: Position BLOCKED ✅
```

**Ожидаемый лог:**
```
WARNING - Cannot open SYMBOL position:
Insufficient free balance on bybit:
Opening $6.00 position would leave $-2.63,
minimum required: $10.00
```

### Test 3: Production мониторинг

После деплоя отслеживать:
1. ✅ Баланс не падает ниже $10
2. ✅ Логи блокировки позиций когда free < $16 ($6 position + $10 reserve)
3. ✅ Нет аварийных ситуаций с балансом

---

## 🚨 POTENTIAL RISKS

### Risk 1: Blocked positions

**Описание:** Если сейчас много открытых позиций, free balance может быть очень маленький

**Пример:**
```
wallet = $50
positions_margin = $47
free = $3 (правильно) vs $50 (текущий баг)

С исправлением: новые позиции блокируются!
```

**Mitigation:**
- Это ПРАВИЛЬНОЕ поведение!
- Защищает от over-leveraging
- Пользователь должен либо закрыть позиции, либо пополнить баланс

**Severity:** LOW (это feature, не bug)

### Risk 2: totalPositionIM может быть пустой строкой

**Описание:** Как и другие поля, `totalPositionIM` может вернуть `""`

**Mitigation:**
```python
total_position_im = float(coin_data.get('totalPositionIM', 0) or 0)
# "or 0" обрабатывает пустые строки
```

**Severity:** LOW (уже обработано в коде)

---

## 📦 GIT STRATEGY

### Commit Message

```bash
git add core/exchange_manager.py
git commit -m "fix(bybit): correct free balance calculation for UNIFIED accounts

CRITICAL BUG: MINIMUM_ACTIVE_BALANCE_USD protection was not working for Bybit.
Balance dropped to $3.36 despite $10 minimum requirement.

Root cause:
- Old formula: walletBalance - locked (WRONG!)
- Ignored totalPositionIM (margin used in open positions)

Fix:
- New formula: walletBalance - totalPositionIM (CORRECT!)
- Properly accounts for margin used in futures positions

Impact:
- Before: free_balance = $50.79 (overestimated by $47.42!)
- After: free_balance = $3.37 (matches Bybit UI)
- MINIMUM_ACTIVE_BALANCE_USD check now works correctly

Verification:
- Test: tests/manual/test_bybit_free_balance_bug.py
- Real balance: $3.36 USDT (confirmed match)

Related: MINIMUM_ACTIVE_BALANCE_USD protection (Phase 3)

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## 🎬 IMPLEMENTATION STEPS

1. ✅ **Investigation completed** (этот документ)
2. ✅ **Test script created** (`tests/manual/test_bybit_free_balance_bug.py`)
3. ✅ **Bug verified** (difference: $47.42!)
4. ⏳ **Awaiting user confirmation**
5. 🔄 **Implementation:**
   - Изменить `_get_free_balance_usdt()` в `core/exchange_manager.py`
   - 6 строк кода
6. ✅ **Verification:**
   - Запустить тест
   - Проверить что результат = $3.37
7. 📝 **Git commit and push**
8. 👁️ **Production monitoring**

---

## 📊 COMPARISON SUMMARY

| Metric | Current (WRONG) | Fixed (CORRECT) | User sees |
|--------|----------------|-----------------|-----------|
| walletBalance | $50.79 | $50.79 | - |
| locked | $0.00 | - | - |
| totalPositionIM | (ignored!) | $47.42 | - |
| **free_balance** | **$50.79** | **$3.37** | **$3.37** ✅ |
| Difference | - | - | $47.42 |
| MINIMUM check | PASS ❌ | FAIL ✅ | - |

---

## 🔑 KEY FINDINGS

1. ✅ **Bug confirmed:** Current code overestimates by **$47.42** (93% error!)
2. ✅ **Root cause identified:** Missing `totalPositionIM` in calculation
3. ✅ **Fix is simple:** 6 lines, change formula
4. ✅ **Test matches reality:** $3.3696 vs $3.3670 (0.08% diff)
5. ✅ **No breaking changes:** Just fixes broken protection

---

## 💡 LESSONS LEARNED

### Why did this happen?

1. **Misleading field name:** `locked` sounds like "all locked funds", but it's only for spot orders
2. **Hidden complexity:** Futures margin tracking requires different field (`totalPositionIM`)
3. **Silent failures:** Empty strings `""` from API masked the real issue
4. **No E2E tests:** Unit tests didn't catch real-world balance scenarios

### How to prevent?

1. ✅ Created comprehensive test script
2. ✅ Document Bybit API quirks (empty strings)
3. ✅ Add production monitoring for balance drops
4. 🔄 Consider E2E test with real positions

---

**СТАТУС:** ⏳ **AWAITING USER CONFIRMATION**

Готов к реализации. Жду команды! 🚀

---

**End of Plan**
