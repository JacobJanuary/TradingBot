"""
Log rotation utilities for the trading bot
Provides centralized log rotation for all components
"""

import logging
import logging.handlers
import os
from pathlib import Path
from typing import Dict, Optional
import glob
import time
from datetime import datetime, timedelta


class LogRotationManager:
    """Manages log rotation for all bot components"""

    def __init__(self,
                 log_dir: str = "logs",
                 max_bytes: int = 10 * 1024 * 1024,  # 10MB
                 backup_count: int = 5,
                 archive_days: int = 7):
        """
        Initialize log rotation manager

        Args:
            log_dir: Directory containing log files
            max_bytes: Maximum size per log file (default 10MB)
            backup_count: Number of backup files to keep
            archive_days: Days to keep archived logs
        """
        self.log_dir = Path(log_dir)
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.archive_days = archive_days
        self.handlers: Dict[str, logging.handlers.RotatingFileHandler] = {}

        # Ensure log directories exist
        self.log_dir.mkdir(exist_ok=True)
        (self.log_dir / "archive").mkdir(exist_ok=True)

    def get_rotating_handler(self,
                           log_file: str,
                           formatter: Optional[logging.Formatter] = None) -> logging.handlers.RotatingFileHandler:
        """
        Get or create a rotating file handler

        Args:
            log_file: Name of the log file
            formatter: Optional log formatter

        Returns:
            Configured rotating file handler
        """
        if log_file not in self.handlers:
            log_path = self.log_dir / log_file

            # Create rotating handler
            handler = logging.handlers.RotatingFileHandler(
                log_path,
                maxBytes=self.max_bytes,
                backupCount=self.backup_count
            )

            # Set formatter
            if formatter is None:
                formatter = logging.Formatter(
                    '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S'
                )
            handler.setFormatter(formatter)

            self.handlers[log_file] = handler

        return self.handlers[log_file]

    def setup_component_logger(self,
                             component: str,
                             level: str = 'INFO') -> logging.Logger:
        """
        Set up logger for a specific component with rotation

        Args:
            component: Component name (e.g., 'exchange', 'signal_processor')
            level: Logging level

        Returns:
            Configured logger
        """
        logger = logging.getLogger(component)
        logger.setLevel(getattr(logging, level.upper()))

        # Remove existing handlers
        logger.handlers = []

        # Add rotating file handler
        log_file = f"{component}.log"
        handler = self.get_rotating_handler(log_file)
        logger.addHandler(handler)

        return logger

    def rotate_all_logs(self):
        """Force rotation of all log files if they exceed size limit"""
        for log_file in self.log_dir.glob("*.log"):
            if log_file.stat().st_size > self.max_bytes:
                # Rename current log to .1 and shift others
                self._rotate_file(log_file)

    def _rotate_file(self, log_file: Path):
        """Manually rotate a single log file"""
        # Shift existing backups
        for i in range(self.backup_count - 1, 0, -1):
            old_backup = log_file.with_suffix(f'.log.{i}')
            new_backup = log_file.with_suffix(f'.log.{i+1}')
            if old_backup.exists():
                if new_backup.exists():
                    new_backup.unlink()
                old_backup.rename(new_backup)

        # Move current log to .1
        if log_file.exists():
            backup_1 = log_file.with_suffix('.log.1')
            if backup_1.exists():
                backup_1.unlink()
            log_file.rename(backup_1)

    def archive_old_logs(self):
        """Archive logs older than archive_days"""
        cutoff_time = time.time() - (self.archive_days * 24 * 60 * 60)
        archive_dir = self.log_dir / "archive"

        # Archive old backup files
        for log_file in self.log_dir.glob("*.log.*"):
            if log_file.stat().st_mtime < cutoff_time:
                archive_name = archive_dir / f"{log_file.name}.{datetime.now().strftime('%Y%m%d')}"
                log_file.rename(archive_name)
                print(f"Archived {log_file.name} to {archive_name}")

    def cleanup_archives(self):
        """Remove archived logs older than 30 days"""
        archive_dir = self.log_dir / "archive"
        cutoff_time = time.time() - (30 * 24 * 60 * 60)

        for archive_file in archive_dir.glob("*"):
            if archive_file.stat().st_mtime < cutoff_time:
                archive_file.unlink()
                print(f"Deleted old archive: {archive_file.name}")

    def get_log_stats(self) -> Dict:
        """Get statistics about current logs"""
        stats: Dict[str, Any] = {
            'total_size': 0,
            'file_count': 0,
            'largest_file': None,
            'largest_size': 0,
            'files': []
        }

        for log_file in self.log_dir.glob("*.log*"):
            if log_file.is_file():
                size = log_file.stat().st_size
                stats['total_size'] += size
                stats['file_count'] += 1
                stats['files'].append({
                    'name': log_file.name,
                    'size': size,
                    'size_mb': round(size / (1024 * 1024), 2)
                })

                if size > stats['largest_size']:
                    stats['largest_size'] = size
                    stats['largest_file'] = log_file.name

        stats['total_size_mb'] = round(stats['total_size'] / (1024 * 1024), 2)

        return stats


# Singleton instance
_rotation_manager: Optional[LogRotationManager] = None


def get_rotation_manager() -> LogRotationManager:
    """Get or create the global rotation manager"""
    global _rotation_manager
    if _rotation_manager is None:
        _rotation_manager = LogRotationManager()
    return _rotation_manager


def setup_rotating_logger(name: str,
                        level: str = 'INFO',
                        log_file: Optional[str] = None) -> logging.Logger:
    """
    Quick setup for a rotating logger

    Args:
        name: Logger name
        level: Logging level
        log_file: Optional specific log file name

    Returns:
        Configured logger with rotation
    """
    manager = get_rotation_manager()

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))
    logger.handlers = []

    # Determine log file name
    if log_file is None:
        log_file = f"{name.replace('.', '_')}.log"

    # Add rotating handler
    handler = manager.get_rotating_handler(log_file)
    logger.addHandler(handler)

    # Also add console handler for important messages
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    console.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    logger.addHandler(console)

    return logger


def perform_maintenance():
    """Perform log maintenance tasks"""
    manager = get_rotation_manager()

    print("🔄 Performing log maintenance...")

    # Get initial stats
    stats = manager.get_log_stats()
    print(f"📊 Current logs: {stats['file_count']} files, {stats['total_size_mb']} MB")

    # Rotate large logs
    manager.rotate_all_logs()

    # Archive old logs
    manager.archive_old_logs()

    # Clean up very old archives
    manager.cleanup_archives()

    # Get final stats
    stats = manager.get_log_stats()
    print(f"✅ After maintenance: {stats['file_count']} files, {stats['total_size_mb']} MB")

    return stats


if __name__ == "__main__":
    # Run maintenance if executed directly
    perform_maintenance()