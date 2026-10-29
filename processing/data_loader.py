import pandas as pd
import sqlite3
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import config
from utils.logger import get_logger

logger = get_logger("DataLoader")

class DataLoader:
    """
    Handles extracting raw CSV event logs and securely loading them 
    into the robust SQLite storage layer.
    """
    
    def __init__(self):
        self.csv_path = config.CSV_EVENTS_PATH
        self.db_path = config.SQLITE_DB_PATH
        
    def _create_schema(self, conn: sqlite3.Connection):
        """Initializes exact SQL schema to ensure strict typing over loose Pandas inferred DDL."""
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                user_id TEXT,
                event_type TEXT,
                amount REAL,
                timestamp DATETIME
            )
        """)
        # Create indexes for high performance analytics querying
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_id ON events (user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_event_type ON events (event_type);")
        conn.commit()

    def run_pipeline(self) -> None:
        """Executes the ETL job to migrate CSV log data into SQL tables."""
        if not os.path.exists(self.csv_path):
            logger.error(f"ETL Failure: CSV Source not found at {self.csv_path}")
            return
            
        try:
            logger.info("Starting Data Loading Pipeline...")
            
            # 1. Extract
            chunk_size = 10000
            for chunk in pd.read_csv(self.csv_path, chunksize=chunk_size):
                
                # 2. Transform/Clean (Basic deduplication/casting in production)
                chunk['timestamp'] = pd.to_datetime(chunk['timestamp'])
                
                # 3. Load. Close explicitly so Windows releases the database file.
                conn = sqlite3.connect(self.db_path)
                try:
                    self._create_schema(conn)
                    chunk.to_sql('events', conn, if_exists='append', index=False)
                    conn.commit()
                    logger.info(f"Loaded batch of {len(chunk)} rows into database.")
                finally:
                    conn.close()
                    
            # Truncate/backup CSV log after successful load to simulate rotation
            # Open file in 'w' to clear it, but keep headers
            with open(self.csv_path, 'w', encoding='utf-8') as f:
                f.write("user_id,event_type,amount,timestamp\n")
            logger.info("Pipeline successful. Cleared staging CSV log.")
            
        except sqlite3.DatabaseError as db_err:
            logger.error(f"Database Integrity Error: {db_err}")
            raise
        except Exception as e:
            logger.error(f"Unexpected ETL Error: {e}")
            raise

if __name__ == "__main__":
    loader = DataLoader()
    loader.run_pipeline()
