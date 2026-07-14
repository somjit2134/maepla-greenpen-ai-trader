import logging
import sys
from pathlib import Path

from src.config import get


def setup() -> logging.Logger:
    cfg = get()
    log_file = Path(cfg.logging.file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, cfg.logging.level.upper(), logging.INFO)
    logger = logging.getLogger("maepla")
    logger.setLevel(level)

    if logger.handlers:
        return logger

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = logging.FileHandler(str(log_file), encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(fmt)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)

    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger("maepla")
