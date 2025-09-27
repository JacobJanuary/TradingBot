#!/usr/bin/env python3
"""Stability test - run bot for extended period and monitor for issues"""

import asyncio
import signal
import sys
import time
from datetime import datetime, timedelta
import psutil
import os
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import TradingBot
import argparse

class StabilityMonitor:
    def __init__(self):
        self.start_time = time.time()
        self.errors = []
        self.warnings = []
        self.metrics = []
        self.running = True
        
    def record_metric(self):
        """Record system metrics"""
        process = psutil.Process()
        
        metric = {
            'timestamp': datetime.now(),
            'memory_mb': process.memory_info().rss / 1024 / 1024,
            'cpu_percent': process.cpu_percent(),
            'num_threads': process.num_threads(),
            'num_fds': process.num_fds() if hasattr(process, 'num_fds') else 0,
        }
        
        self.metrics.append(metric)
        return metric
        
    def record_error(self, error):
        """Record error"""
        self.errors.append({
            'timestamp': datetime.now(),
            'error': str(error)
        })
        
    def record_warning(self, warning):
        """Record warning"""
        self.warnings.append({
            'timestamp': datetime.now(),
            'warning': str(warning)
        })
        
    def get_report(self):
        """Generate stability report"""
        runtime = time.time() - self.start_time
        
        if self.metrics:
            avg_memory = sum(m['memory_mb'] for m in self.metrics) / len(self.metrics)
            max_memory = max(m['memory_mb'] for m in self.metrics)
            avg_cpu = sum(m['cpu_percent'] for m in self.metrics) / len(self.metrics)
        else:
            avg_memory = max_memory = avg_cpu = 0
            
        return {
            'runtime_seconds': runtime,
            'runtime_hours': runtime / 3600,
            'errors_count': len(self.errors),
            'warnings_count': len(self.warnings),
            'metrics_collected': len(self.metrics),
            'avg_memory_mb': avg_memory,
            'max_memory_mb': max_memory,
            'avg_cpu_percent': avg_cpu,
            'memory_leak': max_memory > avg_memory * 1.5,  # 50% increase indicates leak
            'stable': len(self.errors) == 0
        }

async def monitor_bot(bot, monitor, duration_minutes=5):
    """Monitor bot for specified duration"""
    
    end_time = time.time() + (duration_minutes * 60)
    check_interval = 10  # seconds
    
    print(f"\n⏱️  Running stability test for {duration_minutes} minutes...")
    print("=" * 60)
    
    metric_count = 0
    
    while time.time() < end_time and monitor.running:
        # Record metrics
        metric = monitor.record_metric()
        metric_count += 1
        
        # Print status every minute
        if metric_count % 6 == 0:  # Every 60 seconds
            runtime = (time.time() - monitor.start_time) / 60
            print(f"[{runtime:.1f}m] Memory: {metric['memory_mb']:.1f}MB | "
                  f"CPU: {metric['cpu_percent']:.1f}% | "
                  f"Threads: {metric['num_threads']} | "
                  f"Errors: {len(monitor.errors)}")
        
        # Check for issues
        if metric['memory_mb'] > 500:
            monitor.record_warning(f"High memory usage: {metric['memory_mb']:.1f}MB")
        
        if metric['cpu_percent'] > 80:
            monitor.record_warning(f"High CPU usage: {metric['cpu_percent']:.1f}%")
        
        await asyncio.sleep(check_interval)
    
    print("=" * 60)
    print("⏹️  Stability test completed")

async def run_stability_test(duration_minutes=5):
    """Run stability test"""
    
    monitor = StabilityMonitor()
    
    # Create bot instance
    args = argparse.Namespace(mode='shadow', config='config')
    bot = TradingBot(args)
    
    # Setup signal handler
    def signal_handler(signum, frame):
        print("\n⚠️  Interrupted by user")
        monitor.running = False
        bot.running = False
        
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # Initialize bot
        print("🤖 Initializing bot...")
        await bot.initialize()
        print("✅ Bot initialized successfully")
        
        # Start bot in background
        bot_task = asyncio.create_task(bot.start())
        
        # Monitor bot
        await monitor_bot(bot, monitor, duration_minutes)
        
        # Stop bot
        print("\n🛑 Stopping bot...")
        bot.running = False
        await asyncio.wait_for(bot_task, timeout=10)
        
    except asyncio.TimeoutError:
        monitor.record_error("Bot failed to stop within timeout")
        print("⚠️  Bot stop timeout - forcing shutdown")
        
    except Exception as e:
        monitor.record_error(f"Test failed: {e}")
        print(f"❌ Test error: {e}")
        
    finally:
        # Cleanup
        print("🧹 Cleaning up...")
        try:
            await bot.cleanup()
        except:
            pass
    
    return monitor

def print_report(report):
    """Print stability report"""
    
    print("\n" + "=" * 60)
    print("📊 STABILITY TEST REPORT")
    print("=" * 60)
    
    print(f"\n⏱️  Runtime: {report['runtime_hours']:.2f} hours ({report['runtime_seconds']:.0f} seconds)")
    print(f"📈 Metrics collected: {report['metrics_collected']}")
    
    print("\n💾 Memory Usage:")
    print(f"  Average: {report['avg_memory_mb']:.1f} MB")
    print(f"  Maximum: {report['max_memory_mb']:.1f} MB")
    print(f"  Memory leak detected: {'❌ YES' if report['memory_leak'] else '✅ NO'}")
    
    print(f"\n⚡ CPU Usage:")
    print(f"  Average: {report['avg_cpu_percent']:.1f}%")
    
    print(f"\n🚨 Issues:")
    print(f"  Errors: {report['errors_count']}")
    print(f"  Warnings: {report['warnings_count']}")
    
    print("\n📋 Overall Status:")
    if report['stable']:
        print("  ✅ STABLE - No critical errors detected")
        print("  System maintained stability throughout the test")
    else:
        print("  ❌ UNSTABLE - Critical errors occurred")
        print("  Review error logs for details")
    
    print("\n🎯 Performance Grade:")
    
    score = 100
    if report['errors_count'] > 0:
        score -= 30
    if report['warnings_count'] > 5:
        score -= 10
    if report['memory_leak']:
        score -= 20
    if report['avg_cpu_percent'] > 50:
        score -= 10
    
    if score >= 90:
        grade = "A - Excellent"
    elif score >= 80:
        grade = "B - Good"
    elif score >= 70:
        grade = "C - Acceptable"
    elif score >= 60:
        grade = "D - Needs Improvement"
    else:
        grade = "F - Critical Issues"
    
    print(f"  Score: {score}/100")
    print(f"  Grade: {grade}")

async def main():
    print("🔬 TRADING BOT STABILITY TEST")
    print("=" * 60)
    
    # Get test duration from command line or use default
    import sys
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 2  # Default 2 minutes for quick test
    
    print(f"Test duration: {duration} minutes")
    print("Press Ctrl+C to stop early\n")
    
    # Run test
    monitor = await run_stability_test(duration)
    
    # Generate report
    report = monitor.get_report()
    
    # Print report
    print_report(report)
    
    # Print any errors
    if monitor.errors:
        print("\n❌ Errors encountered:")
        for error in monitor.errors[:5]:  # Show first 5 errors
            print(f"  [{error['timestamp'].strftime('%H:%M:%S')}] {error['error']}")
        if len(monitor.errors) > 5:
            print(f"  ... and {len(monitor.errors) - 5} more errors")
    
    # Print any warnings
    if monitor.warnings:
        print("\n⚠️  Warnings:")
        for warning in monitor.warnings[:5]:  # Show first 5 warnings
            print(f"  [{warning['timestamp'].strftime('%H:%M:%S')}] {warning['warning']}")
        if len(monitor.warnings) > 5:
            print(f"  ... and {len(monitor.warnings) - 5} more warnings")
    
    # Save detailed report
    import json
    with open('stability_report.json', 'w') as f:
        json.dump({
            'summary': report,
            'errors': [{'timestamp': e['timestamp'].isoformat(), 'error': e['error']} for e in monitor.errors],
            'warnings': [{'timestamp': w['timestamp'].isoformat(), 'warning': w['warning']} for w in monitor.warnings],
            'metrics': [{'timestamp': m['timestamp'].isoformat(), **{k: v for k, v in m.items() if k != 'timestamp'}} for m in monitor.metrics]
        }, f, indent=2)
    
    print("\n📄 Detailed report saved to stability_report.json")
    
    return 0 if report['stable'] else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)