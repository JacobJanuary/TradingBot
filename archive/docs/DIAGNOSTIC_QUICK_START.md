# 🔍 Zombie Manager Diagnostics - Quick Start

## 📊 Текущий статус диагностики

**Запущено:** 2025-10-15 02:39:29
**Длительность:** 10 минут
**Завершится:** ~02:49:29
**PID процесса:** 92336

---

## 📁 Файлы результатов

После завершения диагностики будут созданы:

1. **Отчёт**: `zombie_diagnostics_report_YYYYMMDD_HHMMSS.txt`
2. **Данные**: `zombie_diagnostics_data_YYYYMMDD_HHMMSS.json`
3. **Лог**: `logs/zombie_diagnostics_YYYYMMDD_HHMMSS.log`

---

## 🔍 Что проверить в отчёте

### 🔴 КРИТИЧНЫЕ проблемы (требуют немедленного исправления)

Ищите секции с маркировкой **🔴 CRITICAL**:

```
🔴 CRITICAL ISSUES (требуют немедленного исправления)

  1. protective_order_deleted_with_open_position
     Protective order XXX (STOP_MARKET) deleted while position was open

     ❌ ЭТО БАГ! Stop-loss был удалён пока позиция открыта!
```

**Что делать:**
- Немедленно проверить код по location из AUDIT_REPORT.md
- Применить critical fix из отчёта
- Перезапустить бота с фиксом

---

### 🟠 ВЫСОКИЙ РИСК

Ищите секции с маркировкой **🟠 HIGH**:

```
🟠 HIGH PRIORITY ISSUES

  1. reduce_only_deleted_with_position
     ReduceOnly order XXX deleted while position was open
```

**Что делать:**
- Проанализировать причину
- Применить high priority fix в течение недели

---

### ✅ Нормальное поведение

```
✅ OK: Order without position (legitimate zombie)
✅ OK: Protective order for closed position (legitimate zombie)
```

Это нормально - зомби-ордера для закрытых позиций должны удаляться.

---

## 📈 Как читать snapshot сравнение

### Пример корректного удаления:

```
Deleted order: 12345
  Symbol: BTCUSDT
  Type: STOP_MARKET
  Position before: ❌ NO
  Position after: ❌ NO

  ✅ OK: Protective order for closed position (legitimate zombie)
```

**Интерпретация:** Позиция была закрыта, SL был удалён - это ПРАВИЛЬНО.

---

### Пример КРИТИЧНОЙ ошибки:

```
Deleted order: 67890
  Symbol: ETHUSDT
  Type: STOP_MARKET
  Position before: ✅ YES (LONG 0.1 ETH)
  Position after: ✅ YES (LONG 0.1 ETH)

  🚨 CRITICAL ISSUE: Protective order deleted with open position!
```

**Интерпретация:** Позиция ОТКРЫТА, но SL был удалён - это **БАГ**!

---

## 🔧 Следующие шаги после диагностики

### Если найдены CRITICAL issues:

1. **СТОП** - не используй бота в production
2. Прочитай полный ZOMBIE_MANAGER_AUDIT_REPORT.md
3. Найди секцию с соответствующим CRITICAL issue
4. Примени предложенный FIX
5. Перезапусти диагностику для проверки

### Если найдены HIGH issues:

1. Запланируй исправления на эту неделю
2. Используй бота, но с повышенным мониторингом
3. Проверяй логи каждые 2-4 часа

### Если всё ✅ OK:

1. Поздравляю! Zombie Manager работает корректно
2. Рекомендуется запускать диагностику еженедельно
3. Следи за метриками в production

---

## 📊 Метрики для мониторинга

После каждого запуска диагностики проверяй:

| Метрика | Норма | Тревога |
|---------|-------|---------|
| Zombie orders deleted | 0-5 | > 10 |
| Positions without SL | 0 | > 0 |
| Critical issues | 0 | > 0 |
| High issues | 0-1 | > 2 |
| API errors | 0-2 | > 5 |

---

## 🚨 Когда бить тревогу

Немедленно останови бота если:

- ❌ Найден critical issue: protective_order_deleted_with_open_position
- ❌ Найден critical issue: reduce_only_deleted_with_position
- ❌ Более 10 zombie orders за один цикл
- ❌ Позиция осталась без SL после cleanup

---

## 📞 Контакты для эскалации

**Критичные баги:**
1. Проверь ZOMBIE_MANAGER_AUDIT_REPORT.md
2. Найди соответствующий CRITICAL FIX
3. Примени исправление
4. Перезапусти диагностику

**Вопросы по диагностике:**
- Лог файл: `logs/zombie_diagnostics_YYYYMMDD_HHMMSS.log`
- JSON данные: `zombie_diagnostics_data_YYYYMMDD_HHMMSS.json`

---

## 🔄 Рекомендуемая частота запуска

- **После каждого изменения кода:** Обязательно
- **В production:** 1 раз в неделю
- **На testnet:** Каждый день
- **После инцидента:** Немедленно

---

## 💡 Быстрая диагностика (1 минута)

Для быстрой проверки используй:

```bash
# Быстрая проверка за 1 минуту
python zombie_manager_monitor.py --duration 1

# Проверить только Bybit
python zombie_manager_monitor.py --duration 1 --exchanges bybit
```

---

**Создано:** 2025-10-15
**Версия:** 1.0
**Автор:** Claude Code Audit

---

## 📝 Checklist после завершения диагностики

- [ ] Отчёт прочитан
- [ ] Critical issues проверены (если есть)
- [ ] High issues задокументированы
- [ ] Snapshot данные сохранены
- [ ] Если найдены баги - применены fixes
- [ ] Перезапущена диагностика для проверки
- [ ] Результаты зафиксированы в git

