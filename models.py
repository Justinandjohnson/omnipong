from sqlalchemy import Column, Integer, String, Date, Float, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True)
    dob = Column(Date)
    usatt_id = Column(String)
    stadium_id = Column(String)
    phone_number = Column(String) # User's personal phone number for SMS reminders
    current_rating = Column(Integer)
    official_rating = Column(Integer)  # USATT Official Rating
    last_updated = Column(DateTime, default=datetime.utcnow)

class Activity(Base):
    __tablename__ = 'activities'
    id = Column(Integer, primary_key=True)
    source = Column(String)  # 'omnipong' or 'stadium'
    source_id = Column(String, unique=True)
    title = Column(String, nullable=False)
    date = Column(Date)
    date_range = Column(String)  # Raw string from site
    location = Column(String)    # Detailed City/State
    city_state = Column(String)  # Explicitly parsed if possible
    activity_type = Column(String)  # 'tournament', 'league', 'camp'
    status = Column(String)  # 'upcoming', 'current', 'past'
    url = Column(String)
    contact_name = Column(String)
    contact_email = Column(String)
    contact_phone = Column(String)
    flyer_url = Column(String)
    raw_details = Column(String)
    last_scraped = Column(DateTime, default=datetime.utcnow)
    
    events = relationship("Event", back_populates="activity")

class Event(Base):
    __tablename__ = 'events'
    id = Column(Integer, primary_key=True)
    activity_id = Column(Integer, ForeignKey('activities.id'))
    name = Column(String, nullable=False)
    rating_limit = Column(Integer)
    fee = Column(Float)
    status = Column(String) # 'Open', 'Closed', 'Entered'
    start_time = Column(String)
    
    activity = relationship("Activity", back_populates="events")

class Match(Base):
    __tablename__ = 'matches'
    id = Column(Integer, primary_key=True)
    activity_id = Column(Integer, ForeignKey('activities.id'), nullable=True)
    date = Column(DateTime)
    winner_name = Column(String)
    loser_name = Column(String)
    opponent_name = Column(String)
    opponent_usatt_id = Column(String)
    opponent_rating = Column(Integer)
    score_summary = Column(String) 
    set_scores = Column(String)
    result = Column(String)  # 'W' or 'L'
    source = Column(String) # 'omnipong' or 'stadium'

class Contact(Base):
    __tablename__ = 'contacts'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    role = Column(String)  # 'Coach', 'Director'
    email = Column(String)
    phone = Column(String)
    club_affiliation = Column(String)
    source_url = Column(String)

class RatingHistory(Base):
    __tablename__ = 'rating_history'
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    rating = Column(Integer, nullable=False)
    source = Column(String, nullable=False)  # 'omnipong' or 'stadium_league'
    match_id = Column(Integer, ForeignKey('matches.id'), nullable=True)
    notes = Column(String)  # Optional context (e.g., "After Spring Tournament")

class Player(Base):
    __tablename__ = 'players'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    usatt_id = Column(String)
    rating = Column(Integer)
    state = Column(String)
    rating_source = Column(String, default="unknown") # 'family_search', 'tournament_entry'
    last_updated = Column(DateTime, default=datetime.utcnow)

class Notification(Base):
    __tablename__ = 'notifications'
    id = Column(Integer, primary_key=True)
    type = Column(String, nullable=False) # e.g., 'new_tournament'
    content = Column(String, nullable=False) # JSON encoded data
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
