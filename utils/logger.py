"""
Centralized logging configuration
"""
import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional


def setup_logger(
        name: str = None,
        level: str = 'INFO',
        log_file: Optional[str] = None,
        console: bool = True,
        format_string: Optional[str] = None
) -> logging.Logger:
    """
    Setup logger with file and console handlers

    Args:
        name: Logger name
        level: Logging level
        log_file: Path to log file
        console: Enable console output
        format_string: Log format string

    Returns:
        Configured logger
    """
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    logger.handlers = []

    # Default format
    if not format_string:
        format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    formatter = logging.Formatter(format_string)

    # Console handler
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # File handler
    if log_file:
        # Create log directory if needed
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Rotating file handler (10MB max, 5 backups)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def setup_trading_logger():
    """Setup specialized trading logger"""
    return setup_logger(
        name='trading_bot',
        level='INFO',
        log_file='logs/trading_bot.log',
        format_string='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )