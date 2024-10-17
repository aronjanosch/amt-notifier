from flask import Flask, jsonify, render_template
from apscheduler.schedulers.background import BackgroundScheduler
import requests
import os
import logging
import random
import datetime
import threading

app = Flask(__name__)

# Setup logging
logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s')

# Configuration
API_AVAILABILITY_URL = 'https://service.stuttgart.de/ssc-stuttgart/ws/availabilities/dates'
API_SESSION_URL_BASE = 'https://service.stuttgart.de/ssc-stuttgart/ws/sessions'

# Location mapping
LOCATION_NAMES = {
    1: "Bürgerbüro MITTE (Eberhardstr. 39)",
    5: "Bürgerbüro WEST (Bebelstr. 22)",
    6: "Bürgerbüro BAD CANNSTATT (Marktplatz 10)",
    7: "Bürgerbüro ZUFFENHAUSEN (Emil-Schuler-Platz 1)",
    8: "Bürgerbüro SÜD (Jella-Lepman-Str. 3)",
    9: "Bürgerbüro VAIHINGEN (Rathausplatz 1)",
    10: "Bürgerbüro OST (Schönbühlstr. 65)",
    # Exclude IDs 12 and 13
}

# Load configuration from environment variables or set defaults
LOCATIONS = list(LOCATION_NAMES.keys())  # Only include relevant locations
FETCH_INTERVAL_MINUTES = int(os.environ.get('FETCH_INTERVAL_MINUTES', 5))  # Default to 5 minutes
SESSION_REFRESH_INTERVAL_MINUTES = int(os.environ.get('SESSION_REFRESH_INTERVAL_MINUTES', 30))  # Adjust as needed

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

session_manager = SessionManager()

class AvailabilityFetcher:
    """Fetches availability data for the specified locations."""

    def __init__(self, session_manager, locations):
        self.session_manager = session_manager
        self.locations = locations
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
                '_': int(datetime.datetime.now().timestamp() * 1000)  # Timestamp to prevent caching
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
            else:
                logging.info(f"No changes in dates for location {location}.")

    def get_availability_data(self):
        """Returns the current availability data."""
        with self.lock:
            return self.availability_data.copy()

availability_fetcher = AvailabilityFetcher(session_manager, LOCATIONS)

# Initialize scheduler
scheduler = BackgroundScheduler()

# Schedule session refresh to maintain a valid session
scheduler.add_job(session_manager.open_session, 'interval', minutes=SESSION_REFRESH_INTERVAL_MINUTES)

# Schedule fetch_availability at intervals
scheduler.add_job(availability_fetcher.fetch_availability, 'interval', minutes=FETCH_INTERVAL_MINUTES)

scheduler.start()

# Ensure scheduler shuts down on app exit
import atexit
atexit.register(lambda: scheduler.shutdown())

# Define routes
@app.route('/')
def index():
    return render_template('index.html', availability=availability_fetcher.get_availability_data(), location_names=LOCATION_NAMES)

@app.route('/api/availability')
def api_availability():
    return jsonify(availability_fetcher.get_availability_data())

if __name__ == '__main__':
    # Initial session creation
    if not session_manager.open_session():
        logging.error("Failed to initialize session. Exiting.")
    else:
        # Initial fetch on startup
        availability_fetcher.fetch_availability()
        # Run the Flask app
        app.run(host='0.0.0.0', port=8088)