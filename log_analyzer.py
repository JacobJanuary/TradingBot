#!/usr/bin/env python3
"""
Log Analyzer Tool
Parses bot logs and generates comprehensive analysis report
"""

import re
from datetime import datetime
from collections import defaultdict, Counter
from typing import List, Dict, Optional
import json
import sys
from pathlib import Path


class LogAnalyzer:
    """Analyzes bot log files"""

    def __init__(self, log_file: str):
        self.log_file = log_file
        self.entries: List[Dict] = []
        self.errors: List[Dict] = []
        self.warnings: List[Dict] = []
        self.critical_events: List[Dict] = []

    def parse_logs(self):
        """Parse log file into structured entries"""

        # Pattern for standard Python logging format
        pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - ([\w.]+) - (\w+) - (.+)'

        try:
            with open(self.log_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    match = re.match(pattern, line)
                    if match:
                        timestamp_str, module, level, message = match.groups()
                        try:
                            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
                        except ValueError:
                            # If parsing fails, use current time
                            timestamp = datetime.now()

                        entry = {
                            'line_num': line_num,
                            'timestamp': timestamp,
                            'module': module,
                            'level': level,
                            'message': message.strip()
                        }

                        self.entries.append(entry)

                        if level == 'ERROR':
                            self.errors.append(entry)
                        elif level == 'WARNING':
                            self.warnings.append(entry)
                        elif level == 'CRITICAL':
                            self.critical_events.append(entry)

            print(f"✅ Parsed {len(self.entries)} log entries")
            print(f"   ├─ Errors: {len(self.errors)}")
            print(f"   ├─ Warnings: {len(self.warnings)}")
            print(f"   └─ Critical: {len(self.critical_events)}")

        except FileNotFoundError:
            print(f"❌ Log file not found: {self.log_file}")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Error parsing log file: {e}")
            sys.exit(1)

    def analyze_position_lifecycle(self):
        """Analyze position opening/closing lifecycle"""

        opened = [e for e in self.entries if 'position opened' in e['message'].lower()]
        closed = [e for e in self.entries if 'position closed' in e['message'].lower()]

        print(f"\n📈 POSITION LIFECYCLE")
        print(f"  Positions Opened: {len(opened)}")
        print(f"  Positions Closed: {len(closed)}")

        # Extract symbols from messages
        symbols_opened = Counter()
        symbols_closed = Counter()

        for entry in opened:
            # Try to extract symbol from message
            match = re.search(r'symbol[=:]?\s*(\w+)', entry['message'], re.IGNORECASE)
            if match:
                symbols_opened[match.group(1)] += 1
            else:
                # Try alternative patterns
                match = re.search(r'(\w+USDT?)', entry['message'])
                if match:
                    symbols_opened[match.group(1)] += 1

        for entry in closed:
            match = re.search(r'symbol[=:]?\s*(\w+)', entry['message'], re.IGNORECASE)
            if match:
                symbols_closed[match.group(1)] += 1
            else:
                match = re.search(r'(\w+USDT?)', entry['message'])
                if match:
                    symbols_closed[match.group(1)] += 1

        if symbols_opened:
            print(f"\n  Top symbols opened:")
            for symbol, count in symbols_opened.most_common(5):
                print(f"    {symbol}: {count}")

        if symbols_closed:
            print(f"\n  Top symbols closed:")
            for symbol, count in symbols_closed.most_common(5):
                print(f"    {symbol}: {count}")

        # Opening rate over time
        if opened:
            time_span = (opened[-1]['timestamp'] - opened[0]['timestamp']).total_seconds() / 60
            if time_span > 0:
                rate = len(opened) / time_span
                print(f"\n  Opening rate: {rate:.2f} positions/minute")

    def analyze_errors(self):
        """Analyze error messages"""

        print(f"\n❌ ERRORS ANALYSIS")
        print(f"  Total errors: {len(self.errors)}")

        if not self.errors:
            print("  No errors found!")
            return

        # Group by error type
        error_types = Counter()
        for error in self.errors:
            # Try to extract exception type
            if 'Exception' in error['message'] or 'Error' in error['message']:
                match = re.search(r'(\w+(?:Exception|Error))', error['message'])
                if match:
                    error_types[match.group(1)] += 1
                else:
                    error_types['Unknown'] += 1
            else:
                # Try to categorize by keywords
                msg_lower = error['message'].lower()
                if 'timeout' in msg_lower:
                    error_types['Timeout'] += 1
                elif 'connection' in msg_lower:
                    error_types['Connection'] += 1
                elif 'api' in msg_lower:
                    error_types['API'] += 1
                else:
                    error_types['Other'] += 1

        print(f"\n  Error types:")
        for error_type, count in error_types.most_common():
            print(f"    {error_type}: {count}")

        # Modules with errors
        error_modules = Counter(e['module'] for e in self.errors)
        print(f"\n  Modules with most errors:")
        for module, count in error_modules.most_common(5):
            print(f"    {module}: {count}")

        # Show first few errors as examples
        print(f"\n  Sample errors (first 3):")
        for error in self.errors[:3]:
            print(f"    [{error['timestamp']}] {error['module']}")
            print(f"    {error['message'][:150]}...")

    def analyze_stop_loss_operations(self):
        """Analyze stop-loss operations"""

        sl_set = [e for e in self.entries if any(keyword in e['message'].lower()
                  for keyword in ['stop loss set', 'sl set', 'stop-loss set'])]
        sl_updated = [e for e in self.entries if any(keyword in e['message'].lower()
                      for keyword in ['stop loss updated', 'sl updated', 'stop-loss updated'])]
        sl_triggered = [e for e in self.entries if any(keyword in e['message'].lower()
                        for keyword in ['stop loss triggered', 'sl triggered', 'stop-loss triggered'])]
        sl_missing = [e for e in self.entries if 'missing stop loss' in e['message'].lower()
                      or 'without sl' in e['message'].lower()
                      or 'no stop loss' in e['message'].lower()]

        print(f"\n🛡️  STOP LOSS OPERATIONS")
        print(f"  SL Set: {len(sl_set)}")
        print(f"  SL Updated: {len(sl_updated)}")
        print(f"  SL Triggered: {len(sl_triggered)}")
        print(f"  ⚠️  SL Missing: {len(sl_missing)}")

        if sl_missing:
            print(f"\n  WARNING: Positions without SL detected!")
            for entry in sl_missing[:5]:  # First 5
                print(f"    [{entry['timestamp']}] {entry['message'][:100]}")

        # Calculate update frequency
        if sl_updated:
            time_span = (sl_updated[-1]['timestamp'] - sl_updated[0]['timestamp']).total_seconds() / 60
            if time_span > 0:
                rate = len(sl_updated) / time_span
                print(f"\n  SL update rate: {rate:.2f} updates/minute")

    def analyze_trailing_stop(self):
        """Analyze trailing stop operations"""

        ts_activated = [e for e in self.entries if 'trailing stop activated' in e['message'].lower()
                        or 'trailing activated' in e['message'].lower()]
        ts_updated = [e for e in self.entries if 'trailing stop updated' in e['message'].lower()
                      or 'trailing updated' in e['message'].lower()]

        print(f"\n📊 TRAILING STOP")
        print(f"  Activated: {len(ts_activated)}")
        print(f"  Updated: {len(ts_updated)}")

        if ts_activated and ts_updated:
            avg_updates = len(ts_updated) / len(ts_activated)
            print(f"  Avg updates per activation: {avg_updates:.2f}")

        # Check for excessive updates
        if ts_updated:
            time_span = (ts_updated[-1]['timestamp'] - ts_updated[0]['timestamp']).total_seconds() / 60
            if time_span > 0:
                rate = len(ts_updated) / time_span
                print(f"  Update rate: {rate:.2f} updates/minute")
                if rate > 5:
                    print(f"  ⚠️  WARNING: High trailing stop update rate!")

    def analyze_websocket_health(self):
        """Analyze WebSocket connection health"""

        ws_connected = [e for e in self.entries if any(keyword in e['message'].lower()
                        for keyword in ['websocket connected', 'ws connected'])]
        ws_disconnected = [e for e in self.entries if any(keyword in e['message'].lower()
                           for keyword in ['websocket disconnected', 'ws disconnected'])]
        ws_reconnecting = [e for e in self.entries if 'reconnect' in e['message'].lower()
                           and 'websocket' in e['message'].lower()]

        print(f"\n🔌 WEBSOCKET HEALTH")
        print(f"  Connections: {len(ws_connected)}")
        print(f"  Disconnections: {len(ws_disconnected)}")
        print(f"  Reconnects: {len(ws_reconnecting)}")

        if len(ws_disconnected) > 10:
            print(f"  ⚠️  WARNING: High disconnection rate!")

        # Calculate uptime percentage
        total_events = len(ws_connected) + len(ws_disconnected)
        if total_events > 0:
            uptime_pct = (len(ws_connected) / total_events) * 100
            print(f"  Connection success rate: {uptime_pct:.1f}%")

    def analyze_timing_issues(self):
        """Analyze timing-related problems"""

        timeout_errors = [e for e in self.errors if 'timeout' in e['message'].lower()]
        rate_limit_errors = [e for e in self.errors if any(keyword in e['message'].lower()
                             for keyword in ['rate limit', 'too many requests', '429'])]
        slow_operations = [e for e in self.warnings if any(keyword in e['message'].lower()
                           for keyword in ['slow', 'took', 'latency', 'delay'])]

        print(f"\n⏱️  TIMING ISSUES")
        print(f"  Timeout errors: {len(timeout_errors)}")
        print(f"  Rate limit errors: {len(rate_limit_errors)}")
        print(f"  Slow operation warnings: {len(slow_operations)}")

        if timeout_errors:
            print(f"\n  Sample timeout errors:")
            for error in timeout_errors[:3]:
                print(f"    [{error['timestamp']}] {error['message'][:100]}")

        if rate_limit_errors:
            print(f"\n  ⚠️  WARNING: Rate limiting detected!")

    def analyze_exchange_distribution(self):
        """Analyze operations by exchange"""

        binance_mentions = [e for e in self.entries if 'binance' in e['message'].lower()]
        bybit_mentions = [e for e in self.entries if 'bybit' in e['message'].lower()]

        print(f"\n🏦 EXCHANGE DISTRIBUTION")
        print(f"  Binance operations: {len(binance_mentions)}")
        print(f"  Bybit operations: {len(bybit_mentions)}")

        # Exchange-specific errors
        binance_errors = [e for e in self.errors if 'binance' in e['message'].lower()]
        bybit_errors = [e for e in self.errors if 'bybit' in e['message'].lower()]

        print(f"\n  Exchange errors:")
        print(f"    Binance: {len(binance_errors)}")
        print(f"    Bybit: {len(bybit_errors)}")

    def generate_report(self):
        """Generate comprehensive analysis report"""

        print("\n" + "="*80)
        print("📋 LOG ANALYSIS REPORT")
        print("="*80)

        print(f"\n📊 OVERVIEW")
        print(f"  Log file: {self.log_file}")
        print(f"  Total entries: {len(self.entries)}")
        print(f"  Errors: {len(self.errors)}")
        print(f"  Warnings: {len(self.warnings)}")
        print(f"  Critical: {len(self.critical_events)}")

        if self.entries:
            time_span = self.entries[-1]['timestamp'] - self.entries[0]['timestamp']
            hours = time_span.total_seconds() / 3600
            print(f"  Time range: {self.entries[0]['timestamp']} - {self.entries[-1]['timestamp']}")
            print(f"  Duration: {hours:.2f} hours")

        self.analyze_position_lifecycle()
        self.analyze_stop_loss_operations()
        self.analyze_trailing_stop()
        self.analyze_websocket_health()
        self.analyze_exchange_distribution()
        self.analyze_errors()
        self.analyze_timing_issues()

        print("\n" + "="*80)
        print("✅ ANALYSIS COMPLETE")
        print("="*80)

    def save_json_report(self, output_file: Optional[str] = None):
        """Save analysis results as JSON"""

        if not output_file:
            output_file = f'log_analysis_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'

        report = {
            'log_file': self.log_file,
            'analysis_timestamp': datetime.now().isoformat(),
            'summary': {
                'total_entries': len(self.entries),
                'errors': len(self.errors),
                'warnings': len(self.warnings),
                'critical': len(self.critical_events)
            },
            'time_range': {
                'start': self.entries[0]['timestamp'].isoformat() if self.entries else None,
                'end': self.entries[-1]['timestamp'].isoformat() if self.entries else None
            },
            'error_samples': [
                {
                    'timestamp': e['timestamp'].isoformat(),
                    'module': e['module'],
                    'message': e['message']
                }
                for e in self.errors[:10]
            ]
        }

        try:
            with open(output_file, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            print(f"\n📄 JSON report saved: {output_file}")
        except Exception as e:
            print(f"❌ Failed to save JSON report: {e}")


def main():
    """Entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Bot Log Analyzer')
    parser.add_argument(
        'log_file',
        help='Path to log file to analyze'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Also save analysis as JSON'
    )
    parser.add_argument(
        '--output',
        help='JSON output file path'
    )

    args = parser.parse_args()

    # Check if file exists
    if not Path(args.log_file).exists():
        print(f"❌ Log file not found: {args.log_file}")
        sys.exit(1)

    analyzer = LogAnalyzer(args.log_file)
    analyzer.parse_logs()
    analyzer.generate_report()

    if args.json:
        analyzer.save_json_report(args.output)


if __name__ == "__main__":
    main()
