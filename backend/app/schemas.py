from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

class IngestEvent(BaseModel):
    device_id: str = Field(..., examples=["esp32-1"])
    raw_event: str = Field(..., examples=["S1_S2", "S2_S1", "saya_masuk", "teman_keluar"])
    distance1_cm: Optional[float] = None
    distance2_cm: Optional[float] = None
    rssi: Optional[int] = None
    meta: Optional[Dict[str, Any]] = None

class EventOut(BaseModel):
    id: int
    device_id: str
    raw_event: str
    predicted_label: Optional[str] = None
    confidence: Optional[float] = None
    server_received_at: str
    image_url: Optional[str] = None

    class Config:
        from_attributes = True
