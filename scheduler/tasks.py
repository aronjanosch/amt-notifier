# scheduler/tasks.py

from apscheduler.schedulers.background import BackgroundScheduler
from services.session_manager import SessionManager
from services.availability_fetcher import AvailabilityFetcher
from config import SESSION_REFRESH_INTERVAL_MINUTES, FETCH_INTERVAL_MINUTES, TELEGRAM_TOKEN
import pytz
import logging

def setup_scheduler(session_manager, availability_fetcher):
    # Initialize scheduler with specified timezone
    scheduler = BackgroundScheduler(timezone=pytz.timezone('Europe/Berlin'))

    # Schedule session refresh to maintain a valid session
    scheduler.add_job(session_manager.open_session, 'interval', minutes=SESSION_REFRESH_INTERVAL_MINUTES)

    # Schedule fetch_availability at intervals
    scheduler.add_job(availability_fetcher.fetch_availability, 'interval', minutes=FETCH_INTERVAL_MINUTES)

    scheduler.start()
    logging.info("Scheduler started.")
    return scheduler