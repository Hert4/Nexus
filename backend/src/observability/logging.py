"""
observability/logging.py — Structured logging với structlog.

Setup JSON logging trong production, pretty console logging trong dev.
Tất cả modules dùng: logger = structlog.get_logger(__name__)
"""

import logging
import sys

import structlog


def setup_logging(log_level: str = "INFO") -> None:
    """
    Khởi tạo structlog với stdlib integration.
    - Development: màu sắc console
    - Production: JSON format
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Dùng stdlib logging làm backend → PrintLogger có .name
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.dev.ConsoleRenderer() if log_level.upper() == "DEBUG"
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
