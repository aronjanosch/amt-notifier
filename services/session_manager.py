# services/session_manager.py

import requests
import random
import threading
import logging
from config import API_SESSION_URL_BASE

class SessionManager:
    """Manages the session and authentication token."""

    def __init__(self):
        self.session = requests.Session()
        self.auth_token = None
        self.lock = threading.Lock()

    def open_session(self):
        """Opens a new session and obtains the auth token."""
        with self.lock:
            logging.info("Opening a new session...")
            max_attempts = 5
            for attempt in range(1, max_attempts + 1):
                number = random.randint(1, 10000)
                session_url = f'{API_SESSION_URL_BASE}/{number}'
                headers = {
                    'User-Agent': 'Mozilla/5.0 (compatible; BuergerbueroMonitor/1.0)',
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                    'Authorization': self.auth_token or 'null',
                }
                payload = {
                    'mandator': '32-42',
                    'online': True
                }
                try:
                    response = self.session.post(session_url, headers=headers, json=payload, timeout=10)
                    response.raise_for_status()
                    data = response.json()
                    self.auth_token = data.get('id')
                    if not self.auth_token:
                        logging.error("Failed to obtain auth token from session creation response.")
                        return False
                    logging.info(f"Session opened with auth token: {self.auth_token}")
                    return True
                except requests.RequestException as e:
                    logging.error(f"Attempt {attempt}: Error opening session: {e}")
                except ValueError:
                    logging.error(f"Attempt {attempt}: Invalid JSON response.")
            logging.error("Failed to open session after multiple attempts.")
            return False

    def get_auth_token(self):
        """Returns the current auth token."""
        with self.lock:
            return self.auth_token