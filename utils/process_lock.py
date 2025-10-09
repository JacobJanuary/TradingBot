"""
Simple and reliable PID-file based process lock
Works on all Unix-like systems including macOS
"""

import os
import sys
import signal
import atexit
import subprocess
from typing import Optional
from utils.logger import logger


class ProcessLock:
    """
    Single-instance lock using PID file.
    
    This is the simplest and most reliable approach:
    1. Write PID to file on start
    2. Check if PID is alive before starting
    3. Remove file on exit
    
    Used by: nginx, postgresql, apache, redis, and countless other daemons
    """

    def __init__(self, pid_file: str = "/tmp/trading_bot.pid"):
        self.pid_file = pid_file
        self.acquired = False

    def _is_process_running(self, pid: int) -> bool:
        """Check if a process with given PID is actually running"""
        try:
            # Send signal 0 to check if process exists (doesn't actually kill)
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def _read_pid_file(self) -> Optional[int]:
        """Read PID from file, return None if file doesn't exist or invalid"""
        try:
            with open(self.pid_file, 'r') as f:
                pid_str = f.read().strip()
                if pid_str and pid_str.isdigit():
                    return int(pid_str)
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.warning(f"Error reading PID file: {e}")
        return None

    def _write_pid_file(self):
        """Write current PID to file"""
        try:
            with open(self.pid_file, 'w') as f:
                f.write(str(os.getpid()))
            logger.info(f"✅ PID file created: {self.pid_file} (PID: {os.getpid()})")
        except Exception as e:
            logger.error(f"Failed to write PID file: {e}")
            raise

    def _remove_pid_file(self):
        """Remove PID file"""
        try:
            if os.path.exists(self.pid_file):
                os.remove(self.pid_file)
                logger.info(f"✅ PID file removed: {self.pid_file}")
        except Exception as e:
            logger.warning(f"Error removing PID file: {e}")

    def acquire(self) -> bool:
        """
        Acquire the process lock.
        Returns True if lock acquired, False if another instance is running.
        """
        # Check if PID file exists
        old_pid = self._read_pid_file()
        
        if old_pid:
            # Check if process is actually running
            if self._is_process_running(old_pid):
                logger.error(f"❌ Another instance is running (PID: {old_pid})")
                logger.error(f"   PID file: {self.pid_file}")
                logger.error(f"   To force kill: kill -9 {old_pid}")
                return False
            else:
                # Stale PID file - remove it
                logger.warning(f"⚠️  Stale PID file detected (PID: {old_pid} is dead)")
                self._remove_pid_file()

        # Write our PID
        try:
            self._write_pid_file()
        except Exception:
            return False

        # Register cleanup handlers
        atexit.register(self.release)
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        self.acquired = True
        logger.info(f"✅ Process lock acquired (PID: {os.getpid()})")
        return True

    def release(self):
        """Release the process lock"""
        if not self.acquired:
            return

        self._remove_pid_file()
        self.acquired = False
        logger.info("✅ Process lock released")

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


def check_running_instances() -> int:
    """
    Check for running bot instances using ps command.
    More reliable than pgrep on macOS.
    """
    try:
        # Use ps to find all python processes running main.py
        result = subprocess.run(
            ['ps', 'aux'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            current_pid = os.getpid()
            count = 0
            
            for line in lines:
                # Look for actual Python process running main.py
                # Must contain "Python" (with capital P) and "main.py"
                # Exclude shell commands (sh, bash, zsh)
                if '/Python' in line and 'main.py' in line:
                    # Also exclude if it's a shell command
                    if '/bin/' in line and any(shell in line for shell in ['sh', 'bash', 'zsh']):
                        continue
                    
                    # Extract PID (second column in ps aux output)
                    parts = line.split()
                    if len(parts) > 1:
                        try:
                            pid = int(parts[1])
                            if pid != current_pid:
                                count += 1
                        except (ValueError, IndexError) as e:
                            logger.debug(f"Malformed ps aux line: {line.strip()}: {e}")
            
            return count
        return 0
    except Exception as e:
        logger.error(f"Error checking instances: {e}")
        return 0


def kill_all_instances() -> int:
    """Kill all running bot instances except current one"""
    try:
        result = subprocess.run(
            ['ps', 'aux'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            current_pid = os.getpid()
            killed = 0
            
            for line in lines:
                # Look for actual Python process running main.py
                if '/Python' in line and 'main.py' in line:
                    # Exclude shell commands
                    if '/bin/' in line and any(shell in line for shell in ['sh', 'bash', 'zsh']):
                        continue
                    
                    parts = line.split()
                    if len(parts) > 1:
                        try:
                            pid = int(parts[1])
                            if pid != current_pid:
                                os.kill(pid, signal.SIGKILL)
                                killed += 1
                                logger.info(f"Killed process {pid}")
                        except Exception as e:
                            logger.warning(f"Failed to kill {pid}: {e}")
            
            return killed
        return 0
    except Exception as e:
        logger.error(f"Error killing instances: {e}")
        return 0
