"""Central configuration for device management"""

import os
from typing import Dict

# Device ID mappings (face service → canonical ID)
DEVICE_MAPPING: Dict[str, str] = {
    "face-service": "esp32-1",      # All face detections → esp32-1
    "face-cam-1": "esp32-1",
    "face-camera": "esp32-1",
    "esp32-1": "esp32-1",            # Direct ESP calls
    "esp32-001": "esp32-1",
}

DEFAULT_DEVICE_ID = os.getenv("DEFAULT_DEVICE_ID", "esp32-1").strip() or "esp32-1"

def resolve_device_id(device_id: str | None) -> str:
    """
    Normalize device_id to canonical form.
    
    Handles:
    - face service using different IDs
    - ESP using different IDs
    - None → default
    
    Example:
        resolve_device_id("face-service") → "esp32-1"
        resolve_device_id("esp32-1") → "esp32-1"
        resolve_device_id(None) → "esp32-1"
    """
    if not device_id:
        return DEFAULT_DEVICE_ID
    
    device_id = str(device_id).strip().lower()
    
    # Check mapping
    if device_id in DEVICE_MAPPING:
        resolved = DEVICE_MAPPING[device_id]
        if device_id != resolved:
            print(f"[CONFIG] Resolved device_id: {device_id} → {resolved}")
        return resolved
    
    # If unmapped but looks like esp32-*, accept it
    if device_id.startswith("esp32"):
        return device_id
    
    # Otherwise use default
    return DEFAULT_DEVICE_ID
