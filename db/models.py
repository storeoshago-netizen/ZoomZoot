from sqlalchemy import Column, String, Integer, JSON
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase


class Base(AsyncAttrs, DeclarativeBase):
    pass


class Session(Base):
    __tablename__ = "sessions"
    session_id = Column(String, primary_key=True)
    last_message = Column(String)
    destination = Column(String, nullable=True)
    days = Column(Integer, nullable=True)
    preferences = Column(JSON, nullable=True)
    history = Column(
        JSON, nullable=True, default=list
    )  # List of {"role": "user/assistant", "content": "text"}
    trip_details = Column(
        JSON, nullable=True, default=dict
    )  # Saved requirements e.g., {"days": 5, "start_date": "2025-09-01", "preferences": ["food"]}


class Itinerary(Base):
    __tablename__ = "itineraries"
    session_id = Column(String, primary_key=True)
    itinerary = Column(JSON, nullable=False)
