import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _first_env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value.strip()
    return default


def _is_unresolved(value: str) -> bool:
    """True when a setting is empty or still a documentation placeholder."""
    if value is None:
        return True
    text = value.strip()
    if not text:
        return True
    return "__SET_AFTER_AWS_ACCESS__" in text


class AWSConfigurationError(RuntimeError):
    """AWS mode was selected without the settings required to run it.

    Callers must not substitute SQLite or an empty result for this error.
    """


@dataclass
class PlatformConfig:
    """
    Centralized configuration for the Customer 360 Platform.
    Environment configuration for local, legacy GCP, and AWS execution.
    """

    BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
    LOGS_DIR: str = os.path.join(BASE_DIR, "logs")
    STORAGE_DIR: str = os.getenv(
        "STORAGE_DIR",
        os.path.join("C:\\", "Customer360", "storage") if os.name == "nt" else os.path.join(BASE_DIR, "storage"),
    )
    CSV_EVENTS_PATH: str = os.path.join(LOGS_DIR, "raw_events.csv")
    SQLITE_DB_PATH: str = os.getenv("SQLITE_DB_PATH", os.path.join(STORAGE_DIR, "customer_360.db"))

    # Local execution is the safe default. EXECUTION_MODE=gcp keeps the legacy
    # path available. EXECUTION_MODE=aws selects Athena and does not fall back.
    EXECUTION_MODE: str = os.getenv("EXECUTION_MODE", "local").strip().lower()
    LOCAL_BACKEND: str = os.getenv("LOCAL_BACKEND", "sqlite").strip().lower()
    AWS_ENABLED: bool = _env_bool("AWS_ENABLED", False)
    USE_GCP: bool = _env_bool("USE_GCP", False)

    # Non-secret AWS identifiers. Credentials come from the environment, AWS_PROFILE, or an IAM role.
    # Account ID is not a secret; it only documents the target account for preflight checks.
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1").strip()
    AWS_ACCOUNT_ID: str = os.getenv("AWS_ACCOUNT_ID", "783764597826").strip()
    AWS_PROFILE: str = os.getenv("AWS_PROFILE", "").strip()
    AWS_S3_BUCKET: str = os.getenv("AWS_S3_BUCKET", "").strip()
    AWS_FIREHOSE_DELIVERY_STREAM: str = _first_env(
        "AWS_FIREHOSE_DELIVERY_STREAM", "AWS_FIREHOSE_STREAM"
    )
    AWS_GLUE_DATABASE: str = _first_env(
        "AWS_GLUE_DATABASE", "AWS_ATHENA_DATABASE", default="customer_360"
    )
    AWS_ATHENA_DATABASE: str = _first_env(
        "AWS_ATHENA_DATABASE", "AWS_GLUE_DATABASE", default="customer_360"
    )
    ATHENA_WORKGROUP: str = os.getenv("ATHENA_WORKGROUP", "").strip()
    ATHENA_RESULTS_S3_URI: str = _first_env(
        "ATHENA_RESULTS_S3_URI", "AWS_ATHENA_QUERY_RESULTS_LOCATION"
    )
    AWS_ATHENA_QUERY_RESULTS_LOCATION: str = _first_env(
        "AWS_ATHENA_QUERY_RESULTS_LOCATION", "ATHENA_RESULTS_S3_URI"
    )

    # GCP Configurations. Retained for the legacy path; not used unless EXECUTION_MODE=gcp.
    GCP_PROJECT_ID: str = "customer-360-492614"
    GCP_PUBSUB_TOPIC: str = "customer-events"
    GCP_PUBSUB_SUB: str = "customer-events-sub"
    GCP_BQ_DATASET: str = "customer_360"

    # Event Generation Settings
    NUM_USERS: int = 500
    EVENT_TYPES: tuple = ("login", "product_view", "add_to_cart", "purchase")
    SIMULATION_WAIT_MIN_SEC: float = 0.5
    SIMULATION_WAIT_MAX_SEC: float = 2.0

    # ML Model Settings
    # CHURN_RULE=heuristic is the historical dashboard contract.
    # CHURN_RULE=inactivity applies CHURN_INACTIVITY_THRESHOLD_DAYS.
    KMEANS_CLUSTERS: int = 3
    CHURN_RULE: str = os.getenv("CHURN_RULE", "heuristic").strip().lower()
    CHURN_INACTIVITY_THRESHOLD_DAYS: int = int(os.getenv("CHURN_INACTIVITY_THRESHOLD_DAYS", "30"))

    def __post_init__(self):
        """Ensure directories exist upon initialization."""
        os.makedirs(self.LOGS_DIR, exist_ok=True)
        os.makedirs(self.STORAGE_DIR, exist_ok=True)

        valid_modes = {"local", "gcp", "aws"}
        if self.EXECUTION_MODE not in valid_modes:
            raise ValueError(f"EXECUTION_MODE must be one of {sorted(valid_modes)}")
        if self.LOCAL_BACKEND != "sqlite":
            raise ValueError("Only LOCAL_BACKEND=sqlite is currently implemented")
        if self.CHURN_RULE not in {"heuristic", "inactivity"}:
            raise ValueError("CHURN_RULE must be heuristic or inactivity")
        if self.CHURN_INACTIVITY_THRESHOLD_DAYS < 0:
            raise ValueError("CHURN_INACTIVITY_THRESHOLD_DAYS must be zero or greater")

        self.AWS_GLUE_DATABASE = self.AWS_GLUE_DATABASE or "customer_360"
        self.AWS_ATHENA_DATABASE = self.AWS_GLUE_DATABASE
        self.AWS_ATHENA_QUERY_RESULTS_LOCATION = self.ATHENA_RESULTS_S3_URI
        self.AWS_FIREHOSE_STREAM = self.AWS_FIREHOSE_DELIVERY_STREAM

        if self.EXECUTION_MODE == "gcp":
            self.USE_GCP = True
        elif self.EXECUTION_MODE == "aws":
            self.USE_GCP = False
            self.AWS_ENABLED = True
            self.validate_aws_analytics()

    def missing_aws_analytics_settings(self) -> list:
        missing = []
        if _is_unresolved(self.AWS_REGION):
            missing.append("AWS_REGION")
        if _is_unresolved(self.AWS_S3_BUCKET):
            missing.append("AWS_S3_BUCKET")
        if _is_unresolved(self.AWS_GLUE_DATABASE):
            missing.append("AWS_GLUE_DATABASE")
        if _is_unresolved(self.ATHENA_WORKGROUP):
            missing.append("ATHENA_WORKGROUP")
        if _is_unresolved(self.ATHENA_RESULTS_S3_URI):
            missing.append("ATHENA_RESULTS_S3_URI")
        elif not self.ATHENA_RESULTS_S3_URI.startswith("s3://"):
            missing.append("ATHENA_RESULTS_S3_URI (must start with s3://)")
        return missing

    def validate_aws_analytics(self) -> None:
        missing = self.missing_aws_analytics_settings()
        if missing:
            raise AWSConfigurationError(
                "AWS execution requires configuration that is not set: "
                + ", ".join(missing)
                + ". Replace __SET_AFTER_AWS_ACCESS__ placeholders with Terraform outputs. "
                "Refusing to fall back to SQLite."
            )

    def validate_firehose(self) -> None:
        missing = []
        if _is_unresolved(self.AWS_REGION):
            missing.append("AWS_REGION")
        if _is_unresolved(self.AWS_FIREHOSE_DELIVERY_STREAM):
            missing.append("AWS_FIREHOSE_STREAM")
        if missing:
            raise AWSConfigurationError(
                "Firehose publishing requires configuration that is not set: "
                + ", ".join(missing)
                + ". Local CSV ingestion remains available with EXECUTION_MODE=local."
            )


config = PlatformConfig()
