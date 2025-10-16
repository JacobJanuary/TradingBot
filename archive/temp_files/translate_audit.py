#!/usr/bin/env python3
"""
Скрипт для перевода аудита торгового бота на русский язык.
Сохраняет код, пути к файлам и техническую терминологию.
"""
import re

# Словарь технических терминов
TECH_TERMS = {
    # Основные термины (оставляем как есть или транслитерируем)
    "Trailing Stop": "Трейлинг-стоп",
    "Stop Loss": "Стоп-лосс",
    "Stop-Loss": "Стоп-лосс",
    "Position Manager": "Менеджер позиций",
    "Race condition": "Race condition (состояние гонки)",
    "Zombie": "Зомби",
    "WebSocket": "WebSocket",
    "Database": "База данных",
    "Event logging": "Логирование событий",

    # Разделы и заголовки
    "EXECUTIVE SUMMARY": "РЕЗЮМЕ",
    "Overall Assessment": "Общая оценка",
    "Code Quality": "Качество кода",
    "Critical Issues Found": "Найдено критических проблем",
    "Database Logging Completeness": "Полнота логирования в БД",
    "Architecture": "Архитектура",
    "Top 5 Must-Fix Issues": "Топ-5 критических проблем для исправления",
    "Recent Critical Fixes": "Недавние критические исправления",
    "Last 2 Weeks": "За последние 2 недели",

    # Секции
    "SYSTEM ARCHITECTURE": "АРХИТЕКТУРА СИСТЕМЫ",
    "High-Level Overview": "Общий обзор",
    "Data Flow": "Поток данных",
    "Key Components": "Ключевые компоненты",
    "Position Opening": "Открытие позиций",
    "Position Monitoring": "Мониторинг позиций",

    "DATABASE & EVENT LOGGING AUDIT": "АУДИТ БАЗЫ ДАННЫХ И ЛОГИРОВАНИЯ СОБЫТИЙ",
    "Database Schema Analysis": "Анализ схемы базы данных",
    "Event Logging Completeness Matrix": "Матрица полноты логирования событий",
    "Missing Event Logs": "Отсутствующие логи событий",
    "Database Issues Found": "Найденные проблемы базы данных",
    "CRITICAL Issues": "КРИТИЧНЫЕ проблемы",
    "MEDIUM Issues": "СРЕДНИЕ проблемы",
    "HIGH Issues": "ВЫСОКИЕ проблемы",
    "LOW Issues": "НИЗКИЕ проблемы",

    "TRAILING STOP DEEP ANALYSIS": "ГЛУБОКИЙ АНАЛИЗ ТРЕЙЛИНГ-СТОПА",
    "How It Works": "Как это работает",
    "Step by Step": "Пошагово",
    "Issues Found": "Найденные проблемы",
    "Comparison with Best Practices": "Сравнение с лучшими практиками",

    "POSITION OPENING & SL PLACEMENT AUDIT": "АУДИТ ОТКРЫТИЯ ПОЗИЦИЙ И РАЗМЕЩЕНИЯ SL",
    "Signal → Entry → SL Flow": "Поток Сигнал → Вход → SL",
    "Is SL Placement Atomic with Entry": "Атомарно ли размещение SL с входом",
    "What Happens If Entry Succeeds But SL Fails": "Что происходит если вход успешен, но SL не удался",
    "Recovery Mechanisms": "Механизмы восстановления",
    "Database Logging at Each Step": "Логирование в БД на каждом этапе",

    "SL GUARD / POSITION PROTECTION AUDIT": "АУДИТ SL GUARD / ЗАЩИТЫ ПОЗИЦИЙ",
    "ZOMBIE CLEANUP AUDIT": "АУДИТ ОЧИСТКИ ЗОМБИ",
    "RACE CONDITIONS & CONCURRENCY ISSUES": "RACE CONDITIONS И ПРОБЛЕМЫ КОНКУРЕНТНОСТИ",
    "API USAGE VERIFICATION": "ПРОВЕРКА ИСПОЛЬЗОВАНИЯ API",
    "RECOVERY & FAULT TOLERANCE": "ВОССТАНОВЛЕНИЕ И ОТКАЗОУСТОЙЧИВОСТЬ",
    "PRIORITIZED ACTION PLAN": "ПРИОРИТИЗИРОВАННЫЙ ПЛАН ДЕЙСТВИЙ",
    "CONCLUSION": "ЗАКЛЮЧЕНИЕ",

    # Статусы и действия
    "Fix": "Исправление",
    "Issue": "Проблема",
    "Impact": "Влияние",
    "Location": "Расположение",
    "Probability": "Вероятность",
    "Mitigation": "Смягчение",
    "Status": "Статус",
    "Risk": "Риск",
    "Solution": "Решение",
    "Example": "Пример",
    "Scenario": "Сценарий",
    "Result": "Результат",
    "Why Critical": "Почему критично",
    "How to Fix": "Как исправить",
    "Estimated Effort": "Оценка трудозатрат",
    "Files to Modify": "Файлы для изменения",
    "Testing": "Тестирование",

    # Технические термины
    "MISSING": "ОТСУТСТВУЕТ",
    "Missing": "Отсутствует",
    "Logged to DB": "Логируется в БД",
    "Only file logger": "Только файловый логгер",
    "No DB logging": "Нет логирования в БД",
    "No DB event": "Нет события в БД",
    "DB update but no event log": "Обновление БД, но нет события",

    # Общие фразы
    "Summary": "Итог",
    "Total critical events": "Всего критических событий",
    "Events logged to DB": "События, залогированные в БД",
    "Logging completeness": "Полнота логирования",
    "Must-Have Event Logs": "Обязательные логи событий",
    "HIGHEST PRIORITY": "НАИВЫСШИЙ ПРИОРИТЕТ",
    "HIGH PRIORITY": "ВЫСОКИЙ ПРИОРИТЕТ",

    # Оценки и рейтинги
    "Better": "Лучше",
    "Worse": "Хуже",
    "Correct": "Корректно",
    "Incorrect": "Некорректно",
    "Good": "Хорошо",
    "Bad": "Плохо",
    "FIXED": "ИСПРАВЛЕНО",
    "Not an issue": "Не проблема",

    # Действия в коде
    "Receives": "Получает",
    "Validates": "Валидирует",
    "Filters": "Фильтрует",
    "Creates": "Создает",
    "Updates": "Обновляет",
    "Deletes": "Удаляет",
    "Detects": "Обнаруживает",
    "Removes": "Удаляет",
    "Reconciles": "Согласовывает",
    "Guarantees": "Гарантирует",
    "Central orchestrator": "Центральный оркестратор",
    "Advanced": "Продвинутый",
    "Underutilized": "Недоиспользуется",

    # Периоды и время
    "every 2 minutes": "каждые 2 минуты",
    "every 120 seconds": "каждые 120 секунд",
    "Periodic sync": "Периодическая синхронизация",
    "Real-time": "В реальном времени",
    "On startup": "При запуске",

    # Уровни серьезности
    "CRITICAL": "КРИТИЧНО",
    "HIGH": "ВЫСОКО",
    "MEDIUM": "СРЕДНЕ",
    "LOW": "НИЗКО",

    # Рекомендации
    "Recommended": "Рекомендуется",
    "Fix immediately": "Исправить немедленно",
    "Fix within days": "Исправить в течение дней",
    "Fix when possible": "Исправить когда возможно",
    "Nice to have": "Желательно иметь",
    "Production risk": "Риск для продакшена",

    # Типы проблем
    "Float vs Decimal": "Float vs Decimal",
    "for Financial Data": "для финансовых данных",
    "Precision loss": "Потеря точности",
    "financial calculations": "финансовые вычисления",
    "Floating-point precision errors": "Ошибки точности с плавающей запятой",
    "Potential rounding errors": "Потенциальные ошибки округления",

    # Таблицы
    "Module": "Модуль",
    "Event": "Событие",
    "Table": "Таблица",
    "Comments": "Комментарии",
    "Feature": "Функция",
    "This Bot": "Этот бот",
    "Industry Standard": "Индустриальный стандарт",

    # Дни и временные оценки
    "days": "дней",
    "day": "день",
    "hours": "часов",
    "minutes": "минут",
    "seconds": "секунд",
}

def translate_line(line: str) -> str:
    """Переводит строку, сохраняя код и техничес кие термины."""

    # Не переводим код и пути
    if line.strip().startswith('```') or line.strip().startswith('│') or line.strip().startswith('├') or line.strip().startswith('└'):
        return line

    # Не переводим пути к файлам
    if '.py:' in line or '.sql' in line or '.md' in line:
        # Только заменяем термины в описаниях
        for eng, rus in TECH_TERMS.items():
            if eng in line and not line.strip().startswith('-'):
                line = line.replace(eng, rus)
        return line

    # Не переводим git commit hashes и сообщения
    if re.search(r'[0-9a-f]{7}', line):
        return line

    # Применяем словарь терминов
    translated = line
    for eng, rus in TECH_TERMS.items():
        translated = translated.replace(eng, rus)

    return translated

def translate_audit_report():
    """Основная функция перевода."""
    input_file = '/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/COMPREHENSIVE_TRADING_BOT_AUDIT_REPORT.md'
    output_file = '/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot/COMPREHENSIVE_TRADING_BOT_AUDIT_REPORT_RU.md'

    print("Начинаю перевод отчета об аудите...")
    print(f"Исходный файл: {input_file}")
    print(f"Целевой файл: {output_file}")

    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    print(f"Всего строк: {len(lines)}")

    translated_lines = []
    in_code_block = False
    code_block_lang = None

    for i, line in enumerate(lines):
        # Определяем блоки кода
        if line.strip().startswith('```'):
            in_code_block = not in_code_block
            if in_code_block:
                # Начало блока кода
                code_block_lang = line.strip()[3:].strip()
            translated_lines.append(line)
            continue

        # Внутри блока кода не переводим
        if in_code_block:
            translated_lines.append(line)
            continue

        # Переводим строку
        translated = translate_line(line)
        translated_lines.append(translated)

        # Прогресс
        if (i + 1) % 500 == 0:
            print(f"Обработано строк: {i + 1}/{len(lines)}")

    # Записываем результат
    with open(output_file, 'w', encoding='utf-8') as f:
        f.writelines(translated_lines)

    print(f"\n✅ Перевод завершен!")
    print(f"Переведено строк: {len(translated_lines)}")
    print(f"Результат сохранен в: {output_file}")

if __name__ == '__main__':
    translate_audit_report()
