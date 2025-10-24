# 🚨 КРИТИЧЕСКИЙ РЕГРЕСС: LEVERAGE УДАЛЁН ПРИ РЕФАКТОРИНГЕ

**Дата обнаружения:** 2025-10-25
**Критичность:** 🔴 **КРИТИЧЕСКАЯ** - Влияет на риск-менеджмент!
**Статус:** ❌ ПОДТВЕРЖДЁН

---

## 🎯 РЕЗЮМЕ

**ВЫ БЫЛИ ПРАВЫ!** Leverage ДЕЙСТВИТЕЛЬНО устанавливался программно в старых версиях бота.

**При рефакторинге (Phase 3.2.4) код установки leverage был СЛУЧАЙНО УДАЛЁН и НЕ ВОССТАНОВЛЕН!**

---

## 📊 ЧТО ПРОИЗОШЛО

### ✅ БЫЛО (v25, коммит a7be064):

```python
# core/position_manager.py - СТАРАЯ ВЕРСИЯ

async def open_position(self, request: PositionRequest):
    # ... validation ...

    # 6.5. Set leverage before opening position
    # Use leverage from config (default: 10 for all exchanges)
    leverage = self.config.leverage  # ✅ Читаем из config!
    await exchange.set_leverage(symbol, leverage)  # ✅ Устанавливаем на бирже!

    # 7. Execute market order
    order = await exchange.create_market_order(symbol, side, quantity)
```

```python
# core/exchange_manager.py - СТАРАЯ ВЕРСИЯ

async def set_leverage(self, symbol: str, leverage: int) -> bool:
    """
    Set leverage for a trading pair

    CRITICAL: Must be called BEFORE opening position!
    """
    try:
        # Bybit requires 'category' parameter
        if self.name.lower() == 'bybit':
            await self.rate_limiter.execute_request(
                self.exchange.set_leverage,
                leverage=leverage,
                symbol=symbol,
                params={'category': 'linear'}
            )
        else:
            # Binance and others
            await self.rate_limiter.execute_request(
                self.exchange.set_leverage,
                leverage=leverage,
                symbol=symbol
            )

        logger.info(f"✅ Leverage set to {leverage}x for {symbol} on {self.name}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to set leverage for {symbol}: {e}")
        return False
```

### ❌ СТАЛО (текущая версия):

```python
# core/position_manager.py - ТЕКУЩАЯ ВЕРСИЯ

async def open_position(self, request: PositionRequest):
    # ... validation ...

    # ❌ КОД УСТАНОВКИ LEVERAGE УДАЛЁН!

    # Сразу создаём ордер БЕЗ установки leverage
    order = await exchange.create_market_order(symbol, side, quantity)
```

```python
# core/exchange_manager.py - ТЕКУЩАЯ ВЕРСИЯ

# ❌ ФУНКЦИЯ set_leverage ОТСУТСТВУЕТ!
```

---

## 🔍 КОГДА ЭТО ПРОИЗОШЛО

**Коммит:** `7f2f3d0` - "✨ Phase 3.2.4: Refactor open_position() to use helper methods (393→62 lines)"

**Дата:** Недавний рефакторинг для упрощения open_position()

**Изменения:**
```diff
- # 6.5. Set leverage before opening position
- # Use leverage from config (default: 10 for all exchanges)
- leverage = self.config.leverage
- await exchange.set_leverage(symbol, leverage)
-
```

**Причина:** При сокращении метода с 393 до 62 строк случайно удалили критический функционал!

---

## ⚠️ ПОСЛЕДСТВИЯ РЕГРЕССА

### 1. Leverage не контролируется ботом

```
БЫЛО (правильно):
  ✅ Бот устанавливает leverage=10 перед КАЖДОЙ позицией
  ✅ Гарантия что все позиции имеют одинаковый leverage
  ✅ Предсказуемая экспозиция

СТАЛО (неправильно):
  ❌ Leverage берётся с биржи (настроен вручную)
  ❌ Разные символы имеют РАЗНЫЙ leverage
  ❌ Непредсказуемая экспозиция
```

### 2. Текущая ситуация на testnet:

**Binance:**
```
SNTUSDT:    20x leverage ⚠️ (в 2 раза больше ожидаемого!)
CGPTUSDT:   10x leverage ✅ (правильно)
SUSHIUSDT:  10x leverage ✅ (правильно)
TRUTHUSDT:  20x leverage ⚠️ (в 2 раза больше!)
STRAXUSDT:  20x leverage ⚠️ (в 2 раза больше!)
```

**Проблема:** Некоторые символы имеют 20x вместо ожидаемых 10x!

### 3. Impact на экспозицию:

```python
# Ожидалось (если бы leverage=10 работал):
150 позиций × $6 × 10x = $9,000 экспозиция

# Реальность (mixed leverage 10x-20x):
- 75 символов × $6 × 10x = $4,500
- 75 символов × $6 × 20x = $9,000
  ИТОГО: $13,500 экспозиция! (на 50% больше ожидаемого!)
```

### 4. Риск ликвидации:

```
При 10x leverage и SL=2%:
  2% движение цены = 20% от маржи ✅ Безопасно

При 20x leverage и SL=2%:
  2% движение цены = 40% от маржи ⚠️ ОПАСНО!

При случайных 50x leverage:
  2% движение цены = 100% = 💀 МГНОВЕННАЯ ЛИКВИДАЦИЯ!
```

---

## 🛠️ КАК ЭТО ИСПРАВИТЬ

### Шаг 1: Восстановить set_leverage в ExchangeManager

```python
# core/exchange_manager.py

class ExchangeManager:
    # ... existing code ...

    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """
        Set leverage for a trading pair

        CRITICAL: Must be called BEFORE opening position!
        For Bybit: automatically adds params={'category': 'linear'}

        Args:
            symbol: Trading symbol (exchange format)
            leverage: Leverage multiplier (e.g., 10 for 10x)

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Convert to exchange format if needed
            exchange_symbol = self.find_exchange_symbol(symbol)
            if not exchange_symbol:
                logger.error(f"Symbol {symbol} not found on {self.name}")
                return False

            # Bybit requires 'category' parameter
            if self.name.lower() == 'bybit':
                await self.rate_limiter.execute_request(
                    self.exchange.set_leverage,
                    leverage=leverage,
                    symbol=exchange_symbol,
                    params={'category': 'linear'}
                )
            else:
                # Binance and others
                await self.rate_limiter.execute_request(
                    self.exchange.set_leverage,
                    leverage=leverage,
                    symbol=exchange_symbol
                )

            logger.info(f"✅ Leverage set to {leverage}x for {symbol} on {self.name}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to set leverage for {symbol}: {e}")
            return False
```

### Шаг 2: Добавить вызов в position_manager

```python
# core/position_manager.py

async def open_position(self, request: PositionRequest):
    """Open new position with proper leverage setup"""

    # ... existing validation ...

    # Get exchange instance
    exchange = self.exchange_manager.get(exchange_name)

    # ... existing checks ...

    # 🆕 ВОССТАНОВЛЕНО: Set leverage before opening position
    leverage = self.config.leverage  # Default: 10
    logger.info(f"Setting {leverage}x leverage for {symbol}")

    leverage_set = await exchange.set_leverage(symbol, leverage)
    if not leverage_set:
        logger.warning(
            f"⚠️ Could not set leverage for {symbol}, "
            f"using exchange default"
        )
        # Continue anyway, but log warning

    # Execute market order
    order = await exchange.create_market_order(symbol, side, quantity)

    # ... rest of the code ...
```

### Шаг 3: Добавить LEVERAGE в config/settings.py

```python
# config/settings.py

@dataclass
class TradingConfig:
    """Trading parameters from .env ONLY"""
    # ... existing fields ...

    # 🆕 НОВОЕ: Leverage control
    leverage: int = 10                    # Default leverage for positions
    max_leverage: int = 20                # Maximum allowed leverage
    auto_set_leverage: bool = True        # Auto-set leverage before each trade

# ... в _init_trading():

if val := os.getenv('LEVERAGE'):
    config.leverage = int(val)
if val := os.getenv('MAX_LEVERAGE'):
    config.max_leverage = int(val)
if val := os.getenv('AUTO_SET_LEVERAGE'):
    config.auto_set_leverage = val.lower() == 'true'
```

### Шаг 4: Обновить .env

```bash
# .env

# ───────────────────────────────────────────────────────────────
# LEVERAGE CONTROL (RESTORED AFTER REGRESSION)
# ───────────────────────────────────────────────────────────────
LEVERAGE=10                    # Default leverage for all positions
MAX_LEVERAGE=20                # Maximum allowed leverage
AUTO_SET_LEVERAGE=true         # Auto-set leverage before opening position
```

---

## 📋 ПЛАН ВОССТАНОВЛЕНИЯ

### ⚡ СРОЧНО (сегодня):

- [ ] 1. Восстановить `set_leverage()` в `core/exchange_manager.py`
- [ ] 2. Добавить вызов в `core/position_manager.py` перед созданием ордера
- [ ] 3. Добавить поле `leverage` в `TradingConfig`
- [ ] 4. Загрузить `LEVERAGE` из .env
- [ ] 5. Протестировать на testnet

### 🧪 ТЕСТИРОВАНИЕ (1 час):

- [ ] 6. Проверить что leverage устанавливается для Binance
- [ ] 7. Проверить что leverage устанавливается для Bybit
- [ ] 8. Убедиться что все новые позиции имеют leverage=10
- [ ] 9. Проверить что не ломается на символах где leverage уже 10

### 🚀 ДЕПЛОЙ:

- [ ] 10. Создать коммит: "fix(critical): restore leverage setup removed in refactoring"
- [ ] 11. Задеплоить на production
- [ ] 12. Мониторить первые 10 позиций - убедиться leverage=10

---

## 📊 ПРОВЕРОЧНЫЙ СКРИПТ

```python
#!/usr/bin/env python3
"""
Verify leverage is being set correctly
"""
import asyncio
from core.exchange_manager import ExchangeManager
from config.settings import config

async def verify_leverage_fix():
    """Test leverage setup"""

    print("=" * 80)
    print("🔍 VERIFYING LEVERAGE FIX")
    print("=" * 80)
    print()

    for exchange_name in ['binance', 'bybit']:
        cfg = config.get_exchange_config(exchange_name)
        if not cfg:
            continue

        em = ExchangeManager(exchange_name, cfg.__dict__)
        await em.initialize()

        # Test symbol
        test_symbol = 'BTCUSDT' if exchange_name == 'binance' else 'BTC/USDT:USDT'

        print(f"📊 Testing {exchange_name.upper()}: {test_symbol}")

        # Set leverage
        result = await em.set_leverage(test_symbol, 10)

        if result:
            print(f"   ✅ SUCCESS: Leverage set to 10x")
        else:
            print(f"   ❌ FAILED: Could not set leverage")

        # Verify
        if exchange_name == 'binance':
            risk = await em.exchange.fapiPrivateV2GetPositionRisk(
                {'symbol': test_symbol}
            )
            actual_leverage = risk[0].get('leverage') if risk else 'N/A'
        else:
            positions = await em.exchange.fetch_positions(
                symbols=[test_symbol],
                params={'category': 'linear'}
            )
            actual_leverage = positions[0].get('leverage') if positions else 'N/A'

        print(f"   📈 Actual leverage: {actual_leverage}x")
        print()

        await em.close()

    print("=" * 80)
    print("✅ VERIFICATION COMPLETE")
    print("=" * 80)

if __name__ == '__main__':
    asyncio.run(verify_leverage_fix())
```

---

## ✅ КРИТЕРИИ УСПЕХА

После исправления должно быть:

1. ✅ `set_leverage()` существует в `ExchangeManager`
2. ✅ Вызывается перед КАЖДЫМ открытием позиции
3. ✅ Leverage загружается из `config.leverage`
4. ✅ Все новые позиции имеют leverage=10
5. ✅ Логи показывают: "✅ Leverage set to 10x for {symbol}"
6. ✅ Binance и Bybit оба работают

---

## 📝 ИЗВЛЕЧЁННЫЕ УРОКИ

### Что пошло не так:

1. ❌ Рефакторинг без тестового покрытия
2. ❌ Критический функционал не был задокументирован
3. ❌ Нет автоматических тестов для leverage
4. ❌ Нет мониторинга leverage в метриках

### Как предотвратить в будущем:

1. ✅ Добавить тесты для set_leverage
2. ✅ Добавить метрики для leverage
3. ✅ Документировать критический функционал
4. ✅ Code review с чеклистом перед рефакторингом

---

## 🔚 ЗАКЛЮЧЕНИЕ

**Регресс подтверждён:**
- ✅ Leverage ДЕЙСТВИТЕЛЬНО устанавливался в v25
- ✅ Был удалён в коммите 7f2f3d0 (Phase 3.2.4)
- ✅ Функция `set_leverage()` полностью удалена

**Текущее состояние:**
- ❌ Leverage НЕ контролируется программно
- ❌ Разные символы имеют разный leverage (10x-20x)
- ❌ Экспозиция непредсказуема

**Необходимые действия:**
- 🔴 КРИТИЧНО: Восстановить set_leverage СРОЧНО!
- ⚡ Приоритет: МАКСИМАЛЬНЫЙ
- ⏱️ Время на исправление: 1-2 часа

---

**Автор:** Claude Code
**Дата:** 2025-10-25
**Тип:** Critical Regression Report
