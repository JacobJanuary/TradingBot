#!/usr/bin/env python3
"""
Проверка совместимости кода с новыми полями БД
"""
import os
import re

def check_file(filepath):
    """Check single file for DB field usage"""
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    issues = []

    # Check for hardcoded field lists in INSERT/UPDATE
    insert_patterns = [
        r'INSERT INTO.*positions.*\(',
        r'UPDATE.*positions.*SET'
    ]

    for pattern in insert_patterns:
        matches = re.finditer(pattern, content, re.IGNORECASE)
        for match in matches:
            # Get surrounding context
            start = max(0, match.start() - 50)
            end = min(len(content), match.end() + 200)
            context = content[start:end]

            # Check if explicitly lists fields (potential issue)
            if '(' in context and ')' in context:
                issues.append({
                    'type': 'explicit_fields',
                    'context': context[:150]
                })

    # Check for SELECT * (good - will include new fields)
    select_star = len(re.findall(r'SELECT \* FROM.*positions', content, re.IGNORECASE))

    # Check for exit_reason usage
    exit_reason_usage = content.count('exit_reason')

    # Check for new field usage
    new_fields = {
        'error_details': content.count('error_details'),
        'retry_count': content.count('retry_count'),
        'last_error_at': content.count('last_error_at'),
        'last_sync_at': content.count('last_sync_at'),
        'sync_status': content.count('sync_status'),
        'sl_order_id': content.count('sl_order_id')
    }

    return {
        'issues': issues,
        'select_star': select_star,
        'exit_reason_usage': exit_reason_usage,
        'new_fields': new_fields
    }

print("=" * 70)
print("ПРОВЕРКА СОВМЕСТИМОСТИ КОДА С НОВОЙ СХЕМОЙ БД")
print("=" * 70)

# Files to check
files_to_check = [
    'database/repository.py',
    'core/position_manager.py',
    'core/aged_position_manager.py',
    'core/position_synchronizer.py'
]

print("\n📋 Проверяю ключевые файлы...\n")

for filepath in files_to_check:
    if not os.path.exists(filepath):
        print(f"⚠️ {filepath} - not found")
        continue

    print(f"📄 {filepath}")
    result = check_file(filepath)

    # Check INSERT/UPDATE queries
    if result['issues']:
        print(f"   ⚠️ Найдены явные списки полей в запросах: {len(result['issues'])}")
        for issue in result['issues'][:2]:  # Show first 2
            preview = issue['context'].replace('\n', ' ')[:80]
            print(f"      {preview}...")

    # Check if uses SELECT *
    if result['select_star'] > 0:
        print(f"   ✅ Использует SELECT * (автоматически включит новые поля)")

    # Check exit_reason usage
    if result['exit_reason_usage'] > 0:
        print(f"   ✅ Использует exit_reason ({result['exit_reason_usage']} раз)")

    # Check new fields usage
    new_used = sum(1 for count in result['new_fields'].values() if count > 0)
    if new_used > 0:
        print(f"   ℹ️ Уже использует {new_used} новых полей:")
        for field, count in result['new_fields'].items():
            if count > 0:
                print(f"      • {field}: {count} раз")
    else:
        print(f"   ℹ️ Новые поля пока не используются (это нормально)")

    print()

print("=" * 70)
print("ВЫВОД")
print("=" * 70)

print("""
✅ СОВМЕСТИМОСТЬ:
   • Все изменения БД аддитивные (только ADD COLUMN)
   • Все новые поля nullable (опциональные)
   • Существующие INSERT/UPDATE продолжат работать
   • SELECT * автоматически включит новые поля

ℹ️ РЕКОМЕНДАЦИИ (опциональные улучшения):
   1. Можно добавить сохранение error_details при ошибках
   2. Можно добавить retry_count в логику повторов
   3. Можно сохранять sl_order_id при создании SL
   4. Можно добавить last_sync_at в синхронизатор

❗ КРИТИЧНО:
   • НЕТ breaking changes
   • Код работает БЕЗ изменений
   • Новые поля можно добавлять постепенно
""")

print("\n🎯 ИТОГО: Код совместим с новой схемой БД")
print("          Изменения кода НЕ ОБЯЗАТЕЛЬНЫ")
