"""SQLite implementation of the local analytics backend."""

from __future__ import annotations

import os
import sqlite3

import pandas as pd

from storage.backend import AnalyticsBackend


class SQLiteBackend(AnalyticsBackend):
    def __init__(self, db_path: str):
        self.db_path = db_path

    def query(self, sql: str) -> pd.DataFrame:
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"SQLite database missing at {self.db_path}")
        connection = sqlite3.connect(self.db_path)
        try:
            with connection:
                return pd.read_sql_query(sql, connection)
        finally:
            connection.close()

    def save_metric_table(self, frame: pd.DataFrame, table_name: str) -> None:
        if frame.empty:
            return
        connection = sqlite3.connect(self.db_path)
        try:
            with connection:
                frame.to_sql(table_name, connection, if_exists='replace', index=False)
        finally:
            connection.close()
