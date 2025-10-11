#!/usr/bin/env python3
"""
Validation test for Phases 2-3 implementation
Verifies all critical fixes are in place
"""

import logging
import re

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_phase_2_1_verification():
    """Phase 2.1: Verify SL check added after zombie cleanup"""
    logger.info("=" * 60)
    logger.info("TEST: Phase 2.1 - SL check after zombie cleanup")
    logger.info("=" * 60)

    with open('core/position_manager.py', 'r') as f:
        content = f.read()

    # Check for the pattern: cleanup_zombie_orders() followed by check_positions_protection()
    pattern = r'await self\.cleanup_zombie_orders\(\).*?await self\.check_positions_protection\(\)'

    if re.search(pattern, content, re.DOTALL):
        logger.info("  ✅ Found check_positions_protection after cleanup_zombie_orders")
        return True
    else:
        logger.error("  ❌ Missing check_positions_protection after cleanup_zombie_orders")
        return False


def test_phase_2_2_verification():
    """Phase 2.2: Verify sync interval reduced to 120 seconds"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST: Phase 2.2 - Sync interval = 120 seconds")
    logger.info("=" * 60)

    with open('core/position_manager.py', 'r') as f:
        content = f.read()

    # Check for sync_interval = 120
    if 'self.sync_interval = 120' in content:
        logger.info("  ✅ sync_interval set to 120 seconds (2 minutes)")

        # Also check adaptive intervals
        if 'min(60, self.sync_interval)' in content:
            logger.info("  ✅ Emergency interval = 60 seconds")
        if 'self.sync_interval = 90' in content:
            logger.info("  ✅ Moderate interval = 90 seconds")
        if 'min(120, self.sync_interval' in content:
            logger.info("  ✅ Normal interval restored to 120 seconds")

        return True
    else:
        logger.error("  ❌ sync_interval not set to 120")
        return False


def test_phase_2_3_verification():
    """Phase 2.3: Verify alert for SL missing > 30 seconds"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST: Phase 2.3 - Alert for SL missing > 30 seconds")
    logger.info("=" * 60)

    with open('core/position_manager.py', 'r') as f:
        content = f.read()

    checks_passed = []

    # Check for positions_without_sl_time tracking dict
    if 'self.positions_without_sl_time' in content:
        logger.info("  ✅ positions_without_sl_time tracking dict exists")
        checks_passed.append(True)
    else:
        logger.error("  ❌ positions_without_sl_time tracking dict missing")
        checks_passed.append(False)

    # Check for 30 second threshold
    if 'time_without_sl > 30' in content:
        logger.info("  ✅ 30 second threshold check exists")
        checks_passed.append(True)
    else:
        logger.error("  ❌ 30 second threshold check missing")
        checks_passed.append(False)

    # Check for CRITICAL alert
    if 'CRITICAL ALERT: Position' in content and 'WITHOUT STOP LOSS' in content:
        logger.info("  ✅ CRITICAL alert message exists")
        checks_passed.append(True)
    else:
        logger.error("  ❌ CRITICAL alert message missing")
        checks_passed.append(False)

    return all(checks_passed)


def test_phase_3_verification():
    """Phase 3: Verify whitelist implementation"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST: Phase 3 - Protected order IDs whitelist")
    logger.info("=" * 60)

    checks_passed = []

    # Check position_manager.py
    with open('core/position_manager.py', 'r') as f:
        pm_content = f.read()

    # Phase 3.1: Whitelist creation
    if 'self.protected_order_ids = set()' in pm_content:
        logger.info("  ✅ Phase 3.1: protected_order_ids set created")
        checks_passed.append(True)
    else:
        logger.error("  ❌ Phase 3.1: protected_order_ids set missing")
        checks_passed.append(False)

    # Phase 3.2: Adding to whitelist
    if 'self.protected_order_ids.add' in pm_content:
        logger.info("  ✅ Phase 3.2: Order IDs added to whitelist")
        checks_passed.append(True)
    else:
        logger.error("  ❌ Phase 3.2: No code adding to whitelist")
        checks_passed.append(False)

    # Check binance_zombie_manager.py
    with open('core/binance_zombie_manager.py', 'r') as f:
        bzm_content = f.read()

    # Phase 3: Whitelist parameter in __init__
    if 'protected_order_ids=None' in bzm_content:
        logger.info("  ✅ Phase 3: BinanceZombieManager accepts protected_order_ids")
        checks_passed.append(True)
    else:
        logger.error("  ❌ Phase 3: BinanceZombieManager missing protected_order_ids parameter")
        checks_passed.append(False)

    # Phase 3.3: Whitelist check before deletion
    if 'if order_id in self.protected_order_ids' in bzm_content:
        logger.info("  ✅ Phase 3.3: Whitelist checked before deletion")
        checks_passed.append(True)
    else:
        logger.error("  ❌ Phase 3.3: Whitelist not checked before deletion")
        checks_passed.append(False)

    # Check stop_loss_manager.py
    with open('core/stop_loss_manager.py', 'r') as f:
        slm_content = f.read()

    # Phase 3.2: Returns order_id
    if 'return True, order_id' in slm_content:
        logger.info("  ✅ Phase 3.2: verify_and_fix_missing_sl returns order_id")
        checks_passed.append(True)
    else:
        logger.error("  ❌ Phase 3.2: verify_and_fix_missing_sl doesn't return order_id")
        checks_passed.append(False)

    return all(checks_passed)


def main():
    """Run all validation tests"""
    logger.info("🧪 VALIDATING PHASES 2-3 IMPLEMENTATION")
    logger.info("=" * 60)

    results = []

    # Run all tests
    results.append(("Phase 2.1", test_phase_2_1_verification()))
    results.append(("Phase 2.2", test_phase_2_2_verification()))
    results.append(("Phase 2.3", test_phase_2_3_verification()))
    results.append(("Phase 3", test_phase_3_verification()))

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("📊 VALIDATION SUMMARY")
    logger.info("=" * 60)

    passed = 0
    failed = 0

    for test_name, result in results:
        if result:
            logger.info(f"  ✅ {test_name}: PASSED")
            passed += 1
        else:
            logger.error(f"  ❌ {test_name}: FAILED")
            failed += 1

    logger.info(f"\nTotal: {passed} passed, {failed} failed")

    if failed == 0:
        logger.info("\n🎉 ALL VALIDATIONS PASSED!")
        logger.info("\n✅ Phases 2-3 successfully implemented:")
        logger.info("  Phase 2.1: SL check after zombie cleanup")
        logger.info("  Phase 2.2: Reduced sync interval (120s)")
        logger.info("  Phase 2.3: Alert for SL missing > 30s")
        logger.info("  Phase 3.1: Protected order IDs whitelist")
        logger.info("  Phase 3.2: Order IDs added to whitelist")
        logger.info("  Phase 3.3: Whitelist checked before deletion")
        return True
    else:
        logger.error(f"\n⚠️ {failed} VALIDATIONS FAILED - Review implementation!")
        return False


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
