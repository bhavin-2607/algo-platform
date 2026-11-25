"""
Centralized Application Logging Configuration
=============================================
Manages categorized rotating file loggers and console streaming:
- logs/trades.log   : Dedicated trade and order execution audit log
- logs/algo.log     : Real-time BSA algo triggers, formula evaluations, and state transitions
- logs/market.log   : Market poller feed, OHLC ingestion, and tick telemetry
- logs/error.log    : Dedicated error log with full stack traces (ERROR and CRITICAL only)
- logs/app.log      : Consolidated application log (FastAPI, auth, system events)
- Console           : Standard output for systemd journald / terminal streaming
"""
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List, Dict, Any, Optional

MAX_LOG_BYTES = 50 * 1024 * 1024  # 50 MB
BACKUP_COUNT = 10
LOG_FORMAT = "%(asctime)s [%(levelname)-7s] [%(name)s:%(lineno)d] - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False
_log_dir = ""


def get_log_dir() -> str:
    """Return the absolute path to the project logs directory."""
    global _log_dir
    if not _log_dir:
        base_dir = Path(__file__).resolve().parent.parent.parent.parent
        _log_dir = os.path.join(base_dir, "logs")
    return _log_dir


def setup_logging(log_dir: str = None) -> None:
    """
    Initialize categorized logging handlers. Safe to call multiple times (idempotent).
    """
    global _configured, _log_dir
    if _configured:
        return

    if not log_dir:
        log_dir = get_log_dir()
    else:
        _log_dir = log_dir

    os.makedirs(log_dir, exist_ok=True)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # 1. Console Handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # 2. General app.log handler (Consolidated)
    app_log_path = os.path.join(log_dir, "app.log")
    app_file_handler = RotatingFileHandler(
        app_log_path,
        maxBytes=MAX_LOG_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    app_file_handler.setLevel(logging.INFO)
    app_file_handler.setFormatter(formatter)

    # 3. Dedicated error.log handler (ERROR and CRITICAL only)
    error_log_path = os.path.join(log_dir, "error.log")
    error_file_handler = RotatingFileHandler(
        error_log_path,
        maxBytes=MAX_LOG_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(formatter)

    # 4. Dedicated trades.log handler (Orders, Fills, Copy Trading, Square-off)
    trades_log_path = os.path.join(log_dir, "trades.log")
    trades_file_handler = RotatingFileHandler(
        trades_log_path,
        maxBytes=MAX_LOG_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    trades_file_handler.setLevel(logging.INFO)
    trades_file_handler.setFormatter(formatter)

    # 5. Dedicated algo.log handler (BSA algo evaluations, targets, stop-loss)
    algo_log_path = os.path.join(log_dir, "algo.log")
    algo_file_handler = RotatingFileHandler(
        algo_log_path,
        maxBytes=MAX_LOG_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    algo_file_handler.setLevel(logging.INFO)
    algo_file_handler.setFormatter(formatter)

    # 6. Dedicated market.log handler (Poller, quotes, OHLC)
    market_log_path = os.path.join(log_dir, "market.log")
    market_file_handler = RotatingFileHandler(
        market_log_path,
        maxBytes=MAX_LOG_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    market_file_handler.setLevel(logging.INFO)
    market_file_handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(app_file_handler)
    root_logger.addHandler(error_file_handler)

    # Attach categorized handlers to specific subsystems
    trade_subsystems = [
        "algo.trade",
        "app.services.dhan_fanout_engine",
        "app.services.order_manager",
        "app.broker.dhan",
        "app.api.routes.trades",
    ]
    for name in trade_subsystems:
        logger = logging.getLogger(name)
        logger.addHandler(trades_file_handler)

    algo_subsystems = [
        "algo.engine",
        "app.services.bsa_algo_engine",
        "app.strategy.executor",
        "app.strategy.excel_formula_engine",
        "app.api.routes.terminal",
    ]
    for name in algo_subsystems:
        logger = logging.getLogger(name)
        logger.addHandler(algo_file_handler)

    market_subsystems = [
        "algo.market",
        "app.market.market_poller",
        "app.market.daily_ohlc",
        "app.api.routes.market",
    ]
    for name in market_subsystems:
        logger = logging.getLogger(name)
        logger.addHandler(market_file_handler)

    # Quiet down noisy external libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("passlib").setLevel(logging.WARNING)

    _configured = True
    root_logger.info(f"Categorized logging initialized. Directory: {log_dir}")


def read_log_tail(log_name: str = "app", lines: int = 100) -> Dict[str, Any]:
    """
    Read the latest N lines from a specified log file safely.
    Valid log_name choices: 'trades', 'algo', 'market', 'error', 'app', 'platform'.
    """
    valid_files = {
        "trades":   "trades.log",
        "algo":     "algo.log",
        "market":   "market.log",
        "error":    "error.log",
        "app":      "app.log",
        "platform": "platform.log",
    }
    file_basename = valid_files.get(log_name.lower().strip(), "app.log")
    log_dir = get_log_dir()
    file_path = os.path.join(log_dir, file_basename)

    if not os.path.exists(file_path):
        return {
            "file": file_basename,
            "exists": False,
            "lines": [],
            "total_lines": 0,
            "size_bytes": 0,
            "last_modified": None,
        }

    try:
        stat = os.stat(file_path)
        size_bytes = stat.st_size
        import datetime
        last_modified = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")

        lines_to_read = max(1, min(lines, 1000))
        # Read from end of file efficiently
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
            tail_lines = [l.rstrip("\r\n") for l in all_lines[-lines_to_read:]]

        return {
            "file": file_basename,
            "exists": True,
            "lines": tail_lines,
            "total_lines": len(all_lines),
            "size_bytes": size_bytes,
            "last_modified": last_modified,
        }
    except Exception as e:
        return {
            "file": file_basename,
            "exists": True,
            "error": str(e),
            "lines": [],
            "total_lines": 0,
            "size_bytes": 0,
            "last_modified": None,
        }
