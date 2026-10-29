"""Validated customer event records shared by local and AWS ingestion."""

from __future__ import annotations

import math
import uuid
from datetime import datetime
from typing import Any, Mapping

from config import config

class InvalidEventError(ValueError):
    """The event cannot be published because it fails schema checks."""


_TIMESTAMP_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S.%fZ",
)


def validate_event(event: Mapping[str, Any]) -> dict:
    """Return a canonical event. A missing event_id is assigned once and reused."""
    if not isinstance(event, Mapping):
        raise InvalidEventError("event must be an object")

    user_id = str(event.get("user_id") or "").strip()
    if not user_id:
        raise InvalidEventError("user_id is required")

    event_type = str(event.get("event_type") or "").strip()
    if event_type not in config.EVENT_TYPES:
        allowed = ", ".join(config.EVENT_TYPES)
        raise InvalidEventError(f"event_type must be one of {allowed}")

    try:
        amount = float(event.get("amount", 0.0))
    except (TypeError, ValueError) as exc:
        raise InvalidEventError("amount must be numeric") from exc
    if math.isnan(amount) or math.isinf(amount) or amount < 0:
        raise InvalidEventError("amount must be a finite number greater than or equal to zero")

    raw_timestamp = event.get("timestamp")
    if not isinstance(raw_timestamp, str) or not raw_timestamp.strip():
        raise InvalidEventError("timestamp is required")
    timestamp = _parse_timestamp(raw_timestamp.strip()).strftime("%Y-%m-%d %H:%M:%S")

    raw_event_id = event.get("event_id")
    if raw_event_id is None or str(raw_event_id).strip() == "":
        event_id = str(uuid.uuid4())
    else:
        event_id = str(raw_event_id).strip()

    if isinstance(event, dict):
        event["event_id"] = event_id

    return {
        "event_id": event_id,
        "user_id": user_id,
        "event_type": event_type,
        "amount": round(amount, 2),
        "timestamp": timestamp,
    }


def _parse_timestamp(value: str) -> datetime:
    for fmt in _TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise InvalidEventError("timestamp must be YYYY-MM-DD HH:MM:SS or ISO-8601")
