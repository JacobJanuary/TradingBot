# 🚀 ДЕПЛОЙ FIX: Bybit UNIFIED Account Error

## ✅ FIX ПРИМЕНЁН И ПРОТЕСТИРОВАН ЛОКАЛЬНО

**Проблема:** `bybit {"retCode":10001,"retMsg":"accountType only support UNIFIED."}`
**Решение:** Изменён `defaultType` с `'future'` на `'unified'`
**Изменено:** 2 строки в `core/exchange_manager.py`

---

## 📊 ТЕСТ РЕЗУЛЬТАТЫ (Локально)

```
✅ defaultType set to: 'unified'
✅ accountType set to: 'UNIFIED'
✅ CCXT will send accountType: 'UNIFIED' to API
✅ SUCCESS! Bybit initialized without errors
```

---

## 🔄 КАК ЗАДЕПЛОИТЬ НА REMOTE SERVER

### Вариант 1: Git Pull (если используешь git)

```bash
# На remote сервере
cd ~/TradingBot
git pull origin main

# Перезапустить бота
pkill -f "python.*main.py"
python main.py --mode production
```

### Вариант 2: Ручное обновление файла

**На remote сервере отредактируй файл:**
```bash
nano ~/TradingBot/core/exchange_manager.py
```

**Найди и измени 2 строки:**

#### Изменение 1 (строка ~111):
```python
# БЫЛО:
exchange_options['options']['defaultType'] = 'future'  # For perpetual futures

# СТАЛО:
exchange_options['options']['defaultType'] = 'unified'  # For UNIFIED account (V5 API requirement)
```

#### Изменение 2 (строка ~129):
```python
# БЫЛО:
self.exchange.options['defaultType'] = 'future'

# СТАЛО:
self.exchange.options['defaultType'] = 'unified'
```

**Сохрани (Ctrl+O, Enter, Ctrl+X) и перезапусти:**
```bash
pkill -f "python.*main.py"
python main.py --mode production
```

---

## ✅ ПРОВЕРКА ЧТО FIX СРАБОТАЛ

После запуска бота на remote проверь логи:

```bash
tail -f logs/trading_bot.log
```

**Должно быть:**
```
INFO - Bybit testnet configured with UNIFIED account settings
INFO - Loaded XXXX markets from bybit
INFO - Connection to bybit verified  ← ✅ ЭТА СТРОКА = SUCCESS!
```

**НЕ должно быть:**
```
ERROR - Unexpected error: bybit {"retCode":10001,"retMsg":"accountType only support UNIFIED."...}  ← ❌ Если это есть, fix не применился
```

---

## 🎯 DIFF (для проверки)

```diff
diff --git a/core/exchange_manager.py b/core/exchange_manager.py
index ef0e730..84848bd 100644
--- a/core/exchange_manager.py
+++ b/core/exchange_manager.py
@@ -108,7 +108,7 @@ class ExchangeManager:
         elif self.name == 'bybit':
             # CRITICAL: Bybit V5 API requires UNIFIED account
             exchange_options['options']['accountType'] = 'UNIFIED'
-            exchange_options['options']['defaultType'] = 'future'  # For perpetual futures
+            exchange_options['options']['defaultType'] = 'unified'  # For UNIFIED account (V5 API requirement)

         self.exchange = exchange_class(exchange_options)

@@ -126,7 +126,7 @@ class ExchangeManager:

                 # Ensure UNIFIED account settings are applied
                 self.exchange.options['accountType'] = 'UNIFIED'
-                self.exchange.options['defaultType'] = 'future'
+                self.exchange.options['defaultType'] = 'unified'

                 logger.info(f"Bybit testnet configured with UNIFIED account settings")
```

---

## 🔍 ЕСЛИ ВСЁ ЕЩЁ НЕ РАБОТАЕТ

### 1. Проверь что изменения применились:
```bash
grep "defaultType.*unified" ~/TradingBot/core/exchange_manager.py
```

Должно вывести 2 строки с `'unified'`.

### 2. Проверь версию CCXT:
```bash
cd ~/TradingBot
source venv/bin/activate  # если используешь venv
pip show ccxt | grep Version
```

Должно быть `>= 4.0.0`

### 3. Проверь credentials:
```bash
grep "BYBIT_API_KEY" ~/TradingBot/.env | head -c 30
grep "BYBIT_TESTNET" ~/TradingBot/.env
```

Должно быть:
- `BYBIT_TESTNET=true`
- API key начинается правильно

---

## 📞 ЕСЛИ НУЖНА ПОМОЩЬ

Пришли мне:
1. Последние 50 строк лога:
   ```bash
   tail -50 ~/TradingBot/logs/trading_bot.log
   ```

2. Проверку что fix применён:
   ```bash
   grep -n "defaultType.*unified" ~/TradingBot/core/exchange_manager.py
   ```

---

**Дата:** 2025-10-17
**Статус:** ✅ FIX TESTED LOCALLY, READY FOR REMOTE DEPLOY
