"""
Graceful Shutdown Manager with timeout control
"""
import asyncio
import signal
import logging
from typing import Dict, List, Callable, Optional, Any
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class ShutdownPriority(Enum):
    """Shutdown priority levels"""
    CRITICAL = 1  # Must complete (e.g., close positions)
    HIGH = 2      # Should complete (e.g., save state)
    MEDIUM = 3    # Nice to complete (e.g., cleanup)
    LOW = 4       # Optional (e.g., logging)


class ShutdownManager:
    """
    Manages graceful shutdown with timeout control
    """
    
    def __init__(self, timeout: int = 10):
        """
        Initialize shutdown manager
        
        Args:
            timeout: Maximum time allowed for shutdown (seconds)
        """
        self.timeout = timeout
        self.shutdown_event = asyncio.Event()
        self.is_shutting_down = False
        self.shutdown_start_time = None
        
        # Components to shutdown organized by priority
        self.shutdown_tasks: Dict[ShutdownPriority, List[Callable]] = {
            ShutdownPriority.CRITICAL: [],
            ShutdownPriority.HIGH: [],
            ShutdownPriority.MEDIUM: [],
            ShutdownPriority.LOW: []
        }
        
        # Running tasks to cancel
        self.running_tasks: List[asyncio.Task] = []
        
        # Shutdown statistics
        self.shutdown_stats = {
            'total_tasks': 0,
            'completed_tasks': 0,
            'failed_tasks': 0,
            'cancelled_tasks': 0,
            'duration': 0
        }
        
        logger.info(f"Shutdown manager initialized with {timeout}s timeout")
    
    def register_shutdown_task(self, task: Callable, priority: ShutdownPriority = ShutdownPriority.MEDIUM):
        """
        Register a shutdown task
        
        Args:
            task: Async function to call during shutdown
            priority: Priority level for the task
        """
        self.shutdown_tasks[priority].append(task)
        logger.debug(f"Registered shutdown task: {task.__name__} (priority: {priority.name})")
    
    def register_running_task(self, task: asyncio.Task):
        """Register a running task that should be cancelled on shutdown"""
        self.running_tasks.append(task)
    
    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, self._signal_handler)
        logger.info("Signal handlers registered for SIGTERM and SIGINT")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum} - initiating graceful shutdown")
        asyncio.create_task(self.shutdown())
    
    async def shutdown(self, reason: str = "Signal received"):
        """
        Initiate graceful shutdown
        
        Args:
            reason: Reason for shutdown
        """
        if self.is_shutting_down:
            logger.warning("Shutdown already in progress")
            return
        
        self.is_shutting_down = True
        self.shutdown_start_time = datetime.now()
        self.shutdown_event.set()
        
        logger.info("=" * 60)
        logger.info(f"🛑 INITIATING GRACEFUL SHUTDOWN")
        logger.info(f"Reason: {reason}")
        logger.info(f"Timeout: {self.timeout} seconds")
        logger.info("=" * 60)
        
        try:
            # Execute shutdown with timeout
            await asyncio.wait_for(
                self._execute_shutdown(),
                timeout=self.timeout
            )
            
            logger.info("✅ Graceful shutdown completed successfully")
            
        except asyncio.TimeoutError:
            logger.error(f"⚠️ Shutdown timeout exceeded ({self.timeout}s) - forcing shutdown")
            await self._force_shutdown()
            
        except Exception as e:
            logger.error(f"❌ Error during shutdown: {e}")
            await self._force_shutdown()
        
        finally:
            # Calculate shutdown duration
            self.shutdown_stats['duration'] = (
                datetime.now() - self.shutdown_start_time
            ).total_seconds()
            
            # Log shutdown statistics
            self._log_shutdown_stats()
    
    async def _execute_shutdown(self):
        """Execute shutdown tasks in priority order"""
        total_tasks = sum(len(tasks) for tasks in self.shutdown_tasks.values())
        self.shutdown_stats['total_tasks'] = total_tasks
        
        completed = 0
        
        # Execute tasks by priority
        for priority in ShutdownPriority:
            tasks = self.shutdown_tasks[priority]
            
            if not tasks:
                continue
            
            logger.info(f"\nExecuting {priority.name} priority tasks ({len(tasks)} tasks)")
            
            # Calculate time budget for this priority level
            elapsed = (datetime.now() - self.shutdown_start_time).total_seconds()
            remaining_time = max(self.timeout - elapsed, 1)
            
            # Higher priority tasks get more time
            if priority == ShutdownPriority.CRITICAL:
                task_timeout = remaining_time * 0.6
            elif priority == ShutdownPriority.HIGH:
                task_timeout = remaining_time * 0.3
            else:
                task_timeout = remaining_time * 0.1
            
            # Execute tasks in parallel with timeout
            task_results = await self._execute_parallel_tasks(tasks, task_timeout)
            
            for task_name, success in task_results:
                if success:
                    self.shutdown_stats['completed_tasks'] += 1
                    logger.info(f"  ✅ {task_name}")
                else:
                    self.shutdown_stats['failed_tasks'] += 1
                    logger.error(f"  ❌ {task_name}")
                completed += 1
            
            # Check if we're running out of time
            elapsed = (datetime.now() - self.shutdown_start_time).total_seconds()
            if elapsed > self.timeout * 0.9:
                logger.warning("Running out of time - skipping lower priority tasks")
                break
        
        # Cancel running tasks
        await self._cancel_running_tasks()
    
    async def _execute_parallel_tasks(self, tasks: List[Callable], timeout: float) -> List[tuple]:
        """
        Execute tasks in parallel with timeout
        
        Returns:
            List of (task_name, success) tuples
        """
        results = []
        
        # Create coroutines for all tasks
        coroutines = []
        for task in tasks:
            coroutines.append(self._execute_single_task(task, timeout))
        
        # Execute all tasks in parallel
        if coroutines:
            task_results = await asyncio.gather(*coroutines, return_exceptions=True)
            
            for i, result in enumerate(task_results):
                task_name = tasks[i].__name__
                if isinstance(result, Exception):
                    logger.error(f"Task {task_name} failed: {result}")
                    results.append((task_name, False))
                else:
                    results.append((task_name, True))
        
        return results
    
    async def _execute_single_task(self, task: Callable, timeout: float):
        """Execute a single shutdown task with timeout"""
        try:
            await asyncio.wait_for(task(), timeout=timeout)
        except asyncio.TimeoutError:
            raise Exception(f"Task timed out after {timeout:.1f}s")
        except Exception as e:
            raise Exception(f"Task failed: {e}")
    
    async def _cancel_running_tasks(self):
        """Cancel all running tasks"""
        if not self.running_tasks:
            return
        
        logger.info(f"\nCancelling {len(self.running_tasks)} running tasks...")
        
        # Cancel all tasks
        for task in self.running_tasks:
            if not task.done():
                task.cancel()
                self.shutdown_stats['cancelled_tasks'] += 1
        
        # Wait for tasks to finish cancellation
        await asyncio.gather(*self.running_tasks, return_exceptions=True)
        
        logger.info(f"  ✅ Cancelled {self.shutdown_stats['cancelled_tasks']} tasks")
    
    async def _force_shutdown(self):
        """Force immediate shutdown"""
        logger.warning("⚡ FORCING IMMEDIATE SHUTDOWN")
        
        # Cancel all running tasks immediately
        for task in self.running_tasks:
            if not task.done():
                task.cancel()
        
        # Execute only critical tasks with minimal timeout
        critical_tasks = self.shutdown_tasks[ShutdownPriority.CRITICAL]
        if critical_tasks:
            logger.info("Executing critical tasks only...")
            for task in critical_tasks:
                try:
                    await asyncio.wait_for(task(), timeout=1)
                    logger.info(f"  ✅ {task.__name__}")
                except:
                    logger.error(f"  ❌ {task.__name__} failed")
    
    def _log_shutdown_stats(self):
        """Log shutdown statistics"""
        logger.info("\n" + "=" * 60)
        logger.info("📊 SHUTDOWN STATISTICS")
        logger.info("=" * 60)
        logger.info(f"Total tasks: {self.shutdown_stats['total_tasks']}")
        logger.info(f"Completed: {self.shutdown_stats['completed_tasks']}")
        logger.info(f"Failed: {self.shutdown_stats['failed_tasks']}")
        logger.info(f"Cancelled: {self.shutdown_stats['cancelled_tasks']}")
        logger.info(f"Duration: {self.shutdown_stats['duration']:.2f}s")
        logger.info("=" * 60)
    
    async def wait_for_shutdown(self):
        """Wait for shutdown signal"""
        await self.shutdown_event.wait()
    
    def is_shutdown_requested(self) -> bool:
        """Check if shutdown has been requested"""
        return self.shutdown_event.is_set()


class ComponentShutdown:
    """
    Helper class for component shutdown tasks
    """
    
    @staticmethod
    async def close_positions(position_manager, exchange_manager, timeout: float = 5):
        """Close all open positions"""
        logger.info("Closing all open positions...")
        
        positions = await position_manager.get_open_positions()
        if not positions:
            logger.info("No open positions to close")
            return
        
        # Close positions in parallel
        close_tasks = []
        for position in positions:
            task = exchange_manager.close_position(
                position['symbol'],
                position['exchange']
            )
            close_tasks.append(task)
        
        results = await asyncio.gather(*close_tasks, return_exceptions=True)
        
        success = sum(1 for r in results if not isinstance(r, Exception))
        logger.info(f"Closed {success}/{len(positions)} positions")
    
    @staticmethod
    async def cancel_orders(exchange_manager, timeout: float = 3):
        """Cancel all open orders"""
        logger.info("Cancelling all open orders...")
        
        for exchange_name, exchange in exchange_manager.exchanges.items():
            try:
                cancelled = await asyncio.wait_for(
                    exchange.cancel_all_orders(),
                    timeout=timeout
                )
                logger.info(f"Cancelled {cancelled} orders on {exchange_name}")
            except asyncio.TimeoutError:
                logger.error(f"Timeout cancelling orders on {exchange_name}")
            except Exception as e:
                logger.error(f"Error cancelling orders on {exchange_name}: {e}")
    
    @staticmethod
    async def save_state(repository, state_data: Dict, timeout: float = 2):
        """Save system state to database"""
        logger.info("Saving system state...")
        
        try:
            await asyncio.wait_for(
                repository.save_system_state(state_data),
                timeout=timeout
            )
            logger.info("System state saved")
        except asyncio.TimeoutError:
            logger.error("Timeout saving system state")
        except Exception as e:
            logger.error(f"Error saving state: {e}")
    
    @staticmethod
    async def disconnect_websockets(websockets: Dict, timeout: float = 2):
        """Disconnect all WebSocket connections"""
        logger.info("Disconnecting WebSocket streams...")
        
        disconnect_tasks = []
        for name, ws in websockets.items():
            if hasattr(ws, 'stop'):
                disconnect_tasks.append(ws.stop())
            elif hasattr(ws, 'disconnect'):
                disconnect_tasks.append(ws.disconnect())
        
        if disconnect_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*disconnect_tasks, return_exceptions=True),
                    timeout=timeout
                )
                logger.info(f"Disconnected {len(disconnect_tasks)} WebSocket streams")
            except asyncio.TimeoutError:
                logger.error("Timeout disconnecting WebSocket streams")
    
    @staticmethod
    async def close_database(repository, timeout: float = 1):
        """Close database connections"""
        logger.info("Closing database connections...")
        
        try:
            await asyncio.wait_for(repository.close(), timeout=timeout)
            logger.info("Database connections closed")
        except asyncio.TimeoutError:
            logger.error("Timeout closing database")
        except Exception as e:
            logger.error(f"Error closing database: {e}")