import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

_SECRET_KEYS = {
    "password",
    "secret",
    "token",
    "access_key",
    "secret_key",
    "authorization",
    "session_token",
    "aws_secret_access_key",
    "aws_access_key_id",
    "aws_session_token",
}


def _enabled(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_logger(name: str) -> logging.Logger:
    """
    Creates and returns a production-grade logger.
    Supports both console logging and file logging with rotation.
    File logging is skipped when LOG_TO_FILE is false, which keeps tests
    from rewriting logs/platform.log.
    """
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(name)

    # Avoid duplicate logs if get_logger is called multiple times
    if not logger.handlers:
        logger.setLevel(logging.INFO)

        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        if _enabled("LOG_TO_FILE", True):
            file_handler = RotatingFileHandler(
                os.path.join(log_dir, "platform.log"),
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

    return logger


def log_event(logger: logging.Logger, level: int, message: str, *, component: str, event_id=None, **fields) -> None:
    """Emit one structured JSON log line. Secret-like keys are dropped."""
    payload = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "severity": logging.getLevelName(level),
        "component": component,
        "message": message,
    }
    if event_id:
        payload["event_id"] = event_id
    for key, value in fields.items():
        if key.lower() in _SECRET_KEYS:
            continue
        payload[key] = value
    logger.log(level, json.dumps(payload, default=str, separators=(",", ":")))
