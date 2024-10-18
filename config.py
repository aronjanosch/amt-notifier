# config.py

import os
import dotenv

# Load environment variables
dotenv.load_dotenv()

# Telegram Bot Token
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN environment variable not set.")

# API URLs
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
}

# List of location IDs
LOCATIONS = list(LOCATION_NAMES.keys())

# Scheduler intervals
FETCH_INTERVAL_MINUTES = int(os.environ.get('FETCH_INTERVAL_MINUTES', 5))
SESSION_REFRESH_INTERVAL_MINUTES = int(os.environ.get('SESSION_REFRESH_INTERVAL_MINUTES', 30))

# Database URL
DATABASE_URL = 'sqlite:///subscribers.db'