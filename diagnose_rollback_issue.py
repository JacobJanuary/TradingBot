#!/usr/bin/env python3
"""
ДИАГНОСТИКА: Проверка механизма отката позиций

Цель: Понять почему откат не работает когда позиция уже на бирже
"""

import asyncio
import re
from datetime import datetime, timedelta

def analyze_rollback_failures():
    """Анализ логов для поиска паттернов отката"""
    print("=" * 80)
    print("🔍 ДИАГНОСТИКА: Механизм отката позиций")
    print("=" * 80)
    print()

    with open('logs/trading_bot.log', 'r') as f:
        lines = f.readlines()

    # Найти последний старт
    start_idx = None
    for i, line in enumerate(lines):
        if '🚀 Starting trading bot' in line:
            start_idx = i

    if not start_idx:
        print("❌ Не найден старт бота")
        return

    lines = lines[start_idx:]

    # Ищем случаи отката
    rollback_cases = []
    i = 0
    while i < len(lines):
        line = lines[i]

        if '🔄 Rolling back position' in line:
            # Найден откат
            match = re.search(r'Rolling back position for (\w+)', line)
            symbol = match.group(1) if match else 'UNKNOWN'

            # Ищем контекст - что было до и после
            context_before = []
            context_after = []

            # 20 строк до
            for j in range(max(0, i-20), i):
                if symbol in lines[j]:
                    context_before.append(lines[j].strip())

            # 20 строк после
            for j in range(i+1, min(len(lines), i+20)):
                if symbol in lines[j]:
                    context_after.append(lines[j].strip())

            # Проверяем успешность отката
            rollback_success = False
            rollback_error = None

            for ctx in context_after:
                if 'successfully deleted from database' in ctx:
                    rollback_success = True
                if 'FAILED to close unprotected position' in ctx:
                    rollback_error = 'Failed to close on exchange'
                if 'Position creation rolled back' in ctx:
                    rollback_success = True  # DB rollback ok

            # Проверяем был ли entry order успешен
            entry_created = False
            for ctx in context_before:
                if 'position_created:' in ctx and symbol in ctx:
                    entry_created = True

            rollback_cases.append({
                'symbol': symbol,
                'entry_created': entry_created,
                'rollback_success': rollback_success,
                'rollback_error': rollback_error,
                'context_before': context_before[-5:],  # Last 5
                'context_after': context_after[:5]      # First 5
            })

        i += 1

    # Анализ
    print(f"Найдено случаев отката: {len(rollback_cases)}")
    print()

    if not rollback_cases:
        print("✅ Откатов не найдено - система работает без откатов")
        return

    # Группируем по типам
    entry_created_then_rollback = [r for r in rollback_cases if r['entry_created']]
    rollback_without_entry = [r for r in rollback_cases if not r['entry_created']]
    failed_to_close = [r for r in rollback_cases if r['rollback_error']]

    print(f"📊 Типы откатов:")
    print(f"   - Entry создан, потом откат: {len(entry_created_then_rollback)}")
    print(f"   - Откат без entry: {len(rollback_without_entry)}")
    print(f"   - Не удалось закрыть на бирже: {len(failed_to_close)}")
    print()

    # КРИТИЧНЫЕ СЛУЧАИ: Entry создан но откат не смог закрыть
    critical_cases = [r for r in rollback_cases
                      if r['entry_created'] and r['rollback_error']]

    if critical_cases:
        print("🔴 КРИТИЧНЫЕ СЛУЧАИ: Позиция открыта но откат failed!")
        print()
        for case in critical_cases:
            print(f"  Symbol: {case['symbol']}")
            print(f"  Entry created: ✅")
            print(f"  Rollback error: {case['rollback_error']}")
            print()
            print("  Context before rollback:")
            for ctx in case['context_before']:
                print(f"    {ctx}")
            print()
            print("  Context after rollback:")
            for ctx in case['context_after']:
                print(f"    {ctx}")
            print()
            print("-" * 80)
            print()

    # Итоги
    print("=" * 80)
    print("📊 ИТОГОВЫЙ ДИАГНОЗ")
    print("=" * 80)
    print()

    if critical_cases:
        print("❌ ПРОБЛЕМА ПОДТВЕРЖДЕНА:")
        print(f"  - {len(critical_cases)} случаев когда entry создан но откат failed")
        print(f"  - Результат: Позиция БЕЗ SL на бирже")
        print()
        print("🎯 ROOT CAUSE:")
        print("  1. Entry ордер успешно создан на бирже")
        print("  2. Позиция записана в БД")
        print("  3. SL ордер failed (amount=0.0)")
        print("  4. Откат пытается закрыть позицию на бирже")
        print("  5. Закрытие failed (amount=0.0 again)")
        print("  6. Позиция остается открытой БЕЗ SL")
        print()
        print("🔧 НУЖЕН ФИКС:")
        print("  - Улучшить откат: использовать реальный размер позиции с биржи")
        print("  - Или: выставить SL принудительно с correct amount")
    else:
        print("✅ Критичных проблем не найдено")
        print("  - Либо откаты работают")
        print("  - Либо откатов не было")

if __name__ == "__main__":
    analyze_rollback_failures()
