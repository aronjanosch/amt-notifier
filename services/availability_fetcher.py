# services/availability_fetcher.py

import requests
import datetime
import threading
import logging
from database import Session, Subscriber
from config import API_AVAILABILITY_URL, LOCATION_NAMES, LOCATIONS
from telegram import Bot

class AvailabilityFetcher:
    """Fetches availability data for the specified locations."""

    def __init__(self, session_manager, bot_token):
        self.session_manager = session_manager
        self.bot = Bot(token=bot_token)
        self.locations = LOCATIONS
        self.availability_data = {location: [] for location in self.locations}
        self.lock = threading.Lock()

    def fetch_availability(self):
        """Fetches the availability data."""
        auth_token = self.session_manager.get_auth_token()
        if not auth_token:
            logging.info("Auth token not available. Attempting to open a new session.")
            if not self.session_manager.open_session():
                logging.error("Failed to open session. Cannot fetch availability.")
                return

        logging.info("Fetching availability...")
        headers = {
            'Authorization': self.session_manager.get_auth_token(),
            'User-Agent': 'Mozilla/5.0 (compatible; BuergerbueroMonitor/1.0)',
            'Accept': 'application/json',
        }
        for location in self.locations:
            params = {
                'from': datetime.datetime.now().strftime('%d.%m.%Y'),
                'until': (datetime.datetime.now() + datetime.timedelta(days=30)).strftime('%d.%m.%Y'),
                'location': location,
                'services': 38,
                '_': int(datetime.datetime.now().timestamp() * 1000)
            }
            try:
                response = self.session_manager.session.get(
                    API_AVAILABILITY_URL, headers=headers, params=params, timeout=10
                )
                if response.status_code == 200:
                    data = response.json()
                    logging.debug(f"Data received for location {location}: {data}")
                    self.process_data(location, data)
                elif response.status_code == 401:
                    logging.warning("Auth token expired or invalid. Re-opening session.")
                    if self.session_manager.open_session():
                        headers['Authorization'] = self.session_manager.get_auth_token()
                        response = self.session_manager.session.get(
                            API_AVAILABILITY_URL, headers=headers, params=params, timeout=10
                        )
                        response.raise_for_status()
                        data = response.json()
                        self.process_data(location, data)
                    else:
                        logging.error("Failed to re-open session.")
                else:
                    logging.error(f"Error fetching data for location {location}: {response.status_code} - {response.text}")
            except requests.RequestException as e:
                logging.error(f"Request exception fetching data for location {location}: {e}")
            except Exception as e:
                logging.exception(f"Unexpected error fetching data for location {location}: {e}")

    def process_data(self, location, data):
        """Processes the data received from the API."""
        new_dates = data.get('availability-dates', [])
        dates_list = []
        for entry in new_dates:
            timestamp = entry.get('date') if isinstance(entry, dict) else entry
            if isinstance(timestamp, int):
                date_obj = datetime.datetime.fromtimestamp(timestamp / 1000)
                date_str = date_obj.strftime('%d.%m.%Y')
                dates_list.append(date_str)
            elif isinstance(timestamp, str):
                dates_list.append(timestamp)
            else:
                logging.warning(f"Unexpected date format for location {location}: {entry}")
        with self.lock:
            new_dates_set = set(dates_list)
            current_dates_set = set(self.availability_data[location])
            if new_dates_set != current_dates_set:
                logging.info(f"Updated dates for location {location}: {dates_list}")
                self.availability_data[location] = dates_list
                # Notify subscribers about the update
                self.notify_subscribers(location, dates_list)
            else:
                logging.info(f"No changes in dates for location {location}.")

    def notify_subscribers(self, location, dates_list):
        """Sends notifications to subscribers."""
        message = f"Neue Termine verfügbar bei {LOCATION_NAMES[location]}:\n" + "\n".join(dates_list)
        # Query subscribers from the database
        session = Session()
        try:
            subscribers = session.query(Subscriber).all()
            for subscriber in subscribers:
                preferred_locations = subscriber.preferred_locations.split(',')
                if str(location) in preferred_locations:
                    try:
                        self.bot.send_message(chat_id=subscriber.chat_id, text=message)
                        logging.info(f"Sent notification to chat_id {subscriber.chat_id}")
                    except Exception as e:
                        logging.error(f"Error sending message to chat_id {subscriber.chat_id}: {e}")
        finally:
            session.close()

    def get_availability_data(self):
        """Returns the current availability data."""
        with self.lock:
            return self.availability_data.copy()