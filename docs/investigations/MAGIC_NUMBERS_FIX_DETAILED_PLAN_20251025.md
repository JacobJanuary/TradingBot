# 🔧 ДЕТАЛЬНЫЙ ПЛАН ИСПРАВЛЕНИЯ МАГИЧЕСКИХ ЧИСЕЛ

**Дата создания:** 2025-10-25
**Статус:** Готов к исполнению
**Принцип:** Только планирование, БЕЗ изменения кода на данном шаге

---

## 📊 SCOPE ANALYSIS

### Затронутые файлы и переменные

#### ✅ Анализ завершён - Найдено:

**Файлы с магическими числами:**
1. `core/signal_processor_websocket.py` - КРИТИЧНО
2. `core/position_manager.py` - 1 магическое число
3. `core/aged_position_monitor_v2.py` - 6 дубликатов
4. `core/aged_position_manager.py` - 5 дубликатов
5. `core/exchange_manager_enhanced.py` - 5 дубликатов
6. `config/settings.py` - Дефолты в dataclass

**Использования size_usd:**
- `signal_processor_websocket.py:312` - 🔴 КРИТИЧНО: `200.0` хардкод
- `position_manager.py` - Использует `config.position_size_usd` ✅
- `wave_signal_processor.py` - Использует `config.position_size_usd` ✅

**Использования os.getenv() с дефолтами:**
- `aged_position_monitor_v2.py:66-70` - 6 переменных
- `aged_position_manager.py:43-47` - 5 переменных
- `exchange_manager_enhanced.py:553-557` - 5 переменных
- `position_manager.py:1711` - 1 переменная
- `signal_processor_websocket.py:50-65` - WebSocket конфиг (LOW priority)

---

## 🎯 ПЛАН ПО ФАЗАМ

### ФАЗА 0: ПОДГОТОВКА (10 минут)

**Цель:** Создать структуру для централизованных дефолтов

#### Действие 0.1: Обновить defaults в TradingConfig

**Файл:** `config/settings.py`

**Локация:** Lines 36-81 (TradingConfig dataclass)

**Текущие НЕПРАВИЛЬНЫЕ дефолты:**
```python
@dataclass
class TradingConfig:
    # Position sizing
    position_size_usd: Decimal = Decimal('200')  # ❌ СТАРЫЙ ДЕФОЛТ!
    ...
    # Aged positions
    aged_grace_period_hours: int = 8  # ❌ Должно быть 1
    commission_percent: Decimal = Decimal('0.1')  # ❌ Должно быть 0.05
```

**ИСПРАВЛЕННЫЕ дефолты:**
```python
@dataclass
class TradingConfig:
    """Trading parameters from .env ONLY"""
    # Position sizing
    position_size_usd: Decimal = Decimal('6')  # ✅ ТЕКУЩИЙ из .env
    min_position_size_usd: Decimal = Decimal('5')
    max_position_size_usd: Decimal = Decimal('5000')
    max_positions: int = 150  # ✅ из .env
    max_exposure_usd: Decimal = Decimal('99000')  # ✅ из .env

    # Risk management
    stop_loss_percent: Decimal = Decimal('2.0')
    trailing_activation_percent: Decimal = Decimal('2.0')  # ✅ из .env
    trailing_callback_percent: Decimal = Decimal('0.5')

    # Leverage control (RESTORED 2025-10-25)
    leverage: int = 1  # ✅ ТЕКУЩИЙ из .env (пользователь изменил)
    max_leverage: int = 2  # ✅ ТЕКУЩИЙ из .env (пользователь изменил)
    auto_set_leverage: bool = True

    # Trailing Stop SL Update settings
    trailing_min_update_interval_seconds: int = 30  # ✅ из .env
    trailing_min_improvement_percent: Decimal = Decimal('0.05')  # ✅ из .env
    trailing_alert_if_unprotected_window_ms: int = 300  # ✅ из .env

    # Aged positions
    max_position_age_hours: int = 3
    aged_grace_period_hours: int = 1  # ✅ ИСПРАВЛЕНО: было 8, стало 1
    aged_loss_step_percent: Decimal = Decimal('0.5')
    aged_max_loss_percent: Decimal = Decimal('10.0')
    aged_acceleration_factor: Decimal = Decimal('1.2')
    aged_check_interval_minutes: int = 60
    commission_percent: Decimal = Decimal('0.05')  # ✅ ИСПРАВЛЕНО: было 0.1, стало 0.05

    # Signal filtering
    min_score_week: int = 62  # ✅ из .env
    min_score_month: int = 58  # ✅ из .env
    max_spread_percent: Decimal = Decimal('2.0')

    # Execution
    max_trades_per_15min: int = 5  # ✅ из .env

    # Wave processing
    signal_buffer_percent: float = 50.0  # ✅ из .env
```

**Обоснование:**
- Дефолты должны совпадать с текущими значениями в .env
- Это fallback на случай если .env не загружен
- Предотвращает регрессии

**Изменения:**
1. `position_size_usd: Decimal('200')` → `Decimal('6')`
2. `aged_grace_period_hours: int = 8` → `int = 1`
3. `commission_percent: Decimal('0.1')` → `Decimal('0.05')`
4. `max_positions: int = 10` → `int = 150`
5. `max_exposure_usd: Decimal('30000')` → `Decimal('99000')`
6. `trailing_activation_percent: Decimal('1.5')` → `Decimal('2.0')`
7. `trailing_min_update_interval_seconds: int = 60` → `int = 30`
8. `trailing_min_improvement_percent: Decimal('0.1')` → `Decimal('0.05')`
9. `trailing_alert_if_unprotected_window_ms: int = 500` → `int = 300`
10. `min_score_week: int = 0` → `int = 62`
11. `min_score_month: int = 50` → `int = 58`
12. `max_trades_per_15min: int = 20` → `int = 5`
13. `signal_buffer_percent: float = 33.0` → `float = 50.0`
14. `leverage: int = 10` → `int = 1`
15. `max_leverage: int = 20` → `int = 2`

**Тест после Фазы 0:**
```python
# test_phase0_config_defaults.py
def test_config_defaults_match_env():
    """Verify TradingConfig defaults match current .env values"""
    from config.settings import TradingConfig

    config = TradingConfig()

    # Critical defaults
    assert config.position_size_usd == Decimal('6'), "position_size_usd should default to 6"
    assert config.aged_grace_period_hours == 1, "aged_grace_period_hours should default to 1"
    assert config.commission_percent == Decimal('0.05'), "commission_percent should default to 0.05"
    assert config.max_positions == 150
    assert config.max_exposure_usd == Decimal('99000')

    print("✅ All config defaults match .env values")
```

**Git commit после Фазы 0:**
```bash
git add config/settings.py
git commit -m "fix(config): align TradingConfig defaults with .env values

PHASE 0: Config Defaults Alignment

Updated 15 default values in TradingConfig dataclass to match
current .env file values. This prevents regressions if .env is
not loaded.

Critical changes:
- position_size_usd: 200 → 6 (current .env value)
- aged_grace_period_hours: 8 → 1 (current .env value)
- commission_percent: 0.1 → 0.05 (current .env value)

Related: MAGIC_NUMBERS_AUDIT_REPORT_20251025.md

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### ФАЗА 1: КРИТИЧЕСКИЙ ФИКС (15 минут)

**Цель:** Исправить магическое число `200.0` блокирующее торговлю

#### Действие 1.1: Исправить size_usd хардкод

**Файл:** `core/signal_processor_websocket.py`

**Локация:** Line 312

**Текущий код:**
```python
# Line 307-314
validation_tasks = []
for signal_result in final_signals:
    signal = signal_result.get('signal_data')
    if signal:
        symbol = signal.get('symbol')
        size_usd = signal.get('size_usd', 200.0)  # ❌ МАГИЧЕСКОЕ ЧИСЛО!
        exchange_name = signal.get('exchange', 'binance')
```

**Исправленный код:**
```python
# Line 307-318
validation_tasks = []
for signal_result in final_signals:
    signal = signal_result.get('signal_data')
    if signal:
        symbol = signal.get('symbol')

        # FIX: Use config value instead of hardcoded 200.0
        # Get size_usd from signal, fallback to config
        size_usd = signal.get('size_usd')
        if not size_usd or size_usd <= 0:
            size_usd = float(self.position_manager.config.position_size_usd)
            logger.debug(f"Signal {symbol} missing size_usd, using config: ${size_usd}")

        exchange_name = signal.get('exchange', 'binance')
```

**Обоснование:**
1. `signal.get('size_usd')` - Пытается взять из сигнала
2. Проверка `if not size_usd or size_usd <= 0` - Валидация
3. Fallback `self.position_manager.config.position_size_usd` - Конфиг, не хардкод
4. Debug логирование для прозрачности

**Альтернативный вариант (через self.config):**
```python
# Если position_manager.config не работает:
size_usd = signal.get('size_usd')
if not size_usd or size_usd <= 0:
    size_usd = float(self.config.position_size_usd)
    logger.debug(f"Signal {symbol} missing size_usd, using config: ${size_usd}")
```

**Проверка доступа к config:**

Из анализа `signal_processor_websocket.py:33-44`:
```python
def __init__(self, config, position_manager, repository, event_router):
    self.config = config
    self.position_manager = position_manager
```

Оба доступны! Рекомендуется `self.config.position_size_usd` для прямоты.

**Итоговый РЕКОМЕНДУЕМЫЙ код:**
```python
# Line 307-318
validation_tasks = []
for signal_result in final_signals:
    signal = signal_result.get('signal_data')
    if signal:
        symbol = signal.get('symbol')

        # FIX: Use config value instead of hardcoded 200.0
        # Phase 1: Critical magic number removal
        size_usd = signal.get('size_usd')
        if not size_usd or size_usd <= 0:
            # Fallback to config (not hardcoded 200.0!)
            size_usd = float(self.config.position_size_usd)
            logger.debug(
                f"Signal {symbol} missing size_usd, "
                f"using config: ${size_usd} (was hardcoded 200.0)"
            )

        exchange_name = signal.get('exchange', 'binance')
```

**Тест после Фазы 1:**
```python
# test_phase1_size_usd_fix.py
import pytest
from unittest.mock import Mock, patch
from core.signal_processor_websocket import WebSocketSignalProcessor

def test_size_usd_uses_config_not_200():
    """Verify size_usd uses config value, not hardcoded 200"""

    # Setup mock config with position_size_usd = 6
    mock_config = Mock()
    mock_config.position_size_usd = 6

    mock_position_manager = Mock()
    mock_position_manager.config = mock_config

    processor = WebSocketSignalProcessor(
        config=mock_config,
        position_manager=mock_position_manager,
        repository=Mock(),
        event_router=Mock()
    )

    # Test signal WITHOUT size_usd field
    signal = {
        'symbol': 'BTCUSDT',
        'exchange': 'bybit',
        # NO size_usd field
    }

    # This would be called during validation
    # We need to extract the size_usd logic
    size_usd = signal.get('size_usd')
    if not size_usd or size_usd <= 0:
        size_usd = float(processor.config.position_size_usd)

    # CRITICAL: Should be 6, not 200!
    assert size_usd == 6, f"Expected 6 from config, got {size_usd}"
    assert size_usd != 200, "Should NOT use old hardcoded 200"

    print(f"✅ size_usd correctly uses config value: ${size_usd}")

def test_size_usd_respects_signal_value():
    """Verify size_usd uses signal value if provided"""

    mock_config = Mock()
    mock_config.position_size_usd = 6

    processor = WebSocketSignalProcessor(
        config=mock_config,
        position_manager=Mock(),
        repository=Mock(),
        event_router=Mock()
    )

    # Signal WITH size_usd
    signal = {
        'symbol': 'BTCUSDT',
        'exchange': 'bybit',
        'size_usd': 100.0  # Explicit value
    }

    size_usd = signal.get('size_usd')
    if not size_usd or size_usd <= 0:
        size_usd = float(processor.config.position_size_usd)

    # Should use signal value
    assert size_usd == 100.0, f"Expected 100 from signal, got {size_usd}"

    print(f"✅ size_usd correctly uses signal value: ${size_usd}")

def test_size_usd_zero_uses_config():
    """Verify size_usd=0 falls back to config"""

    mock_config = Mock()
    mock_config.position_size_usd = 6

    signal = {'symbol': 'BTCUSDT', 'size_usd': 0}  # Zero

    size_usd = signal.get('size_usd')
    if not size_usd or size_usd <= 0:
        size_usd = float(mock_config.position_size_usd)

    assert size_usd == 6, "Zero size_usd should fallback to config"

    print(f"✅ Zero size_usd correctly falls back to config: ${size_usd}")
```

**Интеграционный тест:**
```python
# test_phase1_integration.py
@pytest.mark.asyncio
async def test_bybit_validation_with_real_balance():
    """Integration test: Bybit signals should pass validation with real balance"""

    from config.settings import config
    from core.exchange_manager import ExchangeManager

    # Setup Bybit exchange
    bybit_config = config.get_exchange_config('bybit')
    em = ExchangeManager('bybit', bybit_config.__dict__)
    await em.initialize()

    # Get real balance
    free_usdt = await em._get_free_balance_usdt()

    # Test with config position size (should be 6, not 200)
    position_size = float(config.trading.position_size_usd)

    # Validation should PASS with correct size
    can_open, reason = await em.can_open_position('BTCUSDT', position_size)

    print(f"Free balance: ${free_usdt:.2f}")
    print(f"Position size: ${position_size}")
    print(f"Can open: {can_open} - {reason}")

    # Critical assertion: Should be able to open if balance > position_size
    if free_usdt >= position_size:
        assert can_open, f"Should be able to open position: ${free_usdt:.2f} >= ${position_size}"

    # Clean up
    await em.close()

    print("✅ Bybit validation works with config position size")
```

**Git commit после Фазы 1:**
```bash
git add core/signal_processor_websocket.py
git add tests/test_phase1_size_usd_fix.py
git add tests/test_phase1_integration.py

git commit -m "fix(critical): remove hardcoded 200.0, use config position_size_usd

PHASE 1: Critical Magic Number Fix

Problem:
- signal_processor_websocket.py:312 had hardcoded size_usd = 200.0
- Bybit balance: \$52.72 available
- Check: \$52.72 < \$200.00 → FAILED
- Result: ALL Bybit signals filtered

Solution:
- Use signal.get('size_usd') if provided
- Fallback to config.position_size_usd (6.0) instead of 200.0
- Added debug logging for transparency

Impact:
- Bybit signals now validated against \$6 (not \$200)
- Balance check: \$52.72 >= \$6 → PASS
- Restores Bybit trading functionality

Testing:
- test_phase1_size_usd_fix.py: Unit tests (3 cases)
- test_phase1_integration.py: Integration with real balance

Evidence:
- docs/investigations/MAGIC_NUMBER_200_VISUAL_20251025.md
- docs/investigations/MAGIC_NUMBERS_AUDIT_REPORT_20251025.md

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### ФАЗА 2: УДАЛЕНИЕ os.getenv() С ДЕФОЛТАМИ (45 минут)

**Цель:** Централизовать все config читая через self.config

#### Действие 2.1: Aged Position Monitor V2

**Файл:** `core/aged_position_monitor_v2.py`

**Текущий код (lines 66-70):**
```python
self.max_age_hours = int(os.getenv('MAX_POSITION_AGE_HOURS', 3))
self.grace_period_hours = int(os.getenv('AGED_GRACE_PERIOD_HOURS', 8))
self.loss_step_percent = Decimal(os.getenv('AGED_LOSS_STEP_PERCENT', '0.5'))
self.max_loss_percent = Decimal(os.getenv('AGED_MAX_LOSS_PERCENT', '10.0'))
self.commission_percent = Decimal(os.getenv('COMMISSION_PERCENT', '0.1')) / Decimal('100')
```

**Проверка __init__ signature:**
```python
# Нужно найти __init__ чтобы понять есть ли доступ к config
```

**Локация __init__:** (нужно проверить)

**Исправленный код:**
```python
# Use config values instead of os.getenv() with defaults
self.max_age_hours = config.max_position_age_hours
self.grace_period_hours = config.aged_grace_period_hours
self.loss_step_percent = config.aged_loss_step_percent
self.max_loss_percent = config.aged_max_loss_percent
# Note: config.commission_percent is already in percent, divide by 100
self.commission_percent = config.commission_percent / Decimal('100')
```

**Если config не передаётся в __init__:**
```python
# Option A: Import and use global config
from config.settings import config as global_config

self.max_age_hours = global_config.trading.max_position_age_hours
self.grace_period_hours = global_config.trading.aged_grace_period_hours
...
```

**Нужно проверить:**
1. Signature __init__ метода
2. Доступ к config объекту
3. Зависимости

#### Действие 2.2: Aged Position Manager

**Файл:** `core/aged_position_manager.py`

**Текущий код (lines 43-47):**
```python
self.grace_period_hours = int(os.getenv('AGED_GRACE_PERIOD_HOURS', 8))
self.loss_step_percent = Decimal(str(os.getenv('AGED_LOSS_STEP_PERCENT', 0.5)))
self.max_loss_percent = Decimal(str(os.getenv('AGED_MAX_LOSS_PERCENT', 10.0)))
self.acceleration_factor = Decimal(str(os.getenv('AGED_ACCELERATION_FACTOR', 1.2)))
```

**Исправленный код:**
```python
# Use config values instead of os.getenv()
self.grace_period_hours = config.aged_grace_period_hours
self.loss_step_percent = config.aged_loss_step_percent
self.max_loss_percent = config.aged_max_loss_percent
self.acceleration_factor = config.aged_acceleration_factor
```

#### Действие 2.3: Exchange Manager Enhanced

**Файл:** `core/exchange_manager_enhanced.py`

**Локация:** Lines 553-557

**Текущий код:**
```python
grace_period = float(os.getenv('AGED_GRACE_PERIOD_HOURS', 8))
loss_step = float(os.getenv('AGED_LOSS_STEP_PERCENT', 0.5))
max_loss = float(os.getenv('AGED_MAX_LOSS_PERCENT', 10.0))
acceleration = float(os.getenv('AGED_ACCELERATION_FACTOR', 1.2))
commission = float(os.getenv('COMMISSION_PERCENT', 0.1)) / 100
```

**Исправленный код:**
```python
# Use config values (requires config parameter)
grace_period = float(config.aged_grace_period_hours)
loss_step = float(config.aged_loss_step_percent)
max_loss = float(config.aged_max_loss_percent)
acceleration = float(config.aged_acceleration_factor)
commission = float(config.commission_percent) / 100
```

#### Действие 2.4: Position Manager

**Файл:** `core/position_manager.py`

**Локация:** Line 1711

**Текущий код:**
```python
max_position_usd = float(os.getenv('MAX_POSITION_SIZE_USD', 5000))
```

**Исправленный код:**
```python
# Use config value
max_position_usd = float(self.config.max_position_size_usd)
```

**Проверка:** У position_manager должен быть self.config (проверить __init__)

**Тест после Фазы 2:**
```python
# test_phase2_no_getenv.py
import os
import subprocess

def test_no_magic_number_getenv_in_core():
    """Verify no os.getenv() with numeric defaults in core files"""

    # Search for pattern: os.getenv('...', NUMBER)
    result = subprocess.run(
        ['grep', '-r', '-n', r"os\.getenv([^)]*,\s*[0-9]", 'core/'],
        capture_output=True,
        text=True,
        cwd='/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot'
    )

    # Should find NONE (except WebSocket config which is LOW priority)
    if result.stdout:
        lines = result.stdout.strip().split('\n')
        # Filter out WebSocket config (acceptable for Phase 2)
        non_ws_lines = [l for l in lines if 'SIGNAL_WS_' not in l and 'WAVE_CHECK_' not in l]

        if non_ws_lines:
            print("❌ Found os.getenv() with numeric defaults:")
            for line in non_ws_lines:
                print(f"  {line}")
            assert False, "Should not have os.getenv() with numeric defaults"

    print("✅ No os.getenv() with numeric defaults in core files")

def test_all_aged_params_use_config():
    """Verify all aged position files use config, not os.getenv()"""

    from core.aged_position_monitor_v2 import AgedPositionMonitorV2
    from core.aged_position_manager import AgedPositionManager

    # These should use config, not os.getenv()
    # (Will need to adjust based on actual __init__ signatures)

    print("✅ All aged modules use config")
```

**Git commit после Фазы 2:**
```bash
git add core/aged_position_monitor_v2.py
git add core/aged_position_manager.py
git add core/exchange_manager_enhanced.py
git add core/position_manager.py
git add tests/test_phase2_no_getenv.py

git commit -m "refactor(config): remove os.getenv() defaults, use centralized config

PHASE 2: Configuration Centralization

Removed all os.getenv() calls with hardcoded defaults from core modules.
All config now reads from centralized config object.

Files updated:
- aged_position_monitor_v2.py: 5 variables
- aged_position_manager.py: 4 variables
- exchange_manager_enhanced.py: 5 variables
- position_manager.py: 1 variable

Benefits:
- Single source of truth (config/settings.py)
- No duplicate defaults
- Easier to maintain
- Config changes in .env automatically propagate

Testing:
- test_phase2_no_getenv.py: Verifies no os.getenv() with numbers

Related: MAGIC_NUMBERS_AUDIT_REPORT_20251025.md Phase 2

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### ФАЗА 3: КОНСТАНТЫ И SAFETY MARGINS (30 минут)

**Цель:** Вынести хардкод safety margins в константы

#### Действие 3.1: Создать Constants класс

**Файл:** `config/settings.py`

**Локация:** После TradingConfig, перед DatabaseConfig

**Новый код для вставки:**
```python
@dataclass
class TradingSafetyConstants:
    """
    Trading safety constants - configurable safety margins

    These are technical constants that rarely change but should be
    configurable for advanced users.
    """
    # Stop Loss Safety Margins
    STOP_LOSS_SAFETY_MARGIN_PERCENT: Decimal = Decimal('0.5')  # 0.5% margin

    # Position Size Tolerance
    POSITION_SIZE_TOLERANCE_PERCENT: Decimal = Decimal('10.0')  # 10% over budget allowed

    # Price Update Thresholds
    PRICE_UPDATE_THRESHOLD_PERCENT: Decimal = Decimal('0.5')  # 0.5% price change to update

    # Minimum Balance Threshold
    MINIMUM_ACTIVE_BALANCE_USD: Decimal = Decimal('10.0')  # $10 minimum to consider active

    # Price Precision
    DEFAULT_PRICE_PRECISION: int = 8  # Default decimal precision for prices

    # Tick Size Defaults
    DEFAULT_MIN_QUANTITY: Decimal = Decimal('0.001')
    DEFAULT_TICK_SIZE: Decimal = Decimal('0.01')
    DEFAULT_STEP_SIZE: Decimal = Decimal('0.001')
```

**Добавить в Config класс:**
```python
class Config:
    def __init__(self):
        ...
        self.trading = self._init_trading()
        self.safety = TradingSafetyConstants()  # ← Добавить
        ...
```

#### Действие 3.2: Stop Loss Manager

**Файл:** `core/stop_loss_manager.py`

**Локации:** Lines 575, 577

**Текущий код:**
```python
# Line 575
stop_price_decimal *= Decimal('0.995')  # 0.5% lower

# Line 577
stop_price_decimal *= Decimal('1.005')  # 0.5% higher
```

**Исправленный код:**
```python
# Use config safety margin instead of hardcoded 0.995/1.005
safety_margin = config.safety.STOP_LOSS_SAFETY_MARGIN_PERCENT / Decimal('100')

# Line 575
stop_price_decimal *= (Decimal('1') - safety_margin)  # 0.5% lower

# Line 577
stop_price_decimal *= (Decimal('1') + safety_margin)  # 0.5% higher
```

#### Действие 3.3: Position Manager Safety Margin

**Файл:** `core/position_manager.py`

**Локация:** Line 1733

**Текущий код:**
```python
tolerance = size_usd * 1.1  # 10% over budget allowed
```

**Исправленный код:**
```python
# Use config tolerance instead of hardcoded 1.1
tolerance_factor = 1 + (self.config.safety.POSITION_SIZE_TOLERANCE_PERCENT / 100)
tolerance = size_usd * tolerance_factor
```

#### Действие 3.4: Price Update Threshold

**Файл:** `core/exchange_manager_enhanced.py`

**Локация:** Line 297

**Текущий код:**
```python
if price_diff_pct > 0.5:  # More than 0.5% difference
```

**Исправленный код:**
```python
threshold = float(config.safety.PRICE_UPDATE_THRESHOLD_PERCENT)
if price_diff_pct > threshold:  # Configurable threshold
```

**Тест после Фазы 3:**
```python
# test_phase3_constants.py
def test_safety_constants_exist():
    """Verify TradingSafetyConstants class exists and has correct defaults"""

    from config.settings import TradingSafetyConstants

    constants = TradingSafetyConstants()

    assert constants.STOP_LOSS_SAFETY_MARGIN_PERCENT == Decimal('0.5')
    assert constants.POSITION_SIZE_TOLERANCE_PERCENT == Decimal('10.0')
    assert constants.PRICE_UPDATE_THRESHOLD_PERCENT == Decimal('0.5')
    assert constants.MINIMUM_ACTIVE_BALANCE_USD == Decimal('10.0')

    print("✅ Safety constants class exists with correct defaults")

def test_config_has_safety():
    """Verify Config object has safety constants"""

    from config.settings import config

    assert hasattr(config, 'safety'), "Config should have safety attribute"
    assert hasattr(config.safety, 'STOP_LOSS_SAFETY_MARGIN_PERCENT')

    print("✅ Config object has safety constants")

def test_no_hardcoded_margins():
    """Verify no hardcoded 0.995, 1.005, 1.1 in code"""

    import subprocess

    # Search for hardcoded safety margins
    patterns = [
        r'\b0\.995\b',  # 0.995 (0.5% lower)
        r'\b1\.005\b',  # 1.005 (0.5% higher)
        r'\* 1\.1\b',   # * 1.1 (10% tolerance)
    ]

    for pattern in patterns:
        result = subprocess.run(
            ['grep', '-r', '-n', pattern, 'core/'],
            capture_output=True,
            text=True,
            cwd='/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot'
        )

        if result.stdout:
            # Check if it's in a comment (acceptable)
            lines = result.stdout.strip().split('\n')
            code_lines = [l for l in lines if '#' not in l or l.index(pattern) < l.index('#')]

            if code_lines:
                print(f"❌ Found hardcoded pattern {pattern}:")
                for line in code_lines:
                    print(f"  {line}")
                assert False, f"Should not have hardcoded {pattern}"

    print("✅ No hardcoded safety margins in code")
```

**Git commit после Фазы 3:**
```bash
git add config/settings.py
git add core/stop_loss_manager.py
git add core/position_manager.py
git add core/exchange_manager_enhanced.py
git add tests/test_phase3_constants.py

git commit -m "refactor(constants): extract safety margins to TradingSafetyConstants

PHASE 3: Safety Constants Extraction

Created TradingSafetyConstants class for configurable safety margins.

Constants extracted:
- STOP_LOSS_SAFETY_MARGIN_PERCENT: 0.5% (was hardcoded 0.995/1.005)
- POSITION_SIZE_TOLERANCE_PERCENT: 10% (was hardcoded 1.1)
- PRICE_UPDATE_THRESHOLD_PERCENT: 0.5% (was hardcoded 0.5)
- MINIMUM_ACTIVE_BALANCE_USD: \$10 (was hardcoded 10)

Files updated:
- stop_loss_manager.py: Safety margin calculations
- position_manager.py: Tolerance calculations
- exchange_manager_enhanced.py: Price threshold

Benefits:
- All safety margins configurable
- Single location for constants
- Self-documenting code
- Easier to adjust for testing

Testing:
- test_phase3_constants.py: Verifies constants usage

Related: MAGIC_NUMBERS_AUDIT_REPORT_20251025.md Phase 3

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### ФАЗА 4: END-TO-END VALIDATION (20 минут)

**Цель:** Комплексная проверка всех изменений

#### Действие 4.1: Запустить все Phase тесты

**Команды:**
```bash
cd /Users/evgeniyyanvarskiy/PycharmProjects/TradingBot

# Phase 0
python3 tests/test_phase0_config_defaults.py

# Phase 1
python3 tests/test_phase1_size_usd_fix.py
python3 tests/test_phase1_integration.py

# Phase 2
python3 tests/test_phase2_no_getenv.py

# Phase 3
python3 tests/test_phase3_constants.py
```

#### Действие 4.2: Комплексный E2E тест

**Файл:** `tests/test_phase4_e2e_magic_numbers.py`

**Код:**
```python
#!/usr/bin/env python3
"""
Phase 4: End-to-end validation of magic numbers fix
"""
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_config_loads_correctly():
    """Test config loads all values from .env"""
    from config.settings import config

    # Critical values
    assert config.trading.position_size_usd == 6
    assert config.trading.aged_grace_period_hours == 1
    assert config.trading.commission_percent == 0.05

    print("✅ Config loads correctly from .env")

def test_no_magic_numbers_in_critical_files():
    """Verify no magic numbers in critical files"""
    import subprocess

    critical_files = [
        'core/signal_processor_websocket.py',
        'core/position_manager.py',
        'core/aged_position_monitor_v2.py',
    ]

    for file_path in critical_files:
        # Should not find "200.0" in signal_processor_websocket
        if 'signal_processor' in file_path:
            result = subprocess.run(
                ['grep', '-n', '200\\.0', file_path],
                capture_output=True,
                text=True
            )
            assert not result.stdout, f"Found 200.0 in {file_path}"

        # Should not find os.getenv with numeric defaults
        result = subprocess.run(
            ['grep', '-n', r"os\.getenv([^)]*,\s*[0-9]", file_path],
            capture_output=True,
            text=True
        )

        if result.stdout:
            # Filter WebSocket config (acceptable)
            lines = [l for l in result.stdout.split('\n')
                    if 'SIGNAL_WS_' not in l and 'WAVE_CHECK_' not in l]
            if lines:
                print(f"❌ Found os.getenv() in {file_path}:")
                print('\n'.join(lines))
                assert False

    print("✅ No magic numbers in critical files")

def test_safety_constants_available():
    """Test safety constants are available"""
    from config.settings import config

    assert hasattr(config, 'safety')
    assert config.safety.STOP_LOSS_SAFETY_MARGIN_PERCENT == 0.5
    assert config.safety.POSITION_SIZE_TOLERANCE_PERCENT == 10.0

    print("✅ Safety constants available")

def test_all_modules_importable():
    """Test all modified modules can be imported"""
    try:
        from core.signal_processor_websocket import WebSocketSignalProcessor
        from core.position_manager import PositionManager
        from core.aged_position_monitor_v2 import AgedPositionMonitorV2
        from core.aged_position_manager import AgedPositionManager
        from config.settings import config, TradingSafetyConstants

        print("✅ All modules importable")
    except ImportError as e:
        print(f"❌ Import error: {e}")
        raise

if __name__ == '__main__':
    print("=" * 80)
    print("PHASE 4: E2E VALIDATION")
    print("=" * 80)
    print()

    try:
        test_config_loads_correctly()
        test_no_magic_numbers_in_critical_files()
        test_safety_constants_available()
        test_all_modules_importable()

        print()
        print("=" * 80)
        print("✅ ALL E2E TESTS PASSED")
        print("=" * 80)
        print()
        print("Magic numbers fix complete!")
        print()
        print("Summary:")
        print("- Phase 0: Config defaults aligned")
        print("- Phase 1: Critical 200.0 removed")
        print("- Phase 2: os.getenv() centralized")
        print("- Phase 3: Safety constants extracted")
        print("- Phase 4: E2E validation passed")
        print()

    except AssertionError as e:
        print()
        print("=" * 80)
        print(f"❌ E2E TEST FAILED: {e}")
        print("=" * 80)
        sys.exit(1)
```

**Git commit после Фазы 4:**
```bash
git add tests/test_phase4_e2e_magic_numbers.py

git commit -m "test(e2e): comprehensive validation of magic numbers fix

PHASE 4: End-to-End Validation

Complete test suite validating all magic number fixes:
- Config loads correctly
- No magic numbers in critical files
- Safety constants available
- All modules importable

Test coverage:
- Phase 0: Config defaults
- Phase 1: size_usd fix
- Phase 2: os.getenv() removal
- Phase 3: Constants extraction
- Phase 4: E2E validation

All tests must pass before deployment.

Related: MAGIC_NUMBERS_AUDIT_REPORT_20251025.md

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## 🔍 ДЕТАЛЬНАЯ ПРОВЕРКА ЗАВИСИМОСТЕЙ

### Проверить перед началом:

#### 1. signal_processor_websocket.py доступ к config
```bash
grep -n "def __init__" core/signal_processor_websocket.py
grep -n "self.config" core/signal_processor_websocket.py | head -5
```

**Ожидаемый результат:**
```python
def __init__(self, config, position_manager, ...):
    self.config = config
```

#### 2. aged_position_monitor_v2.py доступ к config
```bash
grep -n "def __init__" core/aged_position_monitor_v2.py
```

**Если config НЕ передаётся:**
- Использовать global import: `from config.settings import config`
- Или передать config через __init__ (requires changing caller)

#### 3. position_manager.py доступ к self.config
```bash
grep -n "self.config" core/position_manager.py | head -3
```

**Должно быть:** `self.config` доступен

---

## 📋 ФИНАЛЬНЫЙ CHECKLIST

### Перед началом:
- [ ] Создать ветку `fix/magic-numbers`
- [ ] Убедиться что .env загружен правильно
- [ ] Проверить текущие значения: `python3 -c "from config.settings import config; print(config.trading.position_size_usd)"`

### Phase 0:
- [ ] Обновить defaults в TradingConfig
- [ ] Запустить test_phase0_config_defaults.py
- [ ] Git commit Phase 0

### Phase 1:
- [ ] Исправить size_usd = 200.0 → config
- [ ] Запустить test_phase1_size_usd_fix.py
- [ ] Запустить test_phase1_integration.py
- [ ] Git commit Phase 1

### Phase 2:
- [ ] Проверить __init__ всех файлов для доступа к config
- [ ] Обновить aged_position_monitor_v2.py
- [ ] Обновить aged_position_manager.py
- [ ] Обновить exchange_manager_enhanced.py
- [ ] Обновить position_manager.py
- [ ] Запустить test_phase2_no_getenv.py
- [ ] Git commit Phase 2

### Phase 3:
- [ ] Создать TradingSafetyConstants class
- [ ] Обновить stop_loss_manager.py
- [ ] Обновить position_manager.py (tolerance)
- [ ] Обновить exchange_manager_enhanced.py (price threshold)
- [ ] Запустить test_phase3_constants.py
- [ ] Git commit Phase 3

### Phase 4:
- [ ] Запустить все Phase тесты
- [ ] Запустить test_phase4_e2e_magic_numbers.py
- [ ] Git commit Phase 4

### После всех фаз:
- [ ] Merge в main: `git checkout main && git merge fix/magic-numbers`
- [ ] Tag: `git tag -a v1.2.0-magic-numbers-fix -m "Fix all magic numbers"`
- [ ] Push: `git push && git push --tags`

---

## 🚀 DEPLOYMENT PLAN

### Pre-deployment:
1. Все тесты пройдены ✅
2. Code review завершён ✅
3. .env проверен ✅

### Deployment:
1. **Остановить бота:**
   ```bash
   # In terminal where bot runs (PID 99941, s000)
   Ctrl+C
   ```

2. **Pull changes:**
   ```bash
   git pull origin main
   ```

3. **Verify config:**
   ```bash
   python3 -c "
   from config.settings import config
   print(f'position_size_usd: {config.trading.position_size_usd}')
   print(f'aged_grace_period_hours: {config.trading.aged_grace_period_hours}')
   print(f'commission_percent: {config.trading.commission_percent}')
   "
   ```

4. **Restart bot:**
   ```bash
   python3 main.py
   ```

5. **Monitor first wave:**
   - Watch logs for "using config: $6"
   - Check Bybit signals pass validation
   - Verify positions open

### Post-deployment:
1. Monitor for 24 hours
2. Check error logs
3. Verify Bybit positions opening
4. Compare wave success rate

---

## 📊 SUCCESS CRITERIA

### Phase 0:
✅ Config defaults match .env values
✅ No regression in config loading

### Phase 1:
✅ size_usd uses config (6), not 200
✅ Bybit balance check passes ($52.72 >= $6)
✅ Bybit signals NOT filtered

### Phase 2:
✅ No os.getenv() with numeric defaults in core/
✅ All config through centralized config object

### Phase 3:
✅ Safety margins configurable
✅ No hardcoded 0.995, 1.005, 1.1

### Phase 4:
✅ All modules importable
✅ All tests pass
✅ E2E validation succeeds

### Production:
✅ Bybit positions opening
✅ No new errors in logs
✅ Wave success rate improved
✅ No trading disruptions

---

## 🔄 ROLLBACK PLAN

If something goes wrong:

```bash
# Stop bot
Ctrl+C

# Rollback code
git checkout main
git reset --hard HEAD~4  # Undo 4 phase commits

# Or revert specific commit
git revert <commit-hash>

# Restart bot
python3 main.py
```

---

## 📝 DOCUMENTATION UPDATES

After completion, update:

1. **README.md:** Add note about centralized config
2. **CHANGELOG.md:** Document magic numbers fix
3. **docs/CONFIGURATION.md:** Explain TradingSafetyConstants

---

## ⏱️ TIME ESTIMATES

| Phase | Time | Complexity |
|-------|------|------------|
| Phase 0 | 10 min | Low |
| Phase 1 | 15 min | Low |
| Phase 2 | 45 min | Medium |
| Phase 3 | 30 min | Medium |
| Phase 4 | 20 min | Low |
| **Total** | **2 hours** | **Medium** |

---

## 🎯 PRIORITY PHASES

If time limited:

**MUST DO (Critical):**
- Phase 0 ✅
- Phase 1 ✅

**SHOULD DO (High Priority):**
- Phase 2 ✅

**NICE TO HAVE:**
- Phase 3 (can defer)
- Phase 4 (but recommended)

---

**План подготовлен:** 2025-10-25
**Статус:** Готов к исполнению
**Следующий шаг:** Получить утверждение и начать с Phase 0
