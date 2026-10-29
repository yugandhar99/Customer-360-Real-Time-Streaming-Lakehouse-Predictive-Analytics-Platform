"""Backend contracts and selection for local and AWS execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd

from config import config


class AnalyticsBackend(ABC):
    """Small interface shared by analytics jobs and the dashboard."""

    @abstractmethod
    def query(self, sql: str) -> pd.DataFrame:
        """Return a query result as a DataFrame."""

    @abstractmethod
    def save_metric_table(self, frame: pd.DataFrame, table_name: str) -> None:
        """Replace a metric table with a DataFrame."""


def get_backend(db_path: Optional[str] = None) -> AnalyticsBackend:
    """Create the backend selected by EXECUTION_MODE.

    Local mode returns SQLite. AWS mode returns Athena and validates its
    configuration before any cloud call. GCP remains on the legacy modules
    and is not selected here. AWS mode never falls back to SQLite.
    """
    if config.EXECUTION_MODE == "local":
        from storage.sqlite_backend import SQLiteBackend

        return SQLiteBackend(db_path or config.SQLITE_DB_PATH)

    if config.EXECUTION_MODE == "aws":
        from storage.athena_backend import AthenaBackend

        return AthenaBackend()

    raise NotImplementedError(
        "The legacy GCP path is handled by existing GCP-aware modules; "
        "use EXECUTION_MODE=local or EXECUTION_MODE=aws for this backend"
    )
