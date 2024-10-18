# bot/handlers.py

from telegram.ext import Updater, CommandHandler, MessageHandler, ConversationHandler, Filters, CallbackContext
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from database import Session, Subscriber
from config import LOCATION_NAMES
import logging

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