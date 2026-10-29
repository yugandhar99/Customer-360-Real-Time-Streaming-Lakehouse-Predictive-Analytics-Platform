"""Ingestion sinks. Event generators depend on this interface, not on AWS."""

from __future__ import annotations

import logging
from typing import Mapping, Protocol

from config import config
from ingestion.data_writer import DataWriter
from ingestion.event_schema import InvalidEventError, validate_event
from utils.logger import get_logger, log_event

logger = get_logger("EventSink")


class EventSink(Protocol):
    def publish(self, event: Mapping) -> bool:
        """Publish one event. Return False when the event is not accepted."""


class LocalCsvEventSink:
    """Validate an event and write it with the existing CSV writer."""

    def __init__(self, writer: DataWriter | None = None):
        self.writer = writer or DataWriter(filename=config.CSV_EVENTS_PATH)

    def publish(self, event: Mapping) -> bool:
        try:
            normalized = validate_event(event)
        except InvalidEventError as exc:
            log_event(
                logger,
                logging.ERROR,
                "Rejected invalid event before local write",
                component="LocalCsvEventSink",
                reason=str(exc),
            )
            return False
        return self.writer.write_event(normalized)


def build_event_sink() -> EventSink:
    """Select the sink from EXECUTION_MODE. Local mode never constructs an AWS client."""
    if config.EXECUTION_MODE == "aws":
        from ingestion.firehose_publisher import FirehoseEventPublisher

        return FirehoseEventPublisher()
    return LocalCsvEventSink()
