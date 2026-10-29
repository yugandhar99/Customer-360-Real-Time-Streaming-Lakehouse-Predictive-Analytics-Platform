import json
import random
import time
import uuid
import sys
import os
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import config
from utils.logger import get_logger

logger = get_logger("GCP_Publisher")

try:
    from google.cloud import pubsub_v1
    GCP_AVAILABLE = True
except ImportError:
    GCP_AVAILABLE = False
    logger.warning("google-cloud-pubsub not installed. Run pip install -r requirements.txt")

class GCPEventPublisher:
    """
    Streams simulated real-time user events directly into a GCP Pub/Sub Topic.
    Acts as the source system replacement for the local CSV writer.
    """
    def __init__(self):
        self.users = [str(uuid.uuid4())[:8] for _ in range(config.NUM_USERS)]
        self.publisher = pubsub_v1.PublisherClient() if GCP_AVAILABLE else None
        self.topic_path = self.publisher.topic_path(config.GCP_PROJECT_ID, config.GCP_PUBSUB_TOPIC) if GCP_AVAILABLE else None

    def generate_event(self) -> dict:
        event_type = random.choice(config.EVENT_TYPES)
        return {
            'user_id': random.choice(self.users),
            'event_type': event_type,
            'amount': round(random.uniform(10.0, 1500.0), 2) if event_type == 'purchase' else 0.0,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

    def start_streaming(self):
        if not GCP_AVAILABLE:
            logger.error("Cannot stream to GCP - PubSub library missing.")
            return

        logger.info(f"🚀 Publishing streaming events to GCP Topic: {self.topic_path}")
        from google.api_core.exceptions import NotFound
        try:
            self.publisher.get_topic(request={"topic": self.topic_path})
        except NotFound:
            logger.info(f"Topic not found. Creating it: {config.GCP_PUBSUB_TOPIC}")
            self.publisher.create_topic(request={"name": self.topic_path})

        try:
            while True:
                event = self.generate_event()
                data_str = json.dumps(event)
                data_bytes = data_str.encode("utf-8")
                
                # Publish event to Pub/Sub
                future = self.publisher.publish(self.topic_path, data_bytes)
                future.result() # block until published
                
                logger.info(f"☁️ Published -> User: {event['user_id']} | Type: {event['event_type']}")
                time.sleep(random.uniform(config.SIMULATION_WAIT_MIN_SEC, config.SIMULATION_WAIT_MAX_SEC))
                
        except KeyboardInterrupt:
            logger.info("🛑 Publisher stopped safely.")
        except Exception as e:
            logger.error(f"Failed to publish to GCP: {e}")

if __name__ == '__main__':
    publisher = GCPEventPublisher()
    publisher.start_streaming()
