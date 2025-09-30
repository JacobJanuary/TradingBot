#!/usr/bin/env python3
"""
Log maintenance script - Run this as a cron job daily
Example crontab entry:
0 3 * * * /usr/bin/python3 /path/to/log_maintenance.py
"""

import sys
from pathlib import Path
import logging

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.log_rotation import perform_maintenance
from datetime import datetime


def main():
    """Run log maintenance tasks"""
    print(f"\n{'='*60}")
    print(f"Log Maintenance - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    try:
        # Perform maintenance
        stats = perform_maintenance()

        # Log results
        with open('logs/maintenance.log', 'a') as f:
            f.write(f"\n{datetime.now().isoformat()} - Maintenance completed")
            f.write(f"\n  Files: {stats['file_count']}")
            f.write(f"\n  Total size: {stats['total_size_mb']} MB")
            f.write(f"\n  Largest: {stats['largest_file']} ({round(stats['largest_size'] / 1024 / 1024, 2)} MB)\n")

        print("\n✅ Maintenance completed successfully")
        return 0

    except Exception as e:
        print(f"\n❌ Maintenance failed: {e}")
        with open('logs/maintenance.log', 'a') as f:
            f.write(f"\n{datetime.now().isoformat()} - ERROR: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())