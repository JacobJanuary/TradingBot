# 🔍 РАССЛЕДОВАНИЕ: Почему AKEUSDT получает обновления но пропускается

**Дата:** 2025-10-23
**Проблема из логов:**
```
2025-10-23 10:22:42,471 - core.position_manager - INFO - 📊 Position update: AKE/USDT:USDT → AKEUSDT, mark_price=0.0016127
2025-10-23 10:22:42,471 - core.position_manager - INFO -   → Skipped: AKEUSDT not in tracked positions
```

---

## 🎯 ПРИЧИНА ПРОБЛЕМЫ

**Позиция AKEUSDT была открыта на бирже, но ещё не загружена в систему!**

---

## 🔄 КАК СЕЙЧАС РАБОТАЕТ СИСТЕМА

### 1. **Синхронизация позиций** (каждые 2 минуты)
```python
# position_manager.py, строка 237
self.sync_interval = 120  # 2 минуты

# Каждые 2 минуты:
start_periodic_sync() → sync_exchange_positions() →
→ Загружает позиции с биржи → Добавляет в self.positions
```

### 2. **WebSocket обновления** (реалтайм)
```python
# position_manager.py, строки 1810-1812
if not symbol or symbol not in self.positions:
    logger.info(f"  → Skipped: {symbol} not in tracked positions")
    return  # ❌ ИГНОРИРУЕТ ОБНОВЛЕНИЕ!
```

---

## ⏰ ВРЕМЕННАЯ ДИАГРАММА ПРОБЛЕМЫ

```
10:20:00 - Последняя синхронизация (всё OK)
10:21:30 - Открыта новая позиция AKEUSDT на бирже
10:21:31 - WebSocket начал слать обновления для AKEUSDT
10:21:31 - ❌ Обновления ИГНОРИРУЮТСЯ (позиции нет в системе)
10:22:00 - ❌ Следующая синхронизация ещё через 30 секунд!
10:22:42 - ❌ Логи показывают "Skipped: AKEUSDT not in tracked positions"
10:22:00 - ✅ Синхронизация, AKEUSDT наконец загружена
```

**РЕЗУЛЬТАТ:** Позиция без защиты 90 секунд! 🚨

---

## 🔴 КРИТИЧЕСКИЕ РИСКИ

1. **До 2 минут БЕЗ ЗАЩИТЫ**
   - Нет Stop Loss
   - Нет Trailing Stop
   - Нет Aged мониторинга

2. **Потеря WebSocket данных**
   - Ценные обновления цен игнорируются
   - История изменений теряется

3. **Несоответствие с биржей**
   - Биржа думает что мы следим за позицией
   - Но мы её игнорируем

---

## 💡 РЕШЕНИЕ

### Вариант 1: **Автоматическая загрузка при WebSocket** (РЕКОМЕНДУЕТСЯ)

Изменить `_on_position_update` в position_manager.py:

```python
async def _on_position_update(self, data: Dict):
    symbol = normalize_symbol(data.get('symbol'))

    if not symbol:
        return

    # НОВОЕ: Если позиции нет - загрузить с биржи
    if symbol not in self.positions:
        logger.warning(f"⚠️ New position {symbol} detected via WebSocket")

        # Определить биржу из WebSocket данных
        exchange_name = data.get('exchange') or self._detect_exchange_from_ws(data)

        # Загрузить позицию с биржи
        exchange = self.exchanges.get(exchange_name)
        if exchange:
            positions = await exchange.fetch_positions()
            for pos in positions:
                if normalize_symbol(pos['symbol']) == symbol:
                    # Добавить позицию в систему
                    await self._add_position_from_exchange(pos, exchange_name)
                    logger.info(f"✅ Position {symbol} loaded from exchange")
                    break

    # Продолжить обычную обработку
    if symbol in self.positions:
        # ... существующий код обновления ...
```

### Вариант 2: **Уменьшить интервал синхронизации**

```python
self.sync_interval = 30  # Было 120 секунд
```

**Минус:** Всё ещё до 30 секунд задержки

### Вариант 3: **Триггерная синхронизация**

При обнаружении неизвестной позиции - сразу запускать синхронизацию:

```python
if symbol not in self.positions:
    logger.warning(f"Unknown position {symbol}, triggering sync")
    await self.sync_exchange_positions(exchange_name)
```

---

## 📊 СТАТИСТИКА ПРОБЛЕМЫ

Анализ логов может показать:
- Сколько позиций открывается между синхронизациями
- Среднее время до защиты новых позиций
- Количество пропущенных обновлений

**Команда для поиска в логах:**
```bash
grep "Skipped.*not in tracked positions" trading_bot.log | wc -l
```

---

## 🎯 РЕКОМЕНДАЦИИ

1. **СРОЧНО:** Реализовать Вариант 1 - автозагрузку позиций
2. **Добавить метрику:** `new_position_detection_delay`
3. **Алерт:** При обнаружении новой позиции через WebSocket
4. **Логирование:** Детальное логирование всех новых позиций

---

## 📈 ОЖИДАЕМЫЙ РЕЗУЛЬТАТ ПОСЛЕ ИСПРАВЛЕНИЯ

- **Время до защиты:** < 1 секунды (вместо 2 минут)
- **Пропущенные обновления:** 0 (вместо сотен)
- **Позиции без защиты:** 0

---

**Подготовил:** AI Assistant
**Статус:** 🔴 КРИТИЧЕСКАЯ ПРОБЛЕМА БЕЗОПАСНОСТИ
**Приоритет:** МАКСИМАЛЬНЫЙ