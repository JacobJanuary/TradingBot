# 🚀 Quick Start - Age Detector Fix Implementation

**ВАЖНО:** Это краткая версия для быстрого старта. Полный план: `AGE_DETECTOR_FIX_IMPLEMENTATION_PLAN.md`

---

## Перед началом (5 минут)

```bash
# 1. Проверить текущее состояние
git status
git branch

# 2. Убедиться что на main и всё закоммичено
git checkout main
git pull origin main

# 3. Создать feature branch
git checkout -b fix/age-detector-order-proliferation

# 4. Открыть план и progress tracker
# - AGE_DETECTOR_FIX_IMPLEMENTATION_PLAN.md (детальный план)
# - IMPLEMENTATION_PROGRESS.md (отслеживание прогресса)
```

---

## Последовательность выполнения

### ✅ Phase 0: Подготовка (30 мин)
```bash
# Создать backup
mkdir -p backups/age_detector_fix_20251015/
cp core/aged_position_manager.py backups/age_detector_fix_20251015/
cp core/exchange_manager_enhanced.py backups/age_detector_fix_20251015/

# Создать baseline метрики
echo "Baseline Date: $(date)" > AGE_DETECTOR_BASELINE.md

# Коммит
git add backups/ AGE_DETECTOR_BASELINE.md
git commit -m "📊 Phase 0: Baseline for Age Detector fixes"
```

**✅ Критерий успеха:** Backup создан, baseline зафиксирован

---

### 🔴 Phase 1: Унифицированный метод (1.5 часа)

**Файл:** `core/exchange_manager_enhanced.py`

**Что делать:**
1. Добавить метод `create_or_update_exit_order()` после строки ~180
2. Добавить unit-тесты в `tests/unit/test_exchange_manager_enhanced.py`

**Проверка:**
```bash
pytest tests/unit/test_exchange_manager_enhanced.py -v
```

**Коммит:**
```bash
git add core/exchange_manager_enhanced.py tests/unit/
git commit -m "✨ Phase 1: Add create_or_update_exit_order() unified method"
```

**✅ Критерий успеха:** Метод работает, тесты зелёные

---

### 🔴 Phase 2: Рефакторинг AgedPositionManager (2 часа)

**Файл:** `core/aged_position_manager.py`

**Что делать:**
1. Заменить метод `_update_single_exit_order()` (строки 266-432)
2. Упростить с ~167 строк до ~40 строк
3. Удалить ручную проверку дубликатов
4. Использовать `create_or_update_exit_order()`

**Проверка:**
```bash
# Синтаксис
python -m py_compile core/aged_position_manager.py

# Тесты
pytest tests/unit/ -k aged -v

# Integration (15 мин с testnet)
# Временно: MAX_POSITION_AGE_HOURS=0.1 в .env
python main.py &
BOT_PID=$!
timeout 900 python monitor_age_detector.py logs/trading_bot.log
kill $BOT_PID
```

**Коммит:**
```bash
git add core/aged_position_manager.py
git commit -m "🔧 Phase 2: Refactor AgedPositionManager to use unified method"
```

**✅ Критерий успеха:** Нет order proliferation в мониторинге, дедупликация работает

---

### 🟡 Phase 3: Кэш-инвалидация (1 час)

**Файл:** `core/exchange_manager_enhanced.py`

**Что делать:**
1. Улучшить `safe_cancel_with_verification()` (строки ~277-320)
2. Добавить `await self._invalidate_order_cache(symbol)` после отмены
3. Увеличить sleep до 0.5 сек

**Коммит:**
```bash
git add core/exchange_manager_enhanced.py
git commit -m "🔧 Phase 3: Improve order cache invalidation timing"
```

**✅ Критерий успеха:** Тесты зелёные

---

### 🟡 Phase 4: Geo-ограничения (1 час)

**Файл:** `core/aged_position_manager.py`

**Что делать:**
1. Добавить обработку `ccxt.ExchangeError` в `process_aged_position()`
2. Проверять код '170209' (geo-restriction)
3. Сохранять `skip_until` в `managed_positions`

**Коммит:**
```bash
git add core/aged_position_manager.py
git commit -m "🛡️ Phase 4: Handle geographic restrictions gracefully"
```

---

### 🟢 Phase 5: Profit-taking (1.5 часа)

**Файл:** `core/aged_position_manager.py`

**Что делать:**
1. Добавить метод `_close_with_market_order()`
2. Добавить проверку прибыльности в `process_aged_position()`
3. Если прибыль > 0.2%: market close

**Коммит:**
```bash
git add core/aged_position_manager.py config/settings.py
git commit -m "✨ Phase 5: Add profit-taking logic for aged positions"
```

---

### 🟢 Phase 6: Валидация ордеров (1 час)

**Файл:** `core/exchange_manager_enhanced.py`

**Что делать:**
1. Добавить метод `_validate_order_state()`
2. Использовать перед отменой в `create_or_update_exit_order()`

**Коммит:**
```bash
git add core/exchange_manager_enhanced.py
git commit -m "🔍 Phase 6: Add order state validation before cancellation"
```

---

### 🔵 Phase 7: Мониторинг (1 час)

**Файлы:** `core/aged_position_manager.py`, `main.py`

**Что делать:**
1. Добавить метод `_detect_duplicate_orders()`
2. Вызывать каждые 5 минут из главного цикла

**Коммит:**
```bash
git add core/aged_position_manager.py main.py
git commit -m "📊 Phase 7: Add duplicate orders monitoring"
```

---

### 🎉 Phase 8: Финальное тестирование (3 часа)

**Что делать:**
1. Запустить 2ч integration test в testnet
2. Собрать метрики
3. Создать документацию

**Команды:**
```bash
# 2-часовой тест
python main.py --testnet &
timeout 7200 python monitor_age_detector.py logs/trading_bot.log

# Анализ результатов
ls -lt age_detector_diagnostic_*.json | head -1

# Создать документацию
# - PHASE8_FINAL_METRICS.md
# - BEFORE_AFTER_COMPARISON.md
# - CHANGELOG_AGE_DETECTOR.md
```

**Коммит:**
```bash
git add PHASE8_*.md BEFORE_AFTER_COMPARISON.md CHANGELOG_AGE_DETECTOR.md
git commit -m "📝 Phase 8: Final testing and documentation"
```

**✅ Критерий успеха:**
- `proliferation_issues` = []
- `duplicates_prevented` > 0
- Все метрики улучшены

---

### 📦 Phase 9: Deployment (1 час + 24ч мониторинг)

**Что делать:**
1. Создать PR
2. Code review
3. Merge в main
4. Deploy в production
5. Мониторинг 24ч

**Команды:**
```bash
# Push branch
git push origin fix/age-detector-order-proliferation

# Создать PR через GitHub/GitLab
# После approval:
git checkout main
git merge --squash fix/age-detector-order-proliferation
git push origin main

# На production:
sudo systemctl restart trading-bot
python monitor_age_detector.py logs/trading_bot.log
```

---

## ⚡ Быстрая проверка статуса

```bash
# Текущая фаза
cat IMPLEMENTATION_PROGRESS.md | grep "Current Phase" -A 5

# Какие коммиты уже сделаны
git log --oneline | grep "Phase"

# Сколько фаз осталось
git log --oneline | grep "Phase" | wc -l
# Ожидается: 9 коммитов (по одному на фазу)

# Текущее состояние тестов
pytest tests/ -v --tb=short

# Последние логи Age Detector
tail -100 logs/trading_bot.log | grep -i "aged\|exit order"
```

---

## 🐛 Если что-то пошло не так

**Откат последней фазы:**
```bash
git reset --hard HEAD~1
git clean -fd
```

**Откат к началу (Фаза 0):**
```bash
git reset --hard HEAD~[ЧИСЛО_ФАЗ]
# ИЛИ
git checkout main
git branch -D fix/age-detector-order-proliferation
git checkout -b fix/age-detector-order-proliferation
```

**Проверка что сломалось:**
```bash
# Запустить все тесты
pytest tests/ -v

# Проверить импорты
python -c "from core.aged_position_manager import AgedPositionManager"
python -c "from core.exchange_manager_enhanced import EnhancedExchangeManager"

# Проверить синтаксис
python -m py_compile core/*.py
```

---

## 📋 Ежедневный чеклист

**Начало работы:**
- [ ] Проверить `git status`
- [ ] Проверить `IMPLEMENTATION_PROGRESS.md` - какая фаза текущая
- [ ] Прочитать план текущей фазы в `AGE_DETECTOR_FIX_IMPLEMENTATION_PLAN.md`
- [ ] Убедиться что тесты проходят: `pytest tests/ -v`

**Во время работы:**
- [ ] Делать частые локальные коммиты
- [ ] Тестировать изменения по мере написания
- [ ] Обновлять `IMPLEMENTATION_PROGRESS.md` по мере выполнения задач

**Конец фазы:**
- [ ] Все задачи фазы выполнены
- [ ] Все тесты проходят
- [ ] Создан git commit с правильным сообщением
- [ ] Обновлён `IMPLEMENTATION_PROGRESS.md`
- [ ] Сделан короткий перерыв перед следующей фазой

---

## 🎯 Цель всего проекта

**Было:**
- 7,165 ордеров создано за 23 часа
- 0 случаев предотвращения дубликатов
- 30+ ордеров на один символ

**Будет:**
- ~14 ордеров создано за 23 часа (по одному на символ)
- >15 случаев предотвращения дубликатов
- Максимум 2-3 ордера на символ (обновления при изменении цены)

**Снижение создания ордеров: 95%**

---

## 📚 Полезные ссылки

- **Полный план:** `AGE_DETECTOR_FIX_IMPLEMENTATION_PLAN.md` (детали каждой фазы)
- **Прогресс:** `IMPLEMENTATION_PROGRESS.md` (отслеживание)
- **Аудит:** `AGE_DETECTOR_AUDIT_REPORT_RU.md` (описание багов)
- **Краткая сводка:** `AGE_DETECTOR_AUDIT_SUMMARY_RU.md` (executive summary)

---

**Готовы начать? Начните с Phase 0! 🚀**

```bash
git checkout -b fix/age-detector-order-proliferation
mkdir -p backups/age_detector_fix_20251015/
# ... следуйте инструкциям Phase 0 выше
```
