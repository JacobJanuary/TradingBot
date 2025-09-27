#!/usr/bin/env python3
"""
Test Graceful Shutdown with Timeout
"""
import asyncio
import signal
import logging
import time
from datetime import datetime
from core.shutdown_manager import ShutdownManager, ShutdownPriority

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ShutdownTest:
    """Test shutdown scenarios"""
    
    def __init__(self):
        self.shutdown_manager = ShutdownManager(timeout=10)
        self.running_tasks = []
    
    async def slow_critical_task(self):
        """Simulates a critical task that takes 3 seconds"""
        logger.info("Starting critical task (3s)...")
        await asyncio.sleep(3)
        logger.info("Critical task completed")
    
    async def fast_critical_task(self):
        """Simulates a critical task that takes 1 second"""
        logger.info("Starting fast critical task (1s)...")
        await asyncio.sleep(1)
        logger.info("Fast critical task completed")
    
    async def medium_task(self):
        """Simulates a medium priority task"""
        logger.info("Starting medium task (2s)...")
        await asyncio.sleep(2)
        logger.info("Medium task completed")
    
    async def slow_low_task(self):
        """Simulates a low priority task that would timeout"""
        logger.info("Starting low priority task (5s)...")
        await asyncio.sleep(5)
        logger.info("Low priority task completed")
    
    async def failing_task(self):
        """Simulates a task that fails"""
        logger.info("Starting failing task...")
        await asyncio.sleep(0.5)
        raise Exception("Task failed!")
    
    async def background_work(self):
        """Simulates background work that should be cancelled"""
        try:
            while True:
                logger.debug("Background work running...")
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("Background work cancelled")
            raise

    async def test_normal_shutdown(self):
        """Test normal shutdown within timeout"""
        logger.info("\n" + "="*60)
        logger.info("TEST 1: Normal Shutdown (Should complete in ~6 seconds)")
        logger.info("="*60)
        
        # Register shutdown tasks
        self.shutdown_manager.register_shutdown_task(
            self.fast_critical_task,
            ShutdownPriority.CRITICAL
        )
        self.shutdown_manager.register_shutdown_task(
            self.slow_critical_task,
            ShutdownPriority.CRITICAL
        )
        self.shutdown_manager.register_shutdown_task(
            self.medium_task,
            ShutdownPriority.MEDIUM
        )
        
        # Start background task
        bg_task = asyncio.create_task(self.background_work())
        self.shutdown_manager.register_running_task(bg_task)
        
        # Wait a bit then trigger shutdown
        await asyncio.sleep(2)
        
        start_time = time.time()
        await self.shutdown_manager.shutdown("Test normal shutdown")
        duration = time.time() - start_time
        
        logger.info(f"\n✅ Normal shutdown completed in {duration:.2f} seconds")
        assert duration < 10, f"Shutdown took too long: {duration:.2f}s"
        
        return duration

    async def test_timeout_scenario(self):
        """Test shutdown that exceeds timeout"""
        logger.info("\n" + "="*60)
        logger.info("TEST 2: Timeout Scenario (Should timeout at 10 seconds)")
        logger.info("="*60)
        
        # Create new shutdown manager for this test
        manager = ShutdownManager(timeout=5)  # 5 second timeout for faster test
        
        # Register tasks that would take too long
        async def very_slow_task():
            logger.info("Starting very slow task (8s)...")
            await asyncio.sleep(8)
            logger.info("Very slow task completed")
        
        manager.register_shutdown_task(very_slow_task, ShutdownPriority.CRITICAL)
        manager.register_shutdown_task(self.slow_low_task, ShutdownPriority.LOW)
        
        start_time = time.time()
        await manager.shutdown("Test timeout scenario")
        duration = time.time() - start_time
        
        logger.info(f"\n⚠️ Shutdown timed out after {duration:.2f} seconds")
        assert duration < 6, f"Shutdown didn't timeout properly: {duration:.2f}s"
        
        return duration

    async def test_failing_tasks(self):
        """Test shutdown with failing tasks"""
        logger.info("\n" + "="*60)
        logger.info("TEST 3: Shutdown with Failing Tasks")
        logger.info("="*60)
        
        # Create new shutdown manager
        manager = ShutdownManager(timeout=10)
        
        # Register mix of good and failing tasks
        manager.register_shutdown_task(self.fast_critical_task, ShutdownPriority.CRITICAL)
        manager.register_shutdown_task(self.failing_task, ShutdownPriority.HIGH)
        manager.register_shutdown_task(self.medium_task, ShutdownPriority.MEDIUM)
        
        start_time = time.time()
        await manager.shutdown("Test with failures")
        duration = time.time() - start_time
        
        logger.info(f"\n✅ Shutdown with failures completed in {duration:.2f} seconds")
        assert duration < 10, f"Shutdown took too long: {duration:.2f}s"
        
        # Check stats
        stats = manager.shutdown_stats
        assert stats['failed_tasks'] == 1, "Should have 1 failed task"
        assert stats['completed_tasks'] == 2, "Should have 2 completed tasks"
        
        return duration

    async def test_parallel_execution(self):
        """Test that tasks execute in parallel within priority groups"""
        logger.info("\n" + "="*60)
        logger.info("TEST 4: Parallel Task Execution")
        logger.info("="*60)
        
        manager = ShutdownManager(timeout=10)
        
        # Register multiple tasks of same priority
        # If they run in parallel, should take ~3s not 9s
        for i in range(3):
            manager.register_shutdown_task(
                self.slow_critical_task,
                ShutdownPriority.CRITICAL
            )
        
        start_time = time.time()
        await manager.shutdown("Test parallel execution")
        duration = time.time() - start_time
        
        logger.info(f"\n✅ Parallel shutdown completed in {duration:.2f} seconds")
        assert duration < 5, f"Tasks didn't run in parallel: {duration:.2f}s"
        
        return duration

    async def test_signal_handling(self):
        """Test signal-based shutdown"""
        logger.info("\n" + "="*60)
        logger.info("TEST 5: Signal-based Shutdown")
        logger.info("="*60)
        
        manager = ShutdownManager(timeout=10)
        manager.setup_signal_handlers()
        
        # Register tasks
        manager.register_shutdown_task(self.fast_critical_task, ShutdownPriority.CRITICAL)
        manager.register_shutdown_task(self.medium_task, ShutdownPriority.MEDIUM)
        
        # Start background task
        bg_task = asyncio.create_task(self.background_work())
        manager.register_running_task(bg_task)
        
        # Send signal after delay
        async def send_signal():
            await asyncio.sleep(2)
            logger.info("Sending SIGINT...")
            signal.raise_signal(signal.SIGINT)
        
        signal_task = asyncio.create_task(send_signal())
        
        start_time = time.time()
        await manager.wait_for_shutdown()
        duration = time.time() - start_time
        
        logger.info(f"\n✅ Signal shutdown completed in {duration:.2f} seconds")
        
        return duration

    async def run_all_tests(self):
        """Run all shutdown tests"""
        logger.info("\n" + "="*60)
        logger.info("🚀 GRACEFUL SHUTDOWN TEST SUITE")
        logger.info("="*60)
        
        results = {}
        
        # Test 1: Normal shutdown
        try:
            duration = await self.test_normal_shutdown()
            results['Normal Shutdown'] = f"PASSED ({duration:.2f}s)"
        except Exception as e:
            logger.error(f"Test failed: {e}")
            results['Normal Shutdown'] = f"FAILED: {e}"
        
        # Test 2: Timeout scenario
        try:
            duration = await self.test_timeout_scenario()
            results['Timeout Scenario'] = f"PASSED ({duration:.2f}s)"
        except Exception as e:
            logger.error(f"Test failed: {e}")
            results['Timeout Scenario'] = f"FAILED: {e}"
        
        # Test 3: Failing tasks
        try:
            duration = await self.test_failing_tasks()
            results['Failing Tasks'] = f"PASSED ({duration:.2f}s)"
        except Exception as e:
            logger.error(f"Test failed: {e}")
            results['Failing Tasks'] = f"FAILED: {e}"
        
        # Test 4: Parallel execution
        try:
            duration = await self.test_parallel_execution()
            results['Parallel Execution'] = f"PASSED ({duration:.2f}s)"
        except Exception as e:
            logger.error(f"Test failed: {e}")
            results['Parallel Execution'] = f"FAILED: {e}"
        
        # Test 5: Signal handling
        try:
            duration = await self.test_signal_handling()
            results['Signal Handling'] = f"PASSED ({duration:.2f}s)"
        except Exception as e:
            logger.error(f"Test failed: {e}")
            results['Signal Handling'] = f"FAILED: {e}"
        
        # Summary
        logger.info("\n" + "="*60)
        logger.info("📊 TEST RESULTS SUMMARY")
        logger.info("="*60)
        
        all_passed = True
        for test_name, result in results.items():
            if "PASSED" in result:
                logger.info(f"✅ {test_name}: {result}")
            else:
                logger.error(f"❌ {test_name}: {result}")
                all_passed = False
        
        if all_passed:
            logger.info("\n🎉 ALL TESTS PASSED!")
            logger.info("The shutdown manager ensures graceful shutdown within 10 seconds")
        else:
            logger.warning("\n⚠️ Some tests failed")
        
        return all_passed


async def main():
    """Main test runner"""
    test = ShutdownTest()
    
    try:
        success = await test.run_all_tests()
        return 0 if success else 1
    except Exception as e:
        logger.error(f"Test suite failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))