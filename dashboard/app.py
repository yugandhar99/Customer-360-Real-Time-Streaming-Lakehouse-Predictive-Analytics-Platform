
"""Customer 360 analytics dashboard with AWS, GCP, and local backends."""

import math
import os
import sys

import pandas as pd
from flask import Flask, jsonify, render_template

# Add the project root to Python's import path.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from config import config
from storage.backend import get_backend
from utils.logger import get_logger

try:
    from google.cloud import bigquery
except ImportError:
    bigquery = None


app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "templates"),
)
logger = get_logger("DashboardApp")


# ---------------------------------------------------------------------
# Platform configuration
# ---------------------------------------------------------------------

def platform_context():
    """Return labels for the configured analytics platform."""
    if config.EXECUTION_MODE == "aws":
        return "AWS Athena", "Firehose to S3"

    if config.USE_GCP:
        return "GCP Cloud", "GCP Pub/Sub"

    return "Local Storage", "Local CSV"


def _normalise_value(value):
    """Convert Pandas/NumPy values to template- and JSON-safe values."""
    if value is None or value is pd.NA:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if hasattr(value, "item"):
        try:
            value = value.item()
        except (ValueError, AttributeError):
            pass

    if isinstance(value, float) and not math.isfinite(value):
        return None

    return value


def _normalise_records(df):
    """Convert a DataFrame into records with normalized values."""
    if df is None or df.empty:
        return []

    return [
        {
            key: _normalise_value(value)
            for key, value in record.items()
        }
        for record in df.to_dict(orient="records")
    ]


def _safe_number(value, default=0.0):
    """Safely convert a value to a finite number."""
    value = _normalise_value(value)

    if value is None or value == "":
        return default

    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError, OverflowError):
        return default


def _safe_int(value, default=0):
    """Safely convert a value to an integer."""
    return int(_safe_number(value, default))


def _safe_rate(numerator, denominator):
    """Calculate a percentage without division-by-zero errors."""
    denominator = _safe_number(denominator)
    numerator = _safe_number(numerator)

    if denominator <= 0:
        return 0.0

    return round((numerator / denominator) * 100, 2)


# ---------------------------------------------------------------------
# Analytics query execution
# ---------------------------------------------------------------------

def fetch_table(query: str, as_dict: bool = True):
    """
    Execute a query through the explicitly configured backend.

    AWS and GCP failures are raised; they never silently fall back
    to local data.
    """
    if config.EXECUTION_MODE == "aws":
        try:
            df = get_backend().query(query)
        except Exception:
            logger.exception(
                "AWS Athena query failed; local data was not substituted."
            )
            raise

        return _normalise_records(df) if as_dict else df

    if config.USE_GCP:
        if bigquery is None:
            raise RuntimeError(
                "BigQuery is enabled but google-cloud-bigquery "
                "is not installed."
            )

        try:
            client = bigquery.Client(
                project=config.GCP_PROJECT_ID
            )

            project = config.GCP_PROJECT_ID
            dataset = config.GCP_BQ_DATASET

            table_names = [
                "retention_metrics",
                "funnel_metrics",
                "user_segments",
                "churn_metrics",
                "cohort_metrics",
                "ltv_metrics",
                "events",
            ]

            bq_query = query

            for table in table_names:
                bq_query = bq_query.replace(
                    f"FROM {table}",
                    f"FROM `{project}.{dataset}.{table}`",
                )

            df = client.query(bq_query).to_dataframe()

        except Exception:
            logger.exception("GCP BigQuery query failed.")
            raise

        return _normalise_records(df) if as_dict else df

    # Local backend is used only when local mode is explicitly configured.
    df = get_backend().query(query)
    return _normalise_records(df) if as_dict else df


def _remember_analytics_error(data_errors, label, exc):
    """Record failed analytics queries for cloud-mode error reporting."""
    message = f"{label}: {exc}"
    logger.error("%s", message)

    if config.EXECUTION_MODE == "aws" or config.USE_GCP:
        data_errors.append(message)


def _first_row(df):
    """Return the first DataFrame row as a normalized dictionary."""
    if df is None or df.empty:
        return {}

    records = _normalise_records(df.head(1))
    return records[0] if records else {}


# ---------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------

@app.route("/health")
def health():
    """Liveness endpoint; does not contact external services."""
    return jsonify({
        "status": "ok",
        "execution_mode": config.EXECUTION_MODE,
        "local_backend": config.LOCAL_BACKEND,
        "aws_enabled": config.AWS_ENABLED,
        "use_gcp": config.USE_GCP,
    }), 200


@app.route("/ready")
def ready():
    """
    Application configuration check.

    This endpoint does not independently verify live Athena connectivity.
    """
    return jsonify({
        "status": "ok",
        "execution_mode": config.EXECUTION_MODE,
        "message": "Dashboard application is running.",
        "note": (
            "Live analytics connectivity is checked by dashboard queries."
        ),
    }), 200


# ---------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------

@app.route("/")
def index():
    """Load dashboard metrics from the configured analytics backend."""
    logger.info("Handling dashboard index request.")

    data_errors = []

    stats = {
        "total_users": 0,
        "total_revenue": 0.0,
        "total_events": 0,
    }

    top_customers = []
    funnel_data = []
    segment_data = []
    cohort_data = []

    retention_metrics = {
        "total_users": 0,
        "retained_users": 0,
        "retention_rate": 0.0,
    }

    churn_metrics = {
        "at_risk_count": 0,
        "total_evaluated": 0,
        "churn_rate": 0.0,
    }

    # Global statistics. Exclude malformed events with missing IDs,
    # event types, or timestamps. Revenue is summed over the same
    # valid-event population for consistency.
    try:
        stats_query = """
            SELECT
                COUNT(DISTINCT user_id) AS total_users,
                COALESCE(ROUND(SUM(amount), 2), 0) AS total_revenue,
                COUNT(*) AS total_events
            FROM events
            WHERE user_id IS NOT NULL
              AND TRIM(user_id) <> ''
              AND event_type IS NOT NULL
              AND timestamp IS NOT NULL
        """

        stats_row = _first_row(
            fetch_table(stats_query, as_dict=False)
        )

        if stats_row:
            stats["total_users"] = _safe_int(
                stats_row.get("total_users")
            )
            stats["total_revenue"] = _safe_number(
                stats_row.get("total_revenue")
            )
            stats["total_events"] = _safe_int(
                stats_row.get("total_events")
            )

    except Exception as exc:
        _remember_analytics_error(data_errors, "Global stats", exc)

    # Top customers / lifetime value.
    try:
        top_query = """
            SELECT user_id, total_ltv
            FROM ltv_metrics
            WHERE user_id IS NOT NULL
            ORDER BY total_ltv DESC
            LIMIT 5
        """
        top_customers = fetch_table(top_query)

    except Exception as exc:
        _remember_analytics_error(data_errors, "LTV metrics", exc)

    # Funnel metrics.
    try:
        funnel_query = """
            SELECT stage, user_count
            FROM funnel_metrics
        """
        funnel_data = fetch_table(funnel_query)

    except Exception as exc:
        _remember_analytics_error(data_errors, "Funnel metrics", exc)

    # Customer segments.
    try:
        segments_query = """
            SELECT
                segment_label AS label,
                COUNT(user_id) AS count
            FROM user_segments
            WHERE user_id IS NOT NULL
            GROUP BY segment_label
        """
        segment_data = fetch_table(segments_query)

    except Exception as exc:
        _remember_analytics_error(data_errors, "Segments", exc)

    # Cohort metrics.
    try:
        cohort_query = """
            SELECT cohort_day, user_count
            FROM cohort_metrics
            ORDER BY cohort_day ASC
        """
        cohort_data = fetch_table(cohort_query)

    except Exception as exc:
        _remember_analytics_error(data_errors, "Cohorts", exc)

    # Retention metrics.
    try:
        retention_query = """
            SELECT total_users, retained_users, retention_rate
            FROM retention_metrics
        """

        retention_row = _first_row(
            fetch_table(retention_query, as_dict=False)
        )

        if retention_row:
            retention_metrics = {
                "total_users": _safe_int(
                    retention_row.get("total_users")
                ),
                "retained_users": _safe_int(
                    retention_row.get("retained_users")
                ),
                "retention_rate": _safe_number(
                    retention_row.get("retention_rate")
                ),
            }

    except Exception as exc:
        _remember_analytics_error(
            data_errors, "Retention metrics", exc
        )

    # Churn metrics.
    try:
        churn_query = """
            SELECT
                COALESCE(SUM(is_at_risk), 0) AS at_risk_count,
                COUNT(*) AS total_evaluated
            FROM churn_metrics
            WHERE user_id IS NOT NULL
        """

        churn_row = _first_row(
            fetch_table(churn_query, as_dict=False)
        )

        if churn_row:
            at_risk_count = _safe_int(
                churn_row.get("at_risk_count")
            )
            total_evaluated = _safe_int(
                churn_row.get("total_evaluated")
            )

            churn_metrics = {
                "at_risk_count": at_risk_count,
                "total_evaluated": total_evaluated,
                "churn_rate": _safe_rate(
                    at_risk_count,
                    total_evaluated,
                ),
            }

    except Exception as exc:
        _remember_analytics_error(
            data_errors, "Churn metrics", exc
        )

    # In cloud mode, do not present partial analytics as successful.
    if data_errors and (
        config.EXECUTION_MODE == "aws" or config.USE_GCP
    ):
        return jsonify({
            "status": "error",
            "execution_mode": (
                "aws" if config.EXECUTION_MODE == "aws" else "gcp"
            ),
            "message": (
                "One or more analytics queries failed. "
                "Local data was not substituted."
            ),
            "errors": data_errors,
        }), 503

    platform_env, ingestion_label = platform_context()

    return render_template(
        "index.html",
        stats=stats,
        top_customers=top_customers,
        funnel_data=funnel_data,
        segment_data=segment_data,
        cohort_data=cohort_data,
        retention_metrics=retention_metrics,
        churn_metrics=churn_metrics,
        platform_env=platform_env,
        ingestion_label=ingestion_label,
        data_errors=data_errors,
    )


# ---------------------------------------------------------------------
# Application entry point
# ---------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("Starting Flask Customer 360 dashboard.")

    debug = (
        os.getenv("FLASK_DEBUG", "false").strip().lower()
        in {"1", "true", "yes", "on"}
    )

    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))

    app.run(host=host, port=port, debug=debug)
