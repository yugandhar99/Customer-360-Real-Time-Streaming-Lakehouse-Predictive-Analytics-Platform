import csv
import os
from typing import Dict, Any
import sys

# Append parent dir to path if strictly running standalone
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import config
from utils.logger import get_logger

logger = get_logger(__name__)

class DataWriter:
    """
    Production-grade Data Writer for initial CSV ingestion.
    Includes thread-safe considerations and error handling.
    """
    
    def __init__(self, filename: str = config.CSV_EVENTS_PATH):
        self.filename = filename
        self.headers = ['user_id', 'event_type', 'amount', 'timestamp']
        self._initialize_csv()

    def _initialize_csv(self) -> None:
        """Initializes the CSV file with headers if it does not exist."""
        try:
            if not os.path.exists(self.filename):
                with open(self.filename, mode='w', newline='', encoding='utf-8') as file:
                    writer = csv.writer(file)
                    writer.writerow(self.headers)
                logger.info(f"Initialized new CSV file with headers at: {self.filename}")
        except IOError as e:
            logger.error(f"Failed to initialize CSV at {self.filename}: {e}")
            raise

    def write_event(self, event: Dict[str, Any]) -> bool:
        """
        Writes a single event dict to the CSV file.
        
        Args:
            event (Dict[str, Any]): The structured event data.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            with open(self.filename, mode='a', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerow([
                    event.get('user_id'),
                    event.get('event_type'),
                    event.get('amount', 0.0),
                    event.get('timestamp')
                ])
            return True
        except IOError as e:
            logger.error(f"IOError occurred while writing event to CSV: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error while writing event: {e}")
            return False
