"""
Logging configuration helper for the OptiBot Mini pipeline.
"""

from __future__ import annotations

from datetime import datetime
import glob
import logging
import os
import sys
import time


def setup_logging(log_dir: str = "logs") -> None:
    """
    Configure standard logging to stdout and daily files, and clean up logs older than 7 days.
    """
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception as e:
        sys.stderr.write(f"Warning: Could not create log directory {log_dir}: {e}\n")

    # Dynamically set active log filename to include the date: pipeline.log.YYYY-MM-DD
    current_date = datetime.now().strftime("%Y-%m-%d")
    log_path = os.path.join(log_dir, f"pipeline.log.{current_date}")

    # Keep only logs from the last 7 days (clean up older pipeline.log.YYYY-MM-DD files)
    try:
        now = time.time()
        for f in glob.glob(os.path.join(log_dir, "pipeline.log.*")):
            basename = os.path.basename(f)
            if basename.startswith("pipeline.log."):
                if os.stat(f).st_mtime < now - 7 * 86400:
                    os.remove(f)
    except Exception as e:
        sys.stderr.write(f"Warning: Could not clean up old logs: {e}\n")

    # Configure daily log file logging (keeps last 7 days via cleanup above)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_path, encoding="utf-8")
        ],
    )

    # Silence noisy SDK loggers.
    # `httpx` emits one "HTTP Request: ..." line per poll tick during upload_and_poll,
    # flooding the log with dozens of GET lines for a single file upload.
    # `openai` and `httpcore` follow the same pattern.
    # We only want to see our own pipeline-level log messages.
    for noisy_logger in ("httpx", "httpcore", "openai"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
