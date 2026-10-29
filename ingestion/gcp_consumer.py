import json
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import config
from utils.logger import get_logger

logger = get_logger("GCP_Consumer")

try:
    from google.cloud import pubsub_v1
    from google.cloud import bigquery
    GCP_AVAILABLE = True
except ImportError:
    GCP_AVAILABLE = False
    logger.warning("google-cloud-pubsub or bigquery not installed.")

class GcPPubSubToBigQuery:
    """
    Consumer process that listens to Pub/Sub events and uses
    Streaming Inserts into Data Warehouse (BigQuery).
    Replaces local SQLite loader for high availability analytics.
    """
    def __init__(self):
        if GCP_AVAILABLE:
            self.subscriber = pubsub_v1.SubscriberClient()
            self.bq_client = bigquery.Client(project=config.GCP_PROJECT_ID)
            self.subscription_path = self.subscriber.subscription_path(config.GCP_PROJECT_ID, config.GCP_PUBSUB_SUB)
            self.table_id = f"{config.GCP_PROJECT_ID}.{config.GCP_BQ_DATASET}.events"

            # Auto-create Subscription
            from google.api_core.exceptions import NotFound
            topic_path = pubsub_v1.PublisherClient().topic_path(config.GCP_PROJECT_ID, config.GCP_PUBSUB_TOPIC)
            try:
                self.subscriber.get_subscription(request={"subscription": self.subscription_path})
            except NotFound:
                logger.info(f"Subscription not found. Creating it: {config.GCP_PUBSUB_SUB} attached to topic {config.GCP_PUBSUB_TOPIC}")
                self.subscriber.create_subscription(request={"name": self.subscription_path, "topic": topic_path})

            # Auto-create BigQuery Dataset
            dataset_id = f"{config.GCP_PROJECT_ID}.{config.GCP_BQ_DATASET}"
            try:
                self.bq_client.get_dataset(dataset_id)
            except NotFound:
                logger.info(f"BigQuery dataset not found. Creating it: {config.GCP_BQ_DATASET}")
                dataset = bigquery.Dataset(dataset_id)
                dataset.location = "US"
                self.bq_client.create_dataset(dataset, timeout=30)

            # Auto-create BigQuery Table
            try:
                self.bq_client.get_table(self.table_id)
            except NotFound:
                logger.info("BigQuery table not found. Creating it: events")
                schema = [
                    bigquery.SchemaField("user_id", "STRING", mode="REQUIRED"),
                    bigquery.SchemaField("event_type", "STRING", mode="REQUIRED"),
                    bigquery.SchemaField("amount", "FLOAT", mode="REQUIRED"),
                    bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
                ]
                table = bigquery.Table(self.table_id, schema=schema)
                self.bq_client.create_table(table, timeout=30)

            import time
            self.buffer = []
            self.last_flush = time.time()
            self.flush_interval = 20  # Flush every 20 seconds

    def callback(self, message):
        """Callback to process each stream payload individually into a buffer."""
        try:
            record = json.loads(message.data.decode('utf-8'))
            self.buffer.append((record, message))
        except Exception as e:
            logger.error(f"Processing error during ingestion: {e}")

    def flush_buffer(self):
        if not self.buffer:
            return
            
        batch = self.buffer.copy()
        self.buffer = []
        records = [item[0] for item in batch]
        messages = [item[1] for item in batch]
        
        logger.info(f"📦 Packaging {len(records)} events into a Free-Tier Batch Load Job...")
        
        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            schema=[
                bigquery.SchemaField("user_id", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("event_type", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("amount", "FLOAT", mode="REQUIRED"),
                bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
            ]
        )
        try:
            job = self.bq_client.load_table_from_json(records, self.table_id, job_config=job_config)
            job.result() # Blocks until job is complete
            
            for msg in messages:
                msg.ack()
                
            logger.info(f"✅ Successfully batch loaded {len(records)} events to BigQuery!")
        except Exception as e:
            logger.error(f"BQ Batch Insert error: {e}")

    def start_listening(self):
        if not GCP_AVAILABLE:
            return

        import time
        logger.info(f"🎧 Listening for events. Micro-batching every {self.flush_interval}s to respect BQ Free Tier limits...")
        streaming_pull_future = self.subscriber.subscribe(self.subscription_path, callback=self.callback)

        try:
            while True:
                time.sleep(1)
                if time.time() - self.last_flush >= self.flush_interval and self.buffer:
                    self.flush_buffer()
                    self.last_flush = time.time()
        except KeyboardInterrupt:
            streaming_pull_future.cancel()
            self.flush_buffer()
            logger.info("🛑 Consumer disconnected from streaming queue.")

if __name__ == '__main__':
    consumer = GcPPubSubToBigQuery()
    consumer.start_listening()
