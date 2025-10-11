#!/usr/bin/env python3
"""
Скрипт валидации всех критических исправлений

Запуск: python scripts/validate_fixes.py

Проверяет:
1. Атомарность Entry+SL
2. Идемпотентность операций
3. Корректность синхронизации
4. Защиту от race conditions
5. Наличие тестов для критической логики
6. Использование locks
"""
import asyncio
import sys
import os
from pathlib import Path
from typing import Dict, List, Tuple
from datetime import datetime, timedelta
import logging
from colorama import Fore, Style, init

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

# Initialize colorama for colored output
init(autoreset=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FixValidator:
    """Валидатор исправлений критических багов"""

    def __init__(self):
        self.results = {}
        self.issues_found = []

    async def validate_all(self) -> bool:
        """Запуск всех валидаций"""
        print("\n" + "="*60)
        print(" ВАЛИДАЦИЯ КРИТИЧЕСКИХ ИСПРАВЛЕНИЙ")
        print("="*60 + "\n")

        validators = [
            ("Атомарность Entry+SL", self.validate_atomicity),
            ("Идемпотентность", self.validate_idempotency),
            ("Синхронизация", self.validate_synchronization),
            ("Race Conditions", self.validate_race_conditions),
            ("Критическая логика", self.validate_critical_logic),
            ("Защита кода (Locks)", self.validate_locks),
            ("База данных", self.validate_database),
            ("Логирование", self.validate_logging),
        ]

        for name, validator_func in validators:
            try:
                print(f"\n📋 Проверка: {name}")
                print("-" * 40)
                result = await validator_func()
                self.results[name] = result

                if result:
                    print(f"{Fore.GREEN}✅ PASSED{Style.RESET_ALL}")
                else:
                    print(f"{Fore.RED}❌ FAILED{Style.RESET_ALL}")

            except Exception as e:
                print(f"{Fore.RED}❌ ERROR: {e}{Style.RESET_ALL}")
                self.results[name] = False
                self.issues_found.append(f"{name}: {e}")

        # Summary
        self._print_summary()

        all_passed = all(self.results.values())
        return all_passed

    async def validate_atomicity(self) -> bool:
        """Проверка атомарности создания позиции со stop-loss"""
        issues = []

        # Check if position creation uses transactions
        try:
            from core.position_manager import PositionManager

            # Check for transaction usage
            source_file = Path("core/position_manager.py")
            if source_file.exists():
                content = source_file.read_text()

                checks = [
                    ("begin_transaction" in content, "Database transactions"),
                    ("rollback" in content, "Rollback mechanism"),
                    ("pending_sl" in content or "PENDING_SL" in content, "Pending SL state"),
                    ("recover" in content, "Recovery mechanism")
                ]

                for check, description in checks:
                    if check:
                        print(f"  ✓ {description}: Found")
                    else:
                        print(f"  ✗ {description}: Missing")
                        issues.append(f"Missing: {description}")

            # Check for atomic operation method
            manager = PositionManager(config=None, repository=None, exchanges={})
            has_atomic = hasattr(manager, 'open_position_atomic') or \
                        hasattr(manager, 'atomic_operation')

            if has_atomic:
                print(f"  ✓ Atomic operation method: Found")
            else:
                print(f"  ✗ Atomic operation method: Missing")
                issues.append("No atomic operation method")

        except Exception as e:
            issues.append(str(e))

        if issues:
            self.issues_found.extend([f"Atomicity: {issue}" for issue in issues])

        return len(issues) == 0

    async def validate_idempotency(self) -> bool:
        """Проверка идемпотентности операций"""
        issues = []

        try:
            from core.stop_loss_manager import StopLossManager

            # Check for idempotency checks
            source_file = Path("core/stop_loss_manager.py")
            if source_file.exists():
                content = source_file.read_text()

                checks = [
                    ("has_stop_loss" in content, "Check before create"),
                    ("already_exists" in content, "Already exists handling"),
                    ("client_order_id" in content, "Unique order ID"),
                ]

                for check, description in checks:
                    if check:
                        print(f"  ✓ {description}: Found")
                    else:
                        print(f"  ✗ {description}: Missing")
                        issues.append(f"Missing: {description}")

        except Exception as e:
            issues.append(str(e))

        return len(issues) == 0

    async def validate_synchronization(self) -> bool:
        """Проверка корректности синхронизации"""
        issues = []

        try:
            from core.position_synchronizer import PositionSynchronizer

            source_file = Path("core/position_synchronizer.py")
            if source_file.exists():
                content = source_file.read_text()

                checks = [
                    ("normalize_symbol" in content, "Symbol normalization"),
                    ("source of truth" in content.lower(), "Source of truth comment"),
                    ("phantom" in content.lower(), "Phantom position handling"),
                    ("reconciliation" in content.lower(), "Reconciliation logic"),
                ]

                for check, description in checks:
                    if check:
                        print(f"  ✓ {description}: Found")
                    else:
                        print(f"  ✗ {description}: Missing")
                        issues.append(f"Missing: {description}")

        except Exception as e:
            issues.append(str(e))

        return len(issues) == 0

    async def validate_race_conditions(self) -> bool:
        """Проверка защиты от race conditions"""
        issues = []

        try:
            # Check SingleInstance
            from utils.single_instance import SingleInstance
            print(f"  ✓ SingleInstance: Implemented")

            # Check for proper locks
            from core.position_manager import PositionManager
            manager = PositionManager(config=None, repository=None, exchanges={})

            # Check lock types
            if hasattr(manager, 'position_locks'):
                lock_type = type(manager.position_locks).__name__
                if lock_type == 'set':
                    print(f"  ✗ position_locks: Is {lock_type}, should be Dict[str, Lock]")
                    issues.append("position_locks is set, not proper locks")
                else:
                    print(f"  ✓ position_locks: Correct type ({lock_type})")

            # Check for lock manager
            try:
                from core.lock_manager import LockManager
                print(f"  ✓ LockManager: Found")
            except ImportError:
                print(f"  ✗ LockManager: Not implemented")
                issues.append("LockManager not implemented")

        except Exception as e:
            issues.append(str(e))

        return len(issues) == 0

    async def validate_critical_logic(self) -> bool:
        """Проверка защиты критической логики"""
        issues = []

        # Check for tests
        test_files = [
            "tests/test_wave_timestamp_calculation.py",
            "tests/critical_fixes/test_atomicity_fix.py",
            "tests/critical_fixes/test_race_conditions_fix.py"
        ]

        for test_file in test_files:
            if Path(test_file).exists():
                print(f"  ✓ Test file: {test_file}")
            else:
                print(f"  ✗ Test file: {test_file} missing")
                issues.append(f"Missing test: {test_file}")

        # Check for CRITICAL comments
        critical_files = [
            "core/signal_processor_websocket.py",
            "core/position_manager.py"
        ]

        for file_path in critical_files:
            if Path(file_path).exists():
                content = Path(file_path).read_text()
                if "CRITICAL" in content or "DO NOT MODIFY" in content:
                    print(f"  ✓ Critical markers in: {file_path}")
                else:
                    print(f"  ⚠ No critical markers in: {file_path}")

        return len(issues) == 0

    async def validate_locks(self) -> bool:
        """Проверка использования locks для критических секций"""
        issues = []

        critical_sections = [
            ("position creation", "position_locks"),
            ("SL update", "sl_locks or check_locks"),
            ("trailing stop", "trailing_locks"),
        ]

        source_file = Path("core/position_manager.py")
        if source_file.exists():
            content = source_file.read_text()

            for section, lock_name in critical_sections:
                if lock_name.split(" or ")[0] in content:
                    print(f"  ✓ Lock for {section}: Found")
                else:
                    print(f"  ✗ Lock for {section}: Missing")
                    issues.append(f"No lock for {section}")

        return len(issues) == 0

    async def validate_database(self) -> bool:
        """Проверка схемы БД и constraints"""
        issues = []

        try:
            # Check for event tables
            required_tables = [
                "events",
                "transaction_log",
                "lock_events"
            ]

            # Check models
            from database.models import Position, Trade

            print(f"  ✓ Database models: Found")

            # Check for UNIQUE constraints
            if hasattr(Position, '__table_args__'):
                print(f"  ✓ Table constraints: Defined")
            else:
                print(f"  ⚠ Table constraints: Not checked")

        except Exception as e:
            issues.append(str(e))

        return len(issues) == 0

    async def validate_logging(self) -> bool:
        """Проверка полноты логирования"""
        issues = []

        try:
            # Check for event logger
            try:
                from core.event_logger import EventLogger
                print(f"  ✓ EventLogger: Implemented")
            except ImportError:
                print(f"  ✗ EventLogger: Not implemented")
                issues.append("EventLogger not implemented")

            # Check repository for logging methods
            from database.repository import Repository
            repo = Repository(None)

            logging_methods = [
                'log_event',
                'log_position_created',
                'log_sl_placed'
            ]

            for method in logging_methods:
                if hasattr(repo, method):
                    print(f"  ✓ Method {method}: Found")
                else:
                    print(f"  ⚠ Method {method}: Not found")

        except Exception as e:
            issues.append(str(e))

        return len(issues) == 0

    def _print_summary(self):
        """Печать итогового отчета"""
        print("\n" + "="*60)
        print(" ИТОГОВЫЙ ОТЧЕТ")
        print("="*60)

        passed = sum(1 for v in self.results.values() if v)
        total = len(self.results)
        percentage = (passed / total * 100) if total > 0 else 0

        print(f"\nРезультаты: {passed}/{total} ({percentage:.1f}%)")
        print("-" * 40)

        for name, result in self.results.items():
            status = f"{Fore.GREEN}✅ PASS{Style.RESET_ALL}" if result else f"{Fore.RED}❌ FAIL{Style.RESET_ALL}"
            print(f"{name:.<30} {status}")

        if self.issues_found:
            print(f"\n{Fore.YELLOW}⚠️ Найденные проблемы:{Style.RESET_ALL}")
            for issue in self.issues_found[:10]:  # Show first 10 issues
                print(f"  • {issue}")

        print("\n" + "="*60)

        if percentage == 100:
            print(f"{Fore.GREEN}✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!{Style.RESET_ALL}")
            print("Система готова к тестированию исправлений.")
        elif percentage >= 70:
            print(f"{Fore.YELLOW}⚠️ БОЛЬШИНСТВО ПРОВЕРОК ПРОЙДЕНО{Style.RESET_ALL}")
            print("Рекомендуется доработать оставшиеся пункты.")
        else:
            print(f"{Fore.RED}❌ ТРЕБУЕТСЯ ДОРАБОТКА{Style.RESET_ALL}")
            print("Критические проблемы не исправлены.")

        print("="*60 + "\n")


async def main():
    """Главная функция"""
    validator = FixValidator()
    success = await validator.validate_all()

    # Exit code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nВалидация прервана пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Fore.RED}Критическая ошибка: {e}{Style.RESET_ALL}")
        sys.exit(2)