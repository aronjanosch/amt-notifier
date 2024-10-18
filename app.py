# app.py

from flask import Flask
import logging
import threading
import atexit

from config import TELEGRAM_TOKEN
from database import Base, engine
from services.session_manager import SessionManager
from services.availability_fetcher import AvailabilityFetcher
from bot import (
    start,
    subscribe,
    location_selection,
    update_subscription,
    new_location_selection,
    unsubscribe,
    status,
    cancel,
    unknown,
    SELECTING_LOCATIONS,
    UPDATING_LOCATIONS
)
from scheduler import setup_scheduler

from telegram.ext import Updater, CommandHandler, MessageHandler, ConversationHandler, Filters, CallbackContext

# Initialize Flask app
app = Flask(__name__)

# Setup logging
logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s')

def main():
    # Initialize SessionManager
    session_manager = SessionManager()
    if not session_manager.open_session():
        logging.error("Failed to initialize session. Exiting.")
        return

    # Initialize AvailabilityFetcher
    availability_fetcher = AvailabilityFetcher(session_manager, TELEGRAM_TOKEN)
    availability_fetcher.fetch_availability()

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

    # Start the bot
    updater.start_polling()
    logging.info("Telegram bot started.")

    # Setup scheduler
    scheduler = setup_scheduler(session_manager, availability_fetcher)

    # Ensure scheduler and updater shutdown on app exit
    atexit.register(lambda: scheduler.shutdown())
    atexit.register(lambda: updater.stop())

    # Run the Flask app
    app.run(host='0.0.0.0', port=8088)

if __name__ == '__main__':
    main()