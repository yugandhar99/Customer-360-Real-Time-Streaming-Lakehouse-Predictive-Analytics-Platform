"""Athena implementation of the analytics backend.

Queries run in the configured workgroup and write results only to the configured
S3 location. A failed or unfinished query raises AthenaQueryError. This backend
does not open SQLite and does not turn a cloud failure into an empty frame.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Callable

import pandas as pd

from config import AWSConfigurationError, config
from storage.backend import AnalyticsBackend
from utils.logger import get_logger, log_event

logger = get_logger("AthenaBackend")

_TABLES = (
    "events",
    "ltv_metrics",
    "funnel_metrics",
    "retention_metrics",
    "cohort_metrics",
    "churn_metrics",
    "user_segments",
)
_INT_TYPES = {"bigint", "integer", "int", "tinyint", "smallint"}
_FLOAT_TYPES = {"double", "float", "real", "decimal"}


class AthenaQueryError(RuntimeError):
    """Athena did not return a usable result set."""


def analytics_sql(sql: str, database: str) -> str:
    """Qualify tables and read each Firehose event id once.

    Delivery is at least once. This wrapper keeps a retried event_id from
    being counted twice. SQL that already deduplicates is left unchanged.
    Local SQLite queries do not use this function.
    """
    statement = qualify_sql(_single_statement(sql), database)
    if re.search(r"(?i)\brow_number\s*\(", statement):
        return statement
    token = "___C360_EVENTS___"
    pattern = re.compile(rf"(?i)\b(from|join)\s+{re.escape(database)}\.events\b")
    marked = pattern.sub(rf"\1 {token}", statement)
    deduped = (
        "(SELECT event_id, user_id, event_type, amount, timestamp FROM ("
        "SELECT event_id, user_id, event_type, amount, timestamp, "
        "row_number() OVER (PARTITION BY event_id ORDER BY timestamp) AS row_num "
        f"FROM {database}.events) deduped_events WHERE row_num = 1)"
    )
    return marked.replace(token, deduped)


def qualify_sql(sql: str, database: str) -> str:
    """Render the database placeholder and qualify known bare table names."""
    rendered = sql.replace("{{database}}", database)
    for table in _TABLES:
        rendered = re.sub(
            rf"(?i)\b(from|join)\s+{table}\b",
            rf"\1 {database}.{table}",
            rendered,
        )
    return rendered


def _single_statement(sql: str) -> str:
    stripped = sql.strip().rstrip(";").strip()
    if not stripped:
        raise AthenaQueryError("SQL statement is empty")
    if ";" in stripped:
        raise AthenaQueryError("Only a single SQL statement is allowed")
    return stripped


def _coerce(value, type_name: str):
    if value is None or value == "":
        return None
    normalized = (type_name or "").lower()
    if normalized in _INT_TYPES:
        return int(float(value))
    if normalized in _FLOAT_TYPES:
        return float(value)
    if normalized == "boolean":
        return str(value).lower() == "true"
    return value


def map_result_set(payload: dict, skip_header: bool = True) -> pd.DataFrame:
    """Map one GetQueryResults page to a DataFrame using Athena column types."""
    result_set = payload.get("ResultSet") or {}
    metadata = (result_set.get("ResultSetMetadata") or {}).get("ColumnInfo") or []
    names = [column.get("Name", f"column_{index}") for index, column in enumerate(metadata)]
    types = [column.get("Type", "varchar") for column in metadata]
    rows = list(result_set.get("Rows") or [])
    if skip_header and rows:
        rows = rows[1:]
    records = []
    for row in rows:
        cells = row.get("Data") or []
        record = {}
        for index, name in enumerate(names):
            cell = cells[index] if index < len(cells) else {}
            raw = cell.get("VarCharValue") if isinstance(cell, dict) else None
            record[name] = _coerce(raw, types[index] if index < len(types) else "varchar")
        records.append(record)
    return pd.DataFrame(records, columns=names)


class AthenaBackend(AnalyticsBackend):
    def __init__(
        self,
        athena_client=None,
        s3_client=None,
        poll_interval: float = 1.0,
        max_polls: int = 30,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        config.validate_aws_analytics()
        self._athena = athena_client
        self._s3 = s3_client
        self.poll_interval = poll_interval
        self.max_polls = max_polls
        self.sleeper = sleeper
        self.database = config.AWS_GLUE_DATABASE
        self.workgroup = config.ATHENA_WORKGROUP
        self.results_uri = config.ATHENA_RESULTS_S3_URI
        self.bucket = config.AWS_S3_BUCKET

    def _service(self, name: str):
        current = self._athena if name == "athena" else self._s3
        if current is not None:
            return current
        try:
            import boto3
        except ImportError as exc:
            raise AWSConfigurationError(
                "boto3 is required for AWS analytics and is not installed"
            ) from exc
        client = boto3.client(name, region_name=config.AWS_REGION)
        if name == "athena":
            self._athena = client
        else:
            self._s3 = client
        return client

    def query(self, sql: str) -> pd.DataFrame:
        statement = analytics_sql(sql, self.database)
        athena = self._service("athena")
        started = athena.start_query_execution(
            QueryString=statement,
            QueryExecutionContext={"Database": self.database},
            WorkGroup=self.workgroup,
            ResultConfiguration={"OutputLocation": self.results_uri},
        )
        query_id = started["QueryExecutionId"]
        log_event(
            logger,
            logging.INFO,
            "Started Athena query",
            component="AthenaBackend",
            event_id=query_id,
            workgroup=self.workgroup,
        )
        state = "QUEUED"
        reason = ""
        for _ in range(self.max_polls):
            status = athena.get_query_execution(QueryExecutionId=query_id)
            info = status["QueryExecution"]["Status"]
            state = info.get("State", "UNKNOWN")
            reason = info.get("StateChangeReason", "")
            if state in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                break
            self.sleeper(self.poll_interval)
        else:
            raise AthenaQueryError(
                f"Athena query {query_id} did not finish within {self.max_polls} polls"
            )
        if state != "SUCCEEDED":
            log_event(
                logger,
                logging.ERROR,
                "Athena query failed",
                component="AthenaBackend",
                event_id=query_id,
                state=state,
                reason=reason,
            )
            raise AthenaQueryError(f"Athena query {query_id} {state}: {reason}".strip())

        frames = []
        token = None
        first_page = True
        while True:
            kwargs = {"QueryExecutionId": query_id}
            if token:
                kwargs["NextToken"] = token
            page = athena.get_query_results(**kwargs)
            frames.append(map_result_set(page, skip_header=first_page))
            first_page = False
            token = page.get("NextToken")
            if not token:
                break
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def save_metric_table(self, frame: pd.DataFrame, table_name: str) -> None:
        if frame.empty:
            return
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table_name):
            raise AthenaQueryError(f"Unsupported metric table name: {table_name}")
        body = frame.to_json(orient="records", lines=True, date_format="iso")
        key = f"analytics/{table_name}/metrics.json"
        try:
            self._service("s3").put_object(
                Bucket=self.bucket,
                Key=key,
                Body=body.encode("utf-8"),
                ContentType="application/x-ndjson",
                ServerSideEncryption="AES256",
            )
        except Exception as exc:
            log_event(
                logger,
                logging.ERROR,
                "Failed to store analytics output",
                component="AthenaBackend",
                table=table_name,
                reason=str(exc),
            )
            raise AthenaQueryError(
                f"Failed to store {table_name} at s3://{self.bucket}/{key}: {exc}"
            ) from exc
        log_event(
            logger,
            logging.INFO,
            "Stored analytics output",
            component="AthenaBackend",
            table=table_name,
            object_key=key,
            rows=len(frame),
        )
