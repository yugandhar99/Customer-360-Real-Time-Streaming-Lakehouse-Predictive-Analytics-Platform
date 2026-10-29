
"""Group customers by the date of their earliest valid recorded event."""

import os
import sys

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pandas as pd

from transformations.base_transformer import BaseAnalyticsModule


class CohortAnalysisJob(BaseAnalyticsModule):
    """Calculate daily customer cohorts from the configured backend."""

    def __init__(self):
        super().__init__(module_name="Cohort_Analysis")

    def run_analysis(self) -> None:
        self.logger.info("Starting time-series cohort analysis.")

        query = """
            SELECT
                TRIM(user_id) AS user_id,
                MIN(timestamp) AS signup_date
            FROM events
            WHERE user_id IS NOT NULL
              AND TRIM(user_id) <> ''
              AND timestamp IS NOT NULL
            GROUP BY TRIM(user_id)
        """

        try:
            df = self.execute_query(query)

            if df.empty:
                self.logger.warning(
                    "No valid event data is available for cohort analysis. "
                    "Existing metrics were not changed."
                )
                return

            required_columns = {"user_id", "signup_date"}
            missing_columns = required_columns.difference(df.columns)

            if missing_columns:
                raise ValueError(
                    "Cohort query is missing columns: "
                    + ", ".join(sorted(missing_columns))
                )

            df = df.copy()
            df["user_id"] = df["user_id"].astype("string").str.strip()

            # Support ISO-8601 timestamps, fractional seconds,
            # timezone suffixes, and SQL timestamp strings.
            df["signup_date"] = pd.to_datetime(
                df["signup_date"],
                format="mixed",
                errors="coerce",
                utc=True,
            )

            invalid_ids = df["user_id"].isna() | (df["user_id"] == "")
            invalid_dates = df["signup_date"].isna()

            if invalid_ids.any():
                self.logger.warning(
                    "Skipping %s rows with invalid customer IDs.",
                    int(invalid_ids.sum()),
                )

            if invalid_dates.any():
                self.logger.warning(
                    "Skipping %s rows with invalid timestamps.",
                    int(invalid_dates.sum()),
                )

            df = df.loc[
                ~(invalid_ids | invalid_dates)
            ].copy()

            # A customer should appear in only one cohort.
            df = df.drop_duplicates(
                subset=["user_id"],
                keep="first",
            )

            if df.empty:
                self.logger.warning(
                    "No valid customer timestamps remain. "
                    "Existing metrics were not changed."
                )
                return

            # Cohort dates are derived in UTC for consistent grouping.
            df["cohort_day"] = df["signup_date"].dt.strftime("%Y-%m-%d")

            cohort_summary = (
                df.groupby("cohort_day", as_index=False)
                .agg(user_count=("user_id", "nunique"))
                .sort_values("cohort_day")
                .reset_index(drop=True)
            )

            self.logger.info(
                "Identified %s daily cohorts containing %s customers.",
                len(cohort_summary),
                int(cohort_summary["user_count"].sum()),
            )

            self.save_metric_table(
                cohort_summary,
                "cohort_metrics",
            )

            self.logger.info(
                "Cohort analysis completed successfully. Rows saved: %s",
                len(cohort_summary),
            )

        except Exception:
            self.logger.exception("Cohort analysis failed.")
            raise


if __name__ == "__main__":
    CohortAnalysisJob().run_analysis()
