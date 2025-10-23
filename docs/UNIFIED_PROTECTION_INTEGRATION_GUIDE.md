# UNIFIED PROTECTION: МИНИМАЛЬНАЯ ИНТЕГРАЦИЯ

## 🎯 ПРИНЦИП: Хирургическая точность

**НЕ МЕНЯЕМ работающий код - только ДОБАВЛЯЕМ новый через feature flag**

---

## 📁 НОВЫЕ ФАЙЛЫ (не трогают существующий код)

```
✅ websocket/unified_price_monitor.py       - Централизованный мониторинг цен
✅ core/protection_adapters.py              - Адаптеры для существующих модулей
✅ core/aged_position_monitor_v2.py         - Новая реализация Aged (V2)
✅ core/position_manager_unified_patch.py   - Патч для интеграции
```

---

## 🔧 МИНИМАЛЬНЫЕ ИЗМЕНЕНИЯ в position_manager.py

### 1. Добавить импорт (в начало файла):
```python
# UNIFIED PROTECTION PATCH
from core.position_manager_unified_patch import (
    init_unified_protection,
    handle_unified_price_update,
    check_and_register_aged_positions
)
```

### 2. В `__init__` после инициализации trailing_managers (~строка 290):
```python
        # UNIFIED PROTECTION (if enabled via env)
        self.unified_protection = init_unified_protection(self)
```

### 3. В `_on_position_update` после обновления current_price (~строка 1805):
```python
            # UNIFIED PRICE UPDATE (if enabled)
            if self.unified_protection:
                await handle_unified_price_update(
                    self.unified_protection,
                    symbol,
                    position.current_price
                )
```

### 4. В `monitor_positions` добавить проверку aged (~строка 512):
```python
                # Check aged positions for unified protection
                if self.unified_protection:
                    await check_and_register_aged_positions(self, self.unified_protection)
```

**ВСЁ! Больше НИЧЕГО не меняем!**

---

## 🚀 АКТИВАЦИЯ

### 1. Добавить в .env:
```bash
# UNIFIED PROTECTION (disabled by default)
USE_UNIFIED_PROTECTION=false

# Aged Position V2 settings (same as V1)
MAX_POSITION_AGE_HOURS=3
AGED_GRACE_PERIOD_HOURS=8
AGED_LOSS_STEP_PERCENT=0.5
AGED_MAX_LOSS_PERCENT=10.0
```

### 2. Запуск в тестовом режиме:
```bash
# Сначала тест без изменений
USE_UNIFIED_PROTECTION=false python main.py

# Потом включить
USE_UNIFIED_PROTECTION=true python main.py
```

---

## 📊 ПРОВЕРКА РАБОТЫ

### Логи при старте:
```
✅ Если USE_UNIFIED_PROTECTION=true:
"Initializing unified protection system..."
"✅ Unified protection initialized successfully"

❌ Если USE_UNIFIED_PROTECTION=false:
"Unified protection disabled (USE_UNIFIED_PROTECTION=false)"
```

### Логи в работе:
```
# TrailingStop через unified:
"TrailingStop subscribed to BTCUSDT via unified monitor"

# Aged positions:
"Position ETHUSDT registered as aged"
"📍 Aged position added: ETHUSDT (age=4.2h, phase=grace, target=$1234.56)"
"🎯 Aged target reached for ETHUSDT"
```

---

## 🔄 ОТКАТ (если что-то пошло не так)

### Вариант 1: Отключить через env (БЕЗ изменения кода)
```bash
USE_UNIFIED_PROTECTION=false python main.py
```

### Вариант 2: Удалить изменения в position_manager.py
```bash
# Откатить только position_manager.py
git checkout -- core/position_manager.py

# Новые файлы не мешают - можно оставить
```

---

## ⚠️ ВАЖНО

1. **Старый aged_position_manager.py продолжает работать!**
   - При USE_UNIFIED_PROTECTION=false используется старая версия
   - При USE_UNIFIED_PROTECTION=true старая версия НЕ вызывается

2. **TrailingStop работает в обоих режимах!**
   - При USE_UNIFIED_PROTECTION=false - напрямую
   - При USE_UNIFIED_PROTECTION=true - через адаптер

3. **Нулевой риск для production!**
   - По умолчанию выключено
   - Можно отключить в любой момент
   - Откат за секунды

---

## 📈 МОНИТОРИНГ

### Проверка статистики:
```python
# В любом месте кода
if position_manager.unified_protection:
    from core.position_manager_unified_patch import get_unified_stats
    stats = get_unified_stats(position_manager.unified_protection)
    print(stats)
```

### Что увидим:
```json
{
    "enabled": true,
    "price_monitor": {
        "update_count": 1234,
        "error_count": 0,
        "symbols_tracked": 15,
        "total_subscribers": 30
    },
    "aged_monitor": {
        "monitored": 3,
        "market_closes": 2,
        "grace_closes": 1
    }
}
```

---

## 🧪 ТЕСТИРОВАНИЕ

### 1. Запустить БЕЗ изменений:
```bash
USE_UNIFIED_PROTECTION=false python main.py
# Убедиться что всё работает как раньше
```

### 2. Включить unified БЕЗ aged:
```bash
USE_UNIFIED_PROTECTION=true
MAX_POSITION_AGE_HOURS=9999  # Отключить aged detection
python main.py
# TrailingStop должен работать через unified
```

### 3. Полный тест:
```bash
USE_UNIFIED_PROTECTION=true
MAX_POSITION_AGE_HOURS=3
python main.py
# И TrailingStop, и Aged должны работать
```

---

## 🎯 РЕЗУЛЬТАТ

### Что получаем:
- ✅ Единый WebSocket поток для всех protection модулей
- ✅ Aged V2 с MARKET ордерами вместо LIMIT
- ✅ Полная совместимость с существующим кодом
- ✅ Возможность отката за секунды

### Чего НЕ трогаем:
- ❌ НЕ меняем логику TrailingStop
- ❌ НЕ меняем aged_position_manager.py
- ❌ НЕ меняем WebSocket streams
- ❌ НЕ меняем БД структуру (пока)

---

## 📋 CHECKLIST для внедрения

- [ ] Создать backup: `cp core/position_manager.py core/position_manager.py.backup`
- [ ] Добавить 4 строки импорта и вызовов в position_manager.py
- [ ] Установить `USE_UNIFIED_PROTECTION=false` в .env
- [ ] Запустить и убедиться что всё работает
- [ ] Изменить на `USE_UNIFIED_PROTECTION=true`
- [ ] Проверить логи инициализации
- [ ] Мониторить 24 часа
- [ ] Если всё OK - оставить включенным

---

*Документация подготовлена: 2025-10-23*
*Принцип: МИНИМАЛЬНЫЕ изменения, МАКСИМАЛЬНЫЙ контроль*