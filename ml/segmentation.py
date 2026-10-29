
"""
Customer Segmentation Model.

Clusters customers using event frequency and monetary value.
Supports the configured analytics backend, including AWS Athena/S3.
"""

import os
import sys

import joblib
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from config import config
from transformations.base_transformer import BaseAnalyticsModule


class ModelLoadError(RuntimeError):
    """Raised when saved segmentation artifacts cannot be loaded."""


class CustomerSegmentationModel(BaseAnalyticsModule):
    """Train a KMeans model and persist customer segmentation results."""

    def __init__(self):
        super().__init__(module_name="SegmentationModel")

        self.n_clusters = config.KMEANS_CLUSTERS
        self.scaler = StandardScaler()
        self.model = KMeans(
            n_clusters=self.n_clusters,
            random_state=42,
            n_init=10,
        )

        self.model_save_path = os.path.join(
            config.STORAGE_DIR,
            "segmentation_kmeans.pkl",
        )
        self.bundle_save_path = os.path.join(
            config.STORAGE_DIR,
            "segmentation_bundle.joblib",
        )

        os.makedirs(config.STORAGE_DIR, exist_ok=True)

    def fetch_training_data(self) -> pd.DataFrame:
        """Fetch valid customer features from the configured backend."""
        query = """
            SELECT
                TRIM(user_id) AS user_id,
                COUNT(timestamp) AS frequency,
                COALESCE(SUM(amount), 0) AS monetary
            FROM events
            WHERE user_id IS NOT NULL
              AND TRIM(user_id) <> ''
            GROUP BY TRIM(user_id)
        """

        df = self.execute_query(query)

        if df.empty:
            self.logger.warning("No customer records were found.")
            return df

        required_columns = {"user_id", "frequency", "monetary"}
        missing_columns = required_columns.difference(df.columns)

        if missing_columns:
            raise ValueError(
                "Segmentation query is missing columns: "
                + ", ".join(sorted(missing_columns))
            )

        df = df.copy()

        df["user_id"] = df["user_id"].astype("string").str.strip()
        df["frequency"] = pd.to_numeric(
            df["frequency"], errors="coerce"
        )
        df["monetary"] = pd.to_numeric(
            df["monetary"], errors="coerce"
        )

        # Remove invalid identifiers and incomplete feature records.
        df = df.dropna(
            subset=["user_id", "frequency", "monetary"]
        )
        df = df[df["user_id"] != ""]
        df = df[
            df["frequency"].ge(0)
            & df["monetary"].ge(0)
        ]

        # Avoid producing multiple records for one customer.
        df = df.drop_duplicates(subset=["user_id"], keep="last")
        df = df.reset_index(drop=True)

        self.logger.info(
            "Loaded %s valid customer records for segmentation.",
            len(df),
        )

        return df

    def load_persisted(self) -> str:
        """Load the saved model and scaler, or raise a clear error."""
        try:
            if os.path.isfile(self.bundle_save_path):
                bundle = joblib.load(self.bundle_save_path)

                if (
                    not isinstance(bundle, dict)
                    or "model" not in bundle
                    or "scaler" not in bundle
                ):
                    raise ModelLoadError(
                        "The saved segmentation bundle is missing "
                        "the model or scaler."
                    )

                self.model = bundle["model"]
                self.scaler = bundle["scaler"]
                return "bundle"

            if os.path.isfile(self.model_save_path):
                self.model = joblib.load(self.model_save_path)
                return "legacy_model"

        except ModelLoadError:
            raise
        except Exception as exc:
            raise ModelLoadError(
                f"Could not load segmentation artifacts: {exc}"
            ) from exc

        raise ModelLoadError(
            "No saved segmentation model is available."
        )

    def train_and_predict(self) -> None:
        """Train KMeans, label clusters, and persist the results."""
        self.logger.info("Starting customer segmentation.")

        df = self.fetch_training_data()

        if df.empty:
            self.logger.error(
                "Segmentation stopped: no valid customers were found."
            )
            return

        if len(df) < self.n_clusters:
            self.logger.error(
                "Segmentation needs at least %s customers; found %s.",
                self.n_clusters,
                len(df),
            )
            return

        features = df[["frequency", "monetary"]].copy()

        # Reject non-finite values rather than passing them into KMeans.
        import numpy as np

        if not np.isfinite(features.to_numpy(dtype=float)).all():
            self.logger.error(
                "Segmentation stopped: features contain non-finite values."
            )
            return

        try:
            scaled_features = self.scaler.fit_transform(features)

            df["segment_id"] = self.model.fit_predict(
                scaled_features
            )

            # Give clusters stable business labels based on their
            # average monetary value, from lowest to highest.
            monetary_means = (
                df.groupby("segment_id")["monetary"]
                .mean()
                .sort_values()
            )

            cluster_ids = monetary_means.index.tolist()

            if len(cluster_ids) == 3:
                labels = {
                    cluster_ids[0]: "Low Value",
                    cluster_ids[1]: "Medium Value",
                    cluster_ids[2]: "High Value",
                }
            else:
                labels = {
                    cluster_id: f"Segment {rank + 1}"
                    for rank, cluster_id in enumerate(cluster_ids)
                }

            df["segment_label"] = df["segment_id"].map(labels)

            # Validate the final output before writing it.
            if df["user_id"].isna().any():
                raise ValueError(
                    "Final segmentation output contains missing user IDs."
                )

            if df["user_id"].duplicated().any():
                raise ValueError(
                    "Final segmentation output contains duplicate user IDs."
                )

            if df[
                ["frequency", "monetary", "segment_id"]
            ].isna().any().any():
                raise ValueError(
                    "Final segmentation output contains missing feature values."
                )

            output_columns = [
                "user_id",
                "frequency",
                "monetary",
                "segment_id",
                "segment_label",
            ]
            output_df = df[output_columns].copy()

            # Uses the configured backend. In AWS mode this writes
            # the metric output to the configured S3 location.
            self.save_metric_table(output_df, "user_segments")

            # Preserve the existing local model artifact formats.
            joblib.dump(self.model, self.model_save_path)
            joblib.dump(
                {
                    "model": self.model,
                    "scaler": self.scaler,
                    "version": 1,
                },
                self.bundle_save_path,
            )

            self.logger.info(
                "Segmentation completed successfully. "
                "Customers saved: %s; clusters: %s.",
                len(output_df),
                len(cluster_ids),
            )

        except Exception:
            self.logger.exception("Customer segmentation failed.")
            raise


if __name__ == "__main__":
    CustomerSegmentationModel().train_and_predict()
