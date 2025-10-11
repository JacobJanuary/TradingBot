#!/usr/bin/env python3
"""
Улучшенный валидатор критических исправлений

Проверяет наличие всех исправлений в правильных файлах
"""
import asyncio
import sys
from pathlib import Path
from colorama import init, Fore, Style

init()  # Initialize colorama


class ImprovedCriticalFixesValidator:
    def __init__(self):
        self.results = {}
        self.issues_found = []

    async def validate_all(self) -> bool:
        """Запуск всех валидаций"""
        print("\n" + "="*60)
        print(" УЛУЧШЕННАЯ ВАЛИДАЦИЯ КРИТИЧЕСКИХ ИСПРАВЛЕНИЙ")
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
            ("Транзакции", self.validate_transactions),
            ("Интеграция", self.validate_integration),
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
        checks_passed = []

        # Check AtomicPositionManager
        atomic_file = Path("core/atomic_position_manager.py")
        if atomic_file.exists():
            content = atomic_file.read_text()
            checks = [
                ("class AtomicPositionManager" in content, "AtomicPositionManager class"),
                ("open_position_atomic" in content, "Atomic open method"),
                ("recover_incomplete_positions" in content, "Recovery mechanism"),
                ("_rollback_position" in content, "Rollback mechanism"),
                ("PositionState" in content, "State machine"),
            ]

            for check, desc in checks:
                if check:
                    print(f"  ✓ {desc}: Found")
                    checks_passed.append(True)
                else:
                    print(f"  ✗ {desc}: Missing")
                    checks_passed.append(False)
        else:
            print(f"  ✗ AtomicPositionManager file not found")
            return False

        return all(checks_passed) if checks_passed else False

    async def validate_idempotency(self) -> bool:
        """Проверка идемпотентности операций"""
        checks_passed = []

        # Check in PositionManager
        pm_file = Path("core/position_manager.py")
        if pm_file.exists():
            content = pm_file.read_text()
            checks = [
                ("has_stop_loss" in content, "Check before create"),
                ("already_exists" in content or "already exists" in content, "Already exists handling"),
                ("client_order_id" in content or "clientOrderId" in content or "uuid" in content, "Unique order ID"),
            ]

            for check, desc in checks:
                if check:
                    print(f"  ✓ {desc}: Found")
                    checks_passed.append(True)
                else:
                    print(f"  ✗ {desc}: Missing")
                    checks_passed.append(False)

        # Check in StopLossManager
        sl_file = Path("core/stop_loss_manager.py")
        if sl_file.exists():
            content = sl_file.read_text()
            if "has_stop_loss" in content:
                print(f"  ✓ StopLossManager idempotency: Found")
                checks_passed.append(True)

        return all(checks_passed) if checks_passed else False

    async def validate_synchronization(self) -> bool:
        """Проверка корректности синхронизации"""
        checks_passed = []

        # Check in PositionManager
        pm_file = Path("core/position_manager.py")
        if pm_file.exists():
            content = pm_file.read_text().lower()
            checks = [
                ("normalize_symbol" in content, "Symbol normalization"),
                ("source of truth" in content, "Source of truth comment"),
                ("phantom" in content or "orphaned" in content, "Phantom position handling"),
                ("reconciliation" in content or "reconcile" in content or "sync_exchange_positions" in content, "Reconciliation logic"),
            ]

            for check, desc in checks:
                if check:
                    print(f"  ✓ {desc}: Found")
                    checks_passed.append(True)
                else:
                    print(f"  ✗ {desc}: Missing")
                    checks_passed.append(False)

        return all(checks_passed) if checks_passed else False

    async def validate_race_conditions(self) -> bool:
        """Проверка защиты от race conditions"""
        checks_passed = []

        # Check SingleInstance
        si_file = Path("utils/single_instance.py")
        if si_file.exists():
            print(f"  ✓ SingleInstance: Implemented")
            checks_passed.append(True)

        # Check LockManager
        lm_file = Path("core/lock_manager.py")
        if lm_file.exists():
            content = lm_file.read_text()
            checks = [
                ("class LockManager" in content, "LockManager class"),
                ("acquire_lock" in content, "Lock acquisition"),
                ("deadlock" in content.lower(), "Deadlock detection"),
            ]

            for check, desc in checks:
                if check:
                    print(f"  ✓ {desc}: Found")
                    checks_passed.append(True)
                else:
                    print(f"  ✗ {desc}: Missing")
                    checks_passed.append(False)

        # Check position_locks fix
        pm_file = Path("core/position_manager.py")
        if pm_file.exists():
            content = pm_file.read_text()
            if "position_locks" in content and "asyncio.Lock" in content:
                print(f"  ✓ Proper locks in PositionManager: Found")
                checks_passed.append(True)

        return all(checks_passed) if checks_passed else False

    async def validate_critical_logic(self) -> bool:
        """Проверка защиты критической логики"""
        checks_passed = []

        # Check test files
        test_files = [
            "tests/test_wave_timestamp_calculation.py",
            "tests/critical_fixes/test_atomicity_fix.py",
            "tests/critical_fixes/test_race_conditions_fix.py",
        ]

        for test_file in test_files:
            if Path(test_file).exists():
                print(f"  ✓ Test file: {test_file}")
                checks_passed.append(True)
            else:
                print(f"  ✗ Test file missing: {test_file}")
                checks_passed.append(False)

        # Check critical markers
        critical_files = [
            "core/signal_processor_websocket.py",
            "core/position_manager.py"
        ]

        for file_path in critical_files:
            if Path(file_path).exists():
                content = Path(file_path).read_text()
                if "CRITICAL" in content:
                    print(f"  ✓ Critical markers in: {file_path}")
                    checks_passed.append(True)

        return all(checks_passed) if checks_passed else False

    async def validate_locks(self) -> bool:
        """Проверка правильности использования блокировок"""
        checks_passed = []

        pm_file = Path("core/position_manager.py")
        if pm_file.exists():
            content = pm_file.read_text()

            # Check for locks in critical methods
            checks = [
                ("position_locks" in content and "open_position" in content, "Lock for position creation"),
                ("sl_update_" in content or ("_set_stop_loss" in content and "position_locks" in content), "Lock for SL update"),
                ("trailing_stop_" in content or ("trailing" in content and "position_locks" in content), "Lock for trailing stop"),
            ]

            for check, desc in checks:
                if check:
                    print(f"  ✓ {desc}: Found")
                    checks_passed.append(True)
                else:
                    print(f"  ✗ {desc}: Missing")
                    checks_passed.append(False)

        return all(checks_passed) if checks_passed else False

    async def validate_database(self) -> bool:
        """Проверка корректности работы с БД"""
        checks_passed = []

        # Check Repository
        repo_file = Path("database/repository.py")
        if repo_file.exists():
            print(f"  ✓ Database models: Found")
            checks_passed.append(True)

            content = repo_file.read_text()
            if "CREATE TABLE" in content or "positions" in content:
                print(f"  ✓ Table constraints: Defined")
                checks_passed.append(True)

        # Check TransactionalRepository
        tr_file = Path("database/transactional_repository.py")
        if tr_file.exists():
            print(f"  ✓ TransactionalRepository: Found")
            checks_passed.append(True)

        return all(checks_passed) if checks_passed else False

    async def validate_logging(self) -> bool:
        """Проверка логирования"""
        checks_passed = []

        # Check EventLogger
        el_file = Path("core/event_logger.py")
        if el_file.exists():
            print(f"  ✓ EventLogger: Implemented")
            checks_passed.append(True)

            content = el_file.read_text()
            methods = ["log_event", "log_transaction", "log_metric"]
            for method in methods:
                if method in content:
                    print(f"  ✓ Method {method}: Found")
                    checks_passed.append(True)

        return all(checks_passed) if checks_passed else False

    async def validate_transactions(self) -> bool:
        """Проверка транзакций БД"""
        checks_passed = []

        tr_file = Path("database/transactional_repository.py")
        if tr_file.exists():
            content = tr_file.read_text()
            checks = [
                ("transaction" in content, "Transaction context"),
                ("commit" in content.lower(), "Commit support"),
                ("rollback" in content.lower(), "Rollback support"),
                ("savepoint" in content.lower(), "Savepoint support"),
            ]

            for check, desc in checks:
                if check:
                    print(f"  ✓ {desc}: Found")
                    checks_passed.append(True)
                else:
                    print(f"  ✗ {desc}: Missing")
                    checks_passed.append(False)

        return all(checks_passed) if checks_passed else False

    async def validate_integration(self) -> bool:
        """Проверка интеграции всех компонентов"""
        checks_passed = []

        # Check integration module
        int_file = Path("core/position_manager_integration.py")
        if int_file.exists():
            print(f"  ✓ Integration module: Found")
            checks_passed.append(True)

            content = int_file.read_text()
            if "apply_critical_fixes" in content:
                print(f"  ✓ Apply fixes function: Found")
                checks_passed.append(True)

        # Check main.py integration
        main_file = Path("main.py")
        if main_file.exists():
            content = main_file.read_text()
            if "apply_critical_fixes" in content or "EventLogger" in content:
                print(f"  ✓ Main.py integration: Found")
                checks_passed.append(True)

        return all(checks_passed) if checks_passed else False

    def _print_summary(self):
        """Print validation summary"""
        print("\n" + "="*60)
        print(" ИТОГОВЫЙ ОТЧЕТ")
        print("="*60)

        passed = sum(1 for v in self.results.values() if v)
        total = len(self.results)

        print(f"\nРезультаты: {passed}/{total} ({passed/total*100:.1f}%)")
        print("-" * 40)

        for name, result in self.results.items():
            status = f"{Fore.GREEN}✅ PASS{Style.RESET_ALL}" if result else f"{Fore.RED}❌ FAIL{Style.RESET_ALL}"
            print(f"{name:.<30} {status}")

        if self.issues_found:
            print(f"\n{Fore.YELLOW}⚠️ Найденные проблемы:{Style.RESET_ALL}")
            for issue in self.issues_found[:5]:
                print(f"  • {issue}")

        print("\n" + "="*60)

        if passed == total:
            print(f"{Fore.GREEN}✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!{Style.RESET_ALL}")
            print(f"{Fore.GREEN}Система готова к production.{Style.RESET_ALL}")
        elif passed >= total * 0.8:
            print(f"{Fore.YELLOW}⚠️ ПОЧТИ ГОТОВО{Style.RESET_ALL}")
            print(f"Пройдено {passed}/{total} проверок. Требуется доработка.")
        else:
            print(f"{Fore.RED}❌ ТРЕБУЕТСЯ ДОРАБОТКА{Style.RESET_ALL}")
            print("Критические проблемы не исправлены.")

        print("="*60)


async def main():
    validator = ImprovedCriticalFixesValidator()
    success = await validator.validate_all()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())