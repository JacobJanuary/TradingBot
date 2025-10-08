"""
FIXED Process lock using pid file with atomic operations
Based on production-ready patterns from daemon libraries
"""

import os
import sys
import signal
import atexit
from pathlib import Path
from typing import Optional
from utils.logger import logger


class ProcessLock:
    """
    Single-instance lock using PID file with atomic operations.
    More reliable than flock on macOS.
    """

    def __init__(self, lock_file: str = "/tmp/trading_bot.lock"):
        self.lock_file = lock_file
        self.acquired = False
        self.pid = os.getpid()

    def acquire(self) -> bool:
        """
        Acquire lock by creating PID file atomically.
        Returns True if acquired, False if another instance is running.
        """
        try:
            # Check if lock file exists
            if os.path.exists(self.lock_file):
                # Try to read existing PID
                try:
                    with open(self.lock_file, 'r') as f:
                        existing_pid = int(f.read().strip())
                    
                    # Check if process is still running
                    try:
                        os.kill(existing_pid, 0)  # Signal 0 = check if alive
                        logger.error(f"❌ Another instance is running (PID: {existing_pid})")
                        logger.error(f"   Lock file: {self.lock_file}")
                        logger.error(f"   To kill: kill -9 {existing_pid}")
                        return False
                    except (OSError, ProcessLookupError):
                        # Process is dead, remove stale lock
                        logger.warning(f"⚠️ Removing stale lock (dead PID: {existing_pid})")
                        os.remove(self.lock_file)
                except (ValueError, IOError) as e:
                    # Corrupt lock file, remove it
                    logger.warning(f"⚠️ Removing corrupt lock file: {e}")
                    try:
                        os.remove(self.lock_file)
                    except:
                        pass

            # Try to create lock file ATOMICALLY using O_CREAT | O_EXCL
            # This is atomic on all Unix systems (including macOS)
            try:
                fd = os.open(
                    self.lock_file,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o644
                )
            except FileExistsError:
                # Another process created the file between our check and create
                logger.error(f"❌ Race condition: lock file created by another process")
                return False

            # Write our PID
            try:
                os.write(fd, f"{self.pid}\n".encode())
                os.close(fd)
            except Exception as e:
                logger.error(f"❌ Error writing PID to lock file: {e}")
                try:
                    os.close(fd)
                    os.remove(self.lock_file)
                except:
                    pass
                return False

            # Register cleanup
            atexit.register(self.release)
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)

            self.acquired = True
            logger.info(f"✅ Process lock acquired (PID: {self.pid})")
            return True

        except Exception as e:
            logger.error(f"❌ Unexpected error acquiring lock: {e}", exc_info=True)
            return False

    def release(self):
        """Release the lock"""
        if not self.acquired:
            return

        try:
            if os.path.exists(self.lock_file):
                # Verify it's our lock before removing
                try:
                    with open(self.lock_file, 'r') as f:
                        file_pid = int(f.read().strip())
                    
                    if file_pid == self.pid:
                        os.remove(self.lock_file)
                        logger.info("✅ Process lock released")
                    else:
                        logger.warning(f"⚠️ Lock file PID mismatch ({file_pid} != {self.pid})")
                except Exception as e:
                    logger.error(f"Error verifying lock: {e}")
            
            self.acquired = False
        except Exception as e:
            logger.error(f"Error releasing lock: {e}")

    def _signal_handler(self, signum, frame):
        """Handle termination signals"""
        logger.info(f"Received signal {signum}, releasing lock and exiting...")
        self.release()
        sys.exit(0)

    def __enter__(self):
        """Context manager entry"""
        if not self.acquire():
            sys.exit(1)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.release()

