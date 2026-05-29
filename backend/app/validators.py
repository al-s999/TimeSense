"""Input validation for all API endpoints"""

from typing import Any, Dict, List, Optional, Tuple

class ValidationError:
    def __init__(self, errors: List[str]):
        self.errors = errors
        self.has_errors = len(errors) > 0
    
    def to_dict(self) -> Dict:
        return {
            "ok": False,
            "error": "; ".join(self.errors),
            "error_count": len(self.errors)
        }

def validate_face_ingest(payload: Dict) -> Tuple[bool, List[str]]:
    """Validate face recognition ingest payload"""
    errors = []
    
    # device_id
    device_id = payload.get("device_id")
    if not device_id:
        errors.append("device_id required")
    elif not isinstance(device_id, str):
        errors.append("device_id must be string")
    
    # label
    label = payload.get("label")
    if not label:
        errors.append("label required")
    elif not isinstance(label, str):
        errors.append("label must be string")
    elif label.lower() == "unknown":
        errors.append("label cannot be 'unknown'")
    
    # confidence
    confidence = payload.get("confidence")
    if confidence is None:
        errors.append("confidence required")
    else:
        try:
            conf = float(confidence)
            if conf < 0 or conf > 1:
                errors.append(f"confidence must be 0-1, got {conf}")
        except (ValueError, TypeError):
            errors.append("confidence must be number")
    
    return len(errors) == 0, errors

def validate_sensor_update(payload: Dict) -> Tuple[bool, List[str]]:
    """Validate sensor update payload"""
    errors = []
    
    # device_id
    device_id = payload.get("device_id")
    if not device_id:
        errors.append("device_id required")
    
    # distance1
    dist1 = payload.get("distance1")
    if dist1 is None:
        errors.append("distance1 required")
    else:
        try:
            d1 = float(dist1)
            if d1 < 0 or d1 > 400:
                errors.append(f"distance1 must be 0-400cm, got {d1}")
        except (ValueError, TypeError):
            errors.append("distance1 must be number")
    
    # distance2
    dist2 = payload.get("distance2")
    if dist2 is None:
        errors.append("distance2 required")
    else:
        try:
            d2 = float(dist2)
            if d2 < 0 or d2 > 400:
                errors.append(f"distance2 must be 0-400cm, got {d2}")
        except (ValueError, TypeError):
            errors.append("distance2 must be number")
    
    # temperature (optional)
    temp = payload.get("temperature")
    if temp is not None:
        try:
            t = float(temp)
            if t < -50 or t > 80:
                errors.append(f"temperature must be -50-80°C, got {t}")
        except (ValueError, TypeError):
            errors.append("temperature must be number")
    
    return len(errors) == 0, errors

def validate_command_execute(payload: Dict) -> Tuple[bool, List[str]]:
    """Validate command execution payload"""
    errors = []
    
    device_id = payload.get("device_id")
    if not device_id:
        errors.append("device_id required")
    
    action = payload.get("action")
    if not action:
        errors.append("action required")
    elif action not in ["open_door", "lock", "unlock"]:
        errors.append(f"invalid action: {action}")
    
    return len(errors) == 0, errors
