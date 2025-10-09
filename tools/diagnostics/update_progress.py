#!/usr/bin/env python3
"""
Обновить прогресс после выполнения шага

USAGE:
    python tools/diagnostics/update_progress.py "1.1" "Исправить баг schema"
    python tools/diagnostics/update_progress.py "0.2" "Backup"

Automatically:
- Updates timestamp in AUDIT_FIX_PROGRESS.md
- Marks step as complete [x]
- Git commits the progress update
"""
import sys
import re
from datetime import datetime
from pathlib import Path
import subprocess

def update_progress(step_id: str, description: str):
    """Отметить шаг как выполненный"""

    progress_file = Path('AUDIT_FIX_PROGRESS.md')
    if not progress_file.exists():
        print("❌ AUDIT_FIX_PROGRESS.md not found!")
        print("   Run from project root directory")
        return False

    content = progress_file.read_text()

    # Обновить timestamp
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    content = re.sub(
        r'\*\*Последнее обновление:\*\* .*',
        f'**Последнее обновление:** {current_time}',
        content
    )

    # Попробовать несколько паттернов для поиска шага
    patterns = [
        # Pattern 1: "- [ ] X.Y Description"
        (f'- \\[ \\] {re.escape(step_id)} {re.escape(description)}',
         f'- [x] {step_id} {description}'),

        # Pattern 2: "- [ ] X/Y file.py"
        (f'- \\[ \\] {re.escape(step_id)} {re.escape(description)}',
         f'- [x] {step_id} {description}'),

        # Pattern 3: Just step_id (more flexible)
        (f'- \\[ \\] {re.escape(step_id)}[^\n]*',
         lambda m: m.group(0).replace('[ ]', '[x]', 1)),
    ]

    found = False
    for pattern, replacement in patterns:
        if isinstance(replacement, str):
            if re.search(pattern, content):
                content = re.sub(pattern, replacement, content)
                found = True
                break
        else:
            # Replacement is a function
            if re.search(pattern, content):
                content = re.sub(pattern, replacement, content)
                found = True
                break

    if not found:
        print(f"⚠️  Step not found: {step_id}")
        print(f"   Searching for: - [ ] {step_id}")
        print()
        print("Available steps:")
        # Show available uncompleted steps
        for line in content.split('\n'):
            if '- [ ]' in line and not line.strip().startswith('#'):
                print(f"   {line.strip()}")
        return False

    # Сохранить
    progress_file.write_text(content)
    print(f"✅ Marked as done: {step_id} {description}")

    # Git commit прогресса
    try:
        subprocess.run(['git', 'add', 'AUDIT_FIX_PROGRESS.md'], check=True)
        subprocess.run([
            'git', 'commit', '-m',
            f'📊 Progress: Completed {step_id} - {description}'
        ], check=True)
        print(f"✅ Git commit created")
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Git commit failed: {e}")
        print("   Progress file updated but not committed")

    return True

def show_current_status():
    """Показать текущий статус прогресса"""
    progress_file = Path('AUDIT_FIX_PROGRESS.md')
    if not progress_file.exists():
        return

    content = progress_file.read_text()

    # Подсчитать выполненные/невыполненные
    total = len(re.findall(r'- \[.\]', content))
    completed = len(re.findall(r'- \[x\]', content))
    pending = total - completed

    print()
    print("="*60)
    print("CURRENT PROGRESS STATUS")
    print("="*60)
    print(f"Total steps: {total}")
    print(f"Completed: {completed}")
    print(f"Pending: {pending}")
    if total > 0:
        percent = (completed / total) * 100
        print(f"Progress: {percent:.1f}%")
    print("="*60)

def main():
    if len(sys.argv) < 2:
        print("Usage: update_progress.py <step_id> [description]")
        print()
        print("Examples:")
        print("  python tools/diagnostics/update_progress.py '0.1' 'Анализ зависимостей'")
        print("  python tools/diagnostics/update_progress.py '1.1' 'Баг schema'")
        print()
        show_current_status()
        sys.exit(1)

    step_id = sys.argv[1]
    description = ' '.join(sys.argv[2:]) if len(sys.argv) > 2 else ""

    success = update_progress(step_id, description)

    if success:
        show_current_status()

    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
