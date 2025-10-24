# 🔍 ГЛУБОКИЙ АУДИТ: КАК УСТАНАВЛИВАЕТСЯ LEVERAGE

**Дата:** 2025-10-25
**Цель:** Выяснить как именно задаётся leverage для позиций
**Результат:** ⚠️ **КРИТИЧЕСКОЕ ОТКРЫТИЕ** - Leverage НЕ контролируется ботом!

---

## 🎯 ГЛАВНЫЙ ВЫВОД

```
┌─────────────────────────────────────────────────────────────────┐
│ LEVERAGE НЕ УСТАНАВЛИВАЕТСЯ ПРОГРАММНО!                         │
│                                                                 │
│ Бот использует leverage, настроенный ВРУЧНУЮ на бирже.         │
│ Каждый символ имеет СВОЙ leverage, который нужно настраивать   │
│ через UI биржи для КАЖДОГО символа отдельно!                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📋 ЧТО Я ПРОВЕРИЛ

### 1️⃣ Все точки создания ордеров (23 места)

Проверил все вызовы `create_order`, `create_market_order`, `create_limit_order`:

**Файлы с созданием ордеров:**
- ✅ `core/position_manager.py` - основное создание позиций
- ✅ `core/atomic_position_manager.py` - атомарное создание
- ✅ `core/order_executor.py` - исполнение с retry логикой
- ✅ `core/exchange_manager.py` - обёртки над CCXT
- ✅ `core/aged_position_manager.py` - закрытие aged позиций
- ✅ `core/stop_loss_manager.py` - установка SL
- ✅ `protection/trailing_stop.py` - трейлинг стопы

**Результат:** ❌ **НИ В ОДНОМ месте не передаётся параметр `leverage`!**

---

### 2️⃣ Параметры при создании ордеров

Проверил все `params = {...}` при создании ордеров.

**Что РЕАЛЬНО передаётся:**

```python
# Пример из order_executor.py
params = {
    'reduceOnly': True,        # ✅ Используется
    'timeInForce': 'IOC'       # ✅ Используется
    # 'leverage': ???           # ❌ ОТСУТСТВУЕТ!
}

# Пример из aged_position_manager.py
params = {
    'reduceOnly': True
    # 'leverage': ???           # ❌ ОТСУТСТВУЕТ!
}

# Пример из exchange_manager.py - stop loss
params = {
    'stopPrice': float(stop_price),
    'reduceOnly': True,
    'workingType': 'CONTRACT_PRICE'
    # 'leverage': ???           # ❌ ОТСУТСТВУЕТ!
}
```

**Найденные параметры в params:**
- ✅ `reduceOnly: True` - всегда при закрытии
- ✅ `timeInForce: IOC/GTC/PostOnly` - время жизни ордера
- ✅ `category: 'linear'` - для Bybit
- ✅ `stopPrice` - для стоп-лоссов
- ✅ `postOnly: True` - для maker ордеров
- ❌ **`leverage` - НИГДЕ НЕТ!**

---

### 3️⃣ Инициализация Exchange

Проверил `ExchangeManager.__init__()` и `ExchangeManager.initialize()`.

**core/exchange_manager.py:74-165:**

```python
def __init__(self, exchange_name: str, config: Dict, repository=None):
    # ... инициализация CCXT ...

    exchange_options = {
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': config.get('rate_limit', True),
        'options': {
            'defaultType': 'future',
            'adjustForTimeDifference': True,
            'recvWindow': 10000,
        }
    }

    # Binance specific
    if self.name == 'binance':
        exchange_options['options']['fetchPositions'] = 'positionRisk'

    # Bybit specific
    elif self.name == 'bybit':
        exchange_options['options']['accountType'] = 'UNIFIED'
        exchange_options['options']['defaultType'] = 'future'
        exchange_options['options']['brokerId'] = ''  # Disable brokerId

    self.exchange = exchange_class(exchange_options)

    # ❌ НЕТ вызова set_leverage()!
```

**Результат:** ❌ **НИ РАЗУ не вызывается `set_leverage()`!**

---

### 4️⃣ Вызовы set_leverage в коде

Поиск по всему коду:

```bash
$ grep -r "set_leverage\|setLeverage" --include="*.py" | grep -v ".venv" | grep -v "test_" | grep -v ".backup"

./core/bybit_zombie_cleaner.py:317:  # Use CCXT's set_leverage method with special params for trading-stop
```

**Единственное упоминание** - это **ошибочный комментарий**!

Проверим этот файл:

```python
# core/bybit_zombie_cleaner.py:317
# Use CCXT's set_leverage method with special params for trading-stop
# ⬆️ НЕПРАВИЛЬНЫЙ КОММЕНТАРИЙ!

# На самом деле там вызывается:
response = await self.exchange.private_post_v5_position_trading_stop(params)
# ⬆️ Это НЕ set_leverage, это trading-stop endpoint!
```

**Результат:** ❌ **`set_leverage()` НИ РАЗУ не вызывается!**

---

## 🔬 ЭКСПЕРИМЕНТ: Проверка реального leverage

Подключился к биржам и проверил какой leverage используется СЕЙЧАС:

### Binance Testnet - Реальные значения:

```
SNTUSDT        : 20x leverage
CGPTUSDT       : 10x leverage
SUSHIUSDT      : 10x leverage
TRUTHUSDT      : 20x leverage
STRAXUSDT      : 20x leverage
```

### Bybit Testnet - Реальные значения:

```
OKB/USDT:USDT  : 10.0x leverage
BOBA/USDT:USDT : 10.0x leverage
ALEO/USDT:USDT : 10.0x leverage
AGI/USDT:USDT  : 10.0x leverage
XDC/USDT:USDT  : 10.0x leverage
```

### 🔍 Анализ:

1. **Binance:** Разные символы имеют РАЗНЫЙ leverage (10x или 20x)
2. **Bybit:** Все символы настроены на 10x
3. **Leverage НЕ одинаковый** для всех символов!
4. **Leverage настраивается ВРУЧНУЮ** через UI биржи

---

## 📚 Как работает CCXT с leverage

### Документация CCXT:

```python
# CCXT поддерживает set_leverage для futures
binance.has['setLeverage']  # True
bybit.has['setLeverage']    # True

# Но если НЕ вызвать set_leverage():
# ➡️ Используется leverage настроенный на БИРЖЕ!
```

### Пример правильного использования:

```python
# Так ДОЛЖНО быть (но у нас этого НЕТ):
await exchange.set_leverage(10, 'BTC/USDT:USDT')  # Установить 10x для BTCUSDT
await exchange.create_market_order('BTC/USDT:USDT', 'buy', 0.001)
```

### Как сейчас работает БОТ:

```python
# Текущая реализация (НЕПРАВИЛЬНО):
# ❌ НЕТ set_leverage()!
await exchange.create_market_order('BTC/USDT:USDT', 'buy', 0.001)
# ➡️ Используется leverage с биржи (может быть 1x, 5x, 10x, 20x, 50x!)
```

---

## ⚠️ КРИТИЧЕСКИЕ РИСКИ

### 1. Непредсказуемость leverage

```
Проблема: Разные символы имеют РАЗНЫЙ leverage!
          - Один символ: 10x leverage
          - Другой символ: 20x leverage
          - Третий символ: 1x leverage (по умолчанию!)

Риск:     Невозможно предсказать реальную экспозицию!
```

### 2. Риск ликвидации

```
Сценарий: Символ случайно настроен на 50x leverage
          Позиция $6 USD при 50x = экспозиция $300!
          При падении на 2% = ликвидация!

Текущий SL: 2% - этого может быть НЕДОСТАТОЧНО при высоком leverage!
```

### 3. Несоответствие расчётам

```python
# config/settings.py
POSITION_SIZE_USD=6           # $6 на позицию
MAX_POSITIONS=150             # 150 позиций
MAX_EXPOSURE_USD=30000        # $30K max

# Расчёт БЕЗ leverage:
# 150 * $6 = $900 экспозиция

# Реальность С leverage 10x:
# 150 * $6 * 10x = $9,000 экспозиция! 🚨

# Реальность С leverage 20x:
# 150 * $6 * 20x = $18,000 экспозиция! 🚨🚨

# Реальность С mixed leverage (10x-20x):
# НЕПРЕДСКАЗУЕМО! Может быть от $9K до $18K!
```

### 4. Новые символы

```
Проблема: Каждый новый символ нужно настраивать ВРУЧНУЮ!
          Если забыть - будет leverage 1x или default биржи!

Риск:     Бот может торговать с разным leverage!
```

---

## 💡 ПОЧЕМУ LEVERAGE=10 В .env НЕ ИСПОЛЬЗУЕТСЯ

### Проверка загрузки:

```python
# config/settings.py - проверено построчно
# ❌ НЕТ загрузки LEVERAGE из .env!

@dataclass
class TradingConfig:
    position_size_usd: Decimal = Decimal('200')
    max_positions: int = 10
    stop_loss_percent: Decimal = Decimal('2.0')
    # ...
    # ❌ НЕТ поля 'leverage'!
```

### Где LEVERAGE упоминается:

1. **`core/risk_manager.py:53`**
   ```python
   self.max_leverage = config.get('max_leverage', 10)
   ```
   ❌ НО! RiskManager не используется в main.py!

2. **WebSocket streams** - ЧИТАЮТ leverage из биржевых данных:
   ```python
   # websocket/bybit_stream.py:126
   'leverage': float(position.get('leverage', 1))  # Чтение с биржи
   ```

3. **Scripts** - диагностические скрипты для расследования

**Вывод:** `LEVERAGE=10` в .env - **мёртвая переменная**! ✅ Можно удалить.

---

## 🛠️ РЕКОМЕНДАЦИИ

### ⚡ СРОЧНО (Критично для безопасности):

#### 1. Проверить leverage на ВСЕХ символах

```bash
# Нужен скрипт для аудита:
python scripts/audit_leverage.py

# Должен показать:
# Symbol          Exchange    Leverage    Status
# BTCUSDT         binance     20x         ⚠️ HIGH
# ETHUSDT         binance     10x         ✅ OK
# NEWCOIN         binance     1x          ❌ TOO LOW
```

#### 2. Установить единый leverage программно

```python
# Добавить в ExchangeManager.initialize():

async def initialize(self):
    await self.exchange.load_markets()

    # 🆕 НОВОЕ: Установить leverage для ВСЕХ символов
    target_leverage = 10  # Из config

    for symbol in self.markets:
        if self.markets[symbol]['future']:  # Только futures
            try:
                await self.exchange.set_leverage(target_leverage, symbol)
                logger.info(f"Set {target_leverage}x leverage for {symbol}")
            except Exception as e:
                logger.warning(f"Could not set leverage for {symbol}: {e}")
```

#### 3. Проверять leverage перед открытием позиции

```python
# В atomic_position_manager.py перед созданием ордера:

# 🆕 НОВОЕ: Проверка и установка leverage
current_leverage = await self._get_symbol_leverage(exchange, symbol)
if current_leverage != self.target_leverage:
    logger.warning(
        f"⚠️ {symbol} leverage mismatch: "
        f"{current_leverage}x != {self.target_leverage}x, fixing..."
    )
    await exchange.set_leverage(self.target_leverage, symbol)
```

### 📋 СРЕДНИЙ ПРИОРИТЕТ:

#### 4. Добавить LEVERAGE в config

```python
# config/settings.py

@dataclass
class TradingConfig:
    # ... existing fields ...

    # 🆕 НОВОЕ: Leverage control
    leverage: int = 10                    # Default leverage for all positions
    max_leverage: int = 20                # Maximum allowed leverage
    auto_set_leverage: bool = True        # Auto-set leverage on initialization
```

```python
# Загрузка из .env:
if val := os.getenv('LEVERAGE'):
    config.leverage = int(val)
if val := os.getenv('MAX_LEVERAGE'):
    config.max_leverage = int(val)
if val := os.getenv('AUTO_SET_LEVERAGE'):
    config.auto_set_leverage = val.lower() == 'true'
```

#### 5. Мониторинг leverage

```python
# 🆕 НОВОЕ: Добавить в monitoring/metrics.py

class MetricsCollector:
    def __init__(self):
        # ...
        self.position_leverage = Histogram(
            'position_leverage',
            'Leverage used for positions',
            ['exchange', 'symbol']
        )

    async def track_position_opened(self, position):
        # Get actual leverage from exchange
        leverage = await self._get_position_leverage(position)

        self.position_leverage.labels(
            exchange=position.exchange,
            symbol=position.symbol
        ).observe(leverage)
```

#### 6. Валидация в пре-чеках

```python
# protection/position_guard.py

async def validate_leverage(self, symbol: str, exchange: str) -> bool:
    """Проверить что leverage в безопасных пределах"""
    current = await self._get_symbol_leverage(exchange, symbol)

    if current > self.config.max_leverage:
        logger.error(
            f"❌ {symbol} leverage {current}x exceeds max {self.config.max_leverage}x!"
        )
        return False

    if current < 1:
        logger.error(f"❌ {symbol} leverage {current}x is invalid!")
        return False

    return True
```

---

## 📊 IMPACT ANALYSIS

### Текущая ситуация:

| Аспект | Статус | Риск |
|--------|--------|------|
| **Leverage контроль** | ❌ Отсутствует | 🔴 КРИТИЧЕСКИЙ |
| **Единообразие** | ❌ Разный по символам | 🔴 КРИТИЧЕСКИЙ |
| **Предсказуемость** | ❌ Неизвестна экспозиция | 🔴 КРИТИЧЕСКИЙ |
| **Новые символы** | ❌ Требуют ручной настройки | 🟡 ВЫСОКИЙ |
| **Мониторинг** | ❌ Нет отслеживания | 🟡 ВЫСОКИЙ |

### После исправления:

| Аспект | Статус | Риск |
|--------|--------|------|
| **Leverage контроль** | ✅ Программный | 🟢 НИЗКИЙ |
| **Единообразие** | ✅ Единый для всех | 🟢 НИЗКИЙ |
| **Предсказуемость** | ✅ Известна заранее | 🟢 НИЗКИЙ |
| **Новые символы** | ✅ Авто-настройка | 🟢 НИЗКИЙ |
| **Мониторинг** | ✅ Prometheus метрики | 🟢 НИЗКИЙ |

---

## 🎯 ПЛАН ДЕЙСТВИЙ

### Фаза 1: Аудит (СРОЧНО - сегодня)

- [ ] Создать скрипт `scripts/audit_leverage.py`
- [ ] Проверить leverage на ВСЕХ торгуемых символах (Binance + Bybit)
- [ ] Создать отчёт: какие символы имеют какой leverage
- [ ] Выявить аномалии (слишком высокий/низкий leverage)

### Фаза 2: Исправление (1-2 дня)

- [ ] Добавить `LEVERAGE`, `MAX_LEVERAGE`, `AUTO_SET_LEVERAGE` в .env
- [ ] Загрузить в `config/settings.py`
- [ ] Реализовать `ExchangeManager.set_leverage_for_symbol()`
- [ ] Добавить вызов при инициализации exchange
- [ ] Добавить проверку перед созданием позиции

### Фаза 3: Валидация (1 день)

- [ ] Добавить pre-check leverage в `PositionGuard`
- [ ] Добавить метрики в `MetricsCollector`
- [ ] Написать тесты для leverage control
- [ ] Протестировать на testnet

### Фаза 4: Мониторинг (ongoing)

- [ ] Dashboard с leverage по символам
- [ ] Алерты при leverage mismatch
- [ ] Еженедельный аудит leverage настроек

---

## 📝 ПРИМЕР КОДА ИСПРАВЛЕНИЯ

### 1. Добавить в .env:

```bash
# Leverage Control
LEVERAGE=10                    # Default leverage for all symbols
MAX_LEVERAGE=20                # Maximum allowed leverage
AUTO_SET_LEVERAGE=true         # Auto-configure leverage on startup
```

### 2. Скрипт для аудита:

```python
#!/usr/bin/env python3
"""
Audit leverage settings across all exchanges
"""
import asyncio
from core.exchange_manager import ExchangeManager
from config.settings import config

async def audit_leverage():
    """Check leverage for all symbols"""

    results = {
        'binance': {},
        'bybit': {}
    }

    for exchange_name in ['binance', 'bybit']:
        cfg = config.get_exchange_config(exchange_name)
        if not cfg:
            continue

        em = ExchangeManager(exchange_name, cfg.__dict__)
        await em.initialize()

        # Get all futures symbols
        futures = [s for s, m in em.markets.items() if m.get('future')]

        print(f"\n{'=' * 80}")
        print(f"📊 {exchange_name.upper()} LEVERAGE AUDIT")
        print(f"{'=' * 80}\n")

        for symbol in futures[:50]:  # First 50
            try:
                # Method depends on exchange
                if exchange_name == 'binance':
                    risk = await em.exchange.fapiPrivateV2GetPositionRisk(
                        {'symbol': symbol.replace('/USDT:USDT', 'USDT')}
                    )
                    leverage = risk[0].get('leverage', 'N/A') if risk else 'N/A'
                else:  # bybit
                    positions = await em.exchange.fetch_positions(
                        symbols=[symbol],
                        params={'category': 'linear'}
                    )
                    leverage = positions[0].get('leverage', 'N/A') if positions else 'N/A'

                results[exchange_name][symbol] = leverage

                # Color code
                lev_int = int(float(leverage)) if leverage != 'N/A' else 0
                status = '✅' if 5 <= lev_int <= 15 else ('⚠️' if lev_int > 15 else '❌')

                print(f"{status} {symbol:25s}: {leverage}x")

            except Exception as e:
                print(f"❌ {symbol:25s}: ERROR - {e}")

        await em.close()

    # Summary
    print(f"\n{'=' * 80}")
    print("📈 SUMMARY")
    print(f"{'=' * 80}\n")

    for exchange, symbols in results.items():
        leverages = [float(v) for v in symbols.values() if v != 'N/A']
        if leverages:
            print(f"{exchange.upper()}:")
            print(f"  Min: {min(leverages)}x")
            print(f"  Max: {max(leverages)}x")
            print(f"  Avg: {sum(leverages)/len(leverages):.1f}x")
            print()

if __name__ == '__main__':
    asyncio.run(audit_leverage())
```

### 3. Интеграция в ExchangeManager:

```python
# core/exchange_manager.py

class ExchangeManager:

    async def initialize(self):
        """Load markets and validate connection"""
        await self.exchange.load_markets()
        logger.info(f"Loaded {len(self.markets)} markets from {self.name}")

        # 🆕 НОВОЕ: Auto-set leverage if enabled
        if self.config.get('auto_set_leverage', True):
            await self._configure_leverage()

        await self.exchange.fetch_balance()
        logger.info(f"Connection to {self.name} verified")

        return True

    async def _configure_leverage(self):
        """Set leverage for all futures symbols"""
        target_leverage = self.config.get('leverage', 10)

        futures_symbols = [
            symbol for symbol, market in self.markets.items()
            if market.get('future', False)
        ]

        logger.info(
            f"🔧 Configuring {target_leverage}x leverage "
            f"for {len(futures_symbols)} symbols on {self.name}..."
        )

        success = 0
        failed = 0

        for symbol in futures_symbols:
            try:
                await self.rate_limiter.execute_request(
                    self.exchange.set_leverage,
                    target_leverage,
                    symbol
                )
                success += 1

                if success % 10 == 0:  # Progress update
                    logger.info(f"  Configured {success}/{len(futures_symbols)}...")

            except Exception as e:
                failed += 1
                logger.warning(f"  ⚠️ Could not set leverage for {symbol}: {e}")

        logger.info(
            f"✅ Leverage configuration complete: "
            f"{success} success, {failed} failed"
        )
```

---

## ✅ ЧЕКЛИСТ ЗАВЕРШЕНИЯ

### Немедленные действия:

- [x] Глубокий аудит всех точек создания ордеров
- [x] Проверка params при создании ордеров
- [x] Проверка инициализации exchange
- [x] Поиск set_leverage вызовов
- [x] Проверка реального leverage на биржах
- [x] Создание отчёта

### Следующие шаги:

- [ ] Создать скрипт аудита leverage
- [ ] Добавить leverage в config
- [ ] Реализовать auto-set leverage
- [ ] Добавить валидацию
- [ ] Добавить мониторинг
- [ ] Тестирование на testnet
- [ ] Deploy в production

---

## 🔚 ЗАКЛЮЧЕНИЕ

**Текущая ситуация:**
- ❌ Leverage НЕ контролируется программно
- ❌ Используется leverage настроенный ВРУЧНУЮ на бирже
- ❌ Разные символы имеют РАЗНЫЙ leverage
- ❌ Невозможно предсказать реальную экспозицию
- ❌ LEVERAGE=10 в .env не используется ✅ МОЖНО УДАЛИТЬ

**Критичность:** 🔴 **КРИТИЧЕСКАЯ** - влияет на риск-менеджмент!

**Рекомендация:**
1. ⚡ СРОЧНО провести аудит текущих leverage настроек
2. 🛠️ Реализовать программный контроль leverage (1-2 дня работы)
3. 📊 Добавить мониторинг leverage
4. ✅ Удалить LEVERAGE=10 из .env (пока не используется)

---

**Автор:** Claude Code
**Дата:** 2025-10-25
