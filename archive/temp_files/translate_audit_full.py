#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Полный перевод отчета об аудите торгового бота на русский язык.
Сохраняет код, пути к файлам, git-хеши и техническую терминологию.
"""

import re

# Полный словарь для перевода
TRANSLATIONS = {
    # Заголовки и метаданные
    "COMPREHENSIVE TRADING BOT AUDIT REPORT": "КОМПЛЕКСНЫЙ ОТЧЕТ ОБ АУДИТЕ ТОРГОВОГО БОТА",
    "Bot Location:": "Расположение бота:",
    "Audit Date:": "Дата аудита:",
    "Code Size:": "Размер кода:",
    "Current Branch:": "Текущая ветка:",
    "lines": "строк",

    # Executive Summary
    "EXECUTIVE SUMMARY": "РЕЗЮМЕ",
    "Overall Assessment": "Общая оценка",
    "Code Quality:": "Качество кода:",
    "Critical Issues Found:": "Найдено критических проблем:",
    "Database Logging Completeness:": "Полнота логирования в БД:",
    "Architecture:": "Архитектура:",
    "Modular but with race condition risks": "Модульная, но с рисками состояний гонки",
    "CRITICAL GAP": "КРИТИЧЕСКИЙ ПРОБЕЛ",

    "Top 5 Must-Fix Issues": "Топ-5 критических проблем для исправления",
    "CRITICAL: Missing Event Logging Infrastructure": "КРИТИЧНО: Отсутствует инфраструктура логирования событий",
    "Only ~25% of critical events are logged to database": "Только ~25% критических событий логируются в базу данных",
    "HIGH: Race Condition in Trailing Stop vs Position Guard": "ВЫСОКО: Состояние гонки между Трейлинг-стопом и Position Guard",
    "Both modules can update SL simultaneously": "Оба модуля могут обновлять SL одновременно",
    "HIGH: Incomplete Atomic Operation Rollback": "ВЫСОКО: Неполный откат атомарной операции",
    "Entry orders not always closed on SL failure": "Entry-ордера не всегда закрываются при неудаче SL",
    "MEDIUM: No Health Check for Trailing Stop Manager": "СРЕДНЕ: Нет проверки здоровья для Trailing Stop Manager",
    "TS can silently fail without Protection Manager fallback": "TS может молча упасть без fallback Protection Manager",
    "MEDIUM: Zombie Order Detection Not Integrated": "СРЕДНЕ: Обнаружение зомби-ордеров не интегрировано",
    "Runs separately from main position flow": "Работает отдельно от основного потока позиций",

    "Recent Critical Fixes": "Недавние критические исправления",
    "Last 2 Weeks": "За последние 2 недели",
    "for SL calculation": "для расчета SL",
    "from string to int": "из строки в int",
    "after order execution": "после исполнения ордера",
    "before reusing existing SL": "перед переиспользованием существующего SL",
    "when closing position": "при закрытии позиции",

    # Section 1: Architecture
    "SECTION 1:": "РАЗДЕЛ 1:",
    "SYSTEM ARCHITECTURE": "АРХИТЕКТУРА СИСТЕМЫ",
    "High-Level Overview": "Общий обзор",
    "Data Flow": "Поток данных",
    "Position Opening:": "Открытие позиций:",
    "Position Monitoring:": "Мониторинг позиций:",
    "Key Components": "Ключевые компоненты",

    "Receives trading signals via WebSocket, implements wave-based trading logic": "Получает торговые сигналы через WebSocket, реализует торговую логику на основе волн",
    "Central orchestrator for position lifecycle": "Центральный оркестратор жизненного цикла позиции",
    "Guarantees Entry+SL atomicity": "Гарантирует атомарность Entry+SL",
    "Advanced trailing stop with activation logic": "Продвинутый трейлинг-стоп с логикой активации",
    "Reconciles exchange reality with database": "Согласовывает состояние биржи с базой данных",
    "Detects and removes orphaned orders": "Обнаруживает и удаляет осиротевшие ордера",
    "Database event logging": "Логирование событий в базу данных",
    "underutilized": "недоиспользуется",

    # Section 2: Database
    "SECTION 2:": "РАЗДЕЛ 2:",
    "DATABASE & EVENT LOGGING AUDIT": "АУДИТ БАЗЫ ДАННЫХ И ЛОГИРОВАНИЯ СОБЫТИЙ",
    "PRIORITY": "ПРИОРИТЕТ",
    "Database Schema Analysis": "Анализ схемы базы данных",
    "PostgreSQL Database with 2 main schemas:": "База данных PostgreSQL с 2 основными схемами:",
    "Schema:": "Схема:",
    "Table:": "Таблица:",
    "Source:": "Источник:",

    "CRITICAL ISSUE #1: Float vs Decimal": "КРИТИЧНАЯ ПРОБЛЕМА #1: Float vs Decimal",
    "All price/quantity fields use": "Все поля цен/количества используют",
    "instead of": "вместо",
    "Risk:": "Риск:",
    "Floating-point precision errors in financial calculations": "Ошибки точности с плавающей запятой в финансовых вычислениях",
    "Example:": "Пример:",
    "in float": "во float",
    "Impact:": "Влияние:",
    "Potential rounding errors in PnL calculations, SL prices": "Потенциальные ошибки округления в расчетах PnL, ценах SL",

    "Logs executed trades": "Логирует исполненные сделки",
    "Links to signals via signal_id": "Связывается с сигналами через signal_id",
    "Status tracking with OrderStatus enum": "Отслеживание статуса с перечислением OrderStatus",

    "Basic risk event logging": "Базовое логирование событий риска",
    "Fields:": "Поля:",
    "created_at": "время_создания",

    "System alerts": "Системные алерты",
    "Acknowledgment tracking": "Отслеживание подтверждений",

    "Performance metrics snapshots": "Снимки метрик производительности",
    "Balance, exposure, win rate tracking": "Отслеживание баланса, экспозиции, винрейта",

    "Trading signals from external system": "Торговые сигналы из внешней системы",
    "flag for signal consumption": "флаг для потребления сигнала",

    "EventLogger Tables": "Таблицы EventLogger",
    "NOT in models.py - created dynamically": "НЕ в models.py - создаются динамически",

    "Tracks database transactions": "Отслеживает транзакции базы данных",
    "Duration, affected rows, error tracking": "Длительность, затронутые строки, отслеживание ошибок",

    "Time-series performance data": "Данные производительности временных рядов",
    "Tags as JSONB for flexible querying": "Теги как JSONB для гибких запросов",

    # Event Logging Matrix
    "Event Logging Completeness Matrix": "Матрица полноты логирования событий",
    "Module": "Модуль",
    "Event": "Событие",
    "Logged to DB?": "Логируется в БД?",
    "Table": "Таблица",
    "Comments": "Комментарии",

    "Signal Processing": "Обработка сигналов",
    "Signal received": "Сигнал получен",
    "Signal validated": "Сигнал валидирован",
    "Signal filtered": "Сигнал отфильтрован",
    "stoplist": "стоп-лист",
    "Wave detected": "Волна обнаружена",
    "Wave processed": "Волна обработана",

    "Only file logger.info()": "Только файловый logger.info()",
    "No DB logging": "Нет логирования в БД",
    "Statistics not persisted": "Статистика не сохраняется",

    "Position Opening": "Открытие позиции",
    "Position create started": "Начало создания позиции",
    "Entry order placed": "Entry-ордер размещен",
    "Entry order filled": "Entry-ордер исполнен",
    "SL placement started": "Начало размещения SL",
    "SL placed successfully": "SL успешно размещен",
    "SL placement failed": "Размещение SL не удалось",
    "Position rollback": "Откат позиции",
    "Position opened": "Позиция открыта",
    "legacy": "устаревший",

    "No DB event": "Нет события в БД",
    "Only in atomic path": "Только в атомарном пути",
    "Non-atomic path not logged": "Неатомарный путь не логируется",

    "Trailing Stop": "Трейлинг-стоп",
    "TS instance created": "TS экземпляр создан",
    "Price update received": "Обновление цены получено",
    "Activation check": "Проверка активации",
    "TS activated": "TS активирован",
    "SL updated": "SL обновлен",
    "trailing": "трейлинг",
    "SL update failed": "Обновление SL не удалось",
    "Breakeven triggered": "Breakeven сработал",

    "Only debug logs": "Только debug-логи",
    "not persisted": "не сохраняется",
    "Only file logger.error()": "Только файловый logger.error()",

    "Position Protection": "Защита позиций",
    "SL check started": "Начало проверки SL",
    "Missing SL detected": "Обнаружен отсутствующий SL",
    "SL set": "SL установлен",
    "protection": "защита",
    "SL set failed": "Установка SL не удалась",

    "Only file logger.warning()": "Только файловый logger.warning()",
    "DB update but no event log": "Обновление БД, но нет лога события",

    "Position Closure": "Закрытие позиции",
    "Position closed": "Позиция закрыта",

    "Position Synchronization": "Синхронизация позиций",
    "Sync started": "Начало синхронизации",
    "Phantom detected": "Обнаружена фантомная позиция",
    "Phantom closed": "Фантом закрыт",
    "Missing position added": "Добавлена отсутствующая позиция",
    "Sync completed": "Синхронизация завершена",

    "Zombie Cleanup": "Очистка зомби",
    "Zombie detected": "Обнаружен зомби",
    "Zombie cancelled": "Зомби отменен",
    "Zombie cancel failed": "Отмена зомби не удалась",

    "System Events": "Системные события",
    "Bot started": "Бот запущен",
    "Bot stopped": "Бот остановлен",
    "Critical error": "Критическая ошибка",

    "Summary:": "Итог:",
    "Total critical events:": "Всего критических событий:",
    "Events logged to DB:": "События, залогированные в БД:",
    "only in atomic path": "только в атомарном пути",
    "Logging completeness:": "Полнота логирования:",

    # Missing Event Logs
    "Missing Event Logs": "Отсутствующие логи событий",
    "CRITICAL": "КРИТИЧНО",
    "Must-Have Event Logs": "Обязательные логи событий",
    "HIGH PRIORITY": "ВЫСОКИЙ ПРИОРИТЕТ",
    "HIGHEST PRIORITY": "НАИВЫСШИЙ ПРИОРИТЕТ",

    "Signal Processing Events": "События обработки сигналов",
    "with full signal data": "с полными данными сигнала",
    "validation result": "результат валидации",
    "filtered reason": "причина фильтрации",
    "detection": "обнаружение",
    "execution summary": "резюме исполнения",

    "Trailing Stop Events": "События Трейлинг-стопа",
    "created": "создан",
    "symbol, entry_price, activation_price": "symbol, цена_входа, цена_активации",
    "Every price update": "Каждое обновление цены",
    "timestamp, price, state": "timestamp, цена, состояние",
    "Activation triggered": "Активация сработала",
    "old SL, new SL, profit %": "старый SL, новый SL, profit %",
    "update": "обновление",
    "old price, new price, reason": "старая цена, новая цена, причина",
    "exchange response, retry count": "ответ биржи, счетчик попыток",
    "removed": "удален",

    "Position Protection Events": "События защиты позиций",
    "Protection check started": "Начало проверки защиты",
    "position list": "список позиций",
    "set by protection manager": "установлен менеджером защиты",
    "position, SL price": "позиция, цена SL",
    "retries": "попытки",

    "Position Closure Events": "События закрытия позиций",
    "Position close triggered": "Закрытие позиции инициировано",
    "reason: SL/TP/manual": "причина: SL/TP/вручную",
    "Close order placed": "Ордер закрытия размещен",
    "Close order filled": "Ордер закрытия исполнен",
    "Position closed in DB": "Позиция закрыта в БД",
    "final PnL": "финальный PnL",

    "Synchronization Events": "События синхронизации",
    "exchange, position count": "биржа, количество позиций",
    "DB state, exchange state": "состояние БД, состояние биржи",
    "details": "детали",
    "stats": "статистика",

    "System Health Events": "События здоровья системы",
    "WebSocket reconnection": "Переподключение WebSocket",
    "Database connection loss/recovery": "Потеря/восстановление соединения с БД",
    "API rate limit hit": "Превышен лимит API",
    "Critical errors": "Критические ошибки",

    # Database Issues
    "Database Issues Found": "Найденные проблемы базы данных",
    "CRITICAL Issues": "КРИТИЧНЫЕ проблемы",
    "Float vs Decimal for Financial Data": "Float vs Decimal для финансовых данных",
    "Location:": "Расположение:",
    "Issue:": "Проблема:",
    "All price fields use FLOAT": "Все поля цен используют FLOAT",
    "32/64-bit floating point": "32/64-битная плавающая запятая",
    "Precision loss in financial calculations": "Потеря точности в финансовых расчетах",
    "Fix:": "Исправление:",
    "Migrate to DECIMAL(20, 8) for all price/quantity fields": "Мигрировать на DECIMAL(20, 8) для всех полей цен/количества",

    "No Foreign Key Constraints": "Нет ограничений внешних ключей",
    "Relationships defined in SQLAlchemy but commented out": "Отношения определены в SQLAlchemy, но закомментированы",
    "Orphaned records": "Осиротевшие записи",
    "trades without positions, etc.": "сделки без позиций и т.д.",

    "Missing Indexes": "Отсутствующие индексы",
    "Missing index on": "Отсутствует индекс на",
    "frequently queried": "часто запрашиваемое",
    "for filtering": "для фильтрации",
    "Missing composite index on": "Отсутствует составной индекс на",

    "No Database-Level Timestamp Tracking": "Нет отслеживания времени на уровне БД",
    "columns exist but not always updated": "колонки существуют, но не всегда обновляются",
    "No triggers to auto-update timestamps": "Нет триггеров для автообновления временных меток",

    "EventLogger Tables Created Dynamically": "Таблицы EventLogger создаются динамически",
    "Tables created in code": "Таблицы создаются в коде",
    "No schema versioning/migration": "Нет версионирования схемы/миграций",
    "Schema drift between environments": "Расхождение схемы между окружениями",

    "MEDIUM Issues": "СРЕДНИЕ проблемы",
    "No Transaction Isolation for Critical Operations": "Нет изоляции транзакций для критических операций",
    "Atomic operations use asyncpg but no explicit transaction control in most places": "Атомарные операции используют asyncpg, но нет явного контроля транзакций в большинстве мест",
    "Partial updates on connection loss": "Частичные обновления при потере соединения",

    "No Data Retention Policy": "Нет политики хранения данных",
    "Events table will grow indefinitely": "Таблица событий будет расти бесконечно",
    "No partitioning or archival strategy": "Нет стратегии партиционирования или архивации",

    "Connection Pool Settings": "Настройки пула соединений",
    "Pool size:": "Размер пула:",
    "min, max": "мин, макс",
    "May be insufficient under high load": "Может быть недостаточно при высокой нагрузке",

    # Section 3: Trailing Stop
    "SECTION 3:": "РАЗДЕЛ 3:",
    "TRAILING STOP DEEP ANALYSIS": "ГЛУБОКИЙ АНАЛИЗ ТРЕЙЛИНГ-СТОПА",
    "How It Works": "Как это работает",
    "Step by Step": "Пошагово",
    "File:": "Файл:",

    "Initialization": "Инициализация",
    "Create TrailingStopInstance dataclass": "Создать dataclass TrailingStopInstance",
    "Set state = INACTIVE": "Установить state = INACTIVE",
    "Calculate activation_price": "Рассчитать activation_price",
    "If initial_stop provided → place stop order on exchange": "Если initial_stop предоставлен → разместить стоп-ордер на бирже",
    "Store in self.trailing_stops[symbol]": "Сохранить в self.trailing_stops[symbol]",

    "State Machine:": "Машина состояний:",
    "create": "создание",
    "breakeven": "безубыток",

    "Price Update Flow": "Поток обновления цены",
    "IF symbol not in trailing_stops:": "ЕСЛИ symbol нет в trailing_stops:",
    "Not monitored": "Не отслеживается",
    "Thread-safe": "Потокобезопасно",
    "Update highest/lowest price": "Обновить highest/lowest price",
    "State-based logic": "Логика на основе состояний",

    "Activation Logic": "Логика активации",
    "Check breakeven first": "Сначала проверить breakeven",
    "if configured": "если настроено",
    "Check activation price": "Проверить цену активации",
    "should_activate = False": "should_activate = False",
    "Time-based activation": "Активация по времени",
    "optional": "опционально",
    "position_age": "возраст_позиции",

    "Activation Action": "Действие активации",
    "Calculate initial trailing stop price": "Рассчитать начальную цену трейлинг-стопа",
    "Update stop order on exchange": "Обновить стоп-ордер на бирже",
    "Mark ownership": "Отметить владение",
    "for conflict prevention": "для предотвращения конфликтов",

    "Trailing Logic": "Логика трейлинга",
    "Trail below highest price": "Трейлить ниже highest price",
    "Only update if new stop is HIGHER than current": "Обновить только если новый стоп ВЫШЕ текущего",
    "Trail above lowest price": "Трейлить выше lowest price",
    "Only update if new stop is LOWER than current": "Обновить только если новый стоп НИЖЕ текущего",
    "Update exchange": "Обновить биржу",

    "Exchange Update": "Обновление на бирже",
    "Cancel old order": "Отменить старый ордер",
    "Small delay": "Небольшая задержка",
    "Place new order": "Разместить новый ордер",
    "Failed to update stop order:": "Не удалось обновить стоп-ордер:",

    # Issues Found
    "Issues Found": "Найденные проблемы",
    "Race Condition: Cancel → Create Window": "Состояние гонки: окно Cancel → Create",
    "Between": "Между",
    "and": "и",
    "price can trigger old order": "цена может сработать старый ордер",
    "Scenario:": "Сценарий:",
    "Price=$100, Current SL=$95": "Цена=$100, Текущий SL=$95",
    "Price=$105, Update triggered": "Цена=$105, Обновление инициировано",
    "SUCCESS": "УСПЕШНО",
    "flash crash": "внезапное падение",
    "No SL exists! Position unprotected!": "SL не существует! Позиция незащищена!",
    "Too late": "Слишком поздно",
    "Position can be unprotected for 100-500ms": "Позиция может быть незащищена 100-500мс",
    "Probability:": "Вероятность:",
    "Low but catastrophic": "Низкая, но катастрофическая",
    "Use exchange-native modify_order if available, or place new order BEFORE canceling old": "Использовать нативный modify_order биржи если доступно, или размещать новый ордер ДО отмены старого",

    "No Database Logging of TS Events": "Нет логирования событий TS в БД",
    "entire file": "весь файл",
    "All TS state changes only logged to file": "Все изменения состояния TS только логируются в файл",
    "Missing events:": "Отсутствующие события:",
    "Activation": "Активация",
    "Every SL update": "Каждое обновление SL",
    "Update failures": "Неудачи обновления",
    "Impossible to reconstruct what happened in production": "Невозможно восстановить что произошло в продакшене",
    "Add EventLogger calls for all critical events": "Добавить вызовы EventLogger для всех критических событий",

    "Conflicting SL Management: TS vs Protection Manager": "Конфликтное управление SL: TS vs Protection Manager",
    "Both modules can place/update SL orders independently": "Оба модуля могут размещать/обновлять SL-ордера независимо",
    "TS places": "TS размещает",
    "Protection Manager checks positions": "Protection Manager проверяет позиции",
    "Protection Manager sees SL order": "Protection Manager видит SL-ордер",
    "queries exchange": "запрашивает биржу",
    "Protection Manager thinks": "Protection Manager думает",
    "all good": "все хорошо",
    "BUT SIMULTANEOUSLY:": "НО ОДНОВРЕМЕННО:",
    "TS updates": "TS обновляет",
    "Protection Manager's view is stale!": "Представление Protection Manager устарело!",

    "Fix Applied:": "Применено исправление:",
    "Recent commit": "Недавний коммит",
    "adds": "добавляет",
    "field": "поле",
    "TS marks ownership on activation:": "TS отмечает владение при активации:",
    "Protection Manager skips TS-managed positions:": "Protection Manager пропускает позиции, управляемые TS:",
    "not yet in code?": "еще не в коде?",
    "REMAINING ISSUE:": "ОСТАЮЩАЯСЯ ПРОБЛЕМА:",
    "Protection Manager skip logic not yet implemented!": "Логика пропуска Protection Manager еще не реализована!",

    "TS Can Silently Fail Without Fallback": "TS может молча упасть без fallback",
    "If TS module crashes or stops updating, positions have no SL protection": "Если модуль TS падает или перестает обновляться, позиции не имеют защиты SL",
    "Current mitigation:": "Текущее смягчение:",
    "Protection Manager checks every 2 minutes": "Protection Manager проверяет каждые 2 минуты",
    "Problem:": "Проблема:",
    "2-minute gap is too long in volatile markets": "2-минутный промежуток слишком долгий на волатильных рынках",
    "Recent fix:": "Недавнее исправление:",
    "Commit": "Коммит",
    "tracking": "отслеживание",
    "But:": "Но:",
    "Fallback logic not yet implemented!": "Логика fallback еще не реализована!",

    "HIGH Issues": "ВЫСОКИЕ проблемы",
    "Bybit: Multiple SL Orders Problem": "Bybit: Проблема множественных SL-ордеров",
    "Method only handles Binance, not Bybit": "Метод обрабатывает только Binance, не Bybit",
    "For Bybit:": "Для Bybit:",
    "creates": "создает",
    "order #A": "ордер #A",
    "order #B": "ордер #B",
    "Both exist simultaneously!": "Оба существуют одновременно!",
    "When SL triggers, TWO orders execute → double position closure": "Когда SL срабатывает, ДВА ордера исполняются → двойное закрытие позиции",
    "Extend _cancel_protection_sl method to support Bybit": "Расширить метод _cancel_protection_sl для поддержки Bybit",

    "No Idempotency for SL Orders": "Нет идемпотентности для SL-ордеров",
    "If _place_stop_order() fails but order was actually placed, retry creates duplicate": "Если _place_stop_order() не удается, но ордер был фактически размещен, повтор создает дубликат",
    "No order ID tracking before confirmation": "Нет отслеживания ID ордера до подтверждения",
    "Query existing orders before placing new one": "Запросить существующие ордера перед размещением нового",

    "Memory Leak: TrailingStopInstance Never Cleaned": "Утечка памяти: TrailingStopInstance никогда не очищается",
    "only called on close": "вызывается только при закрытии",
    "If position closed externally (manual, liquidation), TS instance remains": "Если позиция закрыта внешне (вручную, ликвидация), экземпляр TS остается",
    "Memory grows over time": "Память растет со временем",
    "Periodic cleanup of stale TS instances": "Периодическая очистка устаревших экземпляров TS",

    "Configuration Hardcoded": "Конфигурация захардкожена",
    "hardcoded": "захардкожено",
    "disabled": "отключено",
    "No runtime configuration changes possible": "Нет возможности изменения конфигурации во время выполнения",
    "Move to database or config file": "Переместить в базу данных или конфигурационный файл",

    "No Rate Limiting for Exchange Updates": "Нет ограничения скорости для обновлений биржи",
    "Rapid price updates can trigger many SL updates": "Быстрые обновления цены могут вызвать много обновлений SL",
    "No throttling mechanism": "Нет механизма троттлинга",
    "Exchange rate limits, API bans": "Лимиты биржи, баны API",
    "Add cooldown period between updates": "Добавить период отдыха между обновлениями",
    "e.g., 5 seconds minimum": "напр., минимум 5 секунд",

    "Decimal Precision Issues": "Проблемы точности Decimal",
    "Conversion from float → Decimal loses precision": "Преобразование из float → Decimal теряет точность",
    "Should validate price precision matches exchange requirements": "Следует валидировать соответствие точности цены требованиям биржи",
    "Use exchange precision info to round properly": "Использовать информацию о точности биржи для правильного округления",

    # Comparison with Best Practices
    "Comparison with Best Practices": "Сравнение с лучшими практиками",
    "How freqtrade Does It": "Как это делает freqtrade",
    "freqtrade Approach:": "Подход freqtrade:",
    "hypothetical": "гипотетический",
    "Check if update needed": "Проверить нужно ли обновление",
    "Calculate new SL": "Рассчитать новый SL",
    "ATOMIC: Update exchange THEN database": "АТОМАРНО: Обновить биржу ЗАТЕМ базу данных",

    "Key Differences:": "Ключевые различия:",
    "Feature": "Функция",
    "This Bot": "Этот бот",
    "freqtrade": "freqtrade",
    "Better?": "Лучше?",
    "Update method": "Метод обновления",
    "Cancel + Create": "Cancel + Create",
    "Modify order": "Modify order",
    "Atomicity": "Атомарность",
    "Not atomic": "Неатомарно",
    "Atomic with DB": "Атомарно с БД",
    "Rate limiting": "Ограничение скорости",
    "None": "Нет",
    "Per-exchange limits": "Лимиты по биржам",
    "Event logging": "Логирование событий",
    "File only": "Только файл",
    "DB + File": "БД + Файл",
    "Recovery": "Восстановление",
    "Protection Manager": "Protection Manager",
    "Built-in reconciliation": "Встроенное согласование",
    "Configuration": "Конфигурация",
    "Hardcoded": "Захардкожено",
    "Per-pair in DB": "По парам в БД",
    "Testing": "Тестирование",
    "Minimal": "Минимальное",
    "Extensive unit tests": "Обширные unit-тесты",

    "What This Bot Does Better:": "Что этот бот делает лучше:",
    "AsyncIO-native": "Нативный AsyncIO",
    "freqtrade uses threads": "freqtrade использует потоки",
    "Separation of concerns": "Разделение ответственности",
    "TS module independent": "Модуль TS независимый",
    "WebSocket price updates": "Обновления цены через WebSocket",
    "freqtrade polls REST API": "freqtrade опрашивает REST API",

    # Общие термины для перевода
    "SECTION": "РАЗДЕЛ",
    "days": "дней",
    "day": "день",
    "hours": "часов",
    "minutes": "минут",
    "seconds": "секунд",
}


def should_skip_translation(line: str) -> bool:
    """Определяет, нужно ли пропустить перевод строки."""
    stripped = line.strip()

    # Пропускаем пустые строки
    if not stripped:
        return True

    # Пропускаем начало/конец блоков кода
    if stripped.startswith('```'):
        return True

    # Пропускаем ASCII-графику
    if any(c in stripped for c in ['┌', '│', '├', '└', '─', '┐', '┘', '┤', '┬', '┴', '▼']):
        return True

    # Пропускаем пути к файлам
    if '.py:' in line or '.sql:' in line or 'database/' in line or 'core/' in line or 'protection/' in line:
        return True

    # Пропускаем git-хеши
    if re.search(r'\b[0-9a-f]{7,40}\b', stripped):
        return True

    # Пропускаем строки, состоящие только из кода
    if stripped.startswith(('def ', 'class ', 'async ', 'await ', 'if ', 'for ', 'while ', 'try:', 'except', 'return')):
        return True

    return False


def translate_text(text: str, in_code_block: bool) -> str:
    """Переводит текст, применяя словарь переводов."""
    if in_code_block or should_skip_translation(text):
        return text

    result = text

    # Применяем переводы от более длинных к более коротким
    for eng, rus in sorted(TRANSLATIONS.items(), key=lambda x: len(x[0]), reverse=True):
        if eng in result:
            result = result.replace(eng, rus)

    return result


def main():
    """Основная функция перевода."""
    input_file = '/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/COMPREHENSIVE_TRADING_BOT_AUDIT_REPORT.md'
    output_file = '/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/COMPREHENSIVE_TRADING_BOT_AUDIT_REPORT_RU.md'

    print("🚀 Начинаю полный перевод отчета об аудите...")
    print(f"   Исходный файл: {input_file}")
    print(f"   Целевой файл: {output_file}")

    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    print(f"   Всего строк: {len(lines)}")
    print(f"   Словарь переводов: {len(TRANSLATIONS)} фраз\n")

    translated_lines = []
    in_code_block = False
    translated_count = 0
    skipped_count = 0

    for i, line in enumerate(lines):
        # Отслеживаем блоки кода
        if line.strip().startswith('```'):
            in_code_block = not in_code_block
            translated_lines.append(line)
            continue

        # Переводим строку
        if in_code_block or should_skip_translation(line):
            translated_lines.append(line)
            skipped_count += 1
        else:
            translated = translate_text(line, in_code_block)
            translated_lines.append(translated)
            if translated != line:
                translated_count += 1

        # Прогресс
        if (i + 1) % 500 == 0:
            print(f"   ⏳ Обработано: {i + 1}/{len(lines)} строк ({(i+1)*100//len(lines)}%)")

    # Записываем результат
    with open(output_file, 'w', encoding='utf-8') as f:
        f.writelines(translated_lines)

    print(f"\n✅ Перевод завершен!")
    print(f"   📝 Всего строк: {len(translated_lines)}")
    print(f"   🔄 Переведено: {translated_count} строк")
    print(f"   ⏭️  Пропущено: {skipped_count} строк (код, пути, хеши)")
    print(f"   💾 Результат сохранен: {output_file}")


if __name__ == '__main__':
    main()
