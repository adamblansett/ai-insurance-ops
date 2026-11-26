import logging
from typing import Any

import structlog

_SENSITIVE_KEY_TOKENS = (
    "authorization",
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "ssn",
)


def _redact_sensitive_keys(
    _: Any,
    __: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Scrub sensitive credential or PII keys from structured log records."""
    for key in list(event_dict.keys()):
        lowered = str(key).lower()
        if any(tok in lowered for tok in _SENSITIVE_KEY_TOKENS):
            event_dict[key] = "[REDACTED]"
    return event_dict


def configure_logging(log_level: str = "INFO", app_env: str = "development") -> None:
    """Configure structlog JSON/structured logging with contextvars and redaction."""
    level_name = log_level.strip().upper()
    numeric_level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(level=numeric_level, format="%(message)s")

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _redact_sensitive_keys,
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ]
    _ = app_env
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
