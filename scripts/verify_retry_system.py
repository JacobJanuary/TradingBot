#!/usr/bin/env python3
"""
Verify that the generic Retry/Resiliency system works.
Tests the @with_retry decorator (or equivalent) used in the bot.
"""
import asyncio
import logging
import sys
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("retry_test")

import os
sys.path.append(os.getcwd())

async def main():
    print("="*60)
    print("TESTING RETRY MECHANISM")
    print("="*60)

    # 1. Locate the retry mechanism
    try:
        from utils.decorators import retry
        print("✅ Found utils.decorators.retry")
        retry_decorator = retry
    except ImportError:
        print("❌ Could not find utils.decorators.retry!")
        return

    # 2. Define a failing function
    call_count = 0
    
    @retry_decorator(retries=3, delay=1.0, backoff=2.0)
    async def failing_operation():
        nonlocal call_count
        call_count += 1
        print(f"   ⚡ Attempt {call_count}...")
        if call_count < 3:
            raise ValueError("Simulated temporary failure")
        print("   ✅ Success on attempt 3!")
        return "SUCCESS"

    # 3. specific test for order execution retry if applicable
    pass

    # 4. Execute
    print("\nRunning operation that fails twice then succeeds...")
    try:
        result = await failing_operation()
        print(f"\nResult: {result}")
    except Exception as e:
        print(f"\n❌ Operation failed deeply: {e}")

    # 5. Check logs logic
    if call_count == 3:
        print("\n✅ RETRY SYSTEM WORKING: Correctly retried 3 times.")
    else:
        print(f"\n❌ RETRY SYSTEM FAILED: Expected 3 calls, got {call_count}")

if __name__ == "__main__":
    asyncio.run(main())
