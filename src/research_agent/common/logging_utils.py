import logging
import os
from typing import Optional, Union

PathLike = Union[str, os.PathLike]


def configure_logging(
    level: int = logging.INFO,
    log_dir: Optional[PathLike] = None,
    logger_name: Optional[str] = None,
) -> logging.Logger:
    """
    Configure a root or named logger with console (and optional file) handlers.

    Call this once at application startup (e.g., in your main entrypoint).
    Then other modules can just call `get_logger(__name__)`.
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)

    # Avoid adding duplicate handlers if configure_logging is called multiple times
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    # Optional file handler
    if log_dir:
        log_dir_str = os.fspath(log_dir)
        os.makedirs(log_dir_str, exist_ok=True)
        log_path = os.path.join(log_dir_str, "app.log")

        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger.propagate = False  # Avoid double logging to root
    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get a logger by name (or the root logger if name is None).
    Use this in your modules instead of calling logging.getLogger directly.
    """
    return logging.getLogger(name)