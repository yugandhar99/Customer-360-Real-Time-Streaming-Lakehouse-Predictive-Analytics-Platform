import pandas as pd
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import config
from transformations.base_transformer import BaseAnalyticsModule

class ChurnPredictionModel(BaseAnalyticsModule):
    """
    Churn calculation used by the dashboard.

    The default rule is the historical heuristic: event_count <= 2 and
    purchase_count == 0. Set CHURN_RULE=inactivity to mark a user at risk when
    the gap between that user's last event and the latest event in the dataset
    is greater than CHURN_INACTIVITY_THRESHOLD_DAYS. The reference point is the
    dataset, not the wall clock, so the result does not change just because the
    job runs on a later day.
    """
    def __init__(self):
        super().__init__(module_name="ChurnModel")
        
    def fetch_transaction_behavior(self) -> pd.DataFrame:
        last_seen = ", MAX(timestamp) as last_seen" if config.CHURN_RULE == "inactivity" else ""
        query = f"""
        SELECT user_id, 
               COUNT(timestamp) as event_count,
               SUM(CASE WHEN event_type='purchase' THEN 1 ELSE 0 END) as purchase_count
               {last_seen}
        FROM events
        GROUP BY user_id
        """
        return self.execute_query(query)

    def apply_risk(self, frame: pd.DataFrame) -> pd.DataFrame:
        scored = frame.copy()
        if config.CHURN_RULE == "inactivity":
            last_seen = pd.to_datetime(scored["last_seen"])
            reference = last_seen.max()
            inactive_days = (reference - last_seen).dt.days.fillna(0)
            scored["is_at_risk"] = (inactive_days > config.CHURN_INACTIVITY_THRESHOLD_DAYS).astype(int)
            return scored
        scored["is_at_risk"] = (
            (scored["event_count"] <= 2) & (scored["purchase_count"] == 0)
        ).astype(int)
        return scored

    def run_prediction(self) -> None:
        self.logger.info("Executing Churn Detection Pipeline...")
        df = self.fetch_transaction_behavior()
        
        if df.empty:
            self.logger.warning("Empty dataset. Skipping churn.")
            return

        try:
            df = self.apply_risk(df)
            at_risk_count = int(df["is_at_risk"].sum())
            self.logger.info(f"Detected {at_risk_count} at-risk users.")
            
            # Push predictions to operational store natively via base function
            self.save_metric_table(df, 'churn_metrics')
            self.logger.info("Churn pipeline completed context injection.")
        except Exception as e:
            self.logger.error(f"Pipeline error: {e}")

if __name__ == "__main__":
    model = ChurnPredictionModel()
    model.run_prediction()
