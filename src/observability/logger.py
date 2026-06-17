"""Basic logging helpers."""

from __future__ import annotations

import logging


def get_logger(name: str = "modular_rag") -> logging.Logger:
    """Return a stderr logger suitable for early bootstrap stages."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger
