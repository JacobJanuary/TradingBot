# 🔧 TRAILING STOP FIX: ДЕТАЛЬНЫЙ ПЛАН С ТЕСТАМИ И GIT WORKFLOW

**Версия:** 1.0  
**Дата:** 2025-11-02  
**Статус:** READY FOR IMPLEMENTATION

---

## 📋 EXECUTIVE SUMMARY

**Проблема:** NameError в `load_positions_from_db()` - переменные `trailing_activation_percent` и `trailing_callback_percent` не определены.

**Решение:** Добавить загрузку параметров из БД с fallback на конфиг, аналогично методам `sync_exchange_positions()` и `open_position()`.

**Масштаб:** КРИТИЧЕСКИЙ - затрагивает ВСЕ позиции при старте бота.

**Риски:** НИЗКИЙ - изменения локализованы в одном методе, паттерн уже используется в 2 других местах.

---

## ✅ ПРОВЕРКА РЕШЕНИЯ

### 1. Анализ областей видимости переменных

**Проблемное место:** `core/position_manager.py:650-651`

```python
# ❌ ПРОБЛЕМА: переменные не определены в методе load_positions_from_db()
position_params={
    'trailing_activation_percent': trailing_activation_percent,  # NOT DEFINED!
    'trailing_callback_percent': trailing_callback_percent      # NOT DEFINED!
}
```

**Корректное использование в других методах:**

| Метод | Строки | Статус | Паттерн |
|-------|--------|--------|---------|
| `sync_exchange_positions()` | 698-716 | ✅ OK | Загрузка из БД + fallback |
| `sync_exchange_positions()` | 888-889, 925-926 | ✅ OK | Использование |
| `open_position()` | 1215-1246 | ✅ OK | Загрузка из БД + fallback |
| `open_position()` | 1332-1333, 1485-1486, 1632-1633 | ✅ OK | Использование |
| `__init__()` | 205-206 | ✅ OK | Использование config |

**Вывод:** Проблема локализована ТОЛЬКО в `load_positions_from_db()`.

---

### 2. Анализ вызовов метода

**Где вызывается `load_positions_from_db()`:**

1. `main.py:` - При старте бота
2. `core/position_synchronizer.py:` - При синхронизации позиций

**Влияние на другие модули:**

| Модуль | Влияние | Риск |
|--------|---------|------|
| `protection.trailing_stop` | ✅ НЕТ - fallback механизм работает | НИЗКИЙ |
| `database.repository` | ✅ НЕТ - метод `get_params_by_exchange_name()` уже используется | НИЗКИЙ |
| `main.py` | ✅ НЕТ - только вызов, без изменений | НЕТ |
| `position_synchronizer.py` | ✅ НЕТ - только вызов, без изменений | НЕТ |
| `aged_position_manager.py` | ✅ НЕТ - не использует trailing параметры | НЕТ |

**Вывод:** Изменения НЕ влияют на другие модули.

---

### 3. Проверка правильности решения

**Сравнение с эталонным методом `sync_exchange_positions()`:**

| Аспект | `sync_exchange_positions()` | Предложенное решение | Соответствие |
|--------|----------------------------|---------------------|--------------|
| Загрузка из БД | `get_params_by_exchange_name()` | `get_params_by_exchange_name()` | ✅ |
| Fallback на .env | `self.config.trailing_activation_percent` | `self.config.trailing_activation_percent` | ✅ |
| Группировка по exchange | ДА (уже есть loop по exchanges) | ДА (добавим группировку) | ✅ |
| Обработка ошибок | try-except с warning | try-except с warning | ✅ |
| Логирование | logger.debug для каждой биржи | logger.debug для каждой биржи | ✅ |

**Вывод:** Решение ПОЛНОСТЬЮ соответствует существующему паттерну.

---

### 4. Проверка параметров функций

**Анализ `trailing_manager.create_trailing_stop()`:**

```python
async def create_trailing_stop(
    self,
    symbol: str,
    side: str,
    entry_price: Decimal,
    quantity: Decimal,
    initial_stop: Optional[Decimal] = None,
    position_params: Optional[Dict] = None  # <-- Может быть None!
) -> TrailingStopInstance:
```

**Fallback механизм в `create_trailing_stop()` (строка 514-523):**

```python
if position_params and position_params.get('trailing_activation_percent') is not None:
    # Use per-position params
    activation_percent = Decimal(str(position_params['trailing_activation_percent']))
    callback_percent = Decimal(str(position_params.get('trailing_callback_percent', self.config.callback_percent)))
else:
    # Fallback to config
    activation_percent = self.config.activation_percent
    callback_percent = self.config.callback_percent
```

**Вывод:**
- ✅ `position_params` может быть `None` - это OK
- ✅ Fallback работает, ЕСЛИ `create_trailing_stop()` вызван успешно
- ❌ НО: NameError происходит ДО вызова → fallback не срабатывает

**Правильное решение:** Передавать корректные значения в `position_params`.

---

## 🎯 ДЕТАЛЬНЫЙ ПЛАН РЕАЛИЗАЦИИ

### ФАЗА 1: ПОДГОТОВКА (15 минут)

#### 1.1. Создать feature branch

```bash
git checkout main
git pull origin main
git checkout -b fix/trailing-stop-params-load-positions
```

#### 1.2. Создать backup

```bash
cp core/position_manager.py core/position_manager.py.BACKUP_TS_FIX_$(date +%Y%m%d_%H%M%S)
```

#### 1.3. Проверить текущее состояние

```bash
# Проверить, что бот запущен
systemctl status trading-bot

# Проверить текущие ошибки в логах
grep "Error initializing trailing stop" logs/trading_bot.log | tail -20

# Проверить активные позиции
PGPASSWORD='' psql -h localhost -U tradingbot -d tradingbot_db -c \
  "SELECT symbol, pnl_percentage, trailing_activated FROM monitoring.positions WHERE status='active';"
```

---

### ФАЗА 2: РЕАЛИЗАЦИЯ ФИКСА (30 минут)

#### 2.1. Рефакторинг: Создать helper метод

**ФАЙЛ:** `core/position_manager.py`

**ДОБАВИТЬ ПЕРЕД МЕТОДОМ `load_positions_from_db()` (около строки 380):**

```python
async def _load_trailing_params(self, exchange_name: str) -> tuple[float, float]:
    """
    Load trailing params for exchange with fallback to config
    
    DRY Pattern: Used by load_positions_from_db(), sync_exchange_positions(), open_position()
    
    Args:
        exchange_name: Exchange name ('binance', 'bybit')
    
    Returns:
        tuple: (trailing_activation_percent, trailing_callback_percent)
    """
    trailing_activation_percent = None
    trailing_callback_percent = None
    
    try:
        exchange_params = await self.repository.get_params_by_exchange_name(exchange_name)
        
        if exchange_params:
            if exchange_params.get('trailing_activation_filter') is not None:
                trailing_activation_percent = float(exchange_params['trailing_activation_filter'])
                
            if exchange_params.get('trailing_distance_filter') is not None:
                trailing_callback_percent = float(exchange_params['trailing_distance_filter'])
    
    except Exception as e:
        logger.warning(f"⚠️  Failed to load trailing params for {exchange_name}: {e}")
    
    # Fallback to config if not in DB
    if trailing_activation_percent is None:
        trailing_activation_percent = float(self.config.trailing_activation_percent)
    
    if trailing_callback_percent is None:
        trailing_callback_percent = float(self.config.trailing_callback_percent)
    
    logger.debug(
        f"📊 {exchange_name}: trailing_activation={trailing_activation_percent}%, "
        f"trailing_callback={trailing_callback_percent}%"
    )
    
    return trailing_activation_percent, trailing_callback_percent
```

**ОБОСНОВАНИЕ:**
- DRY принцип - избегаем дублирования кода
- Легко тестировать отдельно
- Унифицированная обработка ошибок

---

#### 2.2. Исправить `load_positions_from_db()`

**ФАЙЛ:** `core/position_manager.py`  
**СТРОКИ:** 618-672

**ЗАМЕНИТЬ:**

```python
# Initialize trailing stops for loaded positions
# NEW: Try to restore from DB first, otherwise create new
logger.info("🎯 Initializing trailing stops for loaded positions...")
for symbol, position in self.positions.items():
    try:
        trailing_manager = self.trailing_managers.get(position.exchange)
        if trailing_manager:
            # ... (код восстановления из БД) ...
            
            else:
                # No state in DB - create new trailing stop
                # FIX: Add timeout to prevent hanging during startup
                await asyncio.wait_for(
                    trailing_manager.create_trailing_stop(
                        symbol=symbol,
                        side=position.side,
                        entry_price=to_decimal(position.entry_price),
                        quantity=to_decimal(safe_get_attr(position, 'quantity', 'qty', 'size', default=0)),
                        position_params={
                            'trailing_activation_percent': trailing_activation_percent,  # ❌ NOT DEFINED
                            'trailing_callback_percent': trailing_callback_percent      # ❌ NOT DEFINED
                        }
                    ),
                    timeout=10.0
                )
```

**НА:**

```python
# Initialize trailing stops for loaded positions
logger.info("🎯 Initializing trailing stops for loaded positions...")

# CRITICAL FIX: Group positions by exchange and load trailing params once per exchange
positions_by_exchange = {}
for symbol, position in self.positions.items():
    if position.exchange not in positions_by_exchange:
        positions_by_exchange[position.exchange] = []
    positions_by_exchange[position.exchange].append((symbol, position))

# Process each exchange with its trailing params
for exchange_name, exchange_positions in positions_by_exchange.items():
    # Load trailing params for this exchange
    trailing_activation_percent, trailing_callback_percent = await self._load_trailing_params(exchange_name)
    
    # Initialize TS for all positions on this exchange
    for symbol, position in exchange_positions:
        try:
            trailing_manager = self.trailing_managers.get(position.exchange)
            if trailing_manager:
                # NEW: Try to restore state from database first
                # Prepare position data to avoid exchange API call during startup
                position_dict = {
                    'symbol': symbol,
                    'side': position.side,
                    'size': safe_get_attr(position, 'quantity', 'qty', 'size', default=0),
                    'entryPrice': position.entry_price
                }
                restored_ts = await trailing_manager._restore_state(symbol, position_data=position_dict)

                if restored_ts:
                    # State restored from DB - add to manager
                    trailing_manager.trailing_stops[symbol] = restored_ts
                    position.has_trailing_stop = True
                    logger.info(f"✅ {symbol}: TS state restored from DB")
                else:
                    # No state in DB - create new trailing stop
                    # FIX: Now using correctly loaded trailing params
                    await asyncio.wait_for(
                        trailing_manager.create_trailing_stop(
                            symbol=symbol,
                            side=position.side,
                            entry_price=to_decimal(position.entry_price),
                            quantity=to_decimal(safe_get_attr(position, 'quantity', 'qty', 'size', default=0)),
                            position_params={
                                'trailing_activation_percent': trailing_activation_percent,  # ✅ NOW DEFINED
                                'trailing_callback_percent': trailing_callback_percent      # ✅ NOW DEFINED
                            }
                        ),
                        timeout=10.0
                    )
                    position.has_trailing_stop = True

                    # CRITICAL FIX: Save has_trailing_stop to database for restart persistence
                    await asyncio.wait_for(
                        self.repository.update_position(
                            position.id,
                            has_trailing_stop=True
                        ),
                        timeout=5.0
                    )

                    logger.info(f"✅ {symbol}: New TS created (no state in DB)")
            else:
                logger.warning(f"⚠️ No trailing manager for exchange {position.exchange}")
        except Exception as e:
            logger.error(f"Error initializing trailing stop for {symbol}: {e}")
```

---

#### 2.3. (ОПЦИОНАЛЬНО) Рефакторить другие методы

Можно также обновить `sync_exchange_positions()` и `open_position()` для использования нового helper метода, но это ОПЦИОНАЛЬНО для данного фикса.

---

### ФАЗА 3: UNIT ТЕСТИРОВАНИЕ (30 минут)

#### 3.1. Создать unit тест для helper метода

**ФАЙЛ:** `tests/unit/test_trailing_params_loader.py`

```python
#!/usr/bin/env python3
"""Unit tests for _load_trailing_params helper"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from core.position_manager import PositionManager


@pytest.mark.asyncio
async def test_load_trailing_params_from_db():
    """Test loading trailing params from monitoring.params"""
    # Mock repository
    mock_repo = AsyncMock()
    mock_repo.get_params_by_exchange_name.return_value = {
        'trailing_activation_filter': 1.5,
        'trailing_distance_filter': 0.4
    }
    
    # Mock config
    mock_config = MagicMock()
    mock_config.trailing_activation_percent = 2.0
    mock_config.trailing_callback_percent = 0.5
    
    # Mock position manager
    pm = PositionManager(...)
    pm.repository = mock_repo
    pm.config = mock_config
    
    # Test
    activation, callback = await pm._load_trailing_params('binance')
    
    assert activation == 1.5
    assert callback == 0.4
    mock_repo.get_params_by_exchange_name.assert_called_once_with('binance')


@pytest.mark.asyncio
async def test_load_trailing_params_fallback_to_config():
    """Test fallback to config when DB returns None"""
    mock_repo = AsyncMock()
    mock_repo.get_params_by_exchange_name.return_value = {
        'trailing_activation_filter': None,
        'trailing_distance_filter': None
    }
    
    mock_config = MagicMock()
    mock_config.trailing_activation_percent = 2.0
    mock_config.trailing_callback_percent = 0.5
    
    pm = PositionManager(...)
    pm.repository = mock_repo
    pm.config = mock_config
    
    activation, callback = await pm._load_trailing_params('binance')
    
    assert activation == 2.0
    assert callback == 0.5


@pytest.mark.asyncio
async def test_load_trailing_params_error_handling():
    """Test error handling when DB query fails"""
    mock_repo = AsyncMock()
    mock_repo.get_params_by_exchange_name.side_effect = Exception("DB error")
    
    mock_config = MagicMock()
    mock_config.trailing_activation_percent = 2.0
    mock_config.trailing_callback_percent = 0.5
    
    pm = PositionManager(...)
    pm.repository = mock_repo
    pm.config = mock_config
    
    # Should not crash, should use fallback
    activation, callback = await pm._load_trailing_params('binance')
    
    assert activation == 2.0
    assert callback == 0.5
```

**ЗАПУСК:**

```bash
pytest tests/unit/test_trailing_params_loader.py -v
```

---

#### 3.2. Расширить существующий integration тест

**ФАЙЛ:** `tests/integration/test_phase3_trailing_params_from_db.py`

**ДОБАВИТЬ:**

```python
@pytest.mark.asyncio
async def test_load_positions_from_db_uses_correct_trailing_params(self, repository):
    """
    Test that load_positions_from_db() loads trailing params correctly
    
    Regression test for NameError bug
    """
    # This test would require mocking position_manager with active positions
    # Implementation depends on existing test fixtures
    pass
```

---

### ФАЗА 4: ЛОКАЛЬНОЕ ТЕСТИРОВАНИЕ (45 минут)

#### 4.1. Статический анализ

```bash
# Проверка синтаксиса Python
python3 -m py_compile core/position_manager.py

# Линтер (если установлен)
pylint core/position_manager.py --disable=all --enable=E

# Проверка импортов
python3 -c "from core.position_manager import PositionManager"
```

#### 4.2. Тест в изолированной среде

**ВАЖНО:** НЕ тестировать на PROD боте с активными позициями!

**Вариант A: Создать тестовый скрипт**

```python
#!/usr/bin/env python3
"""Test script for trailing params fix"""
import asyncio
from core.position_manager import PositionManager
from config.settings import config
from database.repository import Repository

async def test_trailing_params_load():
    # Initialize
    repo = Repository(...)
    await repo.initialize()
    
    pm = PositionManager(config, repo, ...)
    
    # Test helper method
    activation, callback = await pm._load_trailing_params('binance')
    print(f"✅ Binance: activation={activation}%, callback={callback}%")
    
    activation, callback = await pm._load_trailing_params('bybit')
    print(f"✅ Bybit: activation={activation}%, callback={callback}%")
    
    await repo.close()

if __name__ == '__main__':
    asyncio.run(test_trailing_params_load())
```

**ЗАПУСК:**

```bash
python3 test_trailing_params.py
```

**Вариант B: Сухой прогон (dry-run)**

Временно добавить в `load_positions_from_db()`:

```python
# DRY RUN MODE - skip actual TS creation
if os.getenv('DRY_RUN_TS_FIX') == '1':
    logger.info(f"[DRY RUN] Would create TS for {symbol} with params: "
                f"activation={trailing_activation_percent}%, callback={trailing_callback_percent}%")
    continue
```

Запуск:

```bash
DRY_RUN_TS_FIX=1 python3 -c "
import asyncio
from main import TradingBot
bot = TradingBot()
asyncio.run(bot.position_manager.load_positions_from_db())
"
```

---

### ФАЗА 5: КОММИТ И ПРОВЕРКА (15 минут)

#### 5.1. Проверить изменения

```bash
git status
git diff core/position_manager.py
```

#### 5.2. Создать коммит

```bash
git add core/position_manager.py

# Если добавили helper метод
git add tests/unit/test_trailing_params_loader.py

git commit -m "fix(critical): resolve NameError in load_positions_from_db() trailing params

PROBLEM:
- Trailing Stop not created for ANY positions on bot restart
- NameError: 'trailing_activation_percent' is not defined (line 650-651)
- Affected: APEXUSDT, APTUSDT and ALL 13+ active positions

ROOT CAUSE:
- Variables used but not defined in load_positions_from_db()
- Correct pattern exists in sync_exchange_positions() and open_position()

SOLUTION:
1. Added _load_trailing_params() helper method (DRY principle)
2. Group positions by exchange before TS initialization
3. Load trailing params once per exchange from monitoring.params
4. Fallback to .env config if DB params not available

TESTING:
- Unit tests: test_trailing_params_loader.py
- Verified pattern matches sync_exchange_positions()
- No impact on other modules

RELATED:
- See: TRAILING_STOP_AUDIT_REPORT.md
- See: TRAILING_STOP_FIX_DETAILED_PLAN.md

Co-Authored-By: Deep Research Analysis <audit@tradingbot.local>"
```

---

### ФАЗА 6: STAGING ТЕСТИРОВАНИЕ (1 час)

#### 6.1. Развернуть на staging (если есть)

```bash
git push origin fix/trailing-stop-params-load-positions

# На staging сервере
git fetch origin
git checkout fix/trailing-stop-params-load-positions
```

#### 6.2. Тест с реальными данными (НО НЕ НА PROD!)

```bash
# Остановить бота
sudo systemctl stop trading-bot

# Очистить trailing_stop_state для тестов
PGPASSWORD='' psql -h localhost -U tradingbot -d tradingbot_db -c \
  "TRUNCATE monitoring.trailing_stop_state;"

# Запустить бота
sudo systemctl start trading-bot

# Проверить логи (в реальном времени)
tail -f logs/trading_bot.log | grep -i "trailing\|TS"
```

#### 6.3. Проверка результатов

```bash
# 1. Проверить, что нет ошибок
grep "Error initializing trailing stop" logs/trading_bot.log
# Должно быть: 0 результатов

# 2. Проверить, что TS создан
PGPASSWORD='' psql -h localhost -U tradingbot -d tradingbot_db -c \
  "SELECT symbol, state, activation_percent, callback_percent 
   FROM monitoring.trailing_stop_state 
   ORDER BY symbol;"
# Должно быть: записи для всех активных позиций

# 3. Проверить параметры в позициях
PGPASSWORD='' psql -h localhost -U tradingbot -d tradingbot_db -c \
  "SELECT symbol, pnl_percentage, trailing_activated, 
          trailing_activation_percent, trailing_callback_percent 
   FROM monitoring.positions 
   WHERE status='active';"
```

---

### ФАЗА 7: PRODUCTION DEPLOYMENT (30 минут)

#### 7.1. Pre-deployment checklist

```bash
# ✅ Все тесты прошли
# ✅ Staging тестирование успешно
# ✅ Backup создан
# ✅ Rollback план готов
```

#### 7.2. Создать PR и merge

```bash
# На GitHub создать Pull Request
# Описание:
# - Корневая причина
# - Решение
# - Тесты
# - Результаты staging

# После review - merge в main
git checkout main
git pull origin main
git merge --no-ff fix/trailing-stop-params-load-positions
git push origin main
```

#### 7.3. Deploy на PRODUCTION

```bash
# На production сервере
cd /home/elcrypto/TradingBot

# Создать backup БД перед изменениями
PGPASSWORD='' pg_dump -h localhost -U tradingbot tradingbot_db \
  > backup_before_ts_fix_$(date +%Y%m%d_%H%M%S).sql

# Pull latest
git fetch origin
git checkout main
git pull origin main

# Проверить версию
git log -1 --oneline

# Restart бота
sudo systemctl restart trading-bot

# Мониторинг в реальном времени
tail -f logs/trading_bot.log
```

#### 7.4. Post-deployment проверка

```bash
# Ждем 2 минуты пока бот стартанет и загрузит позиции

# Проверка 1: Нет ошибок
grep "Error initializing trailing stop" logs/trading_bot.log | tail -20
# Ожидаемый результат: 0 новых ошибок после времени перезапуска

# Проверка 2: TS созданы для всех позиций
PGPASSWORD='' psql -h localhost -U tradingbot -d tradingbot_db -c \
  "SELECT COUNT(*) as ts_count FROM monitoring.trailing_stop_state;"
# Ожидаемый результат: количество = количество активных позиций

# Проверка 3: Параметры корректны
PGPASSWORD='' psql -h localhost -U tradingbot -d tradingbot_db -c \
  "SELECT symbol, activation_percent, callback_percent 
   FROM monitoring.trailing_stop_state 
   LIMIT 5;"
# Ожидаемый результат: activation_percent и callback_percent заполнены

# Проверка 4: TS активируются при достижении порога
# Ждем позицию с pnl > activation_percent
watch -n 10 "PGPASSWORD='' psql -h localhost -U tradingbot -d tradingbot_db -c \
  \"SELECT symbol, pnl_percentage, trailing_activated 
   FROM monitoring.positions 
   WHERE status='active' AND pnl_percentage > 1.0 
   ORDER BY pnl_percentage DESC 
   LIMIT 5;\""
```

---

### ФАЗА 8: МОНИТОРИНГ (24 часа)

#### 8.1. Continuous monitoring

```bash
# Скрипт для автоматической проверки
cat > monitor_ts_health.sh << 'EOF'
#!/bin/bash
while true; do
  echo "=== $(date) ==="
  
  # Проверка ошибок
  errors=$(grep "Error initializing trailing stop" /home/elcrypto/TradingBot/logs/trading_bot.log | wc -l)
  echo "Total TS init errors: $errors"
  
  # Проверка количества активных TS
  ts_count=$(PGPASSWORD='' psql -h localhost -U tradingbot -d tradingbot_db -t -c \
    "SELECT COUNT(*) FROM monitoring.trailing_stop_state;")
  pos_count=$(PGPASSWORD='' psql -h localhost -U tradingbot -d tradingbot_db -t -c \
    "SELECT COUNT(*) FROM monitoring.positions WHERE status='active';")
  echo "Active TS: $ts_count / Positions: $pos_count"
  
  # Проверка активаций
  activated=$(PGPASSWORD='' psql -h localhost -U tradingbot -d tradingbot_db -t -c \
    "SELECT COUNT(*) FROM monitoring.trailing_stop_state WHERE state='active';")
  echo "TS Activated: $activated"
  
  sleep 600  # Каждые 10 минут
done
EOF

chmod +x monitor_ts_health.sh
./monitor_ts_health.sh &
```

#### 8.2. Алерты

Настроить уведомления (если есть система мониторинга):

```python
# Псевдокод для алертов
if ts_count < pos_count:
    alert("WARNING: TS count mismatch!")

if errors_in_last_hour > 0:
    alert("ERROR: TS initialization errors detected!")
```

---

## 🔄 ROLLBACK ПЛАН

Если что-то пошло не так:

### Быстрый откат (2 минуты)

```bash
# На production
cd /home/elcrypto/TradingBot

# Остановить бота
sudo systemctl stop trading-bot

# Откат к предыдущей версии
git log --oneline -5  # Найти commit до merge
git reset --hard <commit_hash_before_merge>

# Или восстановить из backup файла
cp core/position_manager.py.BACKUP_TS_FIX_* core/position_manager.py

# Запустить бота
sudo systemctl start trading-bot

# Проверить
tail -f logs/trading_bot.log
```

### Откат БД (если нужно)

```bash
# Если были изменения в БД (в нашем случае НЕТ)
PGPASSWORD='' psql -h localhost -U tradingbot tradingbot_db \
  < backup_before_ts_fix_*.sql
```

---

## 📊 SUCCESS CRITERIA

Фикс считается успешным, если:

✅ **КРИТИЧЕСКИЕ МЕТРИКИ:**
1. Нет ошибок `"Error initializing trailing stop"` в логах после перезапуска
2. Количество записей в `trailing_stop_state` = количество активных позиций
3. Все позиции имеют `trailing_activation_percent` и `trailing_callback_percent`

✅ **ФУНКЦИОНАЛЬНЫЕ МЕТРИКИ:**
4. TS активируется когда pnl_percentage > activation_percent
5. TS обновляет stop_loss_price при росте цены (для long)
6. TS срабатывает при откате от пика

✅ **ПРОИЗВОДИТЕЛЬНОСТЬ:**
7. Время запуска бота не увеличилось значительно (< +5%)
8. Нет зависаний при `load_positions_from_db()`

---

## 🎯 RISK ASSESSMENT

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Ошибка в helper методе | НИЗКАЯ | ВЫСОКОЕ | Unit тесты, staging тест |
| Несовместимость с БД | ОЧЕНЬ НИЗКАЯ | СРЕДНЕЕ | Метод уже используется в других местах |
| Производительность (группировка) | НИЗКАЯ | НИЗКОЕ | Оптимизация - 1 запрос на exchange |
| Откат срабатывает некорректно | НИЗКАЯ | ВЫСОКОЕ | Backup + git reset |
| TS не активируется после фикса | ОЧЕНЬ НИЗКАЯ | ВЫСОКОЕ | Staging тест с реальными данными |

---

## 📚 ДОПОЛНИТЕЛЬНЫЕ МАТЕРИАЛЫ

**Создано:**
- `TRAILING_STOP_AUDIT_REPORT.md` - Детальное расследование
- `TRAILING_STOP_FIX_DETAILED_PLAN.md` - Этот документ

**Существующие тесты:**
- `tests/integration/test_phase3_trailing_params_from_db.py`
- `tests/unit/test_entry_price_fix.py`

**Документация:**
- `docs/SL_TS_PARAMS_MIGRATION_RESEARCH_SUMMARY.md`
- `docs/PARAMS_MIGRATION_VERIFICATION_GUIDE.md`

---

## ✅ FINAL CHECKLIST

Перед началом работы:

- [ ] Прочитан TRAILING_STOP_AUDIT_REPORT.md
- [ ] Прочитан этот план полностью
- [ ] Создан backup текущего кода
- [ ] Создан backup БД
- [ ] Есть доступ к staging/тестовой среде
- [ ] Rollback план понятен
- [ ] Команда в курсе (если есть)

После каждой фазы:

- [ ] Фаза 1: Подготовка завершена
- [ ] Фаза 2: Код реализован и проверен
- [ ] Фаза 3: Unit тесты написаны и прошли
- [ ] Фаза 4: Локальное тестирование успешно
- [ ] Фаза 5: Коммит создан с правильным сообщением
- [ ] Фаза 6: Staging тестирование успешно
- [ ] Фаза 7: Production deployment завершен
- [ ] Фаза 8: Мониторинг настроен

---

**ВАЖНО:** Этот план разработан для безопасного исправления критической ошибки. Следуйте всем фазам последовательно. При любых сомнениях - ОСТАНОВИТЕСЬ и проконсультируйтесь.

**Удачи с фиксом!** 🚀

---

*План создан: 2025-11-02*  
*Версия: 1.0*  
*Автор: Deep Research Analysis*
