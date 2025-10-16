#!/usr/bin/env python3
"""
Age Detector Module Live Diagnostic Script
Monitors Age Detector operation for 15 minutes and detects order proliferation
"""

import subprocess
import time
import re
import json
from datetime import datetime
from collections import defaultdict
import sys
import signal
import os

class AgeDetectorMonitor:
    def __init__(self, log_file):
        self.log_file = log_file
        self.start_time = None
        self.end_time = None
        self.duration = 15 * 60  # 15 minutes
        self.bot_process = None
        self.tail_process = None

        # Metrics for tracking
        self.metrics = {
            'positions_identified': 0,      # Positions identified as aged
            'initial_orders_created': 0,    # "Creating initial exit order"
            'orders_updated': 0,            # "Updating exit order"
            'orders_created_total': 0,      # Total "Exit order created"
            'duplicates_prevented': 0,      # "Exit order already exists"
            'errors': [],
            'warnings': [],

            # CRITICAL: per-symbol order tracking
            'orders_per_symbol': defaultdict(list),  # symbol -> [{order_id, price, timestamp, type}]
            'symbols_with_proliferation': [],

            # Timeline events
            'events': []
        }

        # Track actively managed symbols
        self.active_symbols = set()

    def parse_log_line(self, line):
        """Parse log line and update metrics"""
        timestamp = datetime.now()

        # Pattern: Position identified as aged
        match = re.search(r'📈 Processing aged position (.+?):', line)
        if match:
            symbol = match.group(1)
            self.active_symbols.add(symbol)
            self.metrics['positions_identified'] += 1
            self.record_event('position_identified', symbol, line, timestamp)

        # Pattern: Creating initial exit order
        match = re.search(r'📝 Creating initial exit order for (.+?):', line)
        if match:
            symbol = match.group(1)
            self.metrics['initial_orders_created'] += 1
            self.record_event('initial_order_created', symbol, line, timestamp)

        # Pattern: Updating exit order
        match = re.search(r'📊 Updating exit order for (.+?):', line)
        if match:
            symbol = match.group(1)
            self.metrics['orders_updated'] += 1
            self.record_event('order_updated', symbol, line, timestamp)

        # Pattern: Exit order created (SUCCESS)
        match = re.search(r'✅ Exit order created: ([\w\-]+) \((\w+) ([\d.]+) (.+?) @ ([\d.]+)\)', line)
        if match:
            order_id = match.group(1)
            side = match.group(2)
            amount = match.group(3)
            symbol = match.group(4)
            price = match.group(5)

            self.metrics['orders_created_total'] += 1
            self.metrics['orders_per_symbol'][symbol].append({
                'order_id': order_id,
                'price': float(price),
                'timestamp': timestamp,
                'type': 'created'
            })
            self.record_event('order_created', symbol, line, timestamp,
                            {'order_id': order_id, 'price': price})

        # Pattern: Exit order already exists (duplicate prevention)
        match = re.search(r'✅ Exit order already exists: ([\w\-]+) at ([\d.]+)', line)
        if match:
            order_id = match.group(1)
            price = match.group(2)
            self.metrics['duplicates_prevented'] += 1
            self.record_event('duplicate_prevented', 'unknown', line, timestamp,
                            {'order_id': order_id, 'price': price})

        # Pattern: Errors
        if 'ERROR' in line and 'aged_position_manager' in line:
            self.metrics['errors'].append({
                'timestamp': timestamp.isoformat(),
                'message': line.strip()
            })
            self.record_event('error', 'unknown', line, timestamp)

        # Pattern: Warnings
        if 'WARNING' in line or 'Could not cancel' in line:
            self.metrics['warnings'].append({
                'timestamp': timestamp.isoformat(),
                'message': line.strip()
            })

    def record_event(self, event_type, symbol, raw_line, timestamp, extra_data=None):
        """Record an event to timeline"""
        event = {
            'timestamp': timestamp.isoformat(),
            'type': event_type,
            'symbol': symbol,
            'raw': raw_line.strip()
        }
        if extra_data:
            event['data'] = extra_data

        self.metrics['events'].append(event)

    def analyze_order_proliferation(self):
        """
        CRITICAL: Detect order proliferation per symbol
        """
        issues = []

        for symbol, orders in self.metrics['orders_per_symbol'].items():
            if len(orders) > 1:
                # Multiple orders created for same symbol
                issues.append({
                    'symbol': symbol,
                    'total_orders_created': len(orders),
                    'order_ids': [o['order_id'] for o in orders],
                    'prices': [o['price'] for o in orders],
                    'timestamps': [o['timestamp'].isoformat() for o in orders],
                    'severity': 'CRITICAL' if len(orders) > 5 else 'HIGH'
                })

        return issues

    def tail_log_file(self):
        """Tail the log file and parse lines"""
        try:
            # Start tailing from current position
            with open(self.log_file, 'r') as f:
                # Seek to end
                f.seek(0, 2)

                while time.time() - self.start_time < self.duration:
                    line = f.readline()
                    if line:
                        self.parse_log_line(line)
                    else:
                        time.sleep(0.1)

                    # Progress indicator every 60 seconds
                    elapsed = time.time() - self.start_time
                    if int(elapsed) % 60 == 0 and elapsed > 0:
                        mins_remaining = (self.duration - elapsed) / 60
                        print(f"[{int(elapsed/60)}m] Events: {len(self.metrics['events'])}, "
                              f"Symbols tracked: {len(self.active_symbols)}, "
                              f"Remaining: {mins_remaining:.1f}m")

        except KeyboardInterrupt:
            print("\n[INTERRUPTED] Monitoring stopped by user")
        except Exception as e:
            print(f"Error tailing log: {e}")
            import traceback
            traceback.print_exc()

    def run(self):
        """Main monitoring loop"""
        print("=" * 80)
        print("AGE DETECTOR MODULE - LIVE DIAGNOSTIC")
        print("=" * 80)
        print(f"\nMonitoring log file: {self.log_file}")
        print(f"Duration: {self.duration/60} minutes")
        print(f"Start time: {datetime.now()}")
        print("\nBot should already be running in separate terminal!")
        print("Press Ctrl+C to stop early")
        print("-" * 80)

        self.start_time = time.time()

        # Monitor the log file
        self.tail_log_file()

        self.end_time = time.time()
        self.generate_report()

    def generate_report(self):
        """Generate comprehensive diagnostic report"""
        print("\n" + "=" * 80)
        print("AGE DETECTOR MODULE - DIAGNOSTIC REPORT")
        print("=" * 80)

        duration = self.end_time - self.start_time
        print(f"\nMonitoring Duration: {duration/60:.1f} minutes")
        print(f"Start: {datetime.fromtimestamp(self.start_time)}")
        print(f"End: {datetime.fromtimestamp(self.end_time)}")

        print("\n" + "-" * 80)
        print("SUMMARY METRICS")
        print("-" * 80)
        print(f"Aged positions identified: {self.metrics['positions_identified']}")
        print(f"Unique symbols tracked: {len(self.active_symbols)}")
        print(f"'Creating initial exit order' logs: {self.metrics['initial_orders_created']}")
        print(f"'Updating exit order' logs: {self.metrics['orders_updated']}")
        print(f"Total 'Exit order created' events: {self.metrics['orders_created_total']}")
        print(f"Duplicates prevented: {self.metrics['duplicates_prevented']}")

        print("\n" + "-" * 80)
        print("ORDER PROLIFERATION ANALYSIS")
        print("-" * 80)

        # CRITICAL SECTION
        proliferation_issues = self.analyze_order_proliferation()

        if proliferation_issues:
            print(f"\n⚠️  ORDER PROLIFERATION DETECTED IN {len(proliferation_issues)} SYMBOLS!")
            print("\nAffected Symbols:")

            for issue in sorted(proliferation_issues, key=lambda x: x['total_orders_created'], reverse=True):
                print(f"\n  Symbol: {issue['symbol']}")
                print(f"  Severity: {issue['severity']}")
                print(f"  Total orders created: {issue['total_orders_created']}")
                print(f"  Order IDs: {', '.join(issue['order_ids'][:5])}{'...' if len(issue['order_ids']) > 5 else ''}")
                print(f"  Price range: {min(issue['prices']):.6f} - {max(issue['prices']):.6f}")

                if issue['total_orders_created'] > 1:
                    print(f"  ❌ BUG CONFIRMED: Multiple orders created without proper deduplication!")
                    self.metrics['symbols_with_proliferation'].append(issue['symbol'])
        else:
            print("✅ No order proliferation detected")

        # Per-symbol statistics
        print("\n" + "-" * 80)
        print("PER-SYMBOL ORDER STATISTICS")
        print("-" * 80)

        for symbol in sorted(self.active_symbols):
            orders_count = len(self.metrics['orders_per_symbol'].get(symbol, []))
            print(f"  {symbol}: {orders_count} order(s) created")

        # Errors and warnings
        if self.metrics['errors']:
            print("\n" + "-" * 80)
            print(f"ERRORS ({len(self.metrics['errors'])})")
            print("-" * 80)
            for err in self.metrics['errors'][:10]:  # First 10
                print(f"  [{err['timestamp']}]")
                print(f"  {err['message'][:200]}")
                print()

        if self.metrics['warnings']:
            print("\n" + "-" * 80)
            print(f"WARNINGS ({len(self.metrics['warnings'])})")
            print("-" * 80)
            for warn in self.metrics['warnings'][:10]:
                print(f"  [{warn['timestamp']}]")
                print(f"  {warn['message'][:200]}")
                print()

        # Save detailed report to JSON
        report_file = f"age_detector_diagnostic_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump({
                'metadata': {
                    'duration_seconds': duration,
                    'start_time': datetime.fromtimestamp(self.start_time).isoformat(),
                    'end_time': datetime.fromtimestamp(self.end_time).isoformat()
                },
                'summary': {
                    'positions_identified': self.metrics['positions_identified'],
                    'unique_symbols': len(self.active_symbols),
                    'initial_orders_created': self.metrics['initial_orders_created'],
                    'orders_updated': self.metrics['orders_updated'],
                    'orders_created_total': self.metrics['orders_created_total'],
                    'duplicates_prevented': self.metrics['duplicates_prevented'],
                    'errors_count': len(self.metrics['errors']),
                    'warnings_count': len(self.metrics['warnings'])
                },
                'proliferation_issues': proliferation_issues,
                'orders_per_symbol': {k: v for k, v in self.metrics['orders_per_symbol'].items()},
                'events': self.metrics['events'][-1000:]  # Last 1000 events
            }, f, indent=2, default=str)

        print(f"\n✅ Full report saved to: {report_file}")

        # FINAL VERDICT
        print("\n" + "=" * 80)
        print("VERDICT")
        print("=" * 80)

        if proliferation_issues:
            print("❌ CRITICAL BUG CONFIRMED: Order Proliferation Detected!")
            print(f"\n   {len(proliferation_issues)} symbols affected")
            print(f"   {sum(i['total_orders_created'] for i in proliferation_issues)} total orders created")
            print(f"   Expected: 1 order per symbol (updated as needed)")
            print(f"   Actual: Multiple NEW orders created instead of updating existing ones")
            print("\n   ROOT CAUSE:")
            print("   - _check_existing_exit_order() is NOT finding existing orders")
            print("   - OR existing orders are being cancelled but check still fails")
            print("   - This leads to creating NEW orders every check cycle")
            print("\n   IMPACT:")
            print("   - Multiple limit orders on exchange for same position")
            print("   - Risk of multiple fills (closing more than position size)")
            print("   - Potential balance/margin errors")
            print("   - Increased exchange API load")
            print("\n   IMMEDIATE ACTION REQUIRED!")

        elif self.metrics['duplicates_prevented'] > 0:
            print("✅ PARTIAL SUCCESS: Duplicate prevention working")
            print(f"   {self.metrics['duplicates_prevented']} duplicates prevented")
            print("   However, verify this is consistent across all aged positions")

        elif self.metrics['positions_identified'] == 0:
            print("ℹ️  NO DATA: No aged positions detected during monitoring")
            print("   Consider:")
            print("   - Running longer (current limit: 15 minutes)")
            print("   - Lowering MAX_POSITION_AGE_HOURS in .env for testing")
            print("   - Opening test positions and waiting for them to age")

        else:
            print("✅ PRELIMINARY PASS: No obvious issues detected")
            print("   However, sample size may be small")
            print("   Recommend extended monitoring in production")


def main():
    # Configuration
    LOG_FILE = "logs/trading_bot.log"  # Default log file

    # Check if custom log file provided
    if len(sys.argv) > 1:
        LOG_FILE = sys.argv[1]

    # Verify log file exists
    if not os.path.exists(LOG_FILE):
        print(f"ERROR: Log file not found: {LOG_FILE}")
        print("\nUsage:")
        print(f"  python {sys.argv[0]} [log_file_path]")
        print(f"\nDefault: {LOG_FILE}")
        print("\nMake sure the trading bot is already running!")
        sys.exit(1)

    print(f"Using log file: {LOG_FILE}")
    print("\n⚠️  IMPORTANT: Make sure trading bot is already running!")
    input("Press Enter to start monitoring...")

    monitor = AgeDetectorMonitor(LOG_FILE)
    monitor.run()


if __name__ == "__main__":
    main()
