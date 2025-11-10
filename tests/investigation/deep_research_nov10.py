#!/usr/bin/env python3
"""
DEEP INVESTIGATION: WebSocket Subscriptions & Position Lifecycle
Comprehensive analysis of subscription management, cleanup, and edge cases
"""
import asyncio
import sys
from pathlib import Path

# From tests/investigation/ go up to project root
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SubscriptionInvestigator:
    """Deep investigation into subscription lifecycle"""

    def __init__(self):
        self.findings = []
        self.issues = []
        self.tests_passed = 0
        self.tests_failed = 0

    def record_finding(self, category, description, severity="INFO"):
        self.findings.append({
            'category': category,
            'description': description,
            'severity': severity
        })

    def record_issue(self, description, severity="WARNING"):
        self.issues.append({
            'description': description,
            'severity': severity
        })
        if severity == "CRITICAL":
            self.tests_failed += 1

    async def investigate_current_state(self, position_manager):
        """Phase 1: Analyze current system state"""
        print("\n" + "="*100)
        print("PHASE 1: CURRENT SYSTEM STATE ANALYSIS")
        print("="*100 + "\n")

        # Check active positions
        active_positions = list(position_manager.positions.keys())
        print(f"📊 Active positions in memory: {len(active_positions)}")
        for symbol in sorted(active_positions):
            pos = position_manager.positions[symbol]
            print(f"  • {symbol}: side={pos.side}, opened={pos.opened_at}, "
                  f"price={pos.current_price}, status={pos.status}")

        self.record_finding("System State", f"{len(active_positions)} active positions", "INFO")

        # Check unified protection
        if not position_manager.unified_protection:
            self.record_issue("Unified protection is DISABLED", "CRITICAL")
            return False

        print("\n✅ Unified protection is ENABLED")

        # Check components
        components = {
            'price_monitor': position_manager.unified_protection.get('price_monitor'),
            'aged_monitor': position_manager.unified_protection.get('aged_monitor'),
            'aged_adapter': position_manager.unified_protection.get('aged_adapter'),
            'ts_adapters': position_manager.unified_protection.get('ts_adapters')
        }

        for name, component in components.items():
            if component:
                print(f"  ✅ {name}: present")
            else:
                print(f"  ❌ {name}: MISSING")
                self.record_issue(f"Component {name} is missing", "CRITICAL")

        return True

    async def investigate_aged_positions(self, position_manager):
        """Phase 2: Deep dive into aged position monitoring"""
        print("\n" + "="*100)
        print("PHASE 2: AGED POSITION MONITORING ANALYSIS")
        print("="*100 + "\n")

        aged_monitor = position_manager.unified_protection.get('aged_monitor')
        aged_adapter = position_manager.unified_protection.get('aged_adapter')

        if not aged_monitor or not aged_adapter:
            self.record_issue("Aged monitoring not available", "WARNING")
            return

        # Check aged_targets
        aged_symbols = list(aged_monitor.aged_targets.keys())
        print(f"👴 Aged targets being monitored: {len(aged_symbols)}")
        for symbol in sorted(aged_symbols):
            target = aged_monitor.aged_targets[symbol]
            print(f"  • {symbol}: phase={target.phase}, hours={target.hours_aged:.1f}h, "
                  f"target_price={target.target_price}")

        # Check monitoring_positions
        monitored_symbols = list(aged_adapter.monitoring_positions.keys())
        print(f"\n📡 Positions subscribed for price updates: {len(monitored_symbols)}")
        for symbol in sorted(monitored_symbols):
            print(f"  • {symbol}")

        # CRITICAL CHECK: Find zombie positions
        active_symbols = set(position_manager.positions.keys())
        aged_zombies = set(aged_symbols) - active_symbols
        monitor_zombies = set(monitored_symbols) - active_symbols

        if aged_zombies:
            print(f"\n🚨 ZOMBIE POSITIONS FOUND in aged_targets: {len(aged_zombies)}")
            for symbol in sorted(aged_zombies):
                print(f"  ❌ {symbol} - NOT in active positions but still in aged_targets")
                self.record_issue(f"Zombie position {symbol} in aged_targets", "CRITICAL")
                self.tests_failed += 1
        else:
            print("\n✅ No zombie positions in aged_targets")
            self.tests_passed += 1

        if monitor_zombies:
            print(f"\n🚨 ZOMBIE SUBSCRIPTIONS FOUND: {len(monitor_zombies)}")
            for symbol in sorted(monitor_zombies):
                print(f"  ❌ {symbol} - NOT in active positions but still subscribed")
                self.record_issue(f"Zombie subscription {symbol} in monitoring_positions", "CRITICAL")
                self.tests_failed += 1
        else:
            print("\n✅ No zombie subscriptions")
            self.tests_passed += 1

    async def investigate_trailing_stops(self, position_manager):
        """Phase 3: Analyze trailing stop subscriptions"""
        print("\n" + "="*100)
        print("PHASE 3: TRAILING STOP SUBSCRIPTION ANALYSIS")
        print("="*100 + "\n")

        ts_adapters = position_manager.unified_protection.get('ts_adapters', {})

        for exchange_name, ts_adapter in ts_adapters.items():
            ts_manager = position_manager.trailing_managers.get(exchange_name)
            if not ts_manager:
                continue

            ts_symbols = list(ts_manager.positions.keys())
            subscribed_symbols = list(ts_adapter.subscribed_symbols)

            print(f"📈 Trailing Stop Manager ({exchange_name}):")
            print(f"  • Positions with TS: {len(ts_symbols)}")
            print(f"  • Subscribed symbols: {len(subscribed_symbols)}")

            for symbol in sorted(ts_symbols):
                pos = ts_manager.positions.get(symbol)
                if pos:
                    print(f"    • {symbol}: entry={pos.entry_price}, stop={pos.stop_price}, "
                          f"highest={pos.highest_price if hasattr(pos, 'highest_price') else 'N/A'}")

            # Check for mismatches
            ts_set = set(ts_symbols)
            sub_set = set(subscribed_symbols)

            missing_subs = ts_set - sub_set
            extra_subs = sub_set - ts_set

            if missing_subs:
                print(f"\n  ⚠️ TS positions WITHOUT subscriptions: {missing_subs}")
                self.record_issue(f"TS positions without subscriptions: {missing_subs}", "WARNING")

            if extra_subs:
                print(f"\n  ⚠️ Subscriptions WITHOUT TS positions: {extra_subs}")
                self.record_issue(f"Extra TS subscriptions: {extra_subs}", "WARNING")

        print()

    async def investigate_price_monitor(self, position_manager):
        """Phase 4: Analyze unified price monitor state"""
        print("\n" + "="*100)
        print("PHASE 4: UNIFIED PRICE MONITOR ANALYSIS")
        print("="*100 + "\n")

        price_monitor = position_manager.unified_protection.get('price_monitor')
        if not price_monitor:
            self.record_issue("Price monitor not available", "CRITICAL")
            return

        # Check subscribers
        print("📊 Price Monitor Subscribers:")
        total_subscriptions = 0

        for symbol, callbacks in price_monitor.subscribers.items():
            print(f"  • {symbol}: {len(callbacks)} subscription(s)")
            for module, callback_list in callbacks.items():
                print(f"      - {module}: {len(callback_list)} callback(s)")
                total_subscriptions += len(callback_list)

        print(f"\n  Total subscriptions: {total_subscriptions}")

        # Check last updates
        print(f"\n📡 Last price updates:")
        import time
        current_time = time.time()

        stale_threshold = 120  # 2 minutes
        stale_symbols = []

        for symbol, last_update in sorted(price_monitor.last_update_time.items()):
            age = current_time - last_update
            status = "✅" if age < stale_threshold else "⚠️ STALE"
            print(f"  {status} {symbol}: {age:.1f}s ago")

            if age >= stale_threshold:
                stale_symbols.append(symbol)
                self.record_issue(f"Stale price for {symbol}: {age:.1f}s", "WARNING")

        if stale_symbols:
            print(f"\n⚠️ {len(stale_symbols)} symbols with stale prices (>{stale_threshold}s)")
        else:
            print(f"\n✅ All subscribed symbols receiving fresh updates")
            self.tests_passed += 1

    async def test_position_lifecycle_simulation(self, position_manager):
        """Phase 5: Simulate position lifecycle to find issues"""
        print("\n" + "="*100)
        print("PHASE 5: POSITION LIFECYCLE SIMULATION")
        print("="*100 + "\n")

        print("🧪 This phase would simulate:")
        print("  1. Opening a new position")
        print("  2. Position aging (becoming aged)")
        print("  3. Trailing stop activation")
        print("  4. Position closure")
        print("  5. Cleanup verification")
        print("\n⚠️ Skipping actual simulation (read-only mode)")
        print("   See separate test file for lifecycle tests")

    def generate_report(self):
        """Generate comprehensive investigation report"""
        print("\n" + "="*100)
        print("INVESTIGATION REPORT - SUMMARY")
        print("="*100 + "\n")

        print(f"Tests Passed: {self.tests_passed}")
        print(f"Tests Failed: {self.tests_failed}")
        print(f"Total Findings: {len(self.findings)}")
        print(f"Total Issues: {len(self.issues)}")

        if self.issues:
            print("\n" + "="*50)
            print("CRITICAL ISSUES FOUND")
            print("="*50)

            critical = [i for i in self.issues if i['severity'] == 'CRITICAL']
            warnings = [i for i in self.issues if i['severity'] == 'WARNING']

            if critical:
                print(f"\n🚨 CRITICAL ({len(critical)}):")
                for issue in critical:
                    print(f"  • {issue['description']}")

            if warnings:
                print(f"\n⚠️ WARNINGS ({len(warnings)}):")
                for issue in warnings:
                    print(f"  • {issue['description']}")
        else:
            print("\n✅ NO CRITICAL ISSUES FOUND")

        print("\n" + "="*100)

        return len(self.issues) == 0


async def main():
    print("="*100)
    print("DEEP INVESTIGATION: WebSocket Subscriptions & Position Lifecycle")
    print("="*100)

    from core.position_manager import PositionManager
    from config.settings import Config

    config = Config()
    position_manager = PositionManager(config=config)

    try:
        await position_manager.initialize()

        investigator = SubscriptionInvestigator()

        # Run investigation phases
        if await investigator.investigate_current_state(position_manager):
            await investigator.investigate_aged_positions(position_manager)
            await investigator.investigate_trailing_stops(position_manager)
            await investigator.investigate_price_monitor(position_manager)
            await investigator.test_position_lifecycle_simulation(position_manager)

        # Generate report
        success = investigator.generate_report()

        return 0 if success else 1

    except Exception as e:
        logger.error(f"Investigation failed: {e}", exc_info=True)
        return 1

    finally:
        await position_manager.close()


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
