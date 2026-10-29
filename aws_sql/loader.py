"""Load Athena SQL files and render the Glue database name."""

from __future__ import annotations

import os

SQL_DIR = os.path.dirname(os.path.abspath(__file__))


def load_sql(name: str, database: str = "customer_360") -> str:
    filename = name if name.endswith(".sql") else f"{name}.sql"
    path = os.path.join(SQL_DIR, filename)
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    with open(path, encoding="utf-8") as handle:
        sql = handle.read()
    return sql.replace("{{database}}", database)


def sqlite_sql(name: str, database: str = "customer_360") -> str:
    """Strip the Glue database qualifier so the same SQL can run on SQLite fixtures."""
    return load_sql(name, database).replace(f"{database}.", "")
