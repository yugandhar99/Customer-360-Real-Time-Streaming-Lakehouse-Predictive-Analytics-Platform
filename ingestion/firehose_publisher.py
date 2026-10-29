"""Publish validated events to Amazon Data Firehose.

Amazon Data Firehose is the delivery path for this platform. The Terraform
default buffers for 60 seconds or 1 MB, whichever comes first, and then writes
gzip JSON under ``raw/events/year=YYYY/month=MM/day=DD/``. That freshness is
coarser than the legacy 20 second Pub/Sub micro-batch and is acceptable for
these analytics jobs. Kinesis Data Streams is not used.

The partition is Firehose arrival time, not the event timestamp. The event
timestamp stays inside the JSON record and is what Athena uses for cohort logic.

Retries send the same JSON body and the same event_id. After a successful
response, this process remembers the event_id and will not send it again.
A restarted process can deliver the same event_id, and Firehose can retry
internally, so Athena readers should dedupe with ``aws_sql/events_deduped.sql``.
Failed deliveries stay in ``failed`` and are not replaced with a local write.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Callable, Mapping

from config import AWSConfigurationError, config
from ingestion.event_schema import InvalidEventError, validate_event
from utils.logger import get_logger, log_event

logger = get_logger("FirehosePublisher")


class FirehoseEventPublisher:
    def __init__(
        self,
        client=None,
        stream_name: str | None = None,
        max_attempts: int = 3,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        config.validate_firehose()
        self.client = client
        self.stream_name = stream_name or config.AWS_FIREHOSE_DELIVERY_STREAM
        self.max_attempts = max_attempts
        self.sleeper = sleeper
        self._delivered: set[str] = set()
        self.failed: list[dict] = []

    def _client(self):
        if self.client is not None:
            return self.client
        try:
            import boto3
        except ImportError as exc:
            raise AWSConfigurationError(
                "boto3 is required for Firehose publishing and is not installed"
            ) from exc
        self.client = boto3.client("firehose", region_name=config.AWS_REGION)
        return self.client

    def publish(self, event: Mapping) -> bool:
        try:
            normalized = validate_event(event)
        except InvalidEventError as exc:
            log_event(
                logger,
                logging.ERROR,
                "Rejected invalid event before Firehose delivery",
                component="FirehosePublisher",
                reason=str(exc),
            )
            return False

        event_id = normalized["event_id"]
        if event_id in self._delivered:
            log_event(
                logger,
                logging.INFO,
                "Skipped event that was already delivered in this process",
                component="FirehosePublisher",
                event_id=event_id,
            )
            return True

        body = json.dumps(normalized, separators=(",", ":")).encode("utf-8") + b"\n"
        delay = 0.2
        last_error = "unknown delivery failure"
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self._client().put_record(
                    DeliveryStreamName=self.stream_name,
                    Record={"Data": body},
                )
            except Exception as exc:
                last_error = str(exc)
                log_event(
                    logger,
                    logging.WARNING,
                    "Firehose put_record attempt failed",
                    component="FirehosePublisher",
                    event_id=event_id,
                    attempt=attempt,
                    reason=last_error,
                )
            else:
                record_id = response.get("RecordId") if isinstance(response, dict) else None
                error_code = response.get("ErrorCode") if isinstance(response, dict) else None
                if record_id and not error_code:
                    self._delivered.add(event_id)
                    log_event(
                        logger,
                        logging.INFO,
                        "Delivered event to Firehose",
                        component="FirehosePublisher",
                        event_id=event_id,
                        attempt=attempt,
                    )
                    return True
                last_error = str(
                    (response or {}).get("ErrorMessage")
                    or error_code
                    or "Firehose response did not include RecordId"
                )
                log_event(
                    logger,
                    logging.WARNING,
                    "Firehose rejected the record",
                    component="FirehosePublisher",
                    event_id=event_id,
                    attempt=attempt,
                    reason=last_error,
                )

            if attempt < self.max_attempts:
                self.sleeper(delay)
                delay *= 2

        self.failed.append({"event_id": event_id, "error": last_error})
        log_event(
            logger,
            logging.ERROR,
            "Firehose delivery failed after retries",
            component="FirehosePublisher",
            event_id=event_id,
            reason=last_error,
        )
        return False

    def publish_many(self, events) -> list[bool]:
        return [self.publish(event) for event in events]
