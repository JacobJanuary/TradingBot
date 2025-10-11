# 🔍 РАССЛЕДОВАНИЕ: Дублирование позиций волны 03:20

## Факты из логов

### Ожидалось: 4 позиции
| Signal ID | Symbol | Exchange |
|-----------|--------|----------|
| 12330443 | AKEUSDT | binance |
| 12330417 | KASUSDT | binance |
| 12330424 | BIDUSDT | binance |
| 12330439 | SKYUSDT | binance |

### Получено: 7 позиций в БД
| ID | Symbol | Opened (UTC) | Signal ID | Delay |
|----|--------|--------------|-----------|-------|
| 274 | AKEUSDT | 23:21:10.127 | 12330443 | - |
| 275 | KASUSDT | 23:21:12.819 | 12330417 | - |
| 276 | KASUSDT | 23:21:12.854 | 12330417 | +34ms |
| 277 | BIDUSDT | 23:21:17.750 | 12330424 | - |
| 278 | BIDUSDT | 23:21:18.057 | 12330424 | +307ms |
| 279 | SKYUSDT | 23:21:22.885 | 12330439 | - |
| 280 | SKYUSDT | 23:21:23.031 | 12330439 | +146ms |

## Анализ логов

### Ключевые моменты:

```
03:20:00.002 - 🔒 Wave 2025-10-10T23:00:00+00:00 marked as processing
03:21:03.104 - ✅ Found 4 RAW signals for wave
03:21:05.879 - 🌊 Wave processing complete: ✅ 4 successful
03:21:05.879 - ✅ Wave validated: 4 signals with buffer

03:21:06.747 - Opening position: AKEUSDT (1st call)
03:21:09.620 - Market info not found for AKEUSDT (2nd call!)
03:21:10.127 - ✅ Position opened: AKEUSDT (ID 274)

03:21:12.164 - Opening position: KASUSDT (1st call)
03:21:14.707 - Market info not found for KASUSDT (2nd call!)
03:21:15.086 - ✅ Position opened: KASUSDT (ID 275)

03:21:17.023 - Opening position: BIDUSDT (1st call)
03:21:19.908 - Market info not found for BIDUSDT (2nd call!)
03:21:20.412 - ✅ Position opened: BIDUSDT (ID 277)

03:21:22.318 - Opening position: SKYUSDT (1st call)
03:21:25.069 - Market info not found for SKYUSDT (2nd call!)
03:21:26.033 - ✅ Position opened: SKYUSDT (ID 280)

03:21:26.033 - 🎯 Wave complete: 4 positions opened
```

### Обнаруженное противоречие:

1. **Лог "Opening position"** - показан 1 раз для каждого символа
2. **Лог "Market info not found"** - показан 2 раза для каждого символа! (этот лог внутри open_position())
3. **Лог "✅ Position opened"** - показан 1 раз для каждого
4. **База данных** - 7 записей вместо 4!

### Пропущенные ID в логах успешных позиций:
- AKEUSDT: ID 274 ✅
- KASUSDT: ID 275 ✅ (ID 276 создан НО не залогирован!)
- BIDUSDT: ID 277 ✅ (ID 278 создан НО не залогирован!)
- SKYUSDT: ID 280 ✅ (ID 279 создан НО не залогирован!)

## Гипотезы

### ❌ Гипотеза 1: asyncio.gather() с параллельной обработкой
**Опровергнута:** Код обрабатывает сигналы последовательно:
```python
# signal_processor_websocket.py:283
for idx, signal_result in enumerate(final_signals):
    success = await self._execute_signal(signal)  # AWAIT - последовательно
    if idx < len(final_signals) - 1:
        await asyncio.sleep(1)  # задержка между сигналами
```

### ❌ Гипотеза 2: Волна обрабатывалась дважды
**Опровергнута:** Лог показывает:
- Только один раз "🔒 Wave marked as processing"
- Только один раз "Wave processing complete: ✅ 4 successful"
- Только один раз "🎯 Wave complete: 4 positions opened"

### ✅ Гипотеза 3: ДВОЙНОЙ вызов position_manager.open_position()
**Подтверждена частично:**
- "Market info not found" (внутри open_position()) показан 2 раза для каждого
- Но "Opening position" (первая строка open_position()) показан только 1 раз
- Значит КАКАЯ-ТО версия open_position() вызывается дважды

### 🔍 Гипотеза 4: Разные пути к созданию позиции
**Требует проверки:** Может быть есть два разных метода создания позиции?

## Архитектура обработки волн

### Путь обработки сигнала:

```
signal_processor_websocket.py
├─ _wave_monitoring_loop() 
│  └─ wave_processor.process_wave_signals()  ← Валидация (WaveSignalProcessor)
│     └─ _process_single_signal()  ← Просто модифицирует signal dict, НЕ открывает позицию
│  
│  └─ for signal in final_signals:           ← Основной цикл выполнения
│     └─ _execute_signal(signal)             ← ЗДЕСЬ открывается позиция
│        └─ position_manager.open_position() ← ЗДЕСЬ создается запись в БД
```

### Вопрос: Откуда второй вызов?

**Возможные источники:**
1. ❓ `_process_single_signal()` в WaveSignalProcessor ТОЖЕ вызывает open_position?
2. ❓ Где-то есть повторный вызов _execute_signal?
3. ❓ open_position вызывается из другого места параллельно?

## Следующие шаги расследования

1. ✅ Проверить что делает `_process_single_signal()` в wave_signal_processor.py
2. ✅ Найти ВСЕ места где вызывается `position_manager.open_position()`
3. ✅ Проверить логи на наличие повторных вызовов `_execute_signal`
4. ✅ Понять почему "Opening position" показан 1 раз, а "Market info" 2 раза
