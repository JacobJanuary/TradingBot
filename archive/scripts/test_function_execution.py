#!/usr/bin/env python3
"""Test if function execution continues after EXEC_CHECK"""

import logging
import sys

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

async def test_function():
    """Simulate _on_position_update logic"""
    symbol = "TEST"

    # Simulate EXEC_CHECK
    logger.info(f"[EXEC_CHECK] {symbol}: After price update, continuing...")

    # Simulate code between EXEC_CHECK and TS_CHECK
    # (lines 1538-1560 in position_manager.py)
    position_unrealized_pnl = 0

    # Calculate PnL percent
    position_entry_price = 100
    if position_entry_price > 0:
        logger.info(f"[DEBUG] Calculating PnL...")

    # Update trailing stop
    logger.info(f"[LOCK_CHECK] {symbol}: Before acquiring lock...")

    # Simulate lock
    trailing_lock_key = f"trailing_stop_{symbol}"
    logger.info(f"[LOCK_CHECK] {symbol}: Lock created, entering async with...")

    # Inside async with block
    logger.info(f"[LOCK_CHECK] {symbol}: Inside async with block")

    # TS_CHECK
    logger.info(f"[TS_CHECK] {symbol}: Checking conditions...")

if __name__ == "__main__":
    import asyncio
    print("Running test function...")
    asyncio.run(test_function())
    print("Test completed.")
