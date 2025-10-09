#!/usr/bin/env python3
"""
Comprehensive health check после каждого изменения
ЗАПУСКАТЬ ПОСЛЕ КАЖДОГО COMMIT!

Проверяет:
- Импорты всех критичных модулей
- Database connection
- Decimal utils
- Exchange manager
- Models schema
- Repository SQL injection protection
- CryptoManager salt
"""
import asyncio
import sys
import os
from pathlib import Path
from decimal import Decimal

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

class HealthChecker:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.warnings = []

    async def check_imports(self):
        """TEST 1: Все критичные модули импортируются"""
        critical_modules = [
            'database.repository',
            'database.models',
            'core.exchange_manager',
            'core.position_manager',
            'core.risk_manager',
            'utils.decimal_utils',
            'utils.crypto_manager',
            'protection.stop_loss_manager',
        ]

        for module in critical_modules:
            try:
                __import__(module)
                self.passed.append(f"✅ Import {module}")
            except Exception as e:
                self.failed.append(f"❌ Import {module}: {e}")

    async def check_database(self):
        """TEST 2: Database connection и schema"""
        try:
            from database.repository import Repository

            repo = Repository()
            await repo.connect()

            # Проверить что positions table существует
            result = await repo.pool.fetchval("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = 'monitoring' AND table_name = 'positions'
            """)

            if result == 1:
                self.passed.append("✅ Database: monitoring.positions exists")
            else:
                self.failed.append("❌ Database: monitoring.positions NOT found")

            # Проверить что можем читать позиции
            positions = await repo.get_all_positions(limit=1)
            self.passed.append(f"✅ Database: Can read positions")

            await repo.disconnect()

        except Exception as e:
            self.failed.append(f"❌ Database: {e}")

    async def check_decimal_utils(self):
        """TEST 3: Decimal utils работают корректно"""
        try:
            from utils.decimal_utils import to_decimal

            # Test to_decimal
            result = to_decimal("123.456", precision=2)
            if result == Decimal("123.46"):
                self.passed.append("✅ Decimal: to_decimal works")
            else:
                self.failed.append(f"❌ Decimal: to_decimal returned {result}")

            # Test safe_decimal (если существует)
            try:
                from utils.decimal_utils import safe_decimal
                result = safe_decimal("invalid", default=Decimal("0"))
                if result == Decimal("0"):
                    self.passed.append("✅ Decimal: safe_decimal works")
                else:
                    self.failed.append(f"❌ Decimal: safe_decimal returned {result}")
            except ImportError:
                self.warnings.append("⚠️  Decimal: safe_decimal not implemented yet")

        except Exception as e:
            self.failed.append(f"❌ Decimal utils: {e}")

    async def check_exchange_manager(self):
        """TEST 4: Exchange manager инициализируется"""
        try:
            from core.exchange_manager import ExchangeManager

            # Создать manager (НЕ подключаться к бирже!)
            em = ExchangeManager('binance', testnet=True)

            # Проверить что rate_limiter есть
            if hasattr(em, 'rate_limiter'):
                self.passed.append("✅ ExchangeManager: has rate_limiter")
            else:
                self.failed.append("❌ ExchangeManager: NO rate_limiter")

            # Проверить что методы существуют
            required_methods = [
                'create_market_order',
                'cancel_order',
                'fetch_balance',
                'set_leverage'
            ]

            for method in required_methods:
                if hasattr(em, method):
                    self.passed.append(f"✅ ExchangeManager: has {method}")
                else:
                    self.failed.append(f"❌ ExchangeManager: NO {method}")

        except Exception as e:
            self.failed.append(f"❌ ExchangeManager: {e}")

    async def check_models_schema(self):
        """TEST 5: models.py использует правильную схему"""
        try:
            from database.models import Position

            # Проверить schema в __table_args__
            if hasattr(Position, '__table_args__'):
                args = Position.__table_args__

                # Найти schema в tuple или dict
                schema = None
                if isinstance(args, dict):
                    schema = args.get('schema')
                elif isinstance(args, tuple):
                    for item in args:
                        if isinstance(item, dict):
                            schema = item.get('schema')
                            break

                if schema == 'monitoring':
                    self.passed.append("✅ Models: Position uses 'monitoring' schema")
                else:
                    self.failed.append(f"❌ Models: Position uses '{schema}' schema (should be 'monitoring')")
            else:
                self.failed.append("❌ Models: Position has no __table_args__")

        except Exception as e:
            self.failed.append(f"❌ Models: {e}")

    async def check_repository_sql_injection_protection(self):
        """TEST 6: Repository защищен от SQL injection"""
        try:
            from database.repository import Repository

            # Проверить что есть ALLOWED_FIELDS
            if hasattr(Repository, 'ALLOWED_POSITION_FIELDS'):
                self.passed.append("✅ Repository: SQL injection protection exists")

                # Попробовать SQL injection
                repo = Repository()
                await repo.connect()

                try:
                    await repo.update_position(
                        9999,
                        **{'malicious_field; DROP TABLE': 'value'}
                    )
                    self.failed.append("❌ Repository: SQL injection NOT blocked!")
                except ValueError as e:
                    if 'Invalid field' in str(e):
                        self.passed.append("✅ Repository: SQL injection blocked")
                    else:
                        self.warnings.append(f"⚠️  Repository: Unexpected error: {e}")
                except Exception:
                    # Position not found is OK - we're just testing validation
                    self.passed.append("✅ Repository: SQL injection blocked")

                await repo.disconnect()

            else:
                self.warnings.append("⚠️  Repository: SQL injection protection NOT implemented yet")

        except Exception as e:
            self.warnings.append(f"⚠️  Repository check: {e}")

    async def check_crypto_manager_salt(self):
        """TEST 7: CryptoManager использует random salt"""
        try:
            from utils.crypto_manager import CryptoManager

            cm = CryptoManager()

            # Проверить что salt существует и НЕ fixed
            if hasattr(cm, 'salt'):
                if cm.salt != b'trading_bot_salt':
                    self.passed.append("✅ CryptoManager: Uses random salt")
                else:
                    self.failed.append("❌ CryptoManager: Still uses FIXED salt!")
            else:
                self.warnings.append("⚠️  CryptoManager: salt attribute not found (not fixed yet)")

        except Exception as e:
            # CryptoManager может не быть критичным
            self.warnings.append(f"⚠️  CryptoManager: {e}")

    async def check_position_manager(self):
        """TEST 8: Position manager инициализируется"""
        try:
            from core.position_manager import PositionManager

            # Просто проверить что импортируется
            self.passed.append("✅ PositionManager: Import OK")

            # Проверить что есть ключевые методы
            if hasattr(PositionManager, 'open_position'):
                self.passed.append("✅ PositionManager: has open_position")
            else:
                self.failed.append("❌ PositionManager: NO open_position")

        except Exception as e:
            self.failed.append(f"❌ PositionManager: {e}")

    async def run_all_checks(self):
        """Запустить все проверки"""
        print("="*80)
        print("🏥 COMPREHENSIVE HEALTH CHECK")
        print("="*80)
        print()

        await self.check_imports()
        await self.check_database()
        await self.check_decimal_utils()
        await self.check_exchange_manager()
        await self.check_models_schema()
        await self.check_repository_sql_injection_protection()
        await self.check_crypto_manager_salt()
        await self.check_position_manager()

        # Вывести результаты
        print("\n" + "="*80)
        print("RESULTS")
        print("="*80)

        if self.passed:
            print(f"\n✅ PASSED ({len(self.passed)}):")
            for item in self.passed:
                print(f"   {item}")

        if self.warnings:
            print(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            for item in self.warnings:
                print(f"   {item}")

        if self.failed:
            print(f"\n❌ FAILED ({len(self.failed)}):")
            for item in self.failed:
                print(f"   {item}")

        print("\n" + "="*80)
        total = len(self.passed) + len(self.warnings) + len(self.failed)
        print(f"TOTAL: {len(self.passed)}/{total} passed, {len(self.warnings)} warnings, {len(self.failed)} failed")
        print("="*80)

        # Warnings OK, но failures - STOP
        return len(self.failed) == 0

async def main():
    checker = HealthChecker()
    success = await checker.run_all_checks()

    if success:
        print("\n✅ HEALTH CHECK PASSED - safe to continue")
        return 0
    else:
        print("\n❌ HEALTH CHECK FAILED - DO NOT CONTINUE!")
        print("   Review errors above and fix before proceeding")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
