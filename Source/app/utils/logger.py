"""Application logging (console + rotating file)."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from app.paths import LOG_FILE

_CONFIGURED = False


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure the root logger once and return the application logger."""
    global _CONFIGURED
    logger = logging.getLogger("media_downloader")
    if _CONFIGURED:
        return logger

    logger.setLevel(level)
    logger.propagate = False
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(threadName)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    logger.addHandler(stream)

    try:
        file_handler = RotatingFileHandler(
            LOG_FILE, maxBytes=1_500_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        pass

    _CONFIGURED = True
    return logger


log = setup_logging()
