# ДЕТАЛЬНЫЙ ПЛАН ПРИМЕНЕНИЯ ПРАВОК v2.0
**С ГЛУБОКИМ АНАЛИЗОМ ВЛИЯНИЯ И МАКСИМАЛЬНОЙ БЕЗОПАСНОСТЬЮ**

**Создан:** 2025-10-09
**Версия:** 2.0
**Всего фаз:** 6
**Ожидаемое время:** 32 часа работы + 72 часа мониторинга

---

## 🎯 ПРИНЦИПЫ БЕЗОПАСНОСТИ

### 1. Анализ влияния перед КАЖДЫМ изменением:
- ❓ Какие модули зависят от изменяемого кода?
- ❓ Какие модули вызывают этот метод?
- ❓ Может ли это сломать работающий функционал?
- ❓ Как это повлияет на открытые позиции?
- ❓ Может ли это привести к финансовым потерям?

### 2. Проверки на КАЖДОМ шаге:
- ✅ Syntax check - код компилируется
- ✅ Import check - все импорты работают
- ✅ Health check - базовый функционал работает
- ✅ Integration test - взаимодействие с другими модулями
- ✅ Testnet test - реальные операции на testnet
- ✅ DB consistency - БД в корректном состоянии

### 3. Точки отката на КАЖДОМ этапе:
- 💾 Git commit после каждого успешного изменения
- 💾 DB snapshot перед критичными изменениями БД
- 💾 State backup перед изменениями stateful компонентов

---

## 🔴 ФАЗА 0: ПОДГОТОВКА (3 часа)

### Шаг 0.1: Анализ зависимостей всех модулей

**ЦЕЛЬ:** Понять граф зависимостей перед изменениями

**Создать:**
```bash
tools/diagnostics/analyze_dependencies.py
DEPENDENCY_GRAPH.txt
```

**Что делает:**
- Находит все файлы которые импортируют критичные модули
- Строит граф зависимостей
- Помогает понять влияние изменений

**Критерий успеха:**
- ✅ Скрипт создан и запустился
- ✅ DEPENDENCY_GRAPH.txt создан
- ✅ Понятно какие модули зависят от изменяемых файлов

**Время:** 30 минут

---

### Шаг 0.2: Создать полный backup

**Что создать:**
1. Backup monitoring схемы (НЕ всей БД!)
2. Git snapshot
3. .env backup
4. restore_from_backup.sh скрипт

**Команды:**
```bash
# Backup БД
PGPASSWORD="LohNeMamont@!21" pg_dump -h localhost -p 5433 -U elcrypto -d fox_crypto \
  --schema=monitoring \
  --file=backup_monitoring_$(date +%Y%m%d_%H%M%S).sql

# Git snapshot
git checkout -b fix/audit-fixes-phase-1
git add -A
git commit -m "📸 Snapshot before audit fixes"

# .env backup
cp .env .env.backup_$(date +%Y%m%d_%H%M%S)

# Restore script
# [создать tools/emergency/restore_from_backup.sh]
```

**Критерий успеха:**
- ✅ Backup БД > 0 bytes
- ✅ Git commit создан
- ✅ .env backup создан
- ✅ restore_from_backup.sh создан и executable

**Критерий STOP:**
- ❌ Если backup НЕ создался - НЕ ПРОДОЛЖАТЬ!

**Время:** 30 минут

---

### Шаг 0.3: Создать testnet окружение

**Что создать:**
1. БД fox_crypto_test
2. Схема monitoring в testnet БД
3. .env.testnet с testnet API keys

**Команды:**
```bash
# Create DB
PGPASSWORD="LohNeMamont@!21" psql -h localhost -p 5433 -U elcrypto -d postgres -c "
CREATE DATABASE fox_crypto_test OWNER elcrypto;
"

# Create schema
PGPASSWORD="LohNeMamont@!21" psql -h localhost -p 5433 -U elcrypto -d fox_crypto_test -c "
CREATE SCHEMA IF NOT EXISTS monitoring;
"

# Create .env.testnet
# [заполнить с testnet API keys]
```

**Критерий успеха:**
- ✅ БД fox_crypto_test создана
- ✅ Схема monitoring создана в testnet БД
- ✅ .env.testnet создан
- ✅ Testnet API keys добавлены

**Время:** 45 минут (включая получение testnet keys)

---

### Шаг 0.4: Создать comprehensive health check

**Файл:** tests/integration/health_check_after_fix.py

**Что проверяет:**
1. Импорты всех критичных модулей
2. Database connection
3. Decimal utils работают
4. Exchange manager инициализируется
5. Models.py использует правильную схему
6. Repository SQL injection protection (когда добавим)
7. CryptoManager random salt (когда исправим)

**Критерий успеха:**
- ✅ Скрипт запускается
- ✅ Базовые тесты (imports, database) проходят
- ✅ Warnings для еще не исправленных issue - OK

**Критерий STOP:**
- ❌ Если базовые тесты НЕ проходят - разобраться ПЕРЕД продолжением!

**Время:** 1 час

---

## 🔴 ФАЗА 1: КРИТИЧНЫЕ БЕЗОПАСНОСТЬ (8 часов)

### Шаг 1.1: Исправить баг schema в models.py

**Файл:** database/models.py:161

**Проблема:**
- Строка 99: `__table_args__ = {'schema': 'monitoring'}`
- Строка 161: `{'schema': 'trading'}` - ПЕРЕОПРЕДЕЛЯЕТ!

**Изменение:**
```python
# BEFORE (line 161):
{'schema': 'trading'}

# AFTER:
{'schema': 'monitoring'}
```

**Влияние:**
- ✅ Низкий риск - все SQL уже используют monitoring
- ✅ Не требует миграции БД
- ✅ Align model с actual usage

**Проверки:**
1. Syntax check
2. Import check
3. Schema verification (runtime='monitoring')
4. Health check

**Branch:** fix/models-schema-bug

**Время:** 30 минут

---

### Шаг 1.2: Исправить SQL Injection в repository.py

**Файл:** database/repository.py:533-569

**Проблема:**
```python
for key, value in kwargs.items():
    set_clauses.append(f"{key} = ${param_count}")  # ❌ SQL INJECTION
```

**Решение:**
1. Найти все вызовы update_position в коде
2. Создать ALLOWED_POSITION_FIELDS whitelist (30+ полей)
3. Валидировать field names перед SQL

**Влияние:**
- ⚠️ ВЫСОКИЙ РИСК - метод вызывается из многих модулей
- ⚠️ Может сломать если добавим whitelist
- ✅ Но защищает от SQL injection

**Проверки:**
1. Анализ всех вызовов update_position
2. Syntax + Import check
3. Valid field update test
4. SQL injection blocked test
5. Integration test - все модули работают
6. Health check

**Branch:** fix/sql-injection-repository

**Время:** 2 часа

---

### Шаг 1.3: Исправить Fixed Salt в crypto_manager.py

**Файл:** utils/crypto_manager.py:58

**Проблема:**
```python
salt=b'trading_bot_salt'  # ❌ FIXED SALT
```

**Решение:**
```python
self.salt = os.urandom(16)  # ✅ RANDOM SALT
```

**КРИТИЧНО:**
- 🔴 Проверить наличие encrypted данных в БД ПЕРЕД изменением!
- 🔴 Если есть - нужна миграция!

**Проверки:**
1. Поиск encrypted данных в БД
2. Проверка использования CryptoManager
3. Random salt test
4. Health check

**Branch:** fix/crypto-manager-salt

**Время:** 1.5 часа (или 3 часа если нужна миграция)

---

### Шаг 1.4: Добавить Rate Limiters (8 методов)

**Файл:** core/exchange_manager.py

**Методы:**
1. cancel_order (line 690)
2. create_trailing_stop_order (line 673)
3. cancel_all_orders (line 703, 707)
4. fetch_order (line 720)
5. fetch_open_orders (line 738, 740)
6. fetch_closed_order (line 779, 786)

**СТРАТЕГИЯ: ПО ОДНОМУ МЕТОДУ ЗА РАЗ!**

**Для КАЖДОГО метода:**
1. Отдельный branch
2. Wrap в rate_limiter.execute_request()
3. Syntax + Import + Health check
4. Testnet test
5. Commit + Merge

**Влияние:**
- ⚠️ Может замедлить операции
- ✅ Защищает от 429 ban

**Время:** 2 часа (по 15 мин на метод)

---

## 🟠 ФАЗА 2: КРИТИЧНЫЕ ФУНКЦИОНАЛ (10 часов)

### Шаг 2.1: Реализовать emergency_liquidation

**⚠️ МАКСИМАЛЬНЫЙ РИСК - МОЖЕТ ЗАКРЫТЬ РЕАЛЬНЫЕ ПОЗИЦИИ!**

**Файл:** core/risk_manager.py:208-211

**Текущий код:**
```python
# This would actually close the position
# For now, just mark as closed  # ❌ STUB!
position.status = 'closed'
```

**Новая реализация:**
1. Cancel all stop orders
2. Close position via market order (reduceOnly)
3. Fallback to direct API
4. Update database
5. Record risk event

**Влияние:**
- 🔴 КРИТИЧНО - margin call protection
- 🔴 Если НЕ работает → потеря всех средств
- 🔴 Если работает неправильно → может закрыть прибыльную позицию

**Проверки:**
1. Анализ когда вызывается
2. Design реализации
3. Create test position на TESTNET
4. Execute emergency_liquidation
5. Manual verification (7 пунктов)
6. Extensive logging

**TESTNET ONLY:**
- ✅ Testnet testing обязателен
- ❌ НЕ merge на mainnet до 7 дней testnet мониторинга

**Branch:** fix/emergency-liquidation

**Время:** 4 часа

---

### Шаг 2.2: Создать safe_decimal() helper

**Файл:** utils/decimal_utils.py (новая функция)

**Что делает:**
```python
def safe_decimal(value, default=Decimal('0'), field_name="value"):
    """Безопасное преобразование в Decimal с обработкой ошибок"""
```

**Проверки:**
1. Unit tests (valid inputs)
2. Unit tests (invalid inputs)
3. Logging работает

**Время:** 1 час

---

### Шаг 2.3: Заменить unsafe float() на safe_decimal()

**ПО ОДНОМУ ФАЙЛУ ЗА РАЗ!**

**Файлы (по порядку):**
1. aged_position_manager.py (11 вызовов)
2. signal_processor_websocket.py (8 вызовов)
3. position_manager.py (7 вызовов)
4. balance_checker.py (5 вызовов)
5. trailing_stop.py (7 вызовов)

**Для КАЖДОГО файла:**
1. Найти все float()
2. Заменить по одному
3. Health check после КАЖДОЙ замены
4. Testnet test после ВСЕХ замен в файле
5. Commit

**Время:** 3 часа (по 30-40 мин на файл)

---

## 🟡 ФАЗА 3: HIGH ПРИОРИТЕТ (6 часов)

### Шаг 3.1: Исправить bare except (6 файлов)

**По одному файлу:**
1. websocket/signal_client.py (line 322)
2. websocket/binance_stream.py (line 245)
3. websocket/bybit_stream.py (line 187)
4. core/position_manager.py (line 1234)
5. protection/trailing_stop.py (line 389)
6. monitoring/health_check.py (line 456)

**Изменение:**
```python
# BEFORE:
except:

# AFTER:
except Exception as e:
    logger.error(f"Error: {e}")
```

**Время:** 1.5 часа

---

### Шаг 3.2: Рефакторинг position_manager.open_position()

**⚠️ САМЫЙ ОПАСНЫЙ РЕФАКТОРИНГ - 393 строки кода!**

**Стратегия:**
1. Создать 6 helper методов (заглушки)
2. Переносить код ПО ОДНОМУ методу
3. После КАЖДОГО метода - integration test

**Методы:**
- _validate_signal
- _check_existing_position
- _prepare_order_params
- _execute_market_order
- _set_stop_loss
- _save_position

**Время:** 4 часа

---

## 🟡 ФАЗА 4: MEDIUM ПРИОРИТЕТ (6 часов)

**Группы:**
1. Missing type hints (25 issues) - 1.5 часа
2. Long methods (15 issues) - 2 часа
3. Magic numbers (20 issues) - 1 час
4. Missing docstrings (30 issues) - 1.5 часа

По одному типу issue за раз.

---

## 📊 ФАЗА 5: ФИНАЛЬНАЯ ПРОВЕРКА (4 часа)

### Шаг 5.1: Full integration test на testnet
- 24 часа работы
- 10+ позиций открыть/закрыть
- Проверить все функции

### Шаг 5.2: Code review всех изменений
- Просмотр всех коммитов
- Diff с исходным состоянием
- Manual review каждого файла

### Шаг 5.3: Performance regression test
- Сравнить до/после
- Latency не должна вырасти

---

## 🚀 ФАЗА 6: DEPLOY НА MAINNET (72 часа мониторинга)

### Шаг 6.1: Merge в main
### Шаг 6.2: Staged rollout
- Paper trading 48h
- Постепенное увеличение position size

---

## 🔄 ПРОЦЕДУРА РАБОТЫ

### Перед КАЖДЫМ шагом:
```bash
python tools/diagnostics/verify_progress.py
cat AUDIT_FIX_PLAN.md | grep -A 20 "Шаг X.Y"
```

### После КАЖДОГО шага:
```bash
python tools/diagnostics/update_progress.py "X.Y" "Description"
python tests/integration/health_check_after_fix.py
git commit -am "Step X.Y complete"
```

---

## ⚠️ КРИТЕРИИ ОТКАТА

### Автоматический откат если:
1. Health check НЕ проходит
2. Integration test НЕ проходит
3. БД corruption
4. Performance падает >20%

### Процедура отката:
```bash
pkill -f "python main.py"
bash tools/emergency/restore_from_backup.sh
python tests/integration/health_check_after_fix.py
```

---

**КОНЕЦ ПЛАНА**
