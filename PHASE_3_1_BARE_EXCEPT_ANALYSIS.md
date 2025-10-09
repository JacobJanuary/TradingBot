# Phase 3.1: Bare Except Analysis and Fixes

**Status:** 🔄 IN PROGRESS
**Priority:** 🟡 HIGH
**Risk:** ⚠️ MEDIUM - PEP 8 violation, может скрывать критические ошибки

---

## 🎯 ПРОБЛЕМА

### PEP 8 Violation:
```python
try:
    something()
except:  # ❌ BAD: Catches ALL exceptions including KeyboardInterrupt, SystemExit
    pass
```

**Риски:**
- Скрывает критические ошибки (KeyboardInterrupt, SystemExit, MemoryError)
- Усложняет debugging
- Нарушает PEP 8 стандарт

### Правильно:
```python
try:
    something()
except Exception as e:  # ✅ GOOD: Catches only Exception and subclasses
    logger.debug(f"Expected error: {e}")
    pass
```

---

## 📊 НАЙДЕННЫЕ СЛУЧАИ

### Production Code (исправляем):

#### 1. **core/zombie_manager.py:552** 🟢 LOW RISK
```python
try:
    await self.exchange.exchange.cancel_all_orders(
        symbol,
        params={'orderFilter': 'StopOrder'}
    )
    logger.info(f"✅ Cancelled all stop orders for {symbol}")
except:  # ❌ BAD
    pass  # Not all exchanges support this
```

**Исправление:**
```python
except Exception as e:  # ✅ GOOD
    logger.debug(f"Exchange doesn't support stop order filter: {e}")
```

**Обоснование:** Не все биржи поддерживают orderFilter, ошибка ожидаема

---

#### 2. **websocket/signal_client.py:323** 🔴 HIGH RISK
```python
try:
    await self.ws.send(json.dumps({
        'type': 'ping'
    }))
    return True
except:  # ❌ BAD
    self.state = ConnectionState.DISCONNECTED
    return False
```

**Исправление:**
```python
except (ConnectionError, websockets.exceptions.WebSocketException, Exception) as e:  # ✅ GOOD
    logger.warning(f"Ping failed: {e}")
    self.state = ConnectionState.DISCONNECTED
    return False
```

**Обоснование:** WebSocket может упасть по разным причинам, нужно их логировать

---

#### 3. **utils/process_lock.py:166** 🟡 MEDIUM RISK
```python
try:
    parts = line.strip().split(':')
    if len(parts) >= 2:
        pid = int(parts[1])
        if pid != current_pid:
            count += 1
except:  # ❌ BAD
    pass
```

**Исправление:**
```python
except (ValueError, IndexError) as e:  # ✅ GOOD
    logger.debug(f"Malformed lock file line: {line.strip()}: {e}")
```

**Обоснование:** Файл может быть повреждён, нужно логировать

---

#### 4. **core/exchange_manager_enhanced.py:437** 🟢 LOW RISK
```python
try:
    market = self.exchange.market(symbol)
    return float(market.get('limits', {}).get('amount', {}).get('min', 0.001))
except:  # ❌ BAD
    # Default minimums
    if 'BTC' in symbol:
        return 0.001
```

**Исправление:**
```python
except (KeyError, AttributeError, ValueError, Exception) as e:  # ✅ GOOD
    logger.debug(f"Failed to get min amount for {symbol}: {e}. Using defaults")
    # Default minimums
    if 'BTC' in symbol:
        return 0.001
```

**Обоснование:** market() может не вернуть данные, или структура другая

---

### Tools/Diagnostics (низкий приоритет, но исправим):

#### 5. **tools/diagnostics/verify_progress.py** 🟢 LOW RISK
Diagnostic tool, но лучше исправить для примера

#### 6. **tools/diagnostics/check_bybit_direct.py** 🟢 LOW RISK
Debug tool, можно оставить или исправить

#### 7. **database/apply_migrations.py** 🟡 MEDIUM RISK
Migration tool, лучше исправить

#### 8. **tests/integration/live_monitor.py** 🟢 LOW RISK
Test file, низкий приоритет

---

### Markdown документы (НЕ исправляем):
- DEEP_RESEARCH_RACE_CONDITION.md
- AUDIT_FIX_PLAN.md
- FINAL_COMPREHENSIVE_AUDIT_REPORT.md
- WEBSOCKET_AND_CORE_DETAILED_AUDIT.md
- SIGNAL_PROCESSOR_DETAILED_AUDIT.md
- LEVERAGE_MANAGER_DETAILED_AUDIT.md

---

## 🔧 ПЛАН ИСПРАВЛЕНИЯ

### Приоритет 1: Core Production Code (сегодня)
1. ✅ zombie_manager.py:552 (5 мин)
2. ✅ signal_client.py:323 (10 мин)
3. ✅ process_lock.py:166 (5 мин)
4. ✅ exchange_manager_enhanced.py:437 (5 мин)

**Время:** 25 минут

### Приоритет 2: Tools (опционально)
5. [ ] verify_progress.py
6. [ ] check_bybit_direct.py
7. [ ] apply_migrations.py
8. [ ] live_monitor.py

**Время:** 20 минут (если делаем)

---

## ✅ КРИТЕРИИ УСПЕХА

- ✅ Все bare except заменены на конкретные исключения
- ✅ Добавлено логирование (logger.debug/warning)
- ✅ Syntax check PASS
- ✅ Health check PASS
- ✅ No regressions (тесты проходят)

---

## 🧪 ТЕСТИРОВАНИЕ

### После каждого исправления:
```bash
# Syntax check
python3 -m py_compile <file>

# Import check
python3 -c "from core import zombie_manager"

# Health check
python3 tests/integration/health_check_after_fix.py
```

### Финальная проверка:
```bash
# Убедиться что bare except остались только в markdown
grep -r "except:" --include="*.py" | grep -v "except Exception" | grep -v "except ("
```

---

## 📋 ЧЕКЛИСТ

### Phase 3.1.1: zombie_manager.py
- [ ] Заменить bare except на Exception
- [ ] Добавить logger.debug
- [ ] Syntax check PASS
- [ ] Git commit

### Phase 3.1.2: signal_client.py
- [ ] Заменить на WebSocket exceptions
- [ ] Добавить logger.warning
- [ ] Syntax check PASS
- [ ] Git commit

### Phase 3.1.3: process_lock.py
- [ ] Заменить на ValueError, IndexError
- [ ] Добавить logger.debug
- [ ] Syntax check PASS
- [ ] Git commit

### Phase 3.1.4: exchange_manager_enhanced.py
- [ ] Заменить на конкретные исключения
- [ ] Добавить logger.debug
- [ ] Syntax check PASS
- [ ] Git commit

### Final:
- [ ] Health check PASS
- [ ] Merge в fix/critical-position-sync-bug
- [ ] Update AUDIT_FIX_PROGRESS.md

---

**Дата:** 2025-10-09
**Статус:** 🔄 READY TO START
**Estimated Time:** 25-45 минут
