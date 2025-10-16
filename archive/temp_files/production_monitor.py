#!/usr/bin/env python3
"""
🔍 PRODUCTION BOT MONITOR - 8 Hour Audit Test
Real-time monitoring of all trading bot modules
"""

import subprocess
import time
import re
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path
import signal
import sys
import os

class ProductionBotMonitor:
    def __init__(self, log_file_path, test_duration_hours=8):
        self.log_file = log_file_path
        self.test_duration = test_duration_hours * 3600
        self.start_time = None
        self.end_time = None

        # Счетчики событий
        self.stats = {
            'websocket': {
                'signals_received': 0,
                'connections': 0,
                'disconnections': 0,
                'reconnections': 0,
                'price_updates': 0,
                'last_price_update': None,
                'last_signal': None,
            },
            'positions': {
                'created': 0,
                'entry_filled': 0,
                'sl_placed': 0,
                'errors_entry': 0,
                'errors_sl': 0,
                'opens_attempted': 0,
            },
            'trailing_stop': {
                'checks': 0,
                'activations': 0,
                'sl_moves': 0,
                'errors': 0,
                'positions_with_ts': set(),
                'last_activation': None,
            },
            'protection': {
                'checks': 0,
                'unprotected_found': 0,
                'sl_added': 0,
                'last_check': None,
            },
            'zombie': {
                'checks': 0,
                'detected': 0,
                'killed': 0,
                'last_check': None,
            },
            'aged_positions': {
                'checks': 0,
                'aged_found': 0,
                'repositioned': 0,
                'last_check': None,
            },
            'errors': defaultdict(list),
        }

        # Флаги активности
        self.health_flags = {
            'websocket_alive': False,
            'signals_flowing': False,
            'positions_creating': False,
            'ts_working': False,
            'protection_running': False,
            'zombie_running': False,
            'aged_running': False,
            'price_updates_fresh': False,
        }

        self.bot_process = None
        self.last_log_position = 0

    def parse_log_line(self, line):
        """Parse log line and update statistics"""
        timestamp = datetime.now()
        line_lower = line.lower()

        # ===== WEBSOCKET =====
        if "websocket connected" in line_lower or "ws connected" in line_lower:
            self.stats['websocket']['connections'] += 1
            self.health_flags['websocket_alive'] = True

        elif "signal received" in line_lower or "received" in line_lower and "signals" in line_lower:
            # Extract count if present
            match = re.search(r'received\s+(\d+)', line_lower)
            if match:
                count = int(match.group(1))
                self.stats['websocket']['signals_received'] += count
            else:
                self.stats['websocket']['signals_received'] += 1
            self.stats['websocket']['last_signal'] = timestamp
            self.health_flags['signals_flowing'] = True

        elif "websocket disconnected" in line_lower or "ws disconnected" in line_lower:
            self.stats['websocket']['disconnections'] += 1
            self.health_flags['websocket_alive'] = False

        elif "reconnecting" in line_lower and "websocket" in line_lower:
            self.stats['websocket']['reconnections'] += 1

        elif "price update" in line_lower or ("mark price" in line_lower and "position" in line_lower):
            self.stats['websocket']['price_updates'] += 1
            self.stats['websocket']['last_price_update'] = timestamp
            self.health_flags['price_updates_fresh'] = True

        # ===== ПОЗИЦИИ =====
        elif "opening position" in line_lower or "executing signal" in line_lower:
            self.stats['positions']['opens_attempted'] += 1

        elif "position created" in line_lower or "position opened" in line_lower:
            self.stats['positions']['created'] += 1
            self.health_flags['positions_creating'] = True

        elif "entry order filled" in line_lower or "entry filled" in line_lower:
            self.stats['positions']['entry_filled'] += 1

        elif "sl placed" in line_lower or "stop loss placed" in line_lower:
            self.stats['positions']['sl_placed'] += 1

        elif "error" in line_lower and ("placing entry" in line_lower or "open position" in line_lower):
            self.stats['positions']['errors_entry'] += 1
            self.stats['errors']['position_entry'].append({
                'time': timestamp,
                'message': line[:200]
            })

        elif "error" in line_lower and ("placing sl" in line_lower or "stop loss" in line_lower):
            self.stats['positions']['errors_sl'] += 1
            self.stats['errors']['position_sl'].append({
                'time': timestamp,
                'message': line[:200]
            })

        # ===== TRAILING STOP =====
        elif "checking ts" in line_lower or "trailing stop" in line_lower and "check" in line_lower:
            self.stats['trailing_stop']['checks'] += 1
            self.health_flags['ts_working'] = True

        elif "ts activated" in line_lower or "trailing" in line_lower and "activated" in line_lower:
            self.stats['trailing_stop']['activations'] += 1
            self.stats['trailing_stop']['last_activation'] = timestamp
            # Extract position symbol if possible
            match = re.search(r'([A-Z]{3,10}USDT?)', line)
            if match:
                self.stats['trailing_stop']['positions_with_ts'].add(match.group(1))

        elif "sl moved" in line_lower or ("stop loss" in line_lower and "moved" in line_lower):
            self.stats['trailing_stop']['sl_moves'] += 1

        elif "error" in line_lower and ("updating sl" in line_lower or "trailing" in line_lower):
            self.stats['trailing_stop']['errors'] += 1
            self.stats['errors']['trailing_stop'].append({
                'time': timestamp,
                'message': line[:200]
            })

        # ===== ЗАЩИТА (Protection Guard) =====
        elif "protection check" in line_lower or "checking protection" in line_lower:
            self.stats['protection']['checks'] += 1
            self.stats['protection']['last_check'] = timestamp
            self.health_flags['protection_running'] = True

        elif "unprotected" in line_lower and ("found" in line_lower or "position" in line_lower):
            # Extract count
            match = re.search(r'(\d+)', line)
            if match:
                count = int(match.group(1))
                self.stats['protection']['unprotected_found'] += count

        elif "adding sl for unprotected" in line_lower or ("sl added" in line_lower and "unprotected" in line_lower):
            self.stats['protection']['sl_added'] += 1

        # ===== ZOMBIE DETECTOR =====
        elif "zombie check" in line_lower or "checking zombies" in line_lower or "zombie orders detected" in line_lower:
            self.stats['zombie']['checks'] += 1
            self.stats['zombie']['last_check'] = timestamp
            self.health_flags['zombie_running'] = True

        elif "zombie detected" in line_lower or "zombie orders" in line_lower:
            # Extract count
            match = re.search(r'detected\s+(\d+)', line_lower)
            if match:
                count = int(match.group(1))
                self.stats['zombie']['detected'] += count
            else:
                self.stats['zombie']['detected'] += 1

        elif "cancelled zombie" in line_lower or "zombie killed" in line_lower or "zombie cleanup" in line_lower:
            # Extract cancelled count
            match = re.search(r'cancelled[:\s]+(\d+)', line_lower)
            if match:
                count = int(match.group(1))
                self.stats['zombie']['killed'] += count
            else:
                self.stats['zombie']['killed'] += 1

        # ===== AGE MODULE =====
        elif "aged position" in line_lower or "processing aged" in line_lower:
            self.stats['aged_positions']['checks'] += 1
            self.stats['aged_positions']['last_check'] = timestamp
            self.health_flags['aged_running'] = True

            # Extract count if present
            match = re.search(r'found\s+(\d+)\s+aged', line_lower)
            if match:
                count = int(match.group(1))
                self.stats['aged_positions']['aged_found'] += count
            else:
                self.stats['aged_positions']['aged_found'] += 1

        elif "repositioning" in line_lower or "repositioned" in line_lower:
            self.stats['aged_positions']['repositioned'] += 1

        # ===== КРИТИЧНЫЕ ОШИБКИ =====
        elif "error" in line_lower or "exception" in line_lower or "failed" in line_lower:
            if "error" not in self.stats['errors']:
                self.stats['errors']['general'] = []
            self.stats['errors']['general'].append({
                'time': timestamp,
                'message': line[:200]
            })

    def check_health(self):
        """Check system health based on timeouts"""
        now = datetime.now()
        issues = []

        # Check price updates freshness
        last_price = self.stats['websocket']['last_price_update']
        if last_price:
            elapsed = (now - last_price).total_seconds()
            if elapsed > 120:  # 2 minutes
                self.health_flags['price_updates_fresh'] = False
                issues.append(f"⚠️  Price updates stale ({elapsed:.0f}s ago)")

        # Check signal flow
        last_signal = self.stats['websocket']['last_signal']
        if last_signal:
            elapsed = (now - last_signal).total_seconds()
            if elapsed > 3600:  # 1 hour
                issues.append(f"⚠️  No signals for {elapsed/60:.0f} minutes")

        return issues

    def print_status(self, elapsed):
        """Print current monitoring status"""
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)

        print(f"\n{'='*80}")
        print(f"⏱️  RUNTIME: {hours}h {minutes}m / {self.test_duration // 3600}h")
        print(f"{'='*80}")

        # WebSocket
        ws = self.stats['websocket']
        ws_status = '🟢 ALIVE' if self.health_flags['websocket_alive'] else '🔴 DOWN'
        print(f"\n📡 WEBSOCKET: {ws_status}")
        print(f"  ├─ Signals received: {ws['signals_received']}")
        print(f"  ├─ Price updates: {ws['price_updates']}")
        print(f"  ├─ Connections: {ws['connections']}")
        print(f"  └─ Disconnections: {ws['disconnections']}")

        # Positions
        pos = self.stats['positions']
        sl_coverage = (pos['sl_placed'] / pos['created'] * 100) if pos['created'] > 0 else 0
        print(f"\n📊 POSITIONS:")
        print(f"  ├─ Opens attempted: {pos['opens_attempted']}")
        print(f"  ├─ Created: {pos['created']}")
        print(f"  ├─ SL placed: {pos['sl_placed']} ({sl_coverage:.1f}% coverage)")
        print(f"  ├─ Entry errors: {pos['errors_entry']}")
        print(f"  └─ SL errors: {pos['errors_sl']}")

        # Trailing Stop
        ts = self.stats['trailing_stop']
        ts_status = '🟢 WORKING' if self.health_flags['ts_working'] else '🟡 NO ACTIVITY'
        print(f"\n📈 TRAILING STOP: {ts_status}")
        print(f"  ├─ Checks: {ts['checks']}")
        print(f"  ├─ Activations: {ts['activations']}")
        print(f"  ├─ Positions with TS: {len(ts['positions_with_ts'])}")
        print(f"  ├─ SL moves: {ts['sl_moves']}")
        print(f"  └─ Errors: {ts['errors']}")

        # Protection
        prot = self.stats['protection']
        prot_status = '🟢 RUNNING' if self.health_flags['protection_running'] else '🟡 NO ACTIVITY'
        print(f"\n🛡️  PROTECTION: {prot_status}")
        print(f"  ├─ Checks: {prot['checks']}")
        print(f"  ├─ Unprotected found: {prot['unprotected_found']}")
        print(f"  └─ SL added: {prot['sl_added']}")

        # Zombie
        zomb = self.stats['zombie']
        zomb_status = '🟢 RUNNING' if self.health_flags['zombie_running'] else '🟡 NO ACTIVITY'
        print(f"\n🧟 ZOMBIE DETECTOR: {zomb_status}")
        print(f"  ├─ Checks: {zomb['checks']}")
        print(f"  ├─ Detected: {zomb['detected']}")
        print(f"  └─ Killed: {zomb['killed']}")

        # Age Module
        aged = self.stats['aged_positions']
        aged_status = '🟢 RUNNING' if self.health_flags['aged_running'] else '🟡 NO ACTIVITY'
        print(f"\n⏳ AGE MODULE: {aged_status}")
        print(f"  ├─ Checks: {aged['checks']}")
        print(f"  ├─ Aged found: {aged['aged_found']}")
        print(f"  └─ Repositioned: {aged['repositioned']}")

        # Health issues
        issues = self.check_health()
        if issues:
            print(f"\n⚠️  HEALTH ISSUES:")
            for issue in issues:
                print(f"  └─ {issue}")

        # Errors
        total_errors = sum(len(v) for v in self.stats['errors'].values() if isinstance(v, list))
        if total_errors > 0:
            print(f"\n❌ ERRORS: {total_errors} total")

    def monitor_existing_log(self, status_interval=300):
        """Monitor existing log file (bot already running or will be started manually)"""
        self.start_time = datetime.now()
        self.end_time = self.start_time + timedelta(seconds=self.test_duration)

        print(f"\n{'='*80}")
        print(f"🔍 PRODUCTION MONITORING STARTED")
        print(f"Start: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"End:   {self.end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Duration: {self.test_duration // 3600} hours")
        print(f"Log file: {self.log_file}")
        print(f"{'='*80}\n")

        # Check if log exists
        if not Path(self.log_file).exists():
            print(f"⚠️  Log file not found: {self.log_file}")
            print(f"Waiting for log file to be created...")

        last_status = time.time()

        try:
            while True:
                # Check time limit
                now = datetime.now()
                if now >= self.end_time:
                    print("\n⏰ Test duration completed!")
                    break

                # Try to read log file
                try:
                    with open(self.log_file, 'r') as f:
                        # Seek to last position
                        f.seek(self.last_log_position)

                        # Read new lines
                        new_lines = f.readlines()
                        self.last_log_position = f.tell()

                        # Parse new lines
                        for line in new_lines:
                            line = line.strip()
                            if line:
                                self.parse_log_line(line)

                                # Print important events in real-time
                                line_lower = line.lower()
                                if any(kw in line_lower for kw in [
                                    'signal received', 'ts activated', 'sl moved',
                                    'zombie detected', 'aged position', 'error', 'exception'
                                ]):
                                    # Extract timestamp from log if present
                                    print(f"📝 {line[:150]}")

                except FileNotFoundError:
                    pass  # File not created yet
                except Exception as e:
                    print(f"⚠️  Error reading log: {e}")

                # Periodic status update
                if time.time() - last_status >= status_interval:
                    elapsed = (now - self.start_time).total_seconds()
                    self.print_status(elapsed)
                    last_status = time.time()

                # Sleep before next check
                time.sleep(1)

        except KeyboardInterrupt:
            print("\n\n⚠️  Monitoring interrupted by user")

    def generate_report(self, output_file="PRODUCTION_TEST_REPORT.md"):
        """Generate detailed test report"""
        report = []
        report.append("# 🔍 PRODUCTION TEST REPORT\n\n")
        report.append(f"**Test Period:** {self.start_time.strftime('%Y-%m-%d %H:%M:%S')} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        actual_duration = (datetime.now() - self.start_time).total_seconds()
        report.append(f"**Duration:** {actual_duration / 3600:.2f} hours\n\n")
        report.append("---\n\n")

        # Assessment
        report.append("## 📊 OVERALL ASSESSMENT\n\n")

        critical_issues = []
        warnings = []
        successes = []

        # WebSocket
        if self.stats['websocket']['signals_received'] == 0:
            critical_issues.append("❌ NO SIGNALS RECEIVED - WebSocket not working or no signals sent")
        elif self.stats['websocket']['signals_received'] > 0:
            successes.append(f"✅ WebSocket working - {self.stats['websocket']['signals_received']} signals received")

        if self.stats['websocket']['price_updates'] == 0:
            critical_issues.append("❌ NO PRICE UPDATES - Price monitoring not working")
        else:
            successes.append(f"✅ Price updates working - {self.stats['websocket']['price_updates']} updates")

        # Positions
        if self.stats['positions']['created'] > 0:
            successes.append(f"✅ Position creation working - {self.stats['positions']['created']} positions")

            sl_ratio = self.stats['positions']['sl_placed'] / self.stats['positions']['created']
            if sl_ratio < 0.95:
                critical_issues.append(f"❌ SL PLACEMENT ISSUE - Only {sl_ratio*100:.1f}% positions have SL")
            else:
                successes.append(f"✅ SL placement - {sl_ratio*100:.1f}% coverage")

        # Trailing Stop
        if self.stats['trailing_stop']['checks'] == 0:
            warnings.append("⚠️ Trailing Stop not active - no checks performed")
        else:
            successes.append(f"✅ Trailing Stop active - {self.stats['trailing_stop']['checks']} checks")

            if self.stats['trailing_stop']['activations'] > 0:
                successes.append(f"✅ TS activations - {self.stats['trailing_stop']['activations']} times")

            if self.stats['trailing_stop']['sl_moves'] > 0:
                successes.append(f"✅ SL moves - {self.stats['trailing_stop']['sl_moves']} moves")

        # Protection
        if self.stats['protection']['checks'] == 0:
            warnings.append("⚠️ Protection module not active")
        else:
            successes.append(f"✅ Protection active - {self.stats['protection']['checks']} checks")

            if self.stats['protection']['unprotected_found'] > 0:
                if self.stats['protection']['sl_added'] == self.stats['protection']['unprotected_found']:
                    successes.append(f"✅ Protection recovery - all {self.stats['protection']['unprotected_found']} fixed")
                else:
                    warnings.append(f"⚠️ Protection incomplete - {self.stats['protection']['unprotected_found']} found, {self.stats['protection']['sl_added']} fixed")

        # Zombie
        if self.stats['zombie']['checks'] == 0:
            warnings.append("⚠️ Zombie detector not active")
        else:
            successes.append(f"✅ Zombie detector active - {self.stats['zombie']['checks']} checks")

            if self.stats['zombie']['detected'] > 0:
                if self.stats['zombie']['killed'] == self.stats['zombie']['detected']:
                    successes.append(f"✅ Zombie cleanup - all {self.stats['zombie']['detected']} killed")
                else:
                    warnings.append(f"⚠️ Zombie cleanup incomplete - {self.stats['zombie']['detected']} detected, {self.stats['zombie']['killed']} killed")

        # Age
        if self.stats['aged_positions']['checks'] == 0:
            warnings.append("⚠️ Age module not active")
        else:
            successes.append(f"✅ Age module active - {self.stats['aged_positions']['checks']} checks")

        # Output assessment
        if critical_issues:
            report.append("### 🔴 CRITICAL ISSUES\n\n")
            for issue in critical_issues:
                report.append(f"- {issue}\n")
            report.append("\n")

        if warnings:
            report.append("### 🟡 WARNINGS\n\n")
            for warning in warnings:
                report.append(f"- {warning}\n")
            report.append("\n")

        if successes:
            report.append("### 🟢 SUCCESSES\n\n")
            for success in successes:
                report.append(f"- {success}\n")
            report.append("\n")

        # Detailed stats
        report.append("---\n\n## 📈 DETAILED STATISTICS\n\n")

        for module, stats in self.stats.items():
            if module != 'errors':
                report.append(f"### {module.replace('_', ' ').title()}\n\n")
                if isinstance(stats, dict):
                    for key, value in stats.items():
                        if key != 'positions_with_ts' and not key.startswith('last_'):
                            report.append(f"- **{key}**: {value}\n")
                report.append("\n")

        # Errors
        total_errors = sum(len(v) for v in self.stats['errors'].values() if isinstance(v, list))
        if total_errors > 0:
            report.append(f"### ❌ Errors ({total_errors} total)\n\n")
            for error_type, errors in self.stats['errors'].items():
                if isinstance(errors, list) and errors:
                    report.append(f"#### {error_type} ({len(errors)})\n\n")
                    for error in errors[:10]:
                        report.append(f"- [{error['time'].strftime('%H:%M:%S')}] {error['message']}\n")
                    if len(errors) > 10:
                        report.append(f"- ... and {len(errors) - 10} more\n")
                    report.append("\n")

        # Write report
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(''.join(report))

        print(f"\n📄 Report saved to: {output_file}")
        print("\n" + ''.join(report))


def main():
    # Configuration
    LOG_FILE = "logs/trading_bot.log"
    TEST_DURATION_HOURS = 8
    STATUS_INTERVAL = 300  # 5 minutes

    print("🔍 Production Bot Monitor v1.0")
    print("=" * 80)

    monitor = ProductionBotMonitor(LOG_FILE, TEST_DURATION_HOURS)

    try:
        monitor.monitor_existing_log(STATUS_INTERVAL)
    except KeyboardInterrupt:
        print("\n\n⚠️  Monitoring stopped by user")
    finally:
        # Always generate report
        monitor.generate_report()


if __name__ == "__main__":
    main()
