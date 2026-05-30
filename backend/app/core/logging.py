"""Loguru-based structured logger."""
import sys

from loguru import logger

from app.core.config import get_settings


def setup_logging() -> None:
    """Configure global logger sinks. Idempotent."""
    settings = get_settings()
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        backtrace=False,
        diagnose=False,
    )


__all__ = ["logger", "setup_logging"]
