import threading
import time
from typing import Any, Optional

_lock = threading.Lock()
_last_face: dict[str, Any] | None = None


def update_face(meta: dict[str, Any], device_id: str | None = None) -> dict[str, Any]:
    payload = {
        "meta": meta,
        "device_id": device_id or "",
        "ts": time.time(),
    }
    with _lock:
        global _last_face
        _last_face = payload
    return payload


def get_face(ttl_seconds: float) -> Optional[dict[str, Any]]:
    with _lock:
        current = _last_face
    if not current:
        return None
    age = time.time() - float(current.get("ts", 0))
    if age > ttl_seconds:
        return None
    return current


def get_last_face() -> Optional[dict[str, Any]]:
    with _lock:
        return _last_face
