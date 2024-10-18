# app.py

from flask import Flask, jsonify, render_template
from apscheduler.schedulers.background import BackgroundScheduler
import requests
import os
import logging
import random
import datetime
import threading
import dotenv
import pytz


# Import Telegram libraries
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, ConversationHandler, CallbackContext
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove

# Import SQLAlchemy components
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.orm import sessionmaker, declarative_base, scoped_session

# Load environment variables
dotenv.load_dotenv()

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
}

# Load configuration from environment variables or set defaults
LOCATIONS = list(LOCATION_NAMES.keys())  # Only include relevant locations
FETCH_INTERVAL_MINUTES = int(os.environ.get('FETCH_INTERVAL_MINUTES', 5))  # Default to 5 minutes
SESSION_REFRESH_INTERVAL_MINUTES = int(os.environ.get('SESSION_REFRESH_INTERVAL_MINUTES', 30))  # Adjust as needed
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')

# Check if TELEGRAM_TOKEN is set
if not TELEGRAM_TOKEN:
    logging.error("TELEGRAM_TOKEN environment variable not set. Exiting.")
    exit(1)

# Database setup
DATABASE_URL = 'sqlite:///subscribers.db'

engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False})
Base = declarative_base()

# Create a scoped session for thread safety
session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)

class Subscriber(Base):
    __tablename__ = 'subscribers'
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, unique=True, index=True, nullable=False)
    preferred_locations = Column(Text, nullable=False)  # Comma-separated list of location IDs

# Create tables
Base.metadata.create_all(bind=engine)

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
                        context.bot.send_message(chat_id=subscriber.chat_id, text=message)
                        logging.info(f"Sent notification to chat_id {subscriber.chat_id}")
                    except Exception as e:
                        logging.error(f"Error sending message to chat_id {subscriber.chat_id}: {e}")
        finally:
            session.close()

    def get_availability_data(self):
        """Returns the current availability data."""
        with self.lock:
            return self.availability_data.copy()

availability_fetcher = AvailabilityFetcher(session_manager, LOCATIONS)

# Telegram Bot Handlers

from telegram.ext import Updater

# Conversation states
SELECTING_LOCATIONS = 1
UPDATING_LOCATIONS = 2

def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Willkommen beim Bürgerbüro Terminbenachrichtigungsbot!\n"
        "Verwende /subscribe, um Benachrichtigungen zu erhalten.\n"
        "Verwende /unsubscribe, um keine Benachrichtigungen mehr zu erhalten.\n"
        "Verwende /update, um deine Standorte zu ändern.\n"
        "Verwende /status, um deine aktuellen Standorte zu sehen."
    )

def subscribe(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    session = Session()
    try:
        # Check if user is already subscribed
        subscriber = session.query(Subscriber).filter_by(chat_id=chat_id).first()
        if subscriber:
            update.message.reply_text(
                "Du bist bereits angemeldet.\n"
                "Verwende /update, um deine Standorte zu ändern.\n"
                "Verwende /unsubscribe, um dich abzumelden."
            )
            return ConversationHandler.END
    finally:
        session.close()
    # Present location options
    location_list = "\n".join([f"{loc_id}: {name}" for loc_id, name in LOCATION_NAMES.items()])
    update.message.reply_text(
        "Bitte wähle die gewünschten Standorte aus.\n"
        "Sende die Nummern der Standorte, getrennt durch Kommas.\n\n"
        f"Verfügbare Standorte:\n{location_list}"
    )
    return SELECTING_LOCATIONS

def location_selection(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    input_text = update.message.text
    # Split the input by commas
    input_ids = input_text.split(',')
    selected_location_ids = []
    for input_id in input_ids:
        input_id = input_id.strip()
        if input_id.isdigit():
            loc_id = int(input_id)
            if loc_id in LOCATION_NAMES:
                selected_location_ids.append(str(loc_id))
            else:
                update.message.reply_text(f"Ungültige Standortnummer: {input_id}. Bitte versuche es erneut.")
                return SELECTING_LOCATIONS
        else:
            update.message.reply_text(f"Ungültige Eingabe: {input_id}. Bitte verwende die Standortnummern.")
            return SELECTING_LOCATIONS
    if selected_location_ids:
        preferred_locations = ','.join(selected_location_ids)
        session = Session()
        try:
            subscriber = Subscriber(
                chat_id=chat_id,
                preferred_locations=preferred_locations
            )
            session.add(subscriber)
            session.commit()
            selected_locations_names = [LOCATION_NAMES[int(loc_id)] for loc_id in selected_location_ids]
            update.message.reply_text(
                "Du erhältst jetzt Benachrichtigungen für folgende Standorte:\n" + "\n".join(selected_locations_names),
                reply_markup=ReplyKeyboardRemove()
            )
        except Exception as e:
            session.rollback()
            logging.error(f"Error adding subscriber {chat_id}: {e}")
            update.message.reply_text("Es ist ein Fehler aufgetreten. Bitte versuche es später erneut.")
        finally:
            session.close()
    else:
        update.message.reply_text("Keine gültigen Standorte ausgewählt. Bitte versuche es erneut.")
        return SELECTING_LOCATIONS
    return ConversationHandler.END

def update_subscription(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    session = Session()
    try:
        # Check if user is already subscribed
        subscriber = session.query(Subscriber).filter_by(chat_id=chat_id).first()
        if not subscriber:
            update.message.reply_text("Du bist nicht angemeldet. Verwende /subscribe, um Benachrichtigungen zu erhalten.")
            return ConversationHandler.END
    finally:
        session.close()
    # Present location options
    location_list = "\n".join([f"{loc_id}: {name}" for loc_id, name in LOCATION_NAMES.items()])
    update.message.reply_text(
        "Aktualisiere deine bevorzugten Standorte.\n"
        "Sende die Nummern der Standorte, getrennt durch Kommas.\n\n"
        f"Verfügbare Standorte:\n{location_list}"
    )
    return UPDATING_LOCATIONS

def new_location_selection(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    input_text = update.message.text
    # Similar processing as in location_selection
    input_ids = input_text.split(',')
    selected_location_ids = []
    for input_id in input_ids:
        input_id = input_id.strip()
        if input_id.isdigit():
            loc_id = int(input_id)
            if loc_id in LOCATION_NAMES:
                selected_location_ids.append(str(loc_id))
            else:
                update.message.reply_text(f"Ungültige Standortnummer: {input_id}. Bitte versuche es erneut.")
                return UPDATING_LOCATIONS
        else:
            update.message.reply_text(f"Ungültige Eingabe: {input_id}. Bitte verwende die Standortnummern.")
            return UPDATING_LOCATIONS
    if selected_location_ids:
        preferred_locations = ','.join(selected_location_ids)
        session = Session()
        try:
            subscriber = session.query(Subscriber).filter_by(chat_id=chat_id).first()
            subscriber.preferred_locations = preferred_locations
            session.commit()
            selected_locations_names = [LOCATION_NAMES[int(loc_id)] for loc_id in selected_location_ids]
            update.message.reply_text(
                "Deine Benachrichtigungseinstellungen wurden aktualisiert. Du erhältst jetzt Benachrichtigungen für folgende Standorte:\n" + "\n".join(selected_locations_names),
                reply_markup=ReplyKeyboardRemove()
            )
        except Exception as e:
            session.rollback()
            logging.error(f"Error updating subscriber {chat_id}: {e}")
            update.message.reply_text("Es ist ein Fehler aufgetreten. Bitte versuche es später erneut.")
        finally:
            session.close()
    else:
        update.message.reply_text("Keine gültigen Standorte ausgewählt. Bitte versuche es erneut.")
        return UPDATING_LOCATIONS
    return ConversationHandler.END

def unsubscribe(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    session = Session()
    try:
        subscriber = session.query(Subscriber).filter_by(chat_id=chat_id).first()
        if subscriber:
            session.delete(subscriber)
            session.commit()
            update.message.reply_text("Du wurdest von Benachrichtigungen abgemeldet.")
        else:
            update.message.reply_text("Du bist nicht für Benachrichtigungen angemeldet.")
    except Exception as e:
        session.rollback()
        logging.error(f"Error removing subscriber {chat_id}: {e}")
        update.message.reply_text("Es ist ein Fehler aufgetreten. Bitte versuche es später erneut.")
    finally:
        session.close()

def status(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    session = Session()
    try:
        subscriber = session.query(Subscriber).filter_by(chat_id=chat_id).first()
        if subscriber:
            preferred_locations = subscriber.preferred_locations.split(',')
            location_names = [LOCATION_NAMES[int(loc_id)] for loc_id in preferred_locations]
            update.message.reply_text("Du bist für folgende Standorte angemeldet:\n" + "\n".join(location_names))
        else:
            update.message.reply_text("Du bist nicht für Benachrichtigungen angemeldet.")
    except Exception as e:
        logging.error(f"Error retrieving status for chat_id {chat_id}: {e}")
        update.message.reply_text("Es ist ein Fehler aufgetreten. Bitte versuche es später erneut.")
    finally:
        session.close()

def cancel(update: Update, context: CallbackContext):
    update.message.reply_text("Aktion abgebrochen.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def unknown(update: Update, context: CallbackContext):
    update.message.reply_text("Entschuldigung, ich habe diesen Befehl nicht verstanden.")

# Telegram Bot Setup

def main():
    # Start the bot
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    # Conversation handler for subscription
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('subscribe', subscribe)],
        states={
            SELECTING_LOCATIONS: [MessageHandler(Filters.text & ~Filters.command, location_selection)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    # Conversation handler for updating subscription
    update_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('update', update_subscription)],
        states={
            UPDATING_LOCATIONS: [MessageHandler(Filters.text & ~Filters.command, new_location_selection)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(conv_handler)
    dp.add_handler(update_conv_handler)
    dp.add_handler(CommandHandler('unsubscribe', unsubscribe))
    dp.add_handler(CommandHandler('status', status))
    dp.add_handler(MessageHandler(Filters.command, unknown))

    # Start the bot in a separate thread
    updater.start_polling()
    logging.info("Telegram bot started.")

    # Initialize scheduler with specified timezone
    scheduler = BackgroundScheduler(timezone=pytz.timezone('Europe/Berlin'))

    # Schedule session refresh to maintain a valid session
    scheduler.add_job(session_manager.open_session, 'interval', minutes=SESSION_REFRESH_INTERVAL_MINUTES)

    # Schedule fetch_availability at intervals
    scheduler.add_job(availability_fetcher.fetch_availability, 'interval', minutes=FETCH_INTERVAL_MINUTES)

    scheduler.start()

    # Ensure scheduler shuts down on app exit
    import atexit
    atexit.register(lambda: scheduler.shutdown())
    atexit.register(lambda: updater.stop())

    # Run the Flask app
    app.run(host='0.0.0.0', port=8088)

if __name__ == '__main__':
    # Initial session creation
    if not session_manager.open_session():
        logging.error("Failed to initialize session. Exiting.")
    else:
        # Initial fetch on startup
        availability_fetcher.fetch_availability()
        main()

