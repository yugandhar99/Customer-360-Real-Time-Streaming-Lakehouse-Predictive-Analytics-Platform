import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import config
from utils.logger import get_logger

logger = get_logger("BQ_Setup")

try:
    from google.cloud import bigquery
except ImportError:
    pass

def init_bigquery():
    """Idempotently sets up the BigQuery Dataset and primary Events table schema."""
    if not config.USE_GCP:
        logger.info("USE_GCP=False. Skipping BigQuery setup.")
        return

    client = bigquery.Client(project=config.GCP_PROJECT_ID)
    
    # Create Dataset
    dataset_id = f"{config.GCP_PROJECT_ID}.{config.GCP_BQ_DATASET}"
    dataset = bigquery.Dataset(dataset_id)
    dataset.location = "US"
    dataset = client.create_dataset(dataset, exists_ok=True)
    logger.info(f"✅ Verified BigQuery Dataset: {dataset.dataset_id}")

    # Create Events Table DDL
    table_id = f"{dataset_id}.events"
    schema = [
        bigquery.SchemaField("user_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("event_type", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("amount", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
    ]
    table = bigquery.Table(table_id, schema=schema)
    table.time_partitioning = bigquery.TimePartitioning(type_=bigquery.TimePartitioningType.DAY, field="timestamp")
    
    table = client.create_table(table, exists_ok=True)
    logger.info(f"✅ Verified BigQuery Table Schema: {table.table_id} (Partitioned)")

if __name__ == '__main__':
    init_bigquery()
