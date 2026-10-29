
"""
Calculate customer engagement and retention metrics
using the configured analytics backend.
"""

import os
import sys

import pandas as pd

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from transformations.base_transformer import BaseAnalyticsModule


class RetentionAnalysisJob(BaseAnalyticsModule):
    """Calculate retention based on meaningful event activity."""

    def __init__(self):
        super().__init__(module_name="Retention_Analysis")
        self.retention_event_threshold = 3

    def run_analysis(self) -> None:
        self.logger.info(
            "Starting engagement and retention calculation."
        )

        query = """
            SELECT
                TRIM(user_id) AS user_id,
                COUNT(DISTINCT event_type) AS unique_actions,
                COUNT(timestamp) AS total_interactions
            FROM events
            WHERE user_id IS NOT NULL
              AND TRIM(user_id) <> ''
            GROUP BY TRIM(user_id)
        """

        try:
            df = self.execute_query(query)

            if df.empty:
                self.logger.warning(
                    "No valid customer records found. "
                    "Retention metrics were not updated."
                )
                return

            required_columns = {
                "user_id",
                "unique_actions",
                "total_interactions",
            }
            missing_columns = required_columns.difference(df.columns)

            if missing_columns:
                raise ValueError(
                    "Retention query is missing columns: "
                    + ", ".join(sorted(missing_columns))
                )

            df = df.copy()
            df["user_id"] = df["user_id"].astype("string").str.strip()
            df["unique_actions"] = pd.to_numeric(
                df["unique_actions"], errors="coerce"
            )
            df["total_interactions"] = pd.to_numeric(
                df["total_interactions"], errors="coerce"
            )

            # Exclude invalid IDs and incomplete interaction counts.
            df = df.dropna(
                subset=["user_id", "total_interactions"]
            )
            df = df[df["user_id"] != ""]
            df = df[df["total_interactions"] >= 0]

            # Each customer must contribute only once.
            df = df.drop_duplicates(
                subset=["user_id"], keep="last"
            )

            total_users = int(df["user_id"].nunique())

            # Preserve the existing definition: more than 3 events.
            retained_df = df[
                df["total_interactions"]
                > self.retention_event_threshold
            ]
            retained_users = int(
                retained_df["user_id"].nunique()
            )

            retention_rate = (
                round((retained_users / total_users) * 100, 2)
                if total_users > 0
                else 0.0
            )

            self.logger.info(
                "Retention calculation completed: "
                "total_users=%s, retained_users=%s, "
                "retention_rate=%s%%",
                total_users,
                retained_users,
                retention_rate,
            )

            retention_df = pd.DataFrame(
                [
                    {
                        "total_users": total_users,
                        "retained_users": retained_users,
                        "retention_rate": retention_rate,
                    }
                ]
            )

            self.save_metric_table(
                retention_df,
                "retention_metrics",
            )

            self.logger.info(
                "Retention metrics saved successfully."
            )

        except Exception:
            self.logger.exception(
                "Retention analysis failed."
            )
            raise


if __name__ == "__main__":
    RetentionAnalysisJob().run_analysis()
