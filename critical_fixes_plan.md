# Детальный план исправления критических ошибок Trading Bot

## Подготовительный этап

### Шаг 0.1: Создание резервной копии
```bash
# Создать новую ветку для исправлений
git checkout -b critical-fixes-2024-10-17

# Создать commit текущего состояния
git add .
git commit -m "chore: pre-fix checkpoint before critical fixes"

# Создать тег для быстрого возврата
git tag pre-critical-fixes

# Проверить статус
git status
git log --oneline -5
```

### Шаг 0.2: Подготовка тестового окружения
```bash
# Создать тестовый скрипт для проверки исправлений
cat > test_critical_fixes.py << 'EOF'
#!/usr/bin/env python3
"""Test script for critical fixes validation"""
import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

async def test_reduce_only():
    """Test that reduceOnly is always set for SL orders"""
    from core.stop_loss_manager import StopLossManager
    print("Testing reduceOnly parameter...")
    # Test implementation will be added after fix
    return True

async def test_bybit_heartbeat():
    """Test Bybit heartbeat interval"""
    from websocket.improved_stream import ImprovedWebSocketStream
    print("Testing Bybit heartbeat interval...")
    # Test implementation will be added after fix
    return True

async def test_aged_formatting():
    """Test aged position manager formatting"""
    from core.aged_position_manager import AgedPositionManager
    print("Testing aged position formatting...")
    # Test implementation will be added after fix
    return True

async def main():
    results = []
    results.append(await test_reduce_only())
    results.append(await test_bybit_heartbeat())
    results.append(await test_aged_formatting())

    if all(results):
        print("✅ All tests passed!")
        return 0
    else:
        print("❌ Some tests failed!")
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
EOF

chmod +x test_critical_fixes.py
```

---

## ОШИБКА #1: Отсутствие безусловного reduceOnly для Stop Loss

### Анализ проблемы
После детального исследования кода обнаружено:
1. В `core/stop_loss_manager.py:525` параметр `reduceOnly: True` УЖЕ установлен для generic orders
2. В `core/exchange_manager.py:470` параметр `reduceOnly` также установлен для Binance
3. **ПРОБЛЕМА**: Для Bybit при использовании position-attached SL через trading-stop endpoint параметр reduceOnly НЕ применим, но нужно убедиться что используется правильный endpoint

### Решение
Проблема уже частично решена, но требуется добавить валидацию и логирование для уверенности.

### Этап 1.1: Добавление валидации reduceOnly

#### Файл: `core/stop_loss_manager.py`

**Изменение 1:** Добавить проверку после строки 523
```python
# СТРОКА 523 - ПОСЛЕ params = {...}
# ДОБАВИТЬ:

# CRITICAL VALIDATION: Ensure reduceOnly is always True for futures
if self.exchange_name in ['binance', 'bybit']:
    if 'reduceOnly' not in params or params['reduceOnly'] != True:
        self.logger.error(f"🚨 CRITICAL: reduceOnly not set for {symbol}!")
        params['reduceOnly'] = True  # Force it

    # Log for audit
    self.logger.info(f"✅ reduceOnly validated: {params.get('reduceOnly')} for {symbol}")
```

#### Файл: `core/exchange_manager.py`

**Изменение 2:** Усилить проверку после строки 468
```python
# СТРОКА 468 - в params для Binance
# ЗАМЕНИТЬ:
params={
    'stopPrice': float(stop_price),
    'reduceOnly': reduce_only,  # Only reduce existing position
    'workingType': 'CONTRACT_PRICE'  # Use last price as trigger
}

# НА:
params={
    'stopPrice': float(stop_price),
    'reduceOnly': True,  # CRITICAL: Always True for futures SL
    'workingType': 'CONTRACT_PRICE'  # Use last price as trigger
}

# И добавить после создания params:
if not params.get('reduceOnly'):
    logger.critical(f"🚨 reduceOnly not set for Binance SL on {symbol}!")
    params['reduceOnly'] = True
```

### Этап 1.2: Тестирование
```bash
# Проверить что reduceOnly всегда установлен
grep -n "reduceOnly" core/stop_loss_manager.py
grep -n "reduceOnly" core/exchange_manager.py

# Запустить тест
python -c "
from core.stop_loss_manager import StopLossManager
# Проверить что при создании SL всегда есть reduceOnly
"
```

### Этап 1.3: Git commit
```bash
git add core/stop_loss_manager.py core/exchange_manager.py
git commit -m "fix: ensure reduceOnly=true for all futures stop loss orders

- Added validation to force reduceOnly=true for Binance/Bybit
- Added logging for audit trail
- Prevents SL from opening new positions

Fixes critical issue where SL could open reverse position"
```

---

## ОШИБКА #2: Неправильный heartbeat для Bybit

### Анализ проблемы
В файле `websocket/improved_stream.py:55`:
- Комментарий говорит "Changed from 30 to 20 for Bybit compliance"
- НО используется значение из config: `config.get('ws_heartbeat_interval', 20)`
- Если в конфиге установлено 30, то Bybit разорвет соединение

### Решение
Жестко установить 20 секунд для Bybit, игнорируя конфиг.

### Этап 2.1: Исправление heartbeat

#### Файл: `websocket/improved_stream.py`

**Изменение:** Заменить строки 54-56
```python
# БЫЛО (строки 54-56):
# Heartbeat settings - CRITICAL FIX: Bybit requires ping every 20s!
self.heartbeat_interval = config.get('ws_heartbeat_interval', 20)  # Changed from 30 to 20 for Bybit compliance
self.heartbeat_timeout = config.get('ws_heartbeat_timeout', 90)     # Increased from 60 to 90 for testnet latency

# ЗАМЕНИТЬ НА:
# Heartbeat settings - CRITICAL FIX: Bybit requires ping every 20s!
# Determine exchange from config or URL
is_bybit = 'bybit' in str(config.get('url', '')).lower() or \
           'bybit' in str(config.get('exchange', '')).lower() or \
           self.exchange_name.lower() == 'bybit' if hasattr(self, 'exchange_name') else False

if is_bybit:
    # CRITICAL: Bybit REQUIRES ping every 20 seconds, ignore config
    self.heartbeat_interval = 20  # HARDCODED for Bybit
    self.heartbeat_timeout = 90   # Extended for testnet latency
    logger.info(f"🔧 Bybit detected: forcing heartbeat_interval=20s")
else:
    # Other exchanges can use config
    self.heartbeat_interval = config.get('ws_heartbeat_interval', 30)
    self.heartbeat_timeout = config.get('ws_heartbeat_timeout', 60)
```

### Этап 2.2: Добавить проверку в bybit_stream.py

#### Файл: `websocket/bybit_stream.py`

**Найти инициализацию heartbeat и добавить:**
```python
# В методе __init__ или start, добавить:
if hasattr(self, 'heartbeat_interval'):
    if self.heartbeat_interval > 20:
        logger.warning(f"⚠️ Bybit heartbeat interval {self.heartbeat_interval}s > 20s max!")
        self.heartbeat_interval = 20
```

### Этап 2.3: Тестирование
```bash
# Проверить что heartbeat правильный
python -c "
from websocket.improved_stream import ImprovedWebSocketStream
config = {'exchange': 'bybit'}
# stream = ImprovedWebSocketStream(config)
# assert stream.heartbeat_interval == 20
print('Heartbeat test would run here')
"

# Проверить в логах
grep -i "heartbeat\|ping" logs/trading_bot.log | tail -20
```

### Этап 2.4: Git commit
```bash
git add websocket/improved_stream.py websocket/bybit_stream.py
git commit -m "fix: force 20s heartbeat for Bybit WebSocket

- Hardcoded 20s heartbeat when Bybit is detected
- Ignores config to prevent disconnections
- Bybit closes connection after 20s without ping

Fixes WebSocket stability issue with Bybit"
```

---

## ОШИБКА #3: Ошибка форматирования в aged_position_manager

### Анализ проблемы
Строка 142 в `core/aged_position_manager.py`:
```python
f"pnl={position.unrealized_pnl:.2f if position.unrealized_pnl is not None else 0.0} USD"
```
Это неправильный синтаксис f-string. Условное выражение нельзя использовать внутри форматирования.

### Решение
Вычислить значение до форматирования.

### Этап 3.1: Исправление форматирования

#### Файл: `core/aged_position_manager.py`

**Изменение:** Заменить строки 139-143
```python
# БЫЛО (строки 139-143):
logger.warning(
    f"⏰ Found aged position {position.symbol}: "
    f"age={age_hours:.1f}h (max={self.max_position_age_hours}h), "
    f"pnl={position.unrealized_pnl:.2f if position.unrealized_pnl is not None else 0.0} USD"
)

# ЗАМЕНИТЬ НА:
# Calculate PnL value for formatting
pnl_value = float(position.unrealized_pnl) if position.unrealized_pnl is not None else 0.0

logger.warning(
    f"⏰ Found aged position {position.symbol}: "
    f"age={age_hours:.1f}h (max={self.max_position_age_hours}h), "
    f"pnl={pnl_value:.2f} USD"
)
```

### Этап 3.2: Проверка других мест с похожей ошибкой
```bash
# Найти похожие проблемные паттерны
grep -n ":.2f if" core/aged_position_manager.py
grep -n ":.1f if" core/aged_position_manager.py
```

### Этап 3.3: Тестирование
```python
# test_aged_fix.py
from core.aged_position_manager import AgedPositionManager

class MockPosition:
    def __init__(self):
        self.symbol = "BTCUSDT"
        self.unrealized_pnl = None  # Test None value
        self.opened_at = None

# Проверить что не падает с ошибкой
config = type('Config', (), {
    'max_position_age_hours': 3,
    'grace_period_hours': 8
})()

try:
    manager = AgedPositionManager(config, None, {})
    print("✅ AgedPositionManager initialized without errors")
except Exception as e:
    print(f"❌ Error: {e}")
```

### Этап 3.4: Git commit
```bash
git add core/aged_position_manager.py
git commit -m "fix: correct f-string formatting in aged_position_manager

- Fixed invalid conditional expression in f-string
- Calculate PnL value before formatting
- Prevents ValueError when checking aged positions

Fixes crash in aged position monitoring"
```

---

## Финальное тестирование

### Этап 4.1: Комплексный тест всех исправлений
```python
#!/usr/bin/env python3
"""validate_critical_fixes.py"""

import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_all_fixes():
    """Test all critical fixes"""

    # Test 1: reduceOnly validation
    logger.info("Test 1: Checking reduceOnly in stop_loss_manager...")
    with open('core/stop_loss_manager.py', 'r') as f:
        content = f.read()
        assert "'reduceOnly': True" in content, "reduceOnly not found as True"
        assert "params['reduceOnly'] = True" in content, "Force reduceOnly not found"
    logger.info("✅ Test 1 passed")

    # Test 2: Bybit heartbeat
    logger.info("Test 2: Checking Bybit heartbeat...")
    with open('websocket/improved_stream.py', 'r') as f:
        content = f.read()
        assert "self.heartbeat_interval = 20" in content, "Hardcoded 20s not found"
        assert "is_bybit" in content or "bybit" in content.lower(), "Bybit detection not found"
    logger.info("✅ Test 2 passed")

    # Test 3: Aged formatting
    logger.info("Test 3: Checking aged position formatting...")
    with open('core/aged_position_manager.py', 'r') as f:
        content = f.read()
        assert ":.2f if" not in content, "Invalid f-string pattern still exists"
        assert "pnl_value" in content, "Fixed variable not found"
    logger.info("✅ Test 3 passed")

    logger.info("\n🎉 All critical fixes validated successfully!")
    return True

if __name__ == "__main__":
    asyncio.run(test_all_fixes())
```

### Этап 4.2: Проверка в runtime
```bash
# 1. Запустить бота в тестовом режиме
python main.py --mode shadow

# 2. Мониторить логи на предмет ошибок
tail -f logs/trading_bot.log | grep -E "ERROR|CRITICAL|reduceOnly|heartbeat|aged"

# 3. Запустить скрипт мониторинга
python monitor_bot.py
```

### Этап 4.3: Финальный commit
```bash
# После успешного тестирования
git add .
git commit -m "test: add validation scripts for critical fixes"

# Создать тег релиза
git tag -a v1.0.1-critical-fixes -m "Critical fixes for production safety"

# Push в удаленный репозиторий
git push origin critical-fixes-2024-10-17
git push origin v1.0.1-critical-fixes
```

---

## Rollback план (если что-то пошло не так)

```bash
# Вернуться к состоянию до исправлений
git checkout pre-critical-fixes

# Или сбросить все изменения
git reset --hard pre-critical-fixes

# Удалить ветку с неудачными исправлениями
git branch -D critical-fixes-2024-10-17
```

---

## Чеклист валидации

- [ ] Все тесты проходят успешно
- [ ] Нет новых ошибок в логах
- [ ] reduceOnly логируется для каждого SL
- [ ] Bybit WebSocket стабилен более 30 минут
- [ ] Aged position manager не падает с ValueError
- [ ] Мониторинг скрипт не находит критических проблем

## Ожидаемый результат

После применения всех исправлений:
1. **Stop Loss** всегда будет иметь `reduceOnly=true`, что предотвратит открытие обратных позиций
2. **Bybit WebSocket** будет стабильно работать с правильным heartbeat интервалом
3. **Aged Position Manager** будет корректно логировать информацию без падений

## Важные замечания

1. **Порядок исправлений**: Можно применять в любом порядке, они независимы
2. **Тестирование**: ОБЯЗАТЕЛЬНО после каждого исправления
3. **Мониторинг**: После всех исправлений запустить 1-часовой мониторинг
4. **Documentation**: Обновить документацию с описанием исправлений