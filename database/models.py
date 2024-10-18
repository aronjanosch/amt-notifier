# database/models.py

from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.orm import sessionmaker, declarative_base, scoped_session
from config import DATABASE_URL
import threading

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