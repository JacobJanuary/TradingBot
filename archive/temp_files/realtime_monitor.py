#!/usr/bin/env python3
"""
Real-time monitoring for Age Detector fix testing
Runs for 10 minutes and collects metrics every minute
"""

import time
import subprocess
from datetime import datetime, timedelta
import json

def count_pattern_in_log(pattern, lines=500):
    """Count occurrences of pattern in last N lines of log"""
    try:
        result = subprocess.run(
            f"tail -n {lines} logs/trading_bot.log | grep -c '{pattern}'",
            shell=True,
            capture_output=True,
            text=True
        )
        return int(result.stdout.strip()) if result.returncode == 0 else 0
    except:
        return 0

def get_recent_logs(pattern, lines=100, tail=10):
    """Get recent log entries matching pattern"""
    try:
        result = subprocess.run(
            f"tail -n {lines} logs/trading_bot.log | grep '{pattern}' | tail -n {tail}",
            shell=True,
            capture_output=True,
            text=True
        )
        return result.stdout.strip()
    except:
        return ""

def check_metrics():
    """Check current metrics"""
    metrics = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'creating_initial': count_pattern_in_log('Creating initial exit order', 1000),
        'order_exists': count_pattern_in_log('Exit order already exists', 1000),
        'updating_order': count_pattern_in_log('Updating exit order', 1000),
        'aged_positions_processed': count_pattern_in_log('Aged positions processed:', 1000),
        'geo_restricted': count_pattern_in_log('not available in this region', 1000),
    }
    return metrics

def main():
    print("=" * 60)
    print("Age Detector Fix - Real-Time Monitor (10 minutes)")
    print("=" * 60)

    start_time = datetime.now()
    end_time = start_time + timedelta(minutes=10)

    print(f"Start: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"End:   {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    all_metrics = []
    check_interval = 60  # Check every minute

    minute = 0
    while datetime.now() < end_time:
        minute += 1

        print(f"\n{'=' * 60}")
        print(f"📊 Minute {minute} - {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'=' * 60}")

        metrics = check_metrics()
        all_metrics.append(metrics)

        print(f"  Creating initial exit order: {metrics['creating_initial']}")
        print(f"  Exit order already exists:   {metrics['order_exists']} {'✅' if metrics['order_exists'] > 0 else '⚠️'}")
        print(f"  Updating exit order:         {metrics['updating_order']}")
        print(f"  Aged positions processed:    {metrics['aged_positions_processed']}")
        print(f"  Geo-restricted (handled):    {metrics['geo_restricted']}")

        # Show recent aged position activity
        recent = get_recent_logs('aged position', 200, 3)
        if recent:
            print(f"\n  Recent activity:")
            for line in recent.split('\n'):
                if line.strip():
                    # Extract just the important part
                    if 'Processing aged position' in line:
                        symbol = line.split('position')[-1].split(':')[0].strip()
                        print(f"    • Processing: {symbol}")

        # Check for order duplication issues
        if minute >= 3:  # After 3 minutes, should see "exists" messages
            if metrics['creating_initial'] > 50:
                print("\n  ⚠️  WARNING: High order creation count - possible proliferation!")
            if metrics['order_exists'] == 0:
                print("\n  ⚠️  WARNING: No 'order exists' messages - duplicate check may not be working")
            else:
                print(f"\n  ✅ GOOD: Duplicate prevention working ({metrics['order_exists']} prevented)")

        # Wait for next check
        if datetime.now() < end_time:
            time.sleep(check_interval)

    # Final report
    print(f"\n\n{'=' * 60}")
    print("📈 FINAL REPORT")
    print(f"{'=' * 60}")

    if all_metrics:
        total_creating = sum(m['creating_initial'] for m in all_metrics)
        total_exists = sum(m['order_exists'] for m in all_metrics)
        total_updating = sum(m['updating_order'] for m in all_metrics)

        print(f"\nTotal over 10 minutes:")
        print(f"  Creating initial: {total_creating}")
        print(f"  Order exists:     {total_exists}")
        print(f"  Updating:         {total_updating}")

        # Verdict
        print(f"\n{'=' * 60}")
        print("🎯 VERDICT:")
        print(f"{'=' * 60}")

        if total_exists > 0:
            print("✅ FIX WORKING: Duplicate prevention is active!")
        else:
            print("❌ ISSUE: No duplicate prevention detected")

        if total_creating < 100:
            print("✅ FIX WORKING: Order creation rate is normal")
        else:
            print("⚠️  WARNING: High order creation rate")

        # Save metrics
        with open('test_metrics_10min.json', 'w') as f:
            json.dump({
                'start_time': start_time.strftime('%Y-%m-%d %H:%M:%S'),
                'end_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'metrics': all_metrics,
                'summary': {
                    'total_creating': total_creating,
                    'total_exists': total_exists,
                    'total_updating': total_updating
                }
            }, f, indent=2)

        print(f"\n📝 Detailed metrics saved to: test_metrics_10min.json")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Monitoring interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
