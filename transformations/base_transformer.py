import pandas as pd
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import config
from storage.backend import get_backend
from utils.logger import get_logger

try:
    import pandas_gbq
except ImportError:
    pass

class BaseAnalyticsModule:
    """
    Abstract Base Class for all Analytics Jobs.
    Enforces pattern of secure DB connection mapping. 
    Now features Hybrid Execution: Supports both Local SQLite & GCP BigQuery based on config.
    """
    def __init__(self, module_name: str):
        self.logger = get_logger(module_name)
        self.db_path = config.SQLITE_DB_PATH
        self.use_gcp = config.USE_GCP
        self.backend = None if self.use_gcp else get_backend()
        
    def _validate_local_db_exists(self) -> bool:
        if not os.path.exists(self.db_path):
            self.logger.error("Core SQLite Database missing.")
            return False
        return True
        
    def execute_query(self, query: str) -> pd.DataFrame:
        """Executes a Select query against the active datastore and returns a DataFrame"""
        if self.use_gcp:
            # BigQuery Path
            try:
                # Add full project qualifier for table access in typical raw queries
                bq_query = query.replace('FROM events', f'FROM `{config.GCP_PROJECT_ID}.{config.GCP_BQ_DATASET}.events`')
                return pandas_gbq.read_gbq(bq_query, project_id=config.GCP_PROJECT_ID)
            except Exception as e:
                self.logger.error(f"GCP BigQuery Read Failure: {e}")
                return pd.DataFrame()
        else:
            try:
                return self.backend.query(query)
            except Exception as e:
                from storage.athena_backend import AthenaBackend

                if isinstance(self.backend, AthenaBackend):
                    self.logger.error(f"AWS analytics query failed: {e}")
                    raise
                self.logger.error(f"Local SQL Read Failure: {e}")
                return pd.DataFrame()
            
    def save_metric_table(self, df: pd.DataFrame, table_name: str) -> None:
        """Saves calculated metrics securely back into storage."""
        if df.empty:
            self.logger.warning(f"Dataframe is empty. Skipping save for {table_name}")
            return
            
        if self.use_gcp:
            # Write to BigQuery Table Destination
            destination_table = f"{config.GCP_BQ_DATASET}.{table_name}"
            try:
                pandas_gbq.to_gbq(df, destination_table, project_id=config.GCP_PROJECT_ID, if_exists='replace')
                self.logger.info(f"Target metric table '{destination_table}' synced to GCP BigQuery.")
            except Exception as e:
                self.logger.error(f"Failed to push metrics to BQ: {e}")
                raise
        else:
            try:
                self.backend.save_metric_table(df, table_name)
                self.logger.info(f"Target metric table '{table_name}' refreshed successfully locally.")
            except Exception as e:
                self.logger.error(f"Failed to save metrics locally: {e}")
                raise
            
    def run_analysis(self) -> None:
        raise NotImplementedError("run_analysis must be implemented by subclasses.")
