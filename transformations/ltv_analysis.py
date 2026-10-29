
"""Calculate customer lifetime value from events in the configured backend."""

import os
import sys

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from transformations.base_transformer import BaseAnalyticsModule


class LTVAnalysisJob(BaseAnalyticsModule):
    """Calculate lifetime spending and event counts for purchasing customers."""

    def __init__(self):
        super().__init__(module_name="LTV_Analysis")

    def run_analysis(self) -> None:
        self.logger.info("Initiating LTV Analysis Calculation...")

        query = """
            SELECT
                user_id,
                SUM(amount) AS total_ltv,
                COUNT(user_id) AS event_count
            FROM events
            WHERE user_id IS NOT NULL
            GROUP BY user_id
            HAVING SUM(amount) > 0
            ORDER BY SUM(amount) DESC
        """

        try:
            df = self.execute_query(query)

            if df.empty:
                self.logger.warning(
                    "No purchasing customers found. "
                    "LTV metrics were not updated."
                )
                return

            required_columns = {
                "user_id",
                "total_ltv",
                "event_count",
            }
            missing_columns = required_columns.difference(df.columns)

            if missing_columns:
                raise ValueError(
                    "LTV query returned missing columns: "
                    + ", ".join(sorted(missing_columns))
                )

            self.logger.info(
                "Calculated LTV for %s purchasing customers.",
                len(df),
            )

            # In AWS mode, the configured Athena backend writes the
            # DataFrame to the existing S3 metric-table location.
            self.save_metric_table(df, "ltv_metrics")

            self.logger.info(
                "LTV analysis completed. Rows saved: %s",
                len(df),
            )

        except Exception:
            self.logger.exception("LTV analysis failed.")
            raise


if __name__ == "__main__":
    job = LTVAnalysisJob()
    job.run_analysis()
