"""
Centralized Application Logging Configuration
=============================================
Manages rotating file loggers and console streaming:
- logs/app.log   : All application logs (INFO and above)
- logs/error.log : Dedicated error log (ERROR and CRITICAL only with stack traces)
- Console        : Standard output for systemd journald / terminal streaming
"""
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# 50 MB per file, 10 rotated backups (giving up to 1 GB log retention on SSD)
MAX_LOG_BYTES = 50 * 1024 * 1024  # 50 MB
BACKUP_COUNT = 10
LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def setup_logging(log_dir: str = None) -> None:
    """
    Initialize root logging handlers. Safe to call multiple times (idempotent).
    """
    global _configured
    if _configured:
        return

    # Default log directory at project root: algo-platform/logs/
    if not log_dir:
        # File is at: backend/app/core/logging_config.py -> project root is 3 levels up
        base_dir = Path(__file__).resolve().parent.parent.parent.parent
        log_dir = os.path.join(base_dir, "logs")

    os.makedirs(log_dir, exist_ok=True)

    app_log_path = os.path.join(log_dir, "app.log")
    error_log_path = os.path.join(log_dir, "error.log")

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # 1. Console Handler (stdout) for systemd journald and interactive terminal
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # 2. Rotating File Handler for general app logs (INFO, WARNING, ERROR, CRITICAL)
    app_file_handler = RotatingFileHandler(
        app_log_path,
        maxBytes=MAX_LOG_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    app_file_handler.setLevel(logging.INFO)
    app_file_handler.setFormatter(formatter)

    # 3. Rotating File Handler for dedicated errors (ERROR and CRITICAL only)
    error_file_handler = RotatingFileHandler(
        error_log_path,
        maxBytes=MAX_LOG_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Clear existing handlers to prevent duplicate lines
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(app_file_handler)
    root_logger.addHandler(error_file_handler)

    # Quiet down excessively noisy external libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("passlib").setLevel(logging.WARNING)

    _configured = True
    root_logger.info(f"Centralized logging initialized. Directory: {log_dir}")
