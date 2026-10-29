import pandas as pd
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import config
from transformations.base_transformer import BaseAnalyticsModule

class FunnelAnalysisJob(BaseAnalyticsModule):
    """
    Computes strict conversion drop-off tracking across key lifecycle events.
    """
    def __init__(self):
        super().__init__(module_name="Funnel_Analysis")
        # Define accurate lifecycle step map
        self.stages = config.EVENT_TYPES
        
    def run_analysis(self):
        self.logger.info("Initiating Multi-Stage Conversion Funnel Tracking...")
        
        funnel_data = []
        try:
            for stage in self.stages:
                query = f"SELECT COUNT(DISTINCT user_id) as user_count FROM events WHERE event_type='{stage}'"
                
                result_df = self.execute_query(query)
                if not result_df.empty:
                    count = int(result_df.iloc[0]['user_count'])
                    funnel_data.append({
                        'stage': stage,
                        'user_count': count
                    })
                    
            df_funnel = pd.DataFrame(funnel_data)
            self.logger.info(f"Funnel mapped across {len(self.stages)} workflow stages.")
            
            self.save_metric_table(df_funnel, 'funnel_metrics')
            
        except Exception as e:
            self.logger.error(f"Error mapping funnel conversion boundaries: {e}")

if __name__ == "__main__":
    job = FunnelAnalysisJob()
    job.run_analysis()
