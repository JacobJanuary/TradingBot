# 📋 SUMMARY: Type Error Fix Plan

## ОШИБКА
```
Failed to create monitoring event: invalid input for query argument $1: 2745 (expected str, got int)
```

## КОРНЕВАЯ ПРИЧИНА
`position.id` возвращает **int** (2745), НЕ конвертируется в **str** при создании `AgedPositionTarget`

## ВЛИЯНИЕ
- ❌ 4 вызова `create_aged_monitoring_event` передают int вместо str
- ❌ asyncpg отклоняет int для VARCHAR(255)
- ❌ Monitoring events НЕ записываются в базу

## РЕШЕНИЕ (1 СТРОКА!)

**Файл:** core/aged_position_monitor_v2.py:157

**БЫЛО:**
```python
position_id=getattr(position, 'id', symbol)
```

**ДОЛЖНО БЫТЬ:**
```python
position_id=str(getattr(position, 'id', symbol))
```

## ОБОСНОВАНИЕ
- ✅ Исправляет в ИСТОЧНИКЕ (1 место вместо 4)
- ✅ Гарантирует что position_id всегда str
- ✅ Соответствует dataclass аннотации
- ✅ str() безопасна для обоих случаев (int → str, str → str)

## ПРОВЕРКА
```bash
python3 tests/test_aged_monitoring_type_investigation.py
```

**Ожидаемый результат ПОСЛЕ ФИКСА:**
- ✅ Тест 4: "✅ position_id конвертируется через str()"
- ✅ Тест 5: "✅ Все вызовы корректны (используют str)"

## СВЯЗАННЫЕ ФИКСЫ
Это продолжение проблемы из предыдущих фиксов:
- ✅ create_aged_position - добавлен str() (коммит 0989488)
- ✅ mark_aged_position_closed - добавлен str() (коммит c74489a)
- ❌ **НЕ ИСПРАВЛЕНО**: create_aged_monitoring_event (4 вызова)

**ТА ЖЕ КОРНЕВАЯ ПРИЧИНА:** position.id возвращает int, база требует VARCHAR

## ДОКУМЕНТАЦИЯ
- 📄 Полное расследование: INVESTIGATION_AGED_MONITORING_TYPE_ERROR_20251023.md
- 🧪 Тесты: tests/test_aged_monitoring_type_investigation.py
