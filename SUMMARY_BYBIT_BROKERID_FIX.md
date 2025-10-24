# 📋 SUMMARY: Bybit Error 170003 Fix

## ОШИБКА
```
bybit {"retCode":170003,"retMsg":"An unknown parameter was sent."}
```

## КОРНЕВАЯ ПРИЧИНА
CCXT добавляет `brokerId: 'CCXT'` автоматически → Bybit V5 API НЕ поддерживает этот параметр → Error 170003

## ПОЛНАЯ ЦЕПОЧКА
```
CCXT default: brokerId='CCXT'
    ↓
ExchangeManager НЕ отключает
    ↓
create_order() вызывается
    ↓
CCXT добавляет brokerId в HTTP запрос
    ↓
Bybit V5: "unknown parameter" ❌
```

## РЕШЕНИЕ (1 СТРОКА!)

**Файл:** `core/exchange_manager.py:111`

**ДОБАВИТЬ после строки 111:**
```python
exchange_options['options']['brokerId'] = ''  # Disable CCXT default
```

**Полный контекст:**
```python
elif self.name == 'bybit':
    # CRITICAL: Bybit V5 API requires UNIFIED account
    exchange_options['options']['accountType'] = 'UNIFIED'
    exchange_options['options']['defaultType'] = 'future'
    exchange_options['options']['brokerId'] = ''  # ← ДОБАВИТЬ ЭТУ СТРОКУ
```

## ОБОСНОВАНИЕ
- ✅ Отключает автоматическое добавление brokerId
- ✅ Применяется ко ВСЕМ ордерам (market, limit, etc.)
- ✅ 1 изменение исправляет все проблемы
- ✅ Bybit V5 API НЕ поддерживает brokerId в create_order

## ПРОВЕРКА
```bash
python3 tests/test_bybit_brokerId_fix_validation.py
```

**Ожидаемый результат ПОСЛЕ ФИКСА:**
- ✅ Исходный код: brokerId отключен
- ✅ Runtime: brokerId = ''
- ✅ Сравнение: 'CCXT' → ''

## ДОКАЗАТЕЛЬСТВА

**Тест 1: CCXT по умолчанию**
```python
exchange = ccxt.bybit()
print(exchange.options['brokerId'])  # 'CCXT' ❌
```

**Тест 2: После фикса**
```python
exchange = ccxt.bybit({'options': {'brokerId': ''}})
print(exchange.options['brokerId'])  # '' ✅
```

**Тест 3: Документация Bybit**
- Проверено: https://bybit-exchange.github.io/docs/v5/order/create-order
- Результат: brokerId **НЕ УПОМИНАЕТСЯ** ❌

## ВЛИЯНИЕ
**До:** ❌ Все market ордера на Bybit падают с Error 170003
**После:** ✅ Market ордера работают

## ДОКУМЕНТАЦИЯ
- 📄 Полное расследование: INVESTIGATION_BYBIT_ERROR_170003_20251023.md
- 🧪 Тесты: tests/test_bybit_brokerId_fix_validation.py
