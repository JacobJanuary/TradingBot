"""Process lock mechanism to prevent multiple instances of the bot"""

import os
import sys
import fcntl
import signal
import atexit
from pathlib import Path
from typing import Optional
from utils.logger import logger

class ProcessLock:
    """Prevents multiple instances of the trading bot from running"""

    def __init__(self, lock_file: str = "/tmp/trading_bot.lock"):
        self.lock_file = lock_file
        self.lock_fd: Optional[int] = None
        self.acquired = False

    def acquire(self) -> bool:
        """
        Acquire the process lock.
        Returns True if lock acquired, False if another instance is running.
        """
        try:
            # Open or create lock file
            self.lock_fd = os.open(self.lock_file, os.O_CREAT | os.O_WRONLY)

            # Try to acquire exclusive lock (non-blocking)
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

            # Write PID to lock file
            os.write(self.lock_fd, str(os.getpid()).encode())
            os.fsync(self.lock_fd)

            # Register cleanup handlers
            atexit.register(self.release)
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)

            self.acquired = True
            logger.info(f"✅ Process lock acquired (PID: {os.getpid()})")
            return True

        except IOError as e:
            # Lock is held by another process
            if e.errno == 11:  # Resource temporarily unavailable
                try:
                    # Try to read PID from lock file
                    with open(self.lock_file, 'r') as f:
                        pid = f.read().strip()
                    logger.error(f"❌ Another instance is already running (PID: {pid})")
                except:
                    logger.error("❌ Another instance is already running")
            else:
                logger.error(f"❌ Failed to acquire lock: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error acquiring lock: {e}")
            return False

    def release(self):
        """Release the process lock"""
        if not self.acquired:
            return

        try:
            if self.lock_fd is not None:
                # Release the lock
                fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
                os.close(self.lock_fd)

                # Remove lock file
                if os.path.exists(self.lock_file):
                    os.remove(self.lock_file)

                self.acquired = False
                logger.info("✅ Process lock released")
        except Exception as e:
            logger.error(f"Error releasing lock: {e}")

    def _signal_handler(self, signum, frame):
        """Handle termination signals"""
        logger.info(f"Received signal {signum}, releasing lock and exiting...")
        self.release()
        sys.exit(0)

    def check_stale_lock(self) -> bool:
        """
        Check if lock file exists but process is dead (stale lock).
        Returns True if lock is stale and was removed.
        """
        if not os.path.exists(self.lock_file):
            return False

        try:
            with open(self.lock_file, 'r') as f:
                pid = int(f.read().strip())

            # Check if process is still running
            try:
                os.kill(pid, 0)  # Signal 0 just checks if process exists
                return False  # Process is still running
            except OSError:
                # Process is dead, remove stale lock
                logger.warning(f"⚠️ Removing stale lock file (dead PID: {pid})")
                os.remove(self.lock_file)
                return True
        except Exception as e:
            logger.error(f"Error checking stale lock: {e}")
            return False

    def __enter__(self):
        """Context manager entry"""
        if not self.acquire():
            sys.exit(1)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.release()


def ensure_single_instance(lock_file: str = "/tmp/trading_bot.lock") -> ProcessLock:
    """
    Ensure only a single instance of the bot is running.
    Exits the program if another instance is detected.
    """
    lock = ProcessLock(lock_file)

    # Check for stale lock first
    lock.check_stale_lock()

    # Try to acquire lock
    if not lock.acquire():
        logger.error("🛑 Cannot start: Another instance of the trading bot is already running!")
        logger.info("💡 To force start, run: rm /tmp/trading_bot.lock")
        sys.exit(1)

    return lock


def check_running_instances() -> int:
    """Check for running bot instances"""
    import subprocess
    try:
        result = subprocess.run(
            ['pgrep', '-f', 'python.*main.py'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            # Filter out empty strings and current process
            current_pid = str(os.getpid())
            pids = [p for p in pids if p and p != current_pid]
            return len(pids)
        return 0
    except Exception as e:
        logger.error(f"Error checking instances: {e}")
        return 0


def kill_all_instances() -> int:
    """Kill all running bot instances"""
    import subprocess
    try:
        # First get all PIDs
        result = subprocess.run(
            ['pgrep', '-f', 'python.*main.py'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            # Filter out current process
            current_pid = str(os.getpid())
            pids = [p for p in pids if p and p != current_pid]
            
            killed = 0
            for pid in pids:
                try:
                    os.kill(int(pid), signal.SIGTERM)
                    killed += 1
                    logger.info(f"Killed process {pid}")
                except:
                    pass
            
            return killed
        return 0
    except Exception as e:
        logger.error(f"Error killing instances: {e}")
        return 0
