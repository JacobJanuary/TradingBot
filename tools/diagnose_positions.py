#!/usr/bin/env python3
"""
Position Duplicate Error Diagnostic Tool
Phase 2.1 of Duplicate Position Audit

ЦЕЛЬ: Диагностика состояния позиций для выявления проблем:
1. Incomplete positions (pending_entry, entry_placed, pending_sl)
2. Duplicate active positions (нарушение unique constraint)
3. Positions without stop loss on exchange
4. DB vs Exchange consistency issues
5. Orphaned positions (в DB но не на бирже, или наоборот)

ИСПОЛЬЗОВАНИЕ:
    python tools/diagnose_positions.py --mode check              # Проверка (read-only)
    python tools/diagnose_positions.py --mode report             # Детальный отчет
    python tools/diagnose_positions.py --mode check --symbol BTCUSDT  # Для конкретного символа

РЕЖИМЫ:
    check   - Быстрая проверка основных проблем
    report  - Полный отчет с статистикой и рекомендациями

ОПЦИИ:
    --symbol SYMBOL    - Проверить только указанный символ
    --exchange EXCHANGE - Проверить только указанную биржу (binance/bybit)
    --age HOURS        - Минимальный возраст incomplete позиций для алерта (default: 1)
"""

import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Set
import asyncpg
import argparse
from decimal import Decimal
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import ccxt.async_support as ccxt
except ImportError:
    print("❌ ERROR: ccxt not found. Install: pip install ccxt")
    sys.exit(1)

load_dotenv()


class PositionDiagnostics:
    """Диагностика позиций для выявления duplicate и других проблем"""

    def __init__(self, symbol_filter: Optional[str] = None,
                 exchange_filter: Optional[str] = None,
                 age_threshold_hours: int = 1):
        self.symbol_filter = symbol_filter
        self.exchange_filter = exchange_filter
        self.age_threshold = timedelta(hours=age_threshold_hours)

        # Результаты диагностики
        self.issues: List[Dict] = []
        self.warnings: List[Dict] = []
        self.stats: Dict = {}

        # Соединения
        self.conn = None
        self.exchanges: Dict = {}

    async def initialize(self):
        """Инициализация соединений с DB и биржами"""
        print("🔌 Initializing connections...")

        # Database connection
        try:
            self.conn = await asyncpg.connect(
                host='localhost',
                port=5433,
                user='elcrypto',
                password='LohNeMamont@!21',
                database='fox_crypto'
            )
            print("✅ Database connected: fox_crypto")
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            raise

        # Exchange connections
        if not self.exchange_filter or self.exchange_filter == 'binance':
            try:
                self.exchanges['binance'] = ccxt.binance({
                    'apiKey': os.getenv('BINANCE_API_KEY'),
                    'secret': os.getenv('BINANCE_API_SECRET'),
                    'enableRateLimit': True,
                    'options': {
                        'defaultType': 'future',
                        'testnet': False  # Production
                    }
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
                    'options': {
                        'defaultType': 'swap',
                        'testnet': False  # Production
                    }
                })
                await self.exchanges['bybit'].load_markets()
                print("✅ Bybit connected")
            except Exception as e:
                print(f"⚠️  Bybit connection failed: {e}")

    async def cleanup(self):
        """Закрытие всех соединений"""
        if self.conn:
            await self.conn.close()
        for exchange in self.exchanges.values():
            await exchange.close()

    # ========================================================================
    # CHECK 1: INCOMPLETE POSITIONS
    # ========================================================================

    async def check_incomplete_positions(self):
        """
        Проверка incomplete позиций (застрявших в промежуточных статусах)

        ПРОБЛЕМА: Позиции могут застрять в:
        - pending_entry: ордер не размещен
        - entry_placed: ордер размещен, SL не установлен (CRITICAL!)
        - pending_sl: SL размещается

        РИСК: Позиции без SL = неограниченные потери
        """
        print(f"\n{'='*80}")
        print("CHECK 1: INCOMPLETE POSITIONS")
        print(f"{'='*80}\n")

        query = """
            SELECT
                id, symbol, exchange, side, quantity, entry_price,
                status, exchange_order_id, stop_loss_order_id,
                created_at, updated_at,
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

        query += " ORDER BY created_at DESC"

        rows = await self.conn.fetch(query, *params)

        if not rows:
            print("✅ No incomplete positions found")
            return

        print(f"⚠️  Found {len(rows)} incomplete position(s):\n")

        for row in rows:
            age_hours = float(row['age_hours'])
            is_critical = row['status'] in ['entry_placed', 'pending_sl']
            is_old = age_hours > self.age_threshold.total_seconds() / 3600

            severity = "🔴 CRITICAL" if is_critical and is_old else "🟡 WARNING"

            print(f"{severity} Position #{row['id']}:")
            print(f"  Symbol:        {row['symbol']}")
            print(f"  Exchange:      {row['exchange']}")
            print(f"  Status:        {row['status']}")
            print(f"  Side:          {row['side']}")
            print(f"  Quantity:      {row['quantity']}")
            print(f"  Entry:         {row['entry_price']}")
            print(f"  Age:           {age_hours:.2f} hours")
            print(f"  Created:       {row['created_at']}")
            print(f"  Updated:       {row['updated_at']}")
            print(f"  Entry Order:   {row['exchange_order_id'] or 'N/A'}")
            print(f"  SL Order:      {row['stop_loss_order_id'] or 'N/A'}")

            if is_critical and is_old:
                self.issues.append({
                    'type': 'incomplete_position',
                    'severity': 'CRITICAL',
                    'position_id': row['id'],
                    'symbol': row['symbol'],
                    'exchange': row['exchange'],
                    'status': row['status'],
                    'age_hours': age_hours,
                    'message': f"Position without SL for {age_hours:.1f}h"
                })
            elif is_old:
                self.warnings.append({
                    'type': 'old_incomplete_position',
                    'position_id': row['id'],
                    'symbol': row['symbol'],
                    'status': row['status'],
                    'age_hours': age_hours
                })

            print()

    # ========================================================================
    # CHECK 2: DUPLICATE ACTIVE POSITIONS
    # ========================================================================

    async def check_duplicate_positions(self):
        """
        Проверка дубликатов активных позиций

        ПРОБЛЕМА: Unique index idx_unique_active_position должен предотвращать,
        но race condition позволяет создать дубликаты

        SQL: Найти все (symbol, exchange) с более чем 1 active позицией
        """
        print(f"\n{'='*80}")
        print("CHECK 2: DUPLICATE ACTIVE POSITIONS")
        print(f"{'='*80}\n")

        query = """
            SELECT symbol, exchange, COUNT(*) as count
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
            ORDER BY COUNT(*) DESC, symbol
        """

        duplicates = await self.conn.fetch(query, *params)

        if not duplicates:
            print("✅ No duplicate active positions found")
            return

        print(f"🔴 CRITICAL: Found {len(duplicates)} duplicate(s):\n")

        for dup in duplicates:
            symbol = dup['symbol']
            exchange = dup['exchange']
            count = dup['count']

            # Получить детали всех дубликатов
            details = await self.conn.fetch("""
                SELECT id, quantity, entry_price, exchange_order_id,
                       stop_loss_order_id, created_at, updated_at
                FROM monitoring.positions
                WHERE symbol = $1 AND exchange = $2 AND status = 'active'
                ORDER BY created_at
            """, symbol, exchange)

            print(f"🔴 {symbol} on {exchange}: {count} active positions")
            for i, pos in enumerate(details, 1):
                print(f"\n  Position #{pos['id']} (created {i}/{count}):")
                print(f"    Quantity:     {pos['quantity']}")
                print(f"    Entry:        {pos['entry_price']}")
                print(f"    Created:      {pos['created_at']}")
                print(f"    Updated:      {pos['updated_at']}")
                print(f"    Entry Order:  {pos['exchange_order_id']}")
                print(f"    SL Order:     {pos['stop_loss_order_id']}")

            self.issues.append({
                'type': 'duplicate_active_position',
                'severity': 'CRITICAL',
                'symbol': symbol,
                'exchange': exchange,
                'count': count,
                'position_ids': [p['id'] for p in details],
                'message': f"{count} active positions for {symbol} on {exchange}"
            })

            print()

    # ========================================================================
    # CHECK 3: DB vs EXCHANGE CONSISTENCY
    # ========================================================================

    async def check_db_exchange_consistency(self):
        """
        Проверка консистентности между DB и биржей

        ПРОБЛЕМА:
        - Позиция в DB, но не на бирже (orphaned в DB)
        - Позиция на бирже, но не в DB (orphaned на бирже)
        - Quantity mismatch
        """
        print(f"\n{'='*80}")
        print("CHECK 3: DB vs EXCHANGE CONSISTENCY")
        print(f"{'='*80}\n")

        for exchange_name, exchange in self.exchanges.items():
            if self.exchange_filter and exchange_name != self.exchange_filter:
                continue

            print(f"\n--- {exchange_name.upper()} ---\n")

            # Получить активные позиции из DB
            query = """
                SELECT id, symbol, side, quantity, entry_price,
                       exchange_order_id, stop_loss_order_id
                FROM monitoring.positions
                WHERE exchange = $1 AND status = 'active'
            """
            params = [exchange_name]

            if self.symbol_filter:
                query += " AND symbol = $2"
                params.append(self.symbol_filter)

            db_positions = await self.conn.fetch(query, *params)
            db_by_symbol = {p['symbol']: p for p in db_positions}

            print(f"DB: {len(db_positions)} active position(s)")

            # Получить позиции с биржи
            try:
                exchange_positions = await exchange.fetch_positions()
                # Фильтр только открытые позиции
                open_positions = [p for p in exchange_positions if float(p.get('contracts', 0)) != 0]

                # Нормализация символов (BTCUSDT:USDT → BTCUSDT)
                exchange_by_symbol = {}
                for p in open_positions:
                    symbol = p['symbol'].replace(':USDT', '').replace('/', '')
                    exchange_by_symbol[symbol] = p

                print(f"Exchange: {len(open_positions)} open position(s)")

                # Сравнение
                db_symbols = set(db_by_symbol.keys())
                exchange_symbols = set(exchange_by_symbol.keys())

                # 1. Orphaned in DB (в DB, но не на бирже)
                orphaned_db = db_symbols - exchange_symbols
                if orphaned_db:
                    print(f"\n⚠️  {len(orphaned_db)} position(s) in DB but NOT on exchange:")
                    for symbol in orphaned_db:
                        pos = db_by_symbol[symbol]
                        print(f"  - {symbol}: position #{pos['id']}, qty={pos['quantity']}")
                        self.warnings.append({
                            'type': 'orphaned_in_db',
                            'symbol': symbol,
                            'exchange': exchange_name,
                            'position_id': pos['id'],
                            'message': f"Position in DB but not on {exchange_name}"
                        })

                # 2. Orphaned on Exchange (на бирже, но не в DB)
                orphaned_exchange = exchange_symbols - db_symbols
                if orphaned_exchange:
                    print(f"\n🔴 {len(orphaned_exchange)} position(s) on exchange but NOT in DB:")
                    for symbol in orphaned_exchange:
                        pos = exchange_by_symbol[symbol]
                        contracts = pos.get('contracts', 0)
                        side = 'LONG' if float(contracts) > 0 else 'SHORT'
                        print(f"  - {symbol}: {side}, contracts={contracts}")
                        self.issues.append({
                            'type': 'orphaned_on_exchange',
                            'severity': 'CRITICAL',
                            'symbol': symbol,
                            'exchange': exchange_name,
                            'contracts': contracts,
                            'side': side,
                            'message': f"Position on {exchange_name} but not tracked in DB"
                        })

                # 3. Quantity mismatch
                common_symbols = db_symbols & exchange_symbols
                if common_symbols:
                    print(f"\n✅ {len(common_symbols)} position(s) found in both DB and exchange")
                    for symbol in common_symbols:
                        db_pos = db_by_symbol[symbol]
                        ex_pos = exchange_by_symbol[symbol]

                        db_qty = float(db_pos['quantity'])
                        ex_qty = abs(float(ex_pos.get('contracts', 0)))

                        # Tolerance 0.1% for rounding
                        if abs(db_qty - ex_qty) / max(db_qty, ex_qty) > 0.001:
                            print(f"  ⚠️  {symbol}: Quantity mismatch - DB: {db_qty}, Exchange: {ex_qty}")
                            self.warnings.append({
                                'type': 'quantity_mismatch',
                                'symbol': symbol,
                                'exchange': exchange_name,
                                'db_quantity': db_qty,
                                'exchange_quantity': ex_qty,
                                'message': f"Quantity mismatch for {symbol}"
                            })

                if not orphaned_db and not orphaned_exchange and not self.warnings:
                    print("✅ DB and exchange are consistent")

            except Exception as e:
                print(f"❌ Failed to fetch positions from {exchange_name}: {e}")
                self.issues.append({
                    'type': 'exchange_fetch_error',
                    'severity': 'ERROR',
                    'exchange': exchange_name,
                    'error': str(e)
                })

    # ========================================================================
    # CHECK 4: POSITIONS WITHOUT STOP LOSS
    # ========================================================================

    async def check_positions_without_sl(self):
        """
        Проверка активных позиций без stop loss

        РИСК: CRITICAL - неограниченные потери
        """
        print(f"\n{'='*80}")
        print("CHECK 4: POSITIONS WITHOUT STOP LOSS")
        print(f"{'='*80}\n")

        query = """
            SELECT id, symbol, exchange, side, quantity, entry_price,
                   stop_loss_order_id, created_at
            FROM monitoring.positions
            WHERE status = 'active'
              AND (stop_loss_order_id IS NULL OR stop_loss_order_id = '')
        """
        params = []

        if self.symbol_filter:
            query += " AND symbol = $1"
            params.append(self.symbol_filter)
        if self.exchange_filter:
            idx = len(params) + 1
            query += f" AND exchange = ${idx}"
            params.append(self.exchange_filter)

        rows = await self.conn.fetch(query, *params)

        if not rows:
            print("✅ All active positions have stop loss")
            return

        print(f"🔴 CRITICAL: {len(rows)} active position(s) WITHOUT stop loss:\n")

        for row in rows:
            print(f"🔴 Position #{row['id']}:")
            print(f"  Symbol:    {row['symbol']}")
            print(f"  Exchange:  {row['exchange']}")
            print(f"  Side:      {row['side']}")
            print(f"  Quantity:  {row['quantity']}")
            print(f"  Entry:     {row['entry_price']}")
            print(f"  Created:   {row['created_at']}")
            print()

            self.issues.append({
                'type': 'no_stop_loss',
                'severity': 'CRITICAL',
                'position_id': row['id'],
                'symbol': row['symbol'],
                'exchange': row['exchange'],
                'message': f"Active position without SL"
            })

    # ========================================================================
    # STATISTICS
    # ========================================================================

    async def collect_statistics(self):
        """Сбор общей статистики по позициям"""
        print(f"\n{'='*80}")
        print("STATISTICS")
        print(f"{'='*80}\n")

        # По статусам
        query = """
            SELECT status, COUNT(*) as count
            FROM monitoring.positions
            WHERE created_at > NOW() - INTERVAL '24 hours'
        """
        params = []

        if self.symbol_filter:
            query += " AND symbol = $1"
            params.append(self.symbol_filter)
        if self.exchange_filter:
            idx = len(params) + 1
            query += f" AND exchange = ${idx}"
            params.append(self.exchange_filter)

        query += " GROUP BY status ORDER BY count DESC"

        status_stats = await self.conn.fetch(query, *params)

        print("Position status (last 24h):")
        for row in status_stats:
            print(f"  {row['status']:15s}: {row['count']:4d}")

        # Частота ошибок
        error_query = """
            SELECT DATE_TRUNC('hour', created_at) as hour, COUNT(*) as count
            FROM monitoring.positions
            WHERE status = 'failed'
              AND created_at > NOW() - INTERVAL '24 hours'
            GROUP BY hour
            ORDER BY hour DESC
            LIMIT 5
        """

        error_stats = await self.conn.fetch(error_query)
        if error_stats:
            print(f"\nFailed positions (last 5 hours):")
            for row in error_stats:
                print(f"  {row['hour']}: {row['count']} failures")

        self.stats = {
            'status_distribution': {r['status']: r['count'] for r in status_stats},
            'error_frequency': [{'hour': r['hour'], 'count': r['count']} for r in error_stats]
        }

    # ========================================================================
    # REPORTS
    # ========================================================================

    def print_summary(self):
        """Вывод итогового резюме"""
        print(f"\n{'='*80}")
        print("SUMMARY")
        print(f"{'='*80}\n")

        critical_count = len([i for i in self.issues if i.get('severity') == 'CRITICAL'])
        warning_count = len(self.warnings)

        if critical_count == 0 and warning_count == 0:
            print("✅ No issues found! System is healthy.")
        else:
            if critical_count > 0:
                print(f"🔴 CRITICAL ISSUES: {critical_count}")
                for issue in self.issues:
                    if issue.get('severity') == 'CRITICAL':
                        print(f"  - {issue['type']}: {issue['message']}")

            if warning_count > 0:
                print(f"\n🟡 WARNINGS: {warning_count}")
                for warning in self.warnings:
                    print(f"  - {warning['type']}: {warning.get('message', '')}")

        print()

    def print_recommendations(self):
        """Вывод рекомендаций по исправлению"""
        if not self.issues and not self.warnings:
            return

        print(f"\n{'='*80}")
        print("RECOMMENDATIONS")
        print(f"{'='*80}\n")

        # Группировка по типам проблем
        issue_types = {}
        for issue in self.issues:
            t = issue['type']
            if t not in issue_types:
                issue_types[t] = []
            issue_types[t].append(issue)

        if 'duplicate_active_position' in issue_types:
            print("🔴 DUPLICATE POSITIONS:")
            print("  ACTION: Use cleanup tool to remove duplicates")
            print("  $ python tools/cleanup_positions.py --mode duplicates --dry-run")
            print()

        if 'incomplete_position' in issue_types:
            print("🔴 INCOMPLETE POSITIONS:")
            print("  ACTION: Recover or close incomplete positions")
            print("  $ python tools/cleanup_positions.py --mode incomplete --dry-run")
            print()

        if 'no_stop_loss' in issue_types:
            print("🔴 POSITIONS WITHOUT STOP LOSS:")
            print("  ACTION: URGENT - Manually set stop loss or close positions")
            print("  $ python tools/emergency/set_stop_loss.py")
            print()

        if 'orphaned_on_exchange' in issue_types:
            print("🔴 ORPHANED POSITIONS ON EXCHANGE:")
            print("  ACTION: Create DB entries or close on exchange")
            print("  $ python tools/cleanup_positions.py --mode orphaned")
            print()


async def main():
    parser = argparse.ArgumentParser(
        description='Diagnose position management issues',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--mode', choices=['check', 'report'], default='check',
                       help='Check mode (default: check)')
    parser.add_argument('--symbol', type=str, help='Filter by symbol')
    parser.add_argument('--exchange', choices=['binance', 'bybit'], help='Filter by exchange')
    parser.add_argument('--age', type=int, default=1,
                       help='Alert threshold for incomplete positions in hours (default: 1)')

    args = parser.parse_args()

    print("="*80)
    print("POSITION DIAGNOSTICS - Duplicate Error Audit Tool")
    print("="*80)
    print(f"Mode: {args.mode}")
    if args.symbol:
        print(f"Symbol filter: {args.symbol}")
    if args.exchange:
        print(f"Exchange filter: {args.exchange}")
    print(f"Age threshold: {args.age} hour(s)")
    print()

    diagnostics = PositionDiagnostics(
        symbol_filter=args.symbol,
        exchange_filter=args.exchange,
        age_threshold_hours=args.age
    )

    try:
        await diagnostics.initialize()

        # Основные проверки
        await diagnostics.check_incomplete_positions()
        await diagnostics.check_duplicate_positions()
        await diagnostics.check_positions_without_sl()
        await diagnostics.check_db_exchange_consistency()

        # Статистика только в режиме report
        if args.mode == 'report':
            await diagnostics.collect_statistics()

        # Резюме и рекомендации
        diagnostics.print_summary()

        if args.mode == 'report':
            diagnostics.print_recommendations()

    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        await diagnostics.cleanup()

    # Exit code
    critical_issues = len([i for i in diagnostics.issues if i.get('severity') == 'CRITICAL'])
    return 1 if critical_issues > 0 else 0


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
