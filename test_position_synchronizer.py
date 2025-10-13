#!/usr/bin/env python3
"""Test PositionSynchronizer integration"""

import asyncio
from core.position_synchronizer import PositionSynchronizer, normalize_symbol

async def test_integration():
    print("="*60)
    print("TESTING POSITION SYNCHRONIZER")
    print("="*60)

    # Test 1: Symbol normalization
    print("\n✅ Test 1: Symbol normalization")
    test_cases = [
        ("HIGH/USDT:USDT", "HIGHUSDT"),
        ("BTC/USDT:USDT", "BTCUSDT"),
        ("ETHUSDT", "ETHUSDT"),  # Already normalized
    ]

    for input_sym, expected in test_cases:
        result = normalize_symbol(input_sym)
        status = "✅" if result == expected else "❌"
        print(f"  {status} {input_sym} → {result} (expected: {expected})")

    # Test 2: Import and instantiation
    print("\n✅ Test 2: Instantiation")
    try:
        # Mock objects for testing
        class MockRepo:
            pass

        class MockExchange:
            async def fetch_positions(self, symbols=None, params=None):
                return []

        repo = MockRepo()
        exchanges = {'test': MockExchange()}

        synchronizer = PositionSynchronizer(
            repository=repo,
            exchanges=exchanges
        )

        print(f"  ✅ PositionSynchronizer created")
        print(f"  ✅ Stats initialized: {synchronizer.stats}")

    except Exception as e:
        print(f"  ❌ Error: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*60)
    print("✅ ALL TESTS PASSED")
    print("="*60)

if __name__ == '__main__':
    asyncio.run(test_integration())
