import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler


def setup_logging(
    level: int = logging.INFO,
    log_file: Path = None,
    fmt: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
):
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(
            str(log_file), maxBytes=10*1024*1024, backupCount=5, encoding="utf-8"
        ))
    logging.basicConfig(level=level, format=fmt, handlers=handlers)
