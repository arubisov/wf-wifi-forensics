"""
Logging utilities for the wf toolkit.

Provides unified structured logging:
- pretty console output via Rich
- structured (JSON) file output to `ingest.log` when running `wf ingest`
"""

import logging
import sys
import json
from pathlib import Path

from rich.logging import RichHandler


class JSONFormatter(logging.Formatter):
    """
    Formatter that serializes log records to JSON.
    """
    def format(self, record: logging.LogRecord) -> str:
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level":     record.levelname,
            "logger":    record.name,
            "message":   record.getMessage(),
        }
        return json.dumps(log_record)


def get_logger(name: str, level: int | str = logging.INFO) -> logging.Logger:
    """
    Return a configured logger for the given name.

    Attaches:
    - a RichHandler for console output
    - when the command is 'ingest', a FileHandler writing JSON logs to {cwd}/ingest.log

    Parameters
    ----------
    name
        Logger name (typically __name__).
    level
        Log level (int or string), defaults to INFO.

    Returns
    -------
    logging.Logger
        Configured logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        # Console via Rich
        console_handler = RichHandler(rich_tracebacks=True)
        console_handler.setLevel(level)
        logger.addHandler(console_handler)

        # File output for `wf ingest`, as structured JSON
        if len(sys.argv) > 1 and sys.argv[1] == "ingest":
            log_path = Path.cwd() / f"{sys.argv[1]}.log"
            file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
            file_handler.setLevel(level)
            file_handler.setFormatter(JSONFormatter())
            logger.addHandler(file_handler)

    return logger