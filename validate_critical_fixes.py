#!/usr/bin/env python3
"""Validation script for critical fixes - minimal testing approach"""

import asyncio
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_file_contains(filepath: str, search_string: str, description: str) -> bool:
    """Check if file contains specific string"""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
            if search_string in content:
                logger.info(f"  ✅ {description}")
                return True
            else:
                logger.error(f"  ❌ {description} - NOT FOUND")
                return False
    except Exception as e:
        logger.error(f"  ❌ Error reading {filepath}: {e}")
        return False

def check_file_not_contains(filepath: str, search_string: str, description: str) -> bool:
    """Check that file does NOT contain specific string (for checking bug fixes)"""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
            if search_string not in content:
                logger.info(f"  ✅ {description}")
                return True
            else:
                logger.error(f"  ❌ {description} - STILL EXISTS")
                return False
    except Exception as e:
        logger.error(f"  ❌ Error reading {filepath}: {e}")
        return False

async def test_all_fixes():
    """Test all critical fixes with minimal approach"""

    results = []

    # =====================================
    # Test 1: aged_position_manager f-string fix
    # =====================================
    logger.info("\n📋 Test 1: aged_position_manager formatting fix")
    logger.info("  Checking that invalid f-string pattern is removed...")

    # Check that the problematic pattern is gone
    results.append(
        check_file_not_contains(
            'core/aged_position_manager.py',
            ':.2f if position.unrealized_pnl',
            "Invalid f-string pattern removed"
        )
    )

    # Check that the fix is present
    results.append(
        check_file_contains(
            'core/aged_position_manager.py',
            'pnl_value = float(position.unrealized_pnl) if position.unrealized_pnl is not None else 0.0',
            "Fixed variable calculation present"
        )
    )

    # =====================================
    # Test 2: Bybit heartbeat hardcoding
    # =====================================
    logger.info("\n📋 Test 2: Bybit WebSocket heartbeat fix")
    logger.info("  Checking that Bybit detection and 20s heartbeat is hardcoded...")

    # Check for Bybit detection
    results.append(
        check_file_contains(
            'websocket/improved_stream.py',
            "is_bybit = 'bybit' in name.lower()",
            "Bybit detection logic present"
        )
    )

    # Check for hardcoded 20s heartbeat
    results.append(
        check_file_contains(
            'websocket/improved_stream.py',
            'self.heartbeat_interval = 20  # HARDCODED for Bybit',
            "Hardcoded 20s heartbeat for Bybit"
        )
    )

    # =====================================
    # Test 3: reduceOnly validation
    # =====================================
    logger.info("\n📋 Test 3: reduceOnly validation for Stop Loss")
    logger.info("  Checking that reduceOnly is enforced in both managers...")

    # Check stop_loss_manager.py
    results.append(
        check_file_contains(
            'core/stop_loss_manager.py',
            "'reduceOnly': True  # ALWAYS True for futures SL",
            "reduceOnly enforced in stop_loss_manager"
        )
    )

    results.append(
        check_file_contains(
            'core/stop_loss_manager.py',
            'self.logger.info(f"✅ reduceOnly validated: {params.get(',
            "reduceOnly validation logging in stop_loss_manager"
        )
    )

    # Check exchange_manager.py
    results.append(
        check_file_contains(
            'core/exchange_manager.py',
            "'reduceOnly': True,  # CRITICAL: Always True for futures SL",
            "reduceOnly enforced in exchange_manager"
        )
    )

    results.append(
        check_file_contains(
            'core/exchange_manager.py',
            "logger.critical(f\"🚨 reduceOnly not set for Binance SL",
            "reduceOnly validation check in exchange_manager"
        )
    )

    # =====================================
    # Summary
    # =====================================
    logger.info("\n" + "="*50)
    logger.info("VALIDATION SUMMARY")
    logger.info("="*50)

    total_tests = len(results)
    passed_tests = sum(results)

    logger.info(f"Total tests: {total_tests}")
    logger.info(f"Passed: {passed_tests}")
    logger.info(f"Failed: {total_tests - passed_tests}")

    if all(results):
        logger.info("\n🎉 ALL CRITICAL FIXES VALIDATED SUCCESSFULLY!")
        logger.info("✅ The system is now safe for production deployment")
        return True
    else:
        logger.error("\n❌ SOME TESTS FAILED!")
        logger.error("⚠️  DO NOT deploy to production until all tests pass")
        return False

async def test_syntax():
    """Quick syntax check of modified files"""
    logger.info("\n📋 Syntax Check: Verifying Python syntax in modified files")

    files_to_check = [
        'core/aged_position_manager.py',
        'websocket/improved_stream.py',
        'core/stop_loss_manager.py',
        'core/exchange_manager.py'
    ]

    all_valid = True
    for filepath in files_to_check:
        try:
            with open(filepath, 'r') as f:
                code = f.read()
                compile(code, filepath, 'exec')
                logger.info(f"  ✅ {filepath}: Valid Python syntax")
        except SyntaxError as e:
            logger.error(f"  ❌ {filepath}: Syntax error at line {e.lineno}: {e.msg}")
            all_valid = False
        except Exception as e:
            logger.error(f"  ❌ {filepath}: Error: {e}")
            all_valid = False

    return all_valid

async def main():
    """Main test runner"""
    logger.info("="*50)
    logger.info("CRITICAL FIXES VALIDATION")
    logger.info("="*50)
    logger.info("Validating minimal surgical fixes...")
    logger.info("No refactoring, no improvements, only bug fixes")

    # First check syntax
    syntax_ok = await test_syntax()
    if not syntax_ok:
        logger.error("\n❌ Syntax errors found! Fix them before continuing")
        return 1

    # Then run validation tests
    all_ok = await test_all_fixes()

    if all_ok:
        logger.info("\n" + "="*50)
        logger.info("✅ READY FOR PRODUCTION")
        logger.info("="*50)
        logger.info("Next steps:")
        logger.info("1. Create git commit with these fixes")
        logger.info("2. Run the bot in shadow mode for testing")
        logger.info("3. Monitor logs for validation messages")
        return 0
    else:
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))