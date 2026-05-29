from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from .db import Base

class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, index=True, nullable=False)
    raw_event = Column(String, index=True, nullable=False)

    predicted_label = Column(String, index=True, nullable=True)  # nanti step model
    confidence = Column(Float, nullable=True)

    server_received_at = Column(DateTime, index=True, nullable=False)
    payload_json = Column(Text, nullable=True)  # simpan payload asli (string JSON)
