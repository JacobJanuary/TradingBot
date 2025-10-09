# Phase 5: Testnet Integration Testing Plan

**Дата:** 2025-10-09
**Статус:** 🔄 IN PROGRESS
**Цель:** Проверить все изменения Phases 0-4 на testnet перед mainnet deployment

---

## 🎯 SCOPE

Протестировать **все 21 выполненную задачу** из Phases 0-4:
- ✅ Phase 0: Подготовка (4/4)
- ✅ Phase 1: КРИТИЧНЫЕ БЕЗОПАСНОСТЬ (4/4)
- 🔄 Phase 2: КРИТИЧНЫЕ ФУНКЦИОНАЛ (2/3 - 2.1 отложена)
- ✅ Phase 3: HIGH ПРИОРИТЕТ (2/2)
- ✅ Phase 4: MEDIUM ПРИОРИТЕТ (4/4)

---

## 📋 TEST PLAN

### STAGE 1: Environment Verification (30 min)

**Цель:** Убедиться, что testnet окружение готово

#### 1.1 Database Check
- [ ] PostgreSQL testnet DB доступна (fox_crypto_test)
- [ ] Schema 'monitoring' существует
- [ ] Все таблицы созданы
- [ ] Миграции применены

**Commands:**
```bash
psql -h localhost -p 5433 -U elcrypto -d fox_crypto_test -c "\dt monitoring.*"
```

#### 1.2 API Keys Check
- [ ] Bybit testnet API keys настроены
- [ ] Binance testnet API keys настроены (если используется)
- [ ] API calls работают

**Test:**
```python
# Запустить простой тест подключения
python3 -c "from core.exchange_manager import ExchangeManager; print('OK')"
```

#### 1.3 Configuration Check
- [ ] .env.testnet правильно настроен
- [ ] Все константы из Phase 4.2 загружаются
- [ ] Health check проходит

**Commands:**
```bash
python3 tests/integration/health_check_after_fix.py
```

**Expected:** 14/18 PASS (стабильный результат)

---

### STAGE 2: Phase 1 Verification - КРИТИЧНЫЕ БЕЗОПАСНОСТЬ (1 hour)

#### 2.1 SQL Injection Protection Test

**What:** Проверить, что ALLOWED_POSITION_FIELDS блокирует инъекции

**Test Steps:**
1. Попытка обновить position с недопустимым полем
2. Ожидаемый результат: ValueError

**Code:**
```python
from database.repository import TradingRepository

# Should FAIL with ValueError
try:
    await repo.update_position(123, **{"malicious_field; DROP TABLE": "value"})
    print("❌ FAILED: SQL injection not blocked!")
except ValueError as e:
    print(f"✅ PASS: SQL injection blocked - {e}")
```

**Expected:** ✅ ValueError raised

---

#### 2.2 Random Salt Test

**What:** Проверить, что CryptoManager использует random salt

**Test Steps:**
1. Создать 2 экземпляра CryptoManager
2. Зашифровать одинаковые данные
3. Проверить, что ciphertext разный

**Code:**
```python
from utils.crypto_manager import CryptoManager

cm1 = CryptoManager()
cm2 = CryptoManager()

encrypted1 = cm1.encrypt("test_data")
encrypted2 = cm2.encrypt("test_data")

if encrypted1 != encrypted2:
    print("✅ PASS: Random salt working")
else:
    print("❌ FAIL: Salt is not random!")
```

**Expected:** ✅ Different ciphertexts

---

#### 2.3 Schema Test

**What:** Проверить, что Position использует schema='monitoring'

**Test Steps:**
1. Создать тестовую позицию
2. Проверить, что она в monitoring.positions

**SQL:**
```sql
SELECT schemaname, tablename FROM pg_tables WHERE tablename = 'positions';
```

**Expected:** ✅ schemaname = 'monitoring'

---

#### 2.4 Rate Limiter Test

**What:** Проверить, что rate limiters работают

**Test Steps:**
1. Вызвать exchange_manager методы с rate limiter
2. Проверить логи - должны быть записи о rate limiting
3. Проверить, что нет 429 ошибок

**Monitor:**
```bash
tail -f logs/trading_bot.log | grep -i "rate"
```

**Expected:** ✅ Rate limiter logs present, no 429 errors

---

### STAGE 3: Phase 2 Verification - safe_decimal() (30 min)

#### 3.1 safe_decimal() Test

**What:** Проверить, что safe_decimal() обрабатывает некорректные данные

**Test Cases:**
```python
from utils.decimal_utils import safe_decimal

# Valid inputs
assert safe_decimal("123.45") == Decimal("123.45")
assert safe_decimal(123.45) == Decimal("123.45")

# Invalid inputs - should return default
assert safe_decimal("invalid") == Decimal("0")
assert safe_decimal(None) == Decimal("0")
assert safe_decimal(float('inf')) == Decimal("0")
assert safe_decimal(float('nan')) == Decimal("0")

print("✅ PASS: safe_decimal() working correctly")
```

**Expected:** ✅ All assertions pass

---

#### 3.2 Float Replacement Test

**What:** Проверить, что замена float() на safe_decimal() не сломала логику

**Test Files:**
- aged_position_manager.py
- stop_loss_manager.py
- leverage_manager.py
- order_utils.py
- zombie_manager.py

**Test Steps:**
1. Импортировать каждый файл
2. Вызвать ключевые методы с edge cases
3. Проверить, что не падает с исключениями

**Expected:** ✅ No crashes, proper error handling

---

### STAGE 4: Phase 3 Verification - Refactoring (2 hours) ⚠️ КРИТИЧНО

#### 4.1 Bare Except Test

**What:** Проверить, что замена bare except не сломала error handling

**Test Files:**
- zombie_manager.py
- signal_client.py
- process_lock.py
- exchange_manager_enhanced.py

**Test Steps:**
1. Вызвать методы с ошибками
2. Проверить, что ошибки логируются
3. Проверить, что исключения правильно обрабатываются

**Expected:** ✅ Proper exception handling, logging works

---

#### 4.2 open_position() Refactoring Test ⚠️ КРИТИЧНО

**What:** Проверить, что refactored open_position() работает идентично оригиналу

**This is CRITICAL** - мы изменили 393 lines → 62 lines, нужно убедиться, что:
1. Все 6 helper методов работают
2. Locks работают корректно
3. Compensating transactions работают
4. Events эмиттятся
5. Логирование работает

**Test Plan:**

**Test 4.2.1: Normal Position Opening**
```python
request = PositionRequest(
    signal_id=1,
    symbol='BTCUSDT',
    exchange='bybit',
    side='long',
    entry_price=Decimal('50000')
)

position = await position_manager.open_position(request)

# Verify
assert position is not None
assert position.symbol == 'BTCUSDT'
assert position.side == 'long'
print("✅ PASS: Normal position opening works")
```

**Test 4.2.2: Race Condition Protection**
```python
# Open same position twice simultaneously
tasks = [
    position_manager.open_position(request),
    position_manager.open_position(request)
]
results = await asyncio.gather(*tasks)

# Verify: Only ONE position created
positions_created = [p for p in results if p is not None]
assert len(positions_created) == 1
print("✅ PASS: Race condition protection works")
```

**Test 4.2.3: Lock Cleanup**
```python
# Open and verify locks are released
position = await position_manager.open_position(request)

# Check: Locks should be released
lock_key = f"bybit_BTCUSDT"
assert lock_key not in position_manager.position_opening_locks
print("✅ PASS: Locks properly released")
```

**Test 4.2.4: Stop Loss Creation**
```python
# Verify stop loss is set
position = await position_manager.open_position(request)

assert position.has_stop_loss == True
assert position.stop_loss_price is not None
print("✅ PASS: Stop loss created")
```

**Test 4.2.5: Compensating Transaction (SL Fails)**
```python
# Mock: SL creation fails
# Expected: Position should be closed on exchange

# This is complex - may need to mock stop_loss_manager
# Or test manually by causing SL to fail
```

**Test 4.2.6: Database Persistence**
```python
# Verify position saved to DB
position = await position_manager.open_position(request)

db_position = await repository.get_position(position.id)
assert db_position is not None
assert db_position.symbol == 'BTCUSDT'
print("✅ PASS: Position persisted to DB")
```

**Manual Testing:**
- [ ] Open position on testnet
- [ ] Verify in DB: `SELECT * FROM monitoring.positions ORDER BY id DESC LIMIT 1;`
- [ ] Verify on exchange UI
- [ ] Verify stop loss exists
- [ ] Check logs for all expected messages
- [ ] Verify trailing stop initialized

**Expected:** ✅ All tests pass, no regressions

---

### STAGE 5: Phase 4 Verification - Safety Checks (1 hour)

#### 5.1 Dict Access Safety Test

**What:** Проверить, что WebSocket парсеры обрабатывают missing fields

**Test Steps:**
1. Send malformed WebSocket message (missing 'symbol')
2. Verify: No KeyError, proper logging

**Test Data:**
```python
# Missing 'symbol' field
malformed_position = {
    'side': 'Buy',
    'size': '1.0'
}

# Expected: Should log error and skip, not crash
```

**Monitor:**
```bash
tail -f logs/trading_bot.log | grep -i "missing.*field"
```

**Expected:** ✅ Error logged, no crash

---

#### 5.2 Division by Zero Test

**What:** Проверить, что price==0 check работает

**Test:**
```python
# Mock ticker with price=0
# Should return None instead of division error
```

**Expected:** ✅ No ZeroDivisionError

---

#### 5.3 Magic Numbers Test

**What:** Проверить, что extracted constants работают

**Test Steps:**
1. Verify constants are loaded
2. Test retry logic uses correct delays
3. Test WebSocket reconnection uses correct delays

**Code:**
```python
from core.position_manager import (
    MAX_ORDER_VERIFICATION_RETRIES,
    ORDER_VERIFICATION_DELAYS,
    POSITION_CLOSE_RETRY_DELAY_SEC
)

assert MAX_ORDER_VERIFICATION_RETRIES == 3
assert ORDER_VERIFICATION_DELAYS == [1.0, 2.0, 3.0]
assert POSITION_CLOSE_RETRY_DELAY_SEC == 60

print("✅ PASS: Constants loaded correctly")
```

**Expected:** ✅ All constants correct

---

### STAGE 6: Integration Test - Full Workflow (3 hours)

#### 6.1 End-to-End Position Lifecycle

**Scenario:** Complete trading cycle on testnet

**Steps:**
1. [ ] Start bot in testnet mode
2. [ ] Wait for signal (or create manual signal)
3. [ ] Verify position opens correctly
4. [ ] Monitor position updates
5. [ ] Wait for stop loss trigger or manual close
6. [ ] Verify position closes correctly
7. [ ] Check all DB records
8. [ ] Verify all events emitted

**Monitoring:**
```bash
# Terminal 1: Logs
tail -f logs/trading_bot.log

# Terminal 2: Database
watch -n 5 'psql -h localhost -p 5433 -U elcrypto -d fox_crypto_test -c "SELECT id, symbol, side, status, entry_price, current_price FROM monitoring.positions ORDER BY id DESC LIMIT 5;"'

# Terminal 3: Process
ps aux | grep python
```

**Success Criteria:**
- ✅ Position opens without errors
- ✅ Stop loss is set
- ✅ Position updates in real-time
- ✅ Position closes cleanly
- ✅ All DB records correct
- ✅ No memory leaks
- ✅ No zombie processes

---

### STAGE 7: Stress Test (2 hours)

#### 7.1 Concurrent Position Opening

**What:** Test race condition protection under load

**Test:**
```python
# Open 10 positions simultaneously
signals = [create_signal(i) for i in range(10)]
tasks = [position_manager.open_position(s) for s in signals]
results = await asyncio.gather(*tasks)

# Verify: All positions unique, no duplicates
```

**Expected:** ✅ No duplicates, all locks work

---

#### 7.2 WebSocket Reconnection Test

**What:** Test WebSocket resilience

**Test Steps:**
1. Start WebSocket connection
2. Kill connection (simulate network loss)
3. Verify: Auto-reconnects
4. Verify: No data loss

**Monitor:**
```bash
tail -f logs/trading_bot.log | grep -i "reconnect"
```

**Expected:** ✅ Reconnects successfully, no crashes

---

### STAGE 8: 24-Hour Monitoring (24 hours)

**What:** Run bot on testnet for 24 hours, monitor for:
- Memory leaks
- Crashes
- Database growth
- Performance degradation
- Error patterns

**Metrics to Track:**
```bash
# Memory usage
ps aux | grep python | awk '{print $4, $6}'

# Database size
psql -h localhost -p 5433 -U elcrypto -d fox_crypto_test -c "SELECT pg_size_pretty(pg_database_size('fox_crypto_test'));"

# Error count
grep -c "ERROR" logs/trading_bot.log

# Position count
psql -h localhost -p 5433 -U elcrypto -d fox_crypto_test -c "SELECT COUNT(*) FROM monitoring.positions;"
```

**Check Every 4 Hours:**
- [ ] Bot still running
- [ ] No critical errors
- [ ] Memory usage stable
- [ ] Database size reasonable

**Success Criteria:**
- ✅ 24 hours uptime
- ✅ <5 critical errors
- ✅ Memory growth <10%
- ✅ All positions handled correctly

---

## 📊 SUCCESS CRITERIA

### Mandatory (MUST PASS):
- ✅ Health check: 14/18 PASS
- ✅ All Phase 1-4 tests pass
- ✅ open_position() refactoring works identically
- ✅ No crashes during 24h run
- ✅ No memory leaks

### Optional (NICE TO HAVE):
- ⭐ Zero critical errors
- ⭐ <1% performance degradation
- ⭐ Clean logs (no warnings)

---

## 🚨 ROLLBACK CRITERIA

**Rollback if:**
- ❌ open_position() refactoring has bugs
- ❌ Race condition protection fails
- ❌ Crashes occur
- ❌ Data corruption in DB
- ❌ Memory leaks detected

**Rollback Process:**
1. Stop testnet bot
2. `git checkout main`
3. Restore DB from backup
4. Analyze logs
5. Fix issues
6. Re-test

---

## 📝 TEST EXECUTION LOG

**Start Time:** _TBD_
**End Time:** _TBD_
**Tester:** _TBD_

### Stage 1: Environment ⏳
- [ ] Database check
- [ ] API keys check
- [ ] Health check

### Stage 2: Phase 1 ⏳
- [ ] SQL injection test
- [ ] Random salt test
- [ ] Schema test
- [ ] Rate limiter test

### Stage 3: Phase 2 ⏳
- [ ] safe_decimal() test
- [ ] Float replacement test

### Stage 4: Phase 3 ⏳
- [ ] Bare except test
- [ ] **open_position() tests (CRITICAL)**

### Stage 5: Phase 4 ⏳
- [ ] Dict access test
- [ ] Division by zero test
- [ ] Magic numbers test

### Stage 6: Integration ⏳
- [ ] E2E workflow test

### Stage 7: Stress ⏳
- [ ] Concurrent test
- [ ] WebSocket test

### Stage 8: 24h Monitor ⏳
- [ ] Start monitoring
- [ ] 4h checkpoint 1
- [ ] 8h checkpoint 2
- [ ] 12h checkpoint 3
- [ ] 16h checkpoint 4
- [ ] 20h checkpoint 5
- [ ] 24h final

---

## 🎯 NEXT STEPS AFTER PHASE 5

**If PASS:**
- Phase 6: Mainnet Deployment Preparation
- Code review
- Performance optimization
- Documentation update

**If FAIL:**
- Fix identified issues
- Re-run failed tests
- Extended monitoring

---

**Дата создания:** 2025-10-09 23:55:00
**Автор:** Claude Code
**Версия:** 1.0
