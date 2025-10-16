# 🔧 ПРИОРИТИЗИРОВАННЫЙ СПИСОК ИСПРАВЛЕНИЙ

**Дата**: 2025-10-15
**Основано на**: FINAL_AUDIT_REPORT.md
**Общее время на фиксы Priority 1**: ~45 минут

---

## 🔴 PRIORITY 1: КРИТИЧНО (исправить сегодня)

### Fix #1: Price Precision в Aged Position Manager

**Severity**: HIGH
**Impact**: Aged positions не могут разместить exit orders
**ETA**: 30 минут

#### Проблема

```python
# Ошибки:
ExchangeError: "Buy order price cannot be higher than 0USDT" (170193)
ExchangeError: "price of ETHBTC/USDT must be greater than minimum price precision of 0.000001"
ExchangeError: "price of SAROS/USDT must be greater than minimum price precision of 0.00001"
```

Причина: `round()` может дать цену < `min_price_precision` или 0.

#### Решение

**Файл**: `core/exchange_manager_enhanced.py`

**ШАГ 1: Добавить функцию** (после imports, строка ~10):

```python
import math
from decimal import Decimal

def apply_price_precision(price: Decimal, min_precision: Decimal, direction: str = 'up') -> Decimal:
    """
    Apply price precision with proper rounding

    Args:
        price: Target price (Decimal)
        min_precision: Minimum price step from exchange (Decimal)
        direction: 'up' (ceil) or 'down' (floor)

    Returns:
        Decimal: Price rounded to valid precision, always >= min_precision

    Examples:
        >>> apply_price_precision(Decimal('0.0000008'), Decimal('0.000001'), 'up')
        Decimal('0.000001')

        >>> apply_price_precision(Decimal('0.123456'), Decimal('0.0001'), 'up')
        Decimal('0.1235')
    """
    if price <= 0:
        return min_precision

    if price < min_precision:
        return min_precision

    # Calculate number of precision steps
    steps = price / min_precision

    if direction == 'up':
        steps = math.ceil(float(steps))
    else:
        steps = math.floor(float(steps))

    result = Decimal(str(min_precision)) * Decimal(str(steps))

    # Ensure result >= min_precision
    return max(result, min_precision)
```

**ШАГ 2: Использовать в `create_or_update_exit_order()`** (строка ~100):

Найти блок где создается ордер:
```python
# ПЕРЕД этим кодом:
order = await self.exchange.create_order(
    symbol=symbol,
    type='limit',
    side=side,
    amount=amount,
    price=price,  # ← ЗДЕСЬ
    params=params
)
```

Добавить:
```python
# ДОБАВИТЬ ДО create_order:

# Get symbol info for precision
await self.exchange.load_markets()
market_info = self.exchange.markets.get(symbol)

if not market_info:
    raise ValueError(f"Market info not found for {symbol}")

# Extract price precision
min_price_precision = Decimal(str(market_info['precision']['price']))

# Apply precision with ceil (always round UP to ensure valid price)
price_decimal = Decimal(str(price))
price_decimal = apply_price_precision(price_decimal, min_price_precision, direction='up')
price = float(price_decimal)

logger.debug(f"Applied price precision for {symbol}: {price} (min_precision={min_price_precision})")

# NOW create order with validated price
order = await self.exchange.create_order(
    symbol=symbol,
    type='limit',
    side=side,
    amount=amount,
    price=price,  # ← Теперь всегда валидная цена
    params=params
)
```

#### Тестирование

```bash
# 1. Проверить что изменения не ломают существующую логику
python3 -c "
from core.exchange_manager_enhanced import apply_price_precision
from decimal import Decimal

# Test 1: Price too small
result = apply_price_precision(Decimal('0.0000008'), Decimal('0.000001'), 'up')
assert result == Decimal('0.000001'), f'Expected 0.000001, got {result}'

# Test 2: Normal rounding
result = apply_price_precision(Decimal('0.123456'), Decimal('0.0001'), 'up')
assert result == Decimal('0.1235'), f'Expected 0.1235, got {result}'

# Test 3: Already at precision
result = apply_price_precision(Decimal('0.0001'), Decimal('0.0001'), 'up')
assert result == Decimal('0.0001'), f'Expected 0.0001, got {result}'

print('✅ All tests passed')
"

# 2. Запустить бота на 5 минут и проверить что aged positions работают
python3 main.py --mode production
# Ждать 5 минут, проверить логи на ошибки 170193
```

---

### Fix #2: JSON Serialization в Event Logger

**Severity**: MEDIUM (высокий приоритет из-за количества ошибок)
**Impact**: ~60,000 ошибок в логах, засоряют мониторинг
**ETA**: 15 минут

#### Проблема

```python
TypeError: Object of type Decimal is not JSON serializable
```

Причина: `json.dumps()` не умеет сериализовать `Decimal` объекты.

#### Решение

**Файл**: `core/event_logger.py`

**ШАГ 1: Добавить encoder** (после imports, строка ~5):

```python
import json
from decimal import Decimal

class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder for Decimal and other special types"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            # Convert Decimal to float for JSON
            return float(obj)
        # Let the base class handle other types
        return super().default(obj)
```

**ШАГ 2: Найти все вызовы `json.dumps()`** и заменить:

```python
# БЫЛО:
json.dumps(data)

# СТАЛО:
json.dumps(data, cls=DecimalEncoder)
```

**Locations** (примерно):
- Строка ~150: в `log_event()`
- Строка ~200: в `_serialize_event()`
- Любые другие места где используется `json.dumps()`

Можно использовать find/replace:
```bash
# В редакторе или через sed:
sed -i '' 's/json.dumps(\([^)]*\))/json.dumps(\1, cls=DecimalEncoder)/g' core/event_logger.py
```

#### Тестирование

```python
# test_decimal_encoder.py
from core.event_logger import DecimalEncoder
from decimal import Decimal
import json

# Test data with Decimal
data = {
    'symbol': 'BTCUSDT',
    'price': Decimal('50000.123456'),
    'amount': Decimal('0.001'),
    'pnl': Decimal('-123.45')
}

# Should not raise TypeError
result = json.dumps(data, cls=DecimalEncoder)
print(f"✅ Serialized: {result}")

# Verify values
parsed = json.loads(result)
assert parsed['price'] == 50000.123456
assert parsed['amount'] == 0.001
assert parsed['pnl'] == -123.45

print("✅ All tests passed")
```

---

### Fix #3: Log Rotation

**Severity**: MEDIUM
**Impact**: Лог файл 928 MB, медленное чтение
**ETA**: 10 минут

#### Проблема

Лог файл растет без ограничений:
- Текущий размер: 928 MB
- Строк: 8,069,838
- Поиск по логам медленный

#### Решение

**Файл**: `main.py`

**ШАГ 1: Заменить logging setup** (строки 28-35):

```python
# БЫЛО:
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/trading_bot.log'),
        logging.StreamHandler()
    ]
)

# СТАЛО:
from logging.handlers import RotatingFileHandler

# Create rotating file handler
file_handler = RotatingFileHandler(
    'logs/trading_bot.log',
    maxBytes=100 * 1024 * 1024,  # 100 MB per file
    backupCount=10,  # Keep 10 backup files (1 GB total)
    encoding='utf-8'
)

# Create console handler
console_handler = logging.StreamHandler()

# Set format for both
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, console_handler]
)

logger.info("✅ Logging configured with rotation: 100MB × 10 files = 1GB max")
```

**Результат**:
- Основной файл: `trading_bot.log` (max 100 MB)
- Backup файлы: `trading_bot.log.1`, `trading_bot.log.2`, ..., `trading_bot.log.10`
- Автоматическая ротация при достижении 100 MB
- Старые файлы удаляются после 10 ротаций

#### Тестирование

```bash
# 1. Запустить бота
python3 main.py --mode production

# 2. Проверить что логи пишутся
tail -f logs/trading_bot.log

# 3. Проверить что ротация настроена
ls -lh logs/trading_bot.log*
# Должен быть только trading_bot.log (новый, маленький)

# 4. При достижении 100 MB проверить что создается .log.1
```

---

## 🟡 PRIORITY 2: ВЫСОКИЙ (исправить завтра)

### Fix #4: Добавить недостающие log patterns

**Severity**: LOW
**Impact**: Monitoring script не видит некоторые события
**ETA**: 20 минут

#### Проблема

В production test monitor показал:
- `SL moves: 0` (но мы знаем что TS двигал SL)

Возможные причины:
1. Паттерн логирования другой
2. Логирование отсутствует

#### Решение

**Файл**: `protection/trailing_stop.py`

**Проверить строки 411-414**:
```python
logger.info(
    f"📈 {ts.symbol}: Trailing stop updated from {old_stop:.4f} to {new_stop_price:.4f} "
    f"(+{improvement:.2f}%)"
)
```

**Добавить explicit "SL moved"**:
```python
logger.info(
    f"📈 {ts.symbol}: SL moved from {old_stop:.4f} to {new_stop_price:.4f} "
    f"(+{improvement:.2f}% improvement)"
)
```

**Также проверить**:
- `_update_stop_order()` (строка 648) - логирует ли успешное обновление?

---

### Fix #5: Dashboard для Aged Positions

**Severity**: LOW
**Impact**: Нет визуализации aged positions
**ETA**: 2-4 часа

#### Создать простой HTML dashboard

**Файл**: `dashboard/aged_positions.html`

```html
<!DOCTYPE html>
<html>
<head>
    <title>Aged Positions Dashboard</title>
    <meta http-equiv="refresh" content="30">
    <style>
        body { font-family: Arial; margin: 20px; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #4CAF50; color: white; }
        .grace { background-color: #fff3cd; }
        .progressive { background-color: #f8d7da; }
        .emergency { background-color: #dc3545; color: white; }
    </style>
</head>
<body>
    <h1>Aged Positions</h1>
    <p>Last updated: <span id="timestamp"></span></p>
    <table id="positions">
        <thead>
            <tr>
                <th>Symbol</th>
                <th>Age (hours)</th>
                <th>Phase</th>
                <th>Entry Price</th>
                <th>Current Price</th>
                <th>Target Exit</th>
                <th>Loss Tolerance</th>
                <th>PnL</th>
            </tr>
        </thead>
        <tbody id="data">
            <!-- Data populated by aged_dashboard.py -->
        </tbody>
    </table>

    <script>
        // Auto-refresh timestamp
        document.getElementById('timestamp').textContent = new Date().toLocaleString();

        // Fetch data from API
        fetch('/api/aged_positions')
            .then(response => response.json())
            .then(data => {
                const tbody = document.getElementById('data');
                tbody.innerHTML = data.positions.map(pos => `
                    <tr class="${pos.phase_class}">
                        <td>${pos.symbol}</td>
                        <td>${pos.age_hours}</td>
                        <td>${pos.phase}</td>
                        <td>${pos.entry_price}</td>
                        <td>${pos.current_price}</td>
                        <td>${pos.target_exit}</td>
                        <td>${pos.loss_tolerance}%</td>
                        <td>${pos.pnl}</td>
                    </tr>
                `).join('');
            });
    </script>
</body>
</html>
```

**Создать API endpoint**: `dashboard/aged_dashboard.py`

```python
from fastapi import FastAPI
from typing import List, Dict
import asyncio

app = FastAPI()

@app.get("/api/aged_positions")
async def get_aged_positions() -> Dict:
    """Get current aged positions"""
    # Get from position_manager
    from main import bot  # Import running bot instance

    aged_positions = []
    for symbol, position in bot.position_manager.positions.items():
        # Check if aged
        age_hours = (datetime.now(timezone.utc) - position.opened_at).total_seconds() / 3600

        if age_hours > bot.aged_position_manager.max_position_age_hours:
            # Calculate phase and target
            hours_over = age_hours - bot.aged_position_manager.max_position_age_hours
            phase, target, loss_pct = bot.aged_position_manager._calculate_target_price(
                position, hours_over, position.current_price
            )

            aged_positions.append({
                'symbol': symbol,
                'age_hours': f"{age_hours:.1f}",
                'phase': phase,
                'phase_class': 'grace' if 'GRACE' in phase else 'progressive' if 'PROGRESSIVE' in phase else 'emergency',
                'entry_price': f"{position.entry_price:.4f}",
                'current_price': f"{position.current_price:.4f}",
                'target_exit': f"{target:.4f}",
                'loss_tolerance': f"{loss_pct:.2f}",
                'pnl': f"{position.unrealized_pnl:.2f}"
            })

    return {'positions': aged_positions}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

**Запустить**:
```bash
python3 dashboard/aged_dashboard.py
# Открыть http://localhost:8000/dashboard/aged_positions.html
```

---

## 🟢 PRIORITY 3: NICE TO HAVE (backlog)

### Fix #6: Интегрировать PositionGuard

**Severity**: LOW
**Impact**: Advanced health monitoring не используется
**ETA**: 1-2 часа

**Файл**: `main.py`

В `main()` добавить:
```python
# After position_manager initialization
from protection.position_guard import PositionGuard

position_guard = PositionGuard(
    exchange_manager=exchanges,
    risk_manager=risk_manager,
    stop_loss_manager=stop_loss_manager,
    trailing_stop_manager=trailing_stop_manager,
    repository=repository,
    event_router=event_router,
    config={
        'max_drawdown_pct': 5.0,
        'critical_loss_pct': 3.0,
        'max_position_hours': 48,
        'volatility_threshold': 2.0,
        'correlation_threshold': 0.7
    }
)

# Start monitoring for new positions
event_router.register_handler('position.opened', position_guard.start_protection)
```

---

### Fix #7: Enhanced Alerts

**Severity**: LOW
**Impact**: Нет уведомлений о критичных событиях
**ETA**: 4 часа

**Создать**: `alerts/telegram_notifier.py`

```python
import asyncio
from telegram import Bot

class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot = Bot(token=bot_token)
        self.chat_id = chat_id

    async def send_alert(self, message: str, level: str = 'INFO'):
        """Send alert to Telegram"""
        emoji = {
            'INFO': 'ℹ️',
            'WARNING': '⚠️',
            'ERROR': '❌',
            'CRITICAL': '🚨'
        }.get(level, 'ℹ️')

        formatted = f"{emoji} {level}\n\n{message}"

        await self.bot.send_message(
            chat_id=self.chat_id,
            text=formatted,
            parse_mode='Markdown'
        )

# Usage in main.py
notifier = TelegramNotifier(
    bot_token=os.getenv('TELEGRAM_BOT_TOKEN'),
    chat_id=os.getenv('TELEGRAM_CHAT_ID')
)

# Alert на критичные события
if aged_position.age > 30:  # 30h = EMERGENCY
    await notifier.send_alert(
        f"Position {symbol} in EMERGENCY phase!\n"
        f"Age: {age}h\n"
        f"Target: ${target}",
        level='CRITICAL'
    )
```

---

## 📋 CHECKLIST ДЛЯ ПРИМЕНЕНИЯ ФИКСОВ

### Перед применением:
- [ ] Сделать backup текущего кода: `git commit -am "Pre-fixes snapshot"`
- [ ] Создать ветку: `git checkout -b fixes/production-audit-2025-10-15`

### Priority 1 (45 минут):
- [ ] Fix #1: Price precision (30 мин)
  - [ ] Добавить `apply_price_precision()` в `exchange_manager_enhanced.py`
  - [ ] Использовать в `create_or_update_exit_order()`
  - [ ] Тестировать с примерами
- [ ] Fix #2: JSON serialization (15 мин)
  - [ ] Добавить `DecimalEncoder` в `event_logger.py`
  - [ ] Заменить все `json.dumps()`
  - [ ] Тестировать
- [ ] Fix #3: Log rotation (10 мин)
  - [ ] Заменить logging setup в `main.py`
  - [ ] Проверить что работает

### Тестирование фиксов:
- [ ] Запустить бота на 30 минут
- [ ] Проверить логи на отсутствие ошибок 170193 и TypeError
- [ ] Проверить что log rotation работает
- [ ] Commit: `git commit -am "Apply priority 1 fixes from audit"`

### Priority 2 (опционально, завтра):
- [ ] Fix #4: Log patterns (20 мин)
- [ ] Fix #5: Dashboard (2-4 часа)

### Деплой:
- [ ] Merge в main: `git checkout main && git merge fixes/production-audit-2025-10-15`
- [ ] Push: `git push origin main`
- [ ] Restart production bot
- [ ] Monitor первые 2 часа

---

## 🎯 ИТОГОВОЕ ВРЕМЯ

**Priority 1**: ~45 минут (критично)
**Priority 2**: ~3-4 часа (желательно завтра)
**Priority 3**: ~5-6 часов (backlog)

**Минимум для production**: Только Priority 1 (45 минут)

---

**Создано**: 2025-10-15 15:27 UTC
**Версия**: 1.0
