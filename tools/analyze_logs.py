#!/usr/bin/env python3
"""
Log Analysis Tool for Duplicate Position Errors
Phase 2.4 of Duplicate Position Audit

ЦЕЛЬ: Парсинг и анализ логов для выявления паттернов duplicate errors

АНАЛИЗИРУЕТ:
1. Частоту UniqueViolationError
2. Timeline событий (CREATE → UPDATE → ERROR)
3. Паттерны race condition (Signal + Sync)
4. Затронутые символы и биржи
5. Timing между событиями
6. Корреляцию с другими событиями

ИСПОЛЬЗОВАНИЕ:
    # Анализ последних N строк
    python tools/analyze_logs.py --lines 10000

    # Анализ за период
    python tools/analyze_logs.py --from "2025-10-22 22:00" --to "2025-10-22 23:00"

    # Анализ конкретного символа
    python tools/analyze_logs.py --symbol APTUSDT --lines 50000

    # Экспорт в JSON
    python tools/analyze_logs.py --lines 10000 --export timeline.json

ОПЦИИ:
    --file PATH         - Путь к лог-файлу (default: logs/trading_bot.log)
    --lines N           - Анализировать последние N строк (default: 10000)
    --from TIMESTAMP    - Начало периода (YYYY-MM-DD HH:MM)
    --to TIMESTAMP      - Конец периода (YYYY-MM-DD HH:MM)
    --symbol SYMBOL     - Фильтр по символу
    --export PATH       - Экспорт результатов в JSON
    --verbose           - Подробный вывод
"""

import sys
import os
import re
import argparse
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
from dataclasses import dataclass, asdict


@dataclass
class LogEntry:
    """Структура записи лога"""
    timestamp: datetime
    module: str
    level: str
    message: str
    raw_line: str


@dataclass
class DuplicateErrorEvent:
    """Событие duplicate error с контекстом"""
    timestamp: datetime
    symbol: str
    exchange: str
    error_message: str
    context_before: List[LogEntry]
    context_after: List[LogEntry]


@dataclass
class PositionCreationEvent:
    """Событие создания позиции"""
    timestamp: datetime
    symbol: str
    exchange: Optional[str]
    position_id: Optional[int]
    quantity: Optional[float]
    action: str  # CREATE, UPDATE, CLOSE, etc.


class LogAnalyzer:
    """Анализатор логов для duplicate position errors"""

    def __init__(self, log_file: str, lines: Optional[int] = None,
                 from_time: Optional[datetime] = None,
                 to_time: Optional[datetime] = None,
                 symbol_filter: Optional[str] = None,
                 verbose: bool = False):
        self.log_file = log_file
        self.lines = lines
        self.from_time = from_time
        self.to_time = to_time
        self.symbol_filter = symbol_filter
        self.verbose = verbose

        # Parsed data
        self.log_entries: List[LogEntry] = []
        self.duplicate_errors: List[DuplicateErrorEvent] = []
        self.position_events: List[PositionCreationEvent] = []

        # Statistics
        self.stats = {
            'total_lines': 0,
            'parsed_lines': 0,
            'duplicate_errors': 0,
            'position_creates': 0,
            'position_updates': 0,
            'unique_symbols': set(),
            'errors_by_symbol': defaultdict(int),
            'errors_by_hour': defaultdict(int),
            'errors_by_exchange': defaultdict(int)
        }

        # Regex patterns
        self.log_pattern = re.compile(
            r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - ([^ ]+) - (\w+) - (.+)$'
        )

        self.duplicate_error_pattern = re.compile(
            r'UniqueViolationError.*duplicate key.*idx_unique_active_position'
        )

        self.symbol_pattern = re.compile(
            r'(symbol[=:\s]+|position for )([A-Z0-9]+USDT)',
            re.IGNORECASE
        )

        self.position_id_pattern = re.compile(
            r'position[_\s#]+(\d+)',
            re.IGNORECASE
        )

        self.exchange_pattern = re.compile(
            r'(binance)',
            re.IGNORECASE
        )

    def parse_log_line(self, line: str) -> Optional[LogEntry]:
        """Парсинг строки лога"""
        match = self.log_pattern.match(line.strip())
        if not match:
            return None

        timestamp_str, module, level, message = match.groups()

        try:
            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
        except ValueError:
            return None

        return LogEntry(
            timestamp=timestamp,
            module=module,
            level=level,
            message=message,
            raw_line=line
        )

    def read_logs(self):
        """Чтение и парсинг лог-файла"""
        print(f"📖 Reading log file: {self.log_file}")

        if not os.path.exists(self.log_file):
            print(f"❌ Log file not found: {self.log_file}")
            return

        # Read file
        with open(self.log_file, 'r', encoding='utf-8', errors='ignore') as f:
            if self.lines:
                # Read last N lines
                all_lines = f.readlines()
                lines = all_lines[-self.lines:]
                print(f"   Reading last {len(lines)} lines")
            else:
                lines = f.readlines()
                print(f"   Reading all {len(lines)} lines")

        self.stats['total_lines'] = len(lines)

        # Parse lines
        for line in lines:
            entry = self.parse_log_line(line)
            if not entry:
                continue

            # Time filter
            if self.from_time and entry.timestamp < self.from_time:
                continue
            if self.to_time and entry.timestamp > self.to_time:
                continue

            # Symbol filter
            if self.symbol_filter:
                if self.symbol_filter.upper() not in entry.message.upper():
                    continue

            self.log_entries.append(entry)
            self.stats['parsed_lines'] += 1

        print(f"✅ Parsed {self.stats['parsed_lines']} log entries")

        if self.from_time or self.to_time:
            print(f"   Time range: {self.log_entries[0].timestamp} → {self.log_entries[-1].timestamp}")

    def analyze_duplicate_errors(self):
        """Анализ duplicate errors с контекстом"""
        print(f"\n{'='*80}")
        print("ANALYZING DUPLICATE ERRORS")
        print(f"{'='*80}\n")

        for i, entry in enumerate(self.log_entries):
            if not self.duplicate_error_pattern.search(entry.message):
                continue

            # Extract symbol and exchange
            symbol_match = self.symbol_pattern.search(entry.message)
            symbol = symbol_match.group(2) if symbol_match else 'UNKNOWN'

            exchange_match = self.exchange_pattern.search(entry.message)
            exchange = exchange_match.group(1).lower() if exchange_match else 'unknown'

            # Get context (10 lines before and after)
            context_before = self.log_entries[max(0, i-10):i]
            context_after = self.log_entries[i+1:min(len(self.log_entries), i+11)]

            error_event = DuplicateErrorEvent(
                timestamp=entry.timestamp,
                symbol=symbol,
                exchange=exchange,
                error_message=entry.message,
                context_before=context_before,
                context_after=context_after
            )

            self.duplicate_errors.append(error_event)

            # Update stats
            self.stats['duplicate_errors'] += 1
            self.stats['unique_symbols'].add(symbol)
            self.stats['errors_by_symbol'][symbol] += 1
            self.stats['errors_by_exchange'][exchange] += 1

            hour_key = entry.timestamp.strftime('%Y-%m-%d %H:00')
            self.stats['errors_by_hour'][hour_key] += 1

        print(f"Found {len(self.duplicate_errors)} duplicate error(s)")

        if self.duplicate_errors:
            print(f"\nErrors by symbol:")
            for symbol, count in sorted(self.stats['errors_by_symbol'].items(),
                                       key=lambda x: x[1], reverse=True):
                print(f"  {symbol:15s}: {count}")

            print(f"\nErrors by exchange:")
            for exchange, count in sorted(self.stats['errors_by_exchange'].items(),
                                         key=lambda x: x[1], reverse=True):
                print(f"  {exchange:10s}: {count}")

            print(f"\nErrors by hour:")
            for hour, count in sorted(self.stats['errors_by_hour'].items()):
                print(f"  {hour}: {count}")

    def analyze_race_conditions(self):
        """Анализ race condition паттернов"""
        print(f"\n{'='*80}")
        print("ANALYZING RACE CONDITION PATTERNS")
        print(f"{'='*80}\n")

        for error in self.duplicate_errors:
            print(f"\n{'─'*80}")
            print(f"DUPLICATE ERROR: {error.symbol} on {error.exchange}")
            print(f"Timestamp: {error.timestamp}")
            print(f"{'─'*80}")

            # Look for CREATE events in context
            creates = []
            updates = []

            for entry in error.context_before:
                msg_lower = entry.message.lower()

                # Look for CREATE
                if 'created position' in msg_lower or 'create_position' in msg_lower:
                    pos_id_match = self.position_id_pattern.search(entry.message)
                    pos_id = int(pos_id_match.group(1)) if pos_id_match else None

                    creates.append({
                        'timestamp': entry.timestamp,
                        'position_id': pos_id,
                        'message': entry.message
                    })

                # Look for UPDATE
                if 'update' in msg_lower and ('entry_placed' in msg_lower or 'pending_sl' in msg_lower):
                    updates.append({
                        'timestamp': entry.timestamp,
                        'message': entry.message
                    })

            # Print timeline
            print("\nTIMELINE (10s before error):")
            for entry in error.context_before[-10:]:
                delta = (error.timestamp - entry.timestamp).total_seconds()
                indicator = ""
                if 'created position' in entry.message.lower():
                    indicator = "← CREATE"
                elif 'entry_placed' in entry.message.lower():
                    indicator = "← UPDATE (exit index)"
                elif 'sync' in entry.message.lower():
                    indicator = "← SYNC"

                print(f"  T-{delta:4.1f}s: {entry.message[:100]} {indicator}")

            print(f"\n  T+0.0s: ❌ DUPLICATE ERROR: {error.error_message[:80]}")

            # Analysis
            if len(creates) >= 2:
                print(f"\n🔴 PATTERN: Multiple CREATE attempts detected!")
                print(f"   {len(creates)} position creation(s) in 10s window")

                for i, create in enumerate(creates):
                    print(f"   {i+1}. Position #{create.get('position_id', '?')} at {create['timestamp']}")

                # Calculate timing
                if len(creates) >= 2:
                    time_diff = (creates[1]['timestamp'] - creates[0]['timestamp']).total_seconds()
                    print(f"\n   Time between creates: {time_diff:.2f}s")

                    if time_diff < 5:
                        print(f"   ⚠️  CONCURRENT CREATE (< 5s) - Likely race condition!")

            if updates:
                print(f"\n⚠️  UPDATE events detected:")
                for update in updates:
                    print(f"   - {update['timestamp']}: {update['message'][:80]}")
                print(f"   Possible Scenario B (Signal + Sync during UPDATE)")

    def analyze_position_events(self):
        """Анализ всех событий создания/обновления позиций"""
        print(f"\n{'='*80}")
        print("ANALYZING POSITION EVENTS")
        print(f"{'='*80}\n")

        for entry in self.log_entries:
            msg_lower = entry.message.lower()

            # CREATE events
            if 'created position' in msg_lower or 'create_position' in msg_lower:
                symbol_match = self.symbol_pattern.search(entry.message)
                symbol = symbol_match.group(2) if symbol_match else None

                pos_id_match = self.position_id_pattern.search(entry.message)
                pos_id = int(pos_id_match.group(1)) if pos_id_match else None

                exchange_match = self.exchange_pattern.search(entry.message)
                exchange = exchange_match.group(1).lower() if exchange_match else None

                event = PositionCreationEvent(
                    timestamp=entry.timestamp,
                    symbol=symbol,
                    exchange=exchange,
                    position_id=pos_id,
                    quantity=None,
                    action='CREATE'
                )
                self.position_events.append(event)
                self.stats['position_creates'] += 1

            # UPDATE events
            elif 'update' in msg_lower and 'position' in msg_lower:
                symbol_match = self.symbol_pattern.search(entry.message)
                symbol = symbol_match.group(2) if symbol_match else None

                pos_id_match = self.position_id_pattern.search(entry.message)
                pos_id = int(pos_id_match.group(1)) if pos_id_match else None

                event = PositionCreationEvent(
                    timestamp=entry.timestamp,
                    symbol=symbol,
                    exchange=None,
                    position_id=pos_id,
                    quantity=None,
                    action='UPDATE'
                )
                self.position_events.append(event)
                self.stats['position_updates'] += 1

        print(f"Position creates: {self.stats['position_creates']}")
        print(f"Position updates: {self.stats['position_updates']}")

        # Find duplicate creates for same symbol
        if self.symbol_filter:
            creates_for_symbol = [e for e in self.position_events
                                 if e.action == 'CREATE' and e.symbol == self.symbol_filter]

            if creates_for_symbol:
                print(f"\nCREATE events for {self.symbol_filter}:")
                for i, event in enumerate(creates_for_symbol):
                    print(f"  {i+1}. {event.timestamp} - Position #{event.position_id}")

                if len(creates_for_symbol) >= 2:
                    print(f"\n⚠️  Multiple creates detected for {self.symbol_filter}")
                    for i in range(len(creates_for_symbol) - 1):
                        time_diff = (creates_for_symbol[i+1].timestamp -
                                   creates_for_symbol[i].timestamp).total_seconds()
                        print(f"   Time between create {i+1} and {i+2}: {time_diff:.2f}s")

    def print_statistics(self):
        """Вывод общей статистики"""
        print(f"\n{'='*80}")
        print("STATISTICS")
        print(f"{'='*80}\n")

        print(f"Total log lines:      {self.stats['total_lines']}")
        print(f"Parsed entries:       {self.stats['parsed_lines']}")
        print(f"Duplicate errors:     {self.stats['duplicate_errors']}")
        print(f"Position creates:     {self.stats['position_creates']}")
        print(f"Position updates:     {self.stats['position_updates']}")
        print(f"Unique symbols:       {len(self.stats['unique_symbols'])}")

        if self.log_entries:
            duration = (self.log_entries[-1].timestamp -
                       self.log_entries[0].timestamp).total_seconds()
            hours = duration / 3600

            if hours > 0 and self.stats['duplicate_errors'] > 0:
                error_rate = self.stats['duplicate_errors'] / hours
                print(f"\nTime span:            {hours:.2f} hours")
                print(f"Error rate:           {error_rate:.2f} errors/hour")
                print(f"Projected daily:      {error_rate * 24:.1f} errors/day")

    def export_results(self, export_path: str):
        """Экспорт результатов в JSON"""
        print(f"\n📤 Exporting results to: {export_path}")

        # Prepare data for JSON serialization
        data = {
            'analysis_timestamp': datetime.now().isoformat(),
            'log_file': self.log_file,
            'filters': {
                'lines': self.lines,
                'from_time': self.from_time.isoformat() if self.from_time else None,
                'to_time': self.to_time.isoformat() if self.to_time else None,
                'symbol': self.symbol_filter
            },
            'statistics': {
                'total_lines': self.stats['total_lines'],
                'parsed_lines': self.stats['parsed_lines'],
                'duplicate_errors': self.stats['duplicate_errors'],
                'position_creates': self.stats['position_creates'],
                'position_updates': self.stats['position_updates'],
                'unique_symbols': list(self.stats['unique_symbols']),
                'errors_by_symbol': dict(self.stats['errors_by_symbol']),
                'errors_by_hour': dict(self.stats['errors_by_hour']),
                'errors_by_exchange': dict(self.stats['errors_by_exchange'])
            },
            'duplicate_errors': [
                {
                    'timestamp': err.timestamp.isoformat(),
                    'symbol': err.symbol,
                    'exchange': err.exchange,
                    'error_message': err.error_message,
                    'context_timeline': [
                        {
                            'timestamp': e.timestamp.isoformat(),
                            'level': e.level,
                            'message': e.message
                        }
                        for e in err.context_before[-10:]
                    ]
                }
                for err in self.duplicate_errors
            ],
            'position_events': [
                {
                    'timestamp': evt.timestamp.isoformat(),
                    'symbol': evt.symbol,
                    'exchange': evt.exchange,
                    'position_id': evt.position_id,
                    'action': evt.action
                }
                for evt in self.position_events
            ]
        }

        with open(export_path, 'w') as f:
            json.dump(data, f, indent=2)

        print(f"✅ Exported {len(self.duplicate_errors)} error event(s)")
        print(f"✅ Exported {len(self.position_events)} position event(s)")


def main():
    parser = argparse.ArgumentParser(
        description='Analyze logs for duplicate position errors',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--file', type=str, default='logs/trading_bot.log',
                       help='Log file path (default: logs/trading_bot.log)')
    parser.add_argument('--lines', type=int,
                       help='Analyze last N lines')
    parser.add_argument('--from', dest='from_time', type=str,
                       help='Start time (YYYY-MM-DD HH:MM)')
    parser.add_argument('--to', dest='to_time', type=str,
                       help='End time (YYYY-MM-DD HH:MM)')
    parser.add_argument('--symbol', type=str,
                       help='Filter by symbol')
    parser.add_argument('--export', type=str,
                       help='Export results to JSON file')
    parser.add_argument('--verbose', action='store_true',
                       help='Verbose output')

    args = parser.parse_args()

    # Parse time arguments
    from_time = None
    to_time = None

    if args.from_time:
        try:
            from_time = datetime.strptime(args.from_time, '%Y-%m-%d %H:%M')
        except ValueError:
            print(f"❌ Invalid --from format. Use: YYYY-MM-DD HH:MM")
            return 1

    if args.to_time:
        try:
            to_time = datetime.strptime(args.to_time, '%Y-%m-%d %H:%M')
        except ValueError:
            print(f"❌ Invalid --to format. Use: YYYY-MM-DD HH:MM")
            return 1

    print("="*80)
    print("LOG ANALYSIS TOOL - Duplicate Position Errors")
    print("="*80)
    print(f"Log file: {args.file}")
    if args.lines:
        print(f"Lines:    Last {args.lines}")
    if from_time:
        print(f"From:     {from_time}")
    if to_time:
        print(f"To:       {to_time}")
    if args.symbol:
        print(f"Symbol:   {args.symbol}")
    print()

    analyzer = LogAnalyzer(
        log_file=args.file,
        lines=args.lines,
        from_time=from_time,
        to_time=to_time,
        symbol_filter=args.symbol,
        verbose=args.verbose
    )

    try:
        # Read and parse logs
        analyzer.read_logs()

        if analyzer.stats['parsed_lines'] == 0:
            print("⚠️  No log entries found matching filters")
            return 0

        # Analyze
        analyzer.analyze_duplicate_errors()
        analyzer.analyze_race_conditions()
        analyzer.analyze_position_events()

        # Statistics
        analyzer.print_statistics()

        # Export
        if args.export:
            analyzer.export_results(args.export)

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
