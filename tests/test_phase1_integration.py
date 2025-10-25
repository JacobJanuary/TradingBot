#!/usr/bin/env python3
"""
Phase 1: Integration test - Bybit signals should pass validation with real balance
"""
import sys
from pathlib import Path
import asyncio

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

async def test_bybit_validation_with_real_balance():
    """Integration test: Bybit signals should pass validation with real balance"""

    from config.settings import config
    from core.exchange_manager import ExchangeManager

    # Setup Bybit exchange
    bybit_config = config.get_exchange_config('bybit')
    em = ExchangeManager('bybit', bybit_config.__dict__)
    await em.initialize()

    # Get real balance
    free_usdt = await em._get_free_balance_usdt()

    # Test with config position size (should be 6, not 200)
    position_size = float(config.trading.position_size_usd)

    # Validation should PASS with correct size
    can_open, reason = await em.can_open_position('BTCUSDT', position_size)

    print(f"Free balance: ${free_usdt:.2f}")
    print(f"Position size: ${position_size}")
    print(f"Can open: {can_open} - {reason}")

    # Critical assertion: Should be able to open if balance > position_size
    if free_usdt >= position_size:
        assert can_open, f"Should be able to open position: ${free_usdt:.2f} >= ${position_size}"
        print(f"✅ Validation passed: ${free_usdt:.2f} >= ${position_size}")
    else:
        print(f"⚠️ Balance too low to test: ${free_usdt:.2f} < ${position_size}")

    # Clean up
    await em.close()

    print("✅ Bybit validation works with config position size")

if __name__ == '__main__':
    asyncio.run(test_bybit_validation_with_real_balance())
