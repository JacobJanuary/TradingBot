#!/usr/bin/env python3
"""
Проверка что мы следуем плану и не вышли в деструктивный цикл

ЗАПУСКАТЬ ПОСЛЕ КАЖДОГО ШАГА!

Usage:
    python tools/diagnostics/verify_progress.py
"""
import sys
import subprocess
from datetime import datetime
from pathlib import Path

def check_progress_file_exists():
    """Проверить что progress файл существует"""
    if not Path('AUDIT_FIX_PROGRESS.md').exists():
        print("❌ AUDIT_FIX_PROGRESS.md NOT FOUND!")
        print("   Plan tracking lost - STOP!")
        return False
    return True

def check_plan_file_exists():
    """Проверить что план существует"""
    if not Path('AUDIT_FIX_PLAN.md').exists():
        print("❌ AUDIT_FIX_PLAN.md NOT FOUND!")
        print("   Detailed plan lost - STOP!")
        return False
    return True

def count_recent_commits():
    """Подсчитать коммиты за последний час"""
    try:
        result = subprocess.run(
            ['git', 'log', '--since=1.hour.ago', '--oneline'],
            capture_output=True,
            text=True,
            check=False
        )
        commits = result.stdout.strip().split('\n')
        commit_count = len([c for c in commits if c])
        return commit_count
    except Exception as e:
        print(f"⚠️  Could not count commits: {e}")
        return 0

def check_destructive_cycle():
    """Проверить признаки деструктивного цикла"""
    # Признак 1: Слишком много коммитов за короткое время
    recent_commits = count_recent_commits()

    if recent_commits > 10:
        print(f"⚠️  WARNING: {recent_commits} commits in last hour")
        print("   Possible destructive cycle - review recent changes")
        print("   Expected: ~1-2 commits per hour max")
        return False

    # Признак 2: Проверить что есть коммиты (не застряли)
    try:
        result = subprocess.run(
            ['git', 'log', '--since=3.hours.ago', '--oneline'],
            capture_output=True,
            text=True,
            check=False
        )
        commits = result.stdout.strip().split('\n')
        commit_count = len([c for c in commits if c])

        if commit_count == 0:
            print("⚠️  WARNING: No commits in last 3 hours")
            print("   Are we stuck? Check progress")
    except:
        pass

    return True

def verify_health_check_exists():
    """Проверить что health check существует"""
    if not Path('tests/integration/health_check_after_fix.py').exists():
        print("⚠️  WARNING: health_check_after_fix.py NOT FOUND!")
        print("   Should be created in Phase 0.4")
        # Not critical if we're in Phase 0
        return True  # Don't fail - might not be created yet
    return True

def check_backup_exists():
    """Проверить что backup существует"""
    backups = list(Path('.').glob('backup_monitoring_*.sql'))
    if not backups:
        print("⚠️  WARNING: No backup files found!")
        print("   Should create backup in Phase 0.2")
        # Not critical if we're in Phase 0
        return True  # Don't fail - might not be created yet

    # Проверить что backup недавний (< 24 часов)
    latest_backup = max(backups, key=lambda p: p.stat().st_mtime)
    age_hours = (datetime.now().timestamp() - latest_backup.stat().st_mtime) / 3600

    if age_hours > 24:
        print(f"⚠️  WARNING: Latest backup is {age_hours:.1f} hours old")
        print("   Consider creating fresh backup")
    else:
        print(f"   Latest backup: {latest_backup.name} ({age_hours:.1f}h old)")

    return True

def check_current_branch():
    """Проверить что мы на правильном branch"""
    try:
        result = subprocess.run(
            ['git', 'branch', '--show-current'],
            capture_output=True,
            text=True,
            check=False
        )
        branch = result.stdout.strip()

        # Должны быть на fix/audit-fixes-phase-1 или sub-branch
        if not branch.startswith('fix/'):
            print(f"⚠️  WARNING: Current branch is '{branch}'")
            print("   Expected: fix/audit-fixes-phase-1 or fix/*")
            print("   Are we on correct branch?")
            return False

        print(f"   Current branch: {branch}")
        return True
    except Exception as e:
        print(f"⚠️  Could not check branch: {e}")
        return True  # Don't fail

def main():
    print("="*60)
    print("PROGRESS VERIFICATION")
    print("="*60)
    print()

    checks = [
        ("Progress file exists", check_progress_file_exists),
        ("Plan file exists", check_plan_file_exists),
        ("Health check exists", verify_health_check_exists),
        ("Backup exists", check_backup_exists),
        ("No destructive cycle", check_destructive_cycle),
        ("Correct git branch", check_current_branch),
    ]

    passed = 0
    failed = 0
    critical_failed = False

    for name, check_func in checks:
        print(f"Checking: {name}...")
        if check_func():
            print(f"  ✅ PASS")
            passed += 1
        else:
            print(f"  ❌ FAIL")
            failed += 1
            # Critical checks
            if name in ["Progress file exists", "Plan file exists"]:
                critical_failed = True

    print("\n" + "="*60)
    print(f"RESULT: {passed}/{len(checks)} checks passed")
    print("="*60)

    if critical_failed:
        print("\n❌ CRITICAL VERIFICATION FAILED!")
        print("   Missing essential files - cannot continue safely")
        return 2
    elif failed > 0:
        print("\n⚠️  VERIFICATION WARNINGS - review issues above")
        print("   Can continue but be careful")
        return 0  # Don't fail - just warnings
    else:
        print("\n✅ VERIFICATION PASSED - safe to continue")
        return 0

if __name__ == "__main__":
    sys.exit(main())
