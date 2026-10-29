import time
import random
import uuid
import sys
import os
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import config
from utils.logger import get_logger
from ingestion.publisher import build_event_sink

class EventGenerator:
    """
    Simulates real-time clickstream and transaction data streams.
    Designed to mimic high-throughput user activity on an e-commerce platform.
    """
    
    def __init__(self, sink=None):
        self.logger = get_logger("EventGenerator")
        self.sink = sink or build_event_sink()
        self.writer = getattr(self.sink, "writer", None)
        # Pre-seed user pool to simulate returning users for retention analytics
        self.users = [str(uuid.uuid4())[:8] for _ in range(config.NUM_USERS)]
        self.event_types = config.EVENT_TYPES
        self.is_running = False
        
    def generate_single_event(self) -> dict:
        """Constructs a simulated user event."""
        user_id = random.choice(self.users)
        event_type = random.choice(self.event_types)
        
        # Determine amount: only purchases have monetary value
        amount = 0.0
        if event_type == 'purchase':
            amount = round(random.uniform(10.0, 1500.0), 2)
            
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        return {
            'user_id': user_id,
            'event_type': event_type,
            'amount': amount,
            'timestamp': timestamp
        }

    def start_simulation(self):
        """Starts the infinite loop simulating continuous real-time data flow."""
        self.logger.info("🚀 Event generator simulation started...")
        self.is_running = True
        
        try:
            while self.is_running:
                event = self.generate_single_event()
                success = self.sink.publish(event)
                
                if success:
                    self.logger.info(
                        f"Event Captured | User: {event['user_id']} | "
                        f"Type: {event['event_type']:12} | "
                        f"Amt: ${event['amount']:.2f}"
                    )
                else:
                    self.logger.warning("Failed to write event.")

                # Throttle generation speed based on config
                sleep_duration = random.uniform(
                    config.SIMULATION_WAIT_MIN_SEC,
                    config.SIMULATION_WAIT_MAX_SEC
                )
                time.sleep(sleep_duration)
                
        except KeyboardInterrupt:
            self.stop_simulation()
            
    def stop_simulation(self):
        """Safely terminates the generation process."""
        self.logger.info("🛑 Simulation stopped safely via user interrupt.")
        self.is_running = False

if __name__ == "__main__":
    generator = EventGenerator()
    generator.start_simulation()
