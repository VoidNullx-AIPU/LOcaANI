import logging
import os
import sys
from logging.handlers import RotatingFileHandler

import config

logger = logging.getLogger("LOcaANI")

if not logger.handlers:
    logger.setLevel(logging.INFO)
    logger.propagate = False
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    try:
        os.makedirs(os.path.dirname(config.LOG_FILE), exist_ok=True)
        file_handler = RotatingFileHandler(config.LOG_FILE, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError as e:
        print(f"[logger] Could not open log file {config.LOG_FILE}: {e}", file=sys.stderr)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)


def log(msg: str, level: str = "info"):
    getattr(logger, level if level in ("error", "warning", "debug") else "info")(msg)
