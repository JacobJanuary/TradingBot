# 📚 Documentation Index

Индекс актуальной документации TradingBot.

---

## 🎯 Актуальные документы (корень проекта)

### Wave Execution Fixes (2025-10-19) ✅

**Проблема:** Критические баги в выполнении волн
**Статус:** ✅ Исправлено и верифицировано в production

1. **[WAVE_EXECUTION_BUG_REPORT.md](WAVE_EXECUTION_BUG_REPORT.md)**
   - Полный анализ проблемы
   - БАГ #1 (P0): event_logger блокировал выполнение волны
   - БАГ #2 (P1): maxNotionalValue=0 неправильно блокировал торговлю
   - БАГ #3 (P2): FLRUSDT zero liquidity (testnet issue)

2. **[FIX_PLAN_WAVE_EXECUTION_BUGS.md](FIX_PLAN_WAVE_EXECUTION_BUGS.md)**
   - Детальный план исправления (6 фаз)
   - Пошаговые инструкции
   - Rollback strategy

3. **[WAVE_EXECUTION_FIX_SUMMARY.md](WAVE_EXECUTION_FIX_SUMMARY.md)**
   - Executive summary
   - Технические изменения
   - Deployment instructions
   - Ожидаемые улучшения: +100% эффективность

4. **[WAVE_EXECUTION_FIX_VERIFICATION.md](WAVE_EXECUTION_FIX_VERIFICATION.md)**
   - Production verification report
   - Результаты первой волны после deployment
   - Success metrics: 71% эффективность (vs 25% до исправления)

---

### Monitoring & Operations

5. **[MONITORING_README.md](MONITORING_README.md)**
   - Документация системы мониторинга
   - Health checks
   - Metrics и alerting

---

## 📁 Архив (docs/archive/)

Старые investigation reports и временные документы перемещены в:

**[docs/archive/investigations_2025-10-19/](docs/archive/investigations_2025-10-19/)**

Включает:
- Bybit balance investigations (6 файлов)
- Trailing stop hang investigations (3 файла)
- Multi-exchange validation reports (2 файла)
- Wave execution investigations (1 файл)
- Other temporary reports (5 файлов)

См. [docs/archive/investigations_2025-10-19/README.md](docs/archive/investigations_2025-10-19/README.md) для деталей.

---

## 🚀 Quick Start

### Для разработчиков:

1. **Понять текущее состояние системы:**
   - Читай: [WAVE_EXECUTION_FIX_VERIFICATION.md](WAVE_EXECUTION_FIX_VERIFICATION.md)
   - Последние исправления работают отлично ✅

2. **Если нужно внести изменения:**
   - Следуй: [FIX_PLAN_WAVE_EXECUTION_BUGS.md](FIX_PLAN_WAVE_EXECUTION_BUGS.md) (как пример подхода)
   - GOLDEN RULE: "If it ain't broke, don't fix it"

3. **Мониторинг:**
   - См: [MONITORING_README.md](MONITORING_README.md)

---

## 📊 Key Metrics (после исправлений)

| Метрика | До | После | Улучшение |
|---------|-----|-------|-----------|
| Сигналов выполнено | 2/4 (50%) | 7/7 (100%) | +250% |
| Позиций открыто | 1/4 (25%) | 5/7 (71%) | +184% |
| Блокировок волны | Да | Нет | ✅ |
| maxNotional errors | Да | Нет | ✅ |

---

## 🔗 Полезные ссылки

- **GitHub:** [JacobJanuary/TradingBot](https://github.com/JacobJanuary/TradingBot)
- **Issues:** Создавай issue для багов/улучшений
- **Branches:**
  - `main` - production
  - `backup/before-wave-execution-fix-2025-10-19` - backup point

---

**Последнее обновление:** 2025-10-19 19:05
