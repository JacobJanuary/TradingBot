#!/usr/bin/env python3
"""
Position Cleanup Tool
Phase 2.3 of Duplicate Position Audit

ЦЕЛЬ: Безопасная очистка проблемных позиций

ВНИМАНИЕ: Этот скрипт ИЗМЕНЯЕТ данные в БД и может закрывать позиции на бирже!
          Используйте ТОЛЬКО после тщательной проверки.

РЕЖИМЫ ОЧИСТКИ:
1. duplicates    - Удаление дубликатов (оставляет самый старый)
2. incomplete    - Очистка incomplete позиций (без SL)
3. orphaned-db   - Удаление позиций из DB, отсутствующих на бирже
4. orphaned-ex   - Закрытие позиций на бирже, отсутствующих в DB
5. all           - Все вышеперечисленное

ИСПОЛЬЗОВАНИЕ:
    # Dry-run (безопасно, только показывает что будет сделано)
    python tools/cleanup_positions.py --mode duplicates --dry-run

    # Реальная очистка с подтверждением
    python tools/cleanup_positions.py --mode duplicates --confirm

    # Очистка конкретного символа
    python tools/cleanup_positions.py --mode incomplete --symbol BTCUSDT --confirm

    # Полная очистка (опасно!)
    python tools/cleanup_positions.py --mode all --confirm

ОПЦИИ:
    --mode MODE         - Режим очистки (см. выше)
    --symbol SYMBOL     - Фильтр по символу
    --exchange EXCHANGE - Фильтр по бирже
    --age HOURS         - Минимальный возраст для incomplete (default: 1)
    --dry-run           - Dry-run mode (default)
    --confirm           - Подтверждение реальных операций
    --backup PATH       - Путь для backup файла (default: auto)
    --no-backup         - Не создавать backup (опасно!)

БЕЗОПАСНОСТЬ:
- По умолчанию dry-run
- Требует явного --confirm
- Создает backup перед изменениями
- Логирует все действия
- Позволяет отменить операцию (Ctrl+C)
"""

import asyncio
import sys
import os
import argparse
import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Set
import asyncpg
from decimal import Decimal
from dotenv import load_dotenv

# Add parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import ccxt.async_support as ccxt
except ImportError:
    print("❌ ERROR: ccxt not found. Install: pip install ccxt")
    sys.exit(1)

load_dotenv()


class PositionCleaner:
    """Безопасная очистка проблемных позиций"""

    def __init__(self, mode: str, symbol_filter: Optional[str],
                 exchange_filter: Optional[str], age_hours: int,
                 dry_run: bool, backup_path: Optional[str],
                 no_backup: bool):
        self.mode = mode
        self.symbol_filter = symbol_filter
        self.exchange_filter = exchange_filter
        self.age_threshold = timedelta(hours=age_hours)
        self.dry_run = dry_run
        self.backup_path = backup_path
        self.no_backup = no_backup

        # Statistics
        self.cleaned = {
            'duplicates': 0,
            'incomplete': 0,
            'orphaned_db': 0,
            'orphaned_ex': 0
        }
        self.errors = []

        # Connections
        self.conn = None
        self.exchanges: Dict = {}

    async def initialize(self):
        """Инициализация соединений"""
        print("🔌 Initializing connections...")

        # Database
        try:
            self.conn = await asyncpg.connect(
                host='localhost',
                port=5433,
                user='elcrypto',
                password='LohNeMamont@!21',
                database='fox_crypto'
            )
            print("✅ Database connected")
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            raise

        # Exchanges (только если нужны)
        if self.mode in ['orphaned-ex', 'all']:
            if not self.exchange_filter or self.exchange_filter == 'binance':
                try:
                    self.exchanges['binance'] = ccxt.binance({
                        'apiKey': os.getenv('BINANCE_API_KEY'),
                        'secret': os.getenv('BINANCE_API_SECRET'),
                        'enableRateLimit': True,
                        'options': {'defaultType': 'future', 'testnet': False}
                    })
                    await self.exchanges['binance'].load_markets()
                    print("✅ Binance connected")
                except Exception as e:
                    print(f"⚠️  Binance connection failed: {e}")

            if not self.exchange_filter or self.exchange_filter == 'bybit':
                try:
                    self.exchanges['bybit'] = ccxt.bybit({
                        'apiKey': os.getenv('BYBIT_API_KEY'),
                        'secret': os.getenv('BYBIT_API_SECRET'),
                        'enableRateLimit': True,
                        'options': {'defaultType': 'swap', 'testnet': False}
                    })
                    await self.exchanges['bybit'].load_markets()
                    print("✅ Bybit connected")
                except Exception as e:
                    print(f"⚠️  Bybit connection failed: {e}")

    async def cleanup(self):
        """Закрытие соединений"""
        if self.conn:
            await self.conn.close()
        for exchange in self.exchanges.values():
            await exchange.close()

    # ========================================================================
    # BACKUP
    # ========================================================================

    async def create_backup(self):
        """Создание backup перед очисткой"""
        if self.no_backup:
            print("⚠️  Backup disabled (--no-backup)")
            return

        if not self.backup_path:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.backup_path = f"backup_positions_{timestamp}.json"

        print(f"📦 Creating backup: {self.backup_path}")

        # Получить все позиции для backup
        query = "SELECT * FROM monitoring.positions WHERE 1=1"
        params = []

        if self.symbol_filter:
            query += " AND symbol = $1"
            params.append(self.symbol_filter)
        if self.exchange_filter:
            idx = len(params) + 1
            query += f" AND exchange = ${idx}"
            params.append(self.exchange_filter)

        rows = await self.conn.fetch(query, *params)

        # Конвертация в JSON-сериализуемый формат
        backup_data = []
        for row in rows:
            record = dict(row)
            # Convert Decimal to string, datetime to ISO format
            for key, value in record.items():
                if isinstance(value, Decimal):
                    record[key] = str(value)
                elif isinstance(value, datetime):
                    record[key] = value.isoformat()
            backup_data.append(record)

        # Сохранение
        with open(self.backup_path, 'w') as f:
            json.dump({
                'created_at': datetime.now().isoformat(),
                'mode': self.mode,
                'filters': {
                    'symbol': self.symbol_filter,
                    'exchange': self.exchange_filter
                },
                'total_records': len(backup_data),
                'data': backup_data
            }, f, indent=2)

        print(f"✅ Backup created: {len(backup_data)} records")

    # ========================================================================
    # MODE 1: CLEAN DUPLICATES
    # ========================================================================

    async def clean_duplicates(self):
        """
        Очистка дубликатов активных позиций

        Стратегия:
        - Для каждой пары (symbol, exchange) с дубликатами
        - ОСТАВИТЬ: самую старую позицию (created_at MIN)
        - УДАЛИТЬ: все остальные дубликаты
        """
        print(f"\n{'='*80}")
        print("MODE 1: CLEAN DUPLICATES")
        print(f"{'='*80}\n")

        # Найти дубликаты
        query = """
            SELECT symbol, exchange, ARRAY_AGG(id ORDER BY created_at) as position_ids
            FROM monitoring.positions
            WHERE status = 'active'
        """
        params = []

        if self.symbol_filter:
            query += " AND symbol = $1"
            params.append(self.symbol_filter)
        if self.exchange_filter:
            idx = len(params) + 1
            query += f" AND exchange = ${idx}"
            params.append(self.exchange_filter)

        query += """
            GROUP BY symbol, exchange
            HAVING COUNT(*) > 1
        """

        duplicates = await self.conn.fetch(query, *params)

        if not duplicates:
            print("✅ No duplicates found")
            return

        print(f"Found {len(duplicates)} duplicate set(s):\n")

        for dup in duplicates:
            symbol = dup['symbol']
            exchange = dup['exchange']
            position_ids = dup['position_ids']

            keep_id = position_ids[0]  # Самый старый
            remove_ids = position_ids[1:]  # Остальные

            print(f"🔴 {symbol} on {exchange}:")
            print(f"  Total duplicates: {len(position_ids)}")
            print(f"  KEEP:   position #{keep_id} (oldest)")
            print(f"  REMOVE: {remove_ids}")

            # Получить детали для логирования
            details = await self.conn.fetch("""
                SELECT id, quantity, entry_price, created_at
                FROM monitoring.positions
                WHERE id = ANY($1)
                ORDER BY created_at
            """, position_ids)

            for pos in details:
                action = "KEEP" if pos['id'] == keep_id else "DELETE"
                print(f"    [{action:6s}] #{pos['id']}: qty={pos['quantity']}, "
                      f"entry={pos['entry_price']}, created={pos['created_at']}")

            # Удаление дубликатов
            if self.dry_run:
                print(f"  [DRY-RUN] Would delete {len(remove_ids)} duplicate(s)")
            else:
                try:
                    result = await self.conn.execute("""
                        DELETE FROM monitoring.positions
                        WHERE id = ANY($1)
                    """, remove_ids)

                    deleted_count = int(result.split()[-1])
                    print(f"  ✅ Deleted {deleted_count} duplicate(s)")
                    self.cleaned['duplicates'] += deleted_count

                except Exception as e:
                    print(f"  ❌ Failed to delete: {e}")
                    self.errors.append({
                        'type': 'duplicate_cleanup_failed',
                        'symbol': symbol,
                        'exchange': exchange,
                        'error': str(e)
                    })

            print()

    # ========================================================================
    # MODE 2: CLEAN INCOMPLETE
    # ========================================================================

    async def clean_incomplete(self):
        """
        Очистка incomplete позиций

        Стратегия:
        - pending_entry (>1h): пометить как 'failed'
        - entry_placed (>1h): попытаться закрыть на бирже, затем пометить
        - pending_sl (>1h): попытаться установить SL, иначе закрыть
        """
        print(f"\n{'='*80}")
        print("MODE 2: CLEAN INCOMPLETE POSITIONS")
        print(f"{'='*80}\n")

        query = """
            SELECT id, symbol, exchange, side, quantity, entry_price,
                   status, exchange_order_id, stop_loss_order_id, created_at,
                   EXTRACT(EPOCH FROM (NOW() - created_at)) / 3600 as age_hours
            FROM monitoring.positions
            WHERE status IN ('pending_entry', 'entry_placed', 'pending_sl')
        """
        params = []

        if self.symbol_filter:
            query += " AND symbol = $1"
            params.append(self.symbol_filter)
        if self.exchange_filter:
            idx = len(params) + 1
            query += f" AND exchange = ${idx}"
            params.append(self.exchange_filter)

        # Фильтр по возрасту
        age_threshold_hours = self.age_threshold.total_seconds() / 3600
        query += f" AND EXTRACT(EPOCH FROM (NOW() - created_at)) / 3600 > {age_threshold_hours}"

        rows = await self.conn.fetch(query, *params)

        if not rows:
            print(f"✅ No incomplete positions older than {age_threshold_hours}h")
            return

        print(f"Found {len(rows)} incomplete position(s) older than {age_threshold_hours}h:\n")

        for row in rows:
            position_id = row['id']
            symbol = row['symbol']
            exchange_name = row['exchange']
            status = row['status']
            age_hours = float(row['age_hours'])

            print(f"{'='*60}")
            print(f"Position #{position_id}: {symbol} on {exchange_name}")
            print(f"Status: {status}, Age: {age_hours:.1f}h")

            if status == 'pending_entry':
                # Безопасно - ордер не размещен
                print("  Action: Mark as 'failed' (order not placed)")

                if not self.dry_run:
                    await self.conn.execute("""
                        UPDATE monitoring.positions
                        SET status = 'failed', updated_at = NOW(),
                            exit_reason = 'cleanup: pending_entry timeout'
                        WHERE id = $1
                    """, position_id)
                    print("  ✅ Marked as 'failed'")
                    self.cleaned['incomplete'] += 1
                else:
                    print("  [DRY-RUN] Would mark as 'failed'")

            elif status in ['entry_placed', 'pending_sl']:
                # CRITICAL - позиция без SL на бирже!
                print("  ⚠️  CRITICAL: Position without SL on exchange!")
                print(f"  Action: Attempt to close on {exchange_name}")

                if exchange_name not in self.exchanges:
                    print(f"  ❌ Exchange {exchange_name} not connected")
                    continue

                exchange = self.exchanges[exchange_name]

                # Попытка найти и закрыть позицию
                try:
                    # Fetch positions
                    positions = await exchange.fetch_positions([symbol])
                    position_found = None

                    for pos in positions:
                        if float(pos.get('contracts', 0)) != 0:
                            position_found = pos
                            break

                    if position_found:
                        contracts = float(position_found['contracts'])
                        side = 'sell' if contracts > 0 else 'buy'
                        quantity = abs(contracts)

                        print(f"  Found position: {side} {quantity} contracts")

                        if not self.dry_run:
                            # Close position
                            close_order = await exchange.create_market_order(
                                symbol, side, quantity
                            )
                            print(f"  ✅ Closed on exchange: {close_order['id']}")

                            # Update DB
                            await self.conn.execute("""
                                UPDATE monitoring.positions
                                SET status = 'closed', updated_at = NOW(),
                                    closed_at = NOW(),
                                    exit_reason = 'cleanup: emergency close (no SL)'
                                WHERE id = $1
                            """, position_id)
                            print(f"  ✅ Updated DB to 'closed'")
                            self.cleaned['incomplete'] += 1
                        else:
                            print(f"  [DRY-RUN] Would close position")

                    else:
                        print(f"  ⚠️  Position not found on exchange")
                        print(f"  Action: Mark as 'failed' (already closed?)")

                        if not self.dry_run:
                            await self.conn.execute("""
                                UPDATE monitoring.positions
                                SET status = 'failed', updated_at = NOW(),
                                    exit_reason = 'cleanup: not found on exchange'
                                WHERE id = $1
                            """, position_id)
                            print(f"  ✅ Marked as 'failed'")
                            self.cleaned['incomplete'] += 1
                        else:
                            print(f"  [DRY-RUN] Would mark as 'failed'")

                except Exception as e:
                    print(f"  ❌ Failed to close position: {e}")
                    self.errors.append({
                        'type': 'incomplete_cleanup_failed',
                        'position_id': position_id,
                        'symbol': symbol,
                        'exchange': exchange_name,
                        'error': str(e)
                    })

            print()

    # ========================================================================
    # MODE 3: CLEAN ORPHANED IN DB
    # ========================================================================

    async def clean_orphaned_db(self):
        """
        Очистка orphaned позиций в DB (нет на бирже)

        Стратегия:
        - Получить активные позиции из DB
        - Получить позиции с биржи
        - Найти различия
        - Пометить отсутствующие на бирже как 'closed'
        """
        print(f"\n{'='*80}")
        print("MODE 3: CLEAN ORPHANED POSITIONS IN DB")
        print(f"{'='*80}\n")

        for exchange_name, exchange in self.exchanges.items():
            if self.exchange_filter and exchange_name != self.exchange_filter:
                continue

            print(f"\n--- {exchange_name.upper()} ---\n")

            # DB positions
            query = """
                SELECT id, symbol, quantity
                FROM monitoring.positions
                WHERE exchange = $1 AND status = 'active'
            """
            params = [exchange_name]

            if self.symbol_filter:
                query += " AND symbol = $2"
                params.append(self.symbol_filter)

            db_positions = await self.conn.fetch(query, *params)
            db_by_symbol = {p['symbol']: p for p in db_positions}

            # Exchange positions
            try:
                exchange_positions = await exchange.fetch_positions()
                open_positions = [p for p in exchange_positions if float(p.get('contracts', 0)) != 0]

                exchange_symbols = set()
                for p in open_positions:
                    symbol = p['symbol'].replace(':USDT', '').replace('/', '')
                    exchange_symbols.add(symbol)

                # Find orphaned
                db_symbols = set(db_by_symbol.keys())
                orphaned = db_symbols - exchange_symbols

                if not orphaned:
                    print(f"✅ No orphaned positions in DB for {exchange_name}")
                    continue

                print(f"Found {len(orphaned)} orphaned position(s) in DB:\n")

                for symbol in orphaned:
                    pos = db_by_symbol[symbol]
                    position_id = pos['id']

                    print(f"Position #{position_id}: {symbol}")
                    print(f"  Quantity: {pos['quantity']}")
                    print(f"  Status: In DB but NOT on exchange")

                    if not self.dry_run:
                        await self.conn.execute("""
                            UPDATE monitoring.positions
                            SET status = 'closed', updated_at = NOW(),
                                closed_at = NOW(),
                                exit_reason = 'cleanup: not found on exchange'
                            WHERE id = $1
                        """, position_id)
                        print(f"  ✅ Marked as 'closed'")
                        self.cleaned['orphaned_db'] += 1
                    else:
                        print(f"  [DRY-RUN] Would mark as 'closed'")

                    print()

            except Exception as e:
                print(f"❌ Failed to fetch positions from {exchange_name}: {e}")
                self.errors.append({
                    'type': 'orphaned_db_cleanup_failed',
                    'exchange': exchange_name,
                    'error': str(e)
                })

    # ========================================================================
    # MODE 4: CLEAN ORPHANED ON EXCHANGE
    # ========================================================================

    async def clean_orphaned_exchange(self):
        """
        Очистка orphaned позиций на бирже (нет в DB)

        Стратегия:
        - Получить позиции с биржи
        - Получить активные позиции из DB
        - Найти различия
        - ЛИБО создать в DB, ЛИБО закрыть на бирже (опасно!)
        """
        print(f"\n{'='*80}")
        print("MODE 4: CLEAN ORPHANED POSITIONS ON EXCHANGE")
        print(f"{'='*80}\n")

        print("⚠️  WARNING: This will CLOSE positions on exchange!")
        print("    Use with extreme caution\n")

        if not self.dry_run:
            print("Waiting 5 seconds... Press Ctrl+C to cancel")
            await asyncio.sleep(5)

        for exchange_name, exchange in self.exchanges.items():
            if self.exchange_filter and exchange_name != self.exchange_filter:
                continue

            print(f"\n--- {exchange_name.upper()} ---\n")

            # DB positions
            query = """
                SELECT symbol FROM monitoring.positions
                WHERE exchange = $1 AND status = 'active'
            """
            params = [exchange_name]

            if self.symbol_filter:
                query += " AND symbol = $2"
                params.append(self.symbol_filter)

            db_positions = await self.conn.fetch(query, *params)
            db_symbols = set(p['symbol'] for p in db_positions)

            # Exchange positions
            try:
                exchange_positions = await exchange.fetch_positions()
                open_positions = [p for p in exchange_positions if float(p.get('contracts', 0)) != 0]

                exchange_by_symbol = {}
                for p in open_positions:
                    symbol = p['symbol'].replace(':USDT', '').replace('/', '')
                    exchange_by_symbol[symbol] = p

                # Find orphaned
                exchange_symbols = set(exchange_by_symbol.keys())
                orphaned = exchange_symbols - db_symbols

                if not orphaned:
                    print(f"✅ No orphaned positions on {exchange_name}")
                    continue

                print(f"🔴 Found {len(orphaned)} orphaned position(s) on exchange:\n")

                for symbol in orphaned:
                    pos = exchange_by_symbol[symbol]
                    contracts = float(pos.get('contracts', 0))
                    side = 'sell' if contracts > 0 else 'buy'
                    quantity = abs(contracts)

                    print(f"{symbol}:")
                    print(f"  Contracts: {contracts}")
                    print(f"  Close: {side} {quantity}")

                    if not self.dry_run:
                        try:
                            close_order = await exchange.create_market_order(
                                symbol, side, quantity
                            )
                            print(f"  ✅ Closed: order {close_order['id']}")
                            self.cleaned['orphaned_ex'] += 1
                        except Exception as e:
                            print(f"  ❌ Failed to close: {e}")
                            self.errors.append({
                                'type': 'orphaned_ex_cleanup_failed',
                                'symbol': symbol,
                                'exchange': exchange_name,
                                'error': str(e)
                            })
                    else:
                        print(f"  [DRY-RUN] Would close position")

                    print()

            except Exception as e:
                print(f"❌ Failed to fetch positions from {exchange_name}: {e}")
                self.errors.append({
                    'type': 'orphaned_ex_cleanup_failed',
                    'exchange': exchange_name,
                    'error': str(e)
                })

    # ========================================================================
    # RUNNER
    # ========================================================================

    async def run(self):
        """Запуск очистки"""
        try:
            await self.initialize()

            # Backup
            if not self.dry_run:
                await self.create_backup()

            # Run cleanup based on mode
            if self.mode in ['duplicates', 'all']:
                await self.clean_duplicates()

            if self.mode in ['incomplete', 'all']:
                await self.clean_incomplete()

            if self.mode in ['orphaned-db', 'all']:
                if not self.exchanges:
                    print("⚠️  Skipping orphaned-db: no exchange connections")
                else:
                    await self.clean_orphaned_db()

            if self.mode in ['orphaned-ex', 'all']:
                if not self.exchanges:
                    print("⚠️  Skipping orphaned-ex: no exchange connections")
                else:
                    await self.clean_orphaned_exchange()

            # Summary
            self.print_summary()

        finally:
            await self.cleanup()

    def print_summary(self):
        """Итоговая сводка"""
        print(f"\n{'='*80}")
        print("CLEANUP SUMMARY")
        print(f"{'='*80}")
        print(f"Mode: {self.mode}")
        print(f"Dry-run: {self.dry_run}")
        print()

        total_cleaned = sum(self.cleaned.values())
        print(f"Total cleaned: {total_cleaned}")
        for key, value in self.cleaned.items():
            if value > 0:
                print(f"  {key:15s}: {value}")

        if self.errors:
            print(f"\nErrors: {len(self.errors)}")
            for err in self.errors[:5]:  # Show first 5
                print(f"  - {err['type']}: {err.get('symbol', err.get('exchange', ''))}")
            if len(self.errors) > 5:
                print(f"  ... and {len(self.errors) - 5} more")

        if self.backup_path and not self.no_backup:
            print(f"\nBackup: {self.backup_path}")

        print()


async def main():
    parser = argparse.ArgumentParser(
        description='Clean up problematic positions',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--mode',
                       choices=['duplicates', 'incomplete', 'orphaned-db', 'orphaned-ex', 'all'],
                       required=True,
                       help='Cleanup mode')
    parser.add_argument('--symbol', type=str, help='Filter by symbol')
    parser.add_argument('--exchange', choices=['binance', 'bybit'], help='Filter by exchange')
    parser.add_argument('--age', type=int, default=1,
                       help='Minimum age in hours for incomplete cleanup (default: 1)')
    parser.add_argument('--dry-run', action='store_true', default=True,
                       help='Dry-run mode (default: True)')
    parser.add_argument('--confirm', action='store_true',
                       help='Confirm real operations (disables dry-run)')
    parser.add_argument('--backup', type=str, help='Backup file path')
    parser.add_argument('--no-backup', action='store_true',
                       help='Disable backup (dangerous!)')

    args = parser.parse_args()

    # Override dry-run if confirm is set
    if args.confirm:
        args.dry_run = False

    # Safety checks
    if not args.dry_run and not args.confirm:
        print("❌ ERROR: Real operations require --confirm flag")
        return 1

    if not args.dry_run and args.no_backup:
        print("⚠️  WARNING: Running without backup!")
        print("   Press Ctrl+C to cancel, or wait 3 seconds...")
        await asyncio.sleep(3)

    print("="*80)
    print("POSITION CLEANUP TOOL")
    print("="*80)
    print(f"Mode:      {args.mode}")
    print(f"Dry-run:   {args.dry_run}")
    if args.symbol:
        print(f"Symbol:    {args.symbol}")
    if args.exchange:
        print(f"Exchange:  {args.exchange}")
    print()

    cleaner = PositionCleaner(
        mode=args.mode,
        symbol_filter=args.symbol,
        exchange_filter=args.exchange,
        age_hours=args.age,
        dry_run=args.dry_run,
        backup_path=args.backup,
        no_backup=args.no_backup
    )

    try:
        await cleaner.run()
    except KeyboardInterrupt:
        print("\n\n❌ Cancelled by user")
        return 1
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
