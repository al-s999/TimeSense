import os, json, time
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .db import Base, engine, get_db
from .models import Event
from .schemas import IngestEvent, EventOut

from typing import Optional, Any
import urllib.request
import urllib.error
from sqlalchemy import and_

import asyncio
from typing import Set

from fastapi.responses import StreamingResponse
from fastapi import BackgroundTasks

from .rds_model import get_model
from .face_router import router as face_router, get_face_app
from .face_cache import update_face as cache_face, get_face as get_cached_face, get_last_face
from .attendance_state import get_attendance_state
from .access_state import get_access_state
from .event_logic import (
    access_identity_from_face,
    is_semantic_access_event,
    label_from_raw_event,
    raw_event_person_id,
)
from .config import resolve_device_id
from .validators import validate_face_ingest, validate_sensor_update, validate_command_execute
from .command_queue import get_command_queue, Command
from dotenv import load_dotenv

from contextlib import asynccontextmanager

load_dotenv()

# Create tables
Base.metadata.create_all(bind=engine)

TZ_NAME = os.getenv("TZ", "Asia/Jakarta")
API_KEY = os.getenv("API_KEY", "").strip()
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
DEBUG_FLAG = os.getenv("DEBUG", "").lower() in {"1", "true", "yes", "on"}
FACE_RECOGNIZE_ENABLED = os.getenv("FACE_RECOGNIZE_ENABLED", "1").lower() in {"1", "true", "yes", "on"}
FACE_RECOGNIZE_TIMEOUT = float(os.getenv("FACE_RECOGNIZE_TIMEOUT", "2.0"))
FACE_ME_IDENTITY = os.getenv("FACE_ME_IDENTITY", "me")
FACE_THR_STRICT = float(os.getenv("FACE_THR_STRICT", "0.35"))
FACE_THR_LOOSE = float(os.getenv("FACE_THR_LOOSE", "0.50"))
FACE_RECOGNIZE_RUNTIME_ENABLED = FACE_RECOGNIZE_ENABLED
FACE_PREVIEW_STARTUP = os.getenv("FACE_PREVIEW_STARTUP", "0").lower() in {"1", "true", "yes", "on"}
FACE_META_TTL_SECONDS = float(os.getenv("FACE_META_TTL_SECONDS", "5"))

ESP32_BASE_URL = os.getenv("ESP32_BASE_URL", "").strip()
ESP32_OPEN_PATH = os.getenv("ESP32_OPEN_PATH", "/open").strip() or "/open"
ESP32_CLOSE_PATH = os.getenv("ESP32_CLOSE_PATH", "/close").strip() or "/close"
ESP32_COMMAND_METHOD = os.getenv("ESP32_COMMAND_METHOD", "POST").upper()
ESP32_API_KEY = os.getenv("ESP32_API_KEY", "").strip()
ESP32_TIMEOUT = float(os.getenv("ESP32_TIMEOUT", "2.0"))
ESP32_RETRIES = int(os.getenv("ESP32_RETRIES", "2"))
ESP32_RETRY_DELAY = float(os.getenv("ESP32_RETRY_DELAY", "0.5"))
ESP32_OPEN_COOLDOWN = float(os.getenv("ESP32_OPEN_COOLDOWN", "5"))
ESP32_CLOSE_COOLDOWN = float(os.getenv("ESP32_CLOSE_COOLDOWN", "5"))
ESP32_OPEN_MIN_CONF = float(os.getenv("ESP32_OPEN_MIN_CONF", "0.6"))
FACE_CONFIDENCE_THRESHOLD = float(os.getenv("FACE_CONFIDENCE_THRESHOLD", "0.7"))
FACE_ACCESS_TIMEOUT = float(os.getenv("FACE_ACCESS_TIMEOUT", "5.0"))

_last_open_ts = 0.0
_last_close_ts = 0.0
_door_state = "unknown"
sensor_store: dict[str, dict[str, Any]] = {}  # Store latest sensor data per device_id

# Face recognition access state management
_last_face_result: dict[str, Any] = {}  # {device_id: {label, confidence, timestamp}}
_last_face_update_time: float = 0.0

# Command queue for ESP32 (simple implementation)
_pending_command: dict[str, Any] = {}  # {device_id: {action, ts}}


def _fallback_label(raw_event: str) -> str:
    return label_from_raw_event(raw_event)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global FACE_RECOGNIZE_RUNTIME_ENABLED
    # init model di main thread
    get_model()
    get_attendance_state()
    face_app = None
    if FACE_RECOGNIZE_ENABLED and os.getenv("FACE_RECOGNIZE_WARMUP", "1").lower() in {"1", "true", "yes", "on"}:
        face_app = get_face_app()
        if face_app is None:
            FACE_RECOGNIZE_RUNTIME_ENABLED = False
            print("[FACE] running in fallback mode (no recognition)")
        else:
            print("[FACE] recognition warmup ok")

    if FACE_RECOGNIZE_ENABLED and face_app is not None:
        if os.getenv("FACE_CAMERA_STARTUP", "1").lower() in {"1", "true", "yes", "on"}:
            try:
                from .camera_face import start_camera_loop
                start_camera_loop()
            except Exception as exc:
                if DEBUG_FLAG:
                    print(f"[FACE] camera startup failed: {exc}")
        if FACE_PREVIEW_STARTUP:
            try:
                from .open_camera import start_preview_loop
                start_preview_loop()
            except Exception as exc:
                if DEBUG_FLAG:
                    print(f"[FACE] preview startup failed: {exc}")

    try:
        yield
    finally:
        try:
            from .camera_face import stop_camera_loop
            stop_camera_loop()
        except Exception:
            pass
        try:
            from .open_camera import stop_preview_loop
            stop_preview_loop()
        except Exception:
            pass

app = FastAPI(
    title="Time Sense Backend",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(face_router)

subscribers: Set[asyncio.Queue] = set()

async def broadcast_event(payload: dict):
    for q in list(subscribers):
        await q.put(payload)
        try:
            q.put_nowait(payload)
        except Exception:
            pass


async def maybe_capture_face() -> Optional[dict[str, Any]]:
    global FACE_RECOGNIZE_RUNTIME_ENABLED
    if not FACE_RECOGNIZE_RUNTIME_ENABLED:
        return None
    if get_face_app() is None:
        FACE_RECOGNIZE_RUNTIME_ENABLED = False
        return None
    try:
        if DEBUG_FLAG:
            print("[FACE] capture requested")
        from .camera_face import capture_and_recognize

        return await asyncio.wait_for(
            asyncio.to_thread(
                capture_and_recognize,
                FACE_ME_IDENTITY,
                FACE_THR_STRICT,
                FACE_THR_LOOSE,
            ),
            timeout=FACE_RECOGNIZE_TIMEOUT,
        )
    except asyncio.TimeoutError:
        if DEBUG_FLAG:
            print("[FACE] capture timeout")
        return None
    except Exception as exc:
        if DEBUG_FLAG:
            print(f"[FACE] capture failed: {exc}")
        return None

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if CORS_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def check_api_key(x_api_key: str | None):
    if API_KEY:
        if not x_api_key or x_api_key != API_KEY:
            raise HTTPException(status_code=401, detail="Invalid API key")


def _ts_to_iso(ts: float) -> Optional[str]:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, ZoneInfo(TZ_NAME)).isoformat()

def _validate_distance(value: Optional[float]) -> float:
    """Validate sensor distance value.
    
    Return -1 if distance <= 0 or > 400 cm (invalid).
    Return 0.0 if None.
    Otherwise return the value as is.
    """
    if value is None:
        return 0.0
    
    if isinstance(value, (int, float)):
        val_num = float(value)
        # Return -1 for invalid distances (negative, zero, or > 400)
        if val_num <= 0 or val_num > 400:
            return -1.0
        return val_num
    
    return 0.0


def build_features(payload: IngestEvent, now: datetime) -> dict:
    return {
        "raw_event": payload.raw_event,
        "hour": now.hour,
        "dow": now.isoweekday(),  # 1-7
        "minute_of_day": now.hour * 60 + now.minute,
        "device_id": payload.device_id,
        "distance1_cm": _validate_distance(payload.distance1_cm),
        "distance2_cm": _validate_distance(payload.distance2_cm),
        "rssi": payload.rssi if payload.rssi is not None else -999,
    }


def _normalize_face_meta(meta: dict | None) -> Optional[dict[str, Any]]:
    if not meta:
        return None
    face_meta = meta.get("face_recognition")
    if isinstance(face_meta, dict):
        # Convert new format (identity, confidence, timestamp) to old format for backward compatibility
        normalized = dict(face_meta)
        if "identity" in normalized and "face_label" not in normalized:
            normalized["face_label"] = normalized["identity"]
        if "confidence" in normalized and "face_conf" not in normalized:
            normalized["face_conf"] = normalized["confidence"]
        return normalized
    keys = {"face_label", "face_is_me", "face_is_known", "face_dist", "face_conf", "face_info"}
    if any(k in meta for k in keys):
        return {k: meta.get(k) for k in keys if k in meta}
    return None


def _coerce_int(val: Any, default: int = 0) -> int:
    try:
        if val is None:
            return default
        if isinstance(val, bool):
            return int(val)
        if isinstance(val, (int, float)):
            return int(val)
        return int(str(val).strip())
    except Exception:
        return default


def _log_event(event: str, payload: dict | None = None) -> None:
    if not DEBUG_FLAG:
        return
    base = {"event": event, "ts": time.time()}
    if payload:
        base.update(payload)
    print(json.dumps(base, ensure_ascii=False))


def _update_access_decision_from_face(face_meta: Optional[dict[str, Any]], *, device_id: Optional[str]) -> None:
    if not face_meta:
        return

    access_state = get_access_state()
    identity = access_identity_from_face(face_meta, FACE_ME_IDENTITY)
    if identity:
        access_state.set_allow(identity=identity, source_device_id=device_id)
        _log_event("access_decision_updated", {"device_id": device_id, "access": "allow", "identity": identity})
        return

    access_state.set_deny(source_device_id=device_id)
    _log_event(
        "access_decision_updated",
        {"device_id": device_id, "access": "deny", "label": face_meta.get("face_label")},
    )


def _send_esp32_command(path: str) -> bool:
    if not ESP32_BASE_URL:
        return False
    url = ESP32_BASE_URL.rstrip("/") + path
    data = json.dumps({"source": "time-sense"}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if ESP32_API_KEY:
        headers["X-API-Key"] = ESP32_API_KEY

    attempts = max(1, ESP32_RETRIES + 1)
    for attempt in range(1, attempts + 1):
        req = urllib.request.Request(url, headers=headers)
        if ESP32_COMMAND_METHOD == "GET":
            req.get_method = lambda: "GET"
            req.data = None
        else:
            req.data = data

        try:
            with urllib.request.urlopen(req, timeout=ESP32_TIMEOUT) as resp:
                status = getattr(resp, "status", 200)
                if 200 <= status < 300:
                    _log_event("esp32_command_ok", {"path": path, "status": status})
                    return True
                _log_event("esp32_command_failed", {"path": path, "status": status})
        except urllib.error.URLError as exc:
            _log_event("esp32_command_failed", {"path": path, "error": str(exc)})

        if attempt < attempts:
            time.sleep(max(ESP32_RETRY_DELAY, 0.1))
    return False


def _maybe_open_door(face_meta: Optional[dict[str, Any]]) -> bool:
    global _last_open_ts, _door_state
    if not face_meta:
        return False
    conf = face_meta.get("face_conf")
    if conf is not None and isinstance(conf, (int, float)) and conf < ESP32_OPEN_MIN_CONF:
        return False
    is_me = _coerce_int(face_meta.get("face_is_me", 0))
    is_known = _coerce_int(face_meta.get("face_is_known", 0))
    if not (is_me or is_known):
        return False
    if _door_state == "open":
        return False
    now_ts = datetime.now().timestamp()
    if now_ts - _last_open_ts < ESP32_OPEN_COOLDOWN:
        return False
    if _send_esp32_command(ESP32_OPEN_PATH):
        _last_open_ts = now_ts
        _door_state = "open"
        return True
    return False


def _maybe_close_door(predicted_label: Optional[str]) -> bool:
    global _last_close_ts, _door_state
    if not predicted_label:
        return False
    if predicted_label not in {"ANDA_PULANG", "SAYA_MASUK", "TEMAN_MASUK"}:
        return False
    if _door_state == "closed":
        return False
    now_ts = datetime.now().timestamp()
    if now_ts - _last_close_ts < ESP32_CLOSE_COOLDOWN:
        return False
    if _send_esp32_command(ESP32_CLOSE_PATH):
        _last_close_ts = now_ts
        _door_state = "closed"
        return True
    return False


def _record_event(
    db: Session,
    background_tasks: BackgroundTasks,
    *,
    device_id: str,
    raw_event: str,
    predicted_label: Optional[str] = None,
    confidence: Optional[float] = None,
    payload: Optional[dict] = None,
) -> Optional[Event]:
    try:
        now = datetime.now(ZoneInfo(TZ_NAME))
        ev = Event(
            device_id=device_id,
            raw_event=raw_event,
            predicted_label=predicted_label,
            confidence=confidence,
            server_received_at=now,
            payload_json=json.dumps(payload, ensure_ascii=False) if payload else None,
        )
        db.add(ev)
        db.commit()
        db.refresh(ev)
        background_tasks.add_task(
            broadcast_event,
            {
                "id": ev.id,
                "device_id": ev.device_id,
                "raw_event": ev.raw_event,
                "predicted_label": ev.predicted_label,
                "confidence": ev.confidence,
                "server_received_at": ev.server_received_at.isoformat(),
            },
        )
        return ev
    except Exception as exc:
        if DEBUG_FLAG:
            print(f"[EVENT] store failed: {exc}")
    return None

@app.get("/api/model/status")
def model_status():
    m = get_model()
    return {"enabled": m.enabled, "path": m.rds_path}

@app.post("/api/model/debug-score")
def debug_score(
    payload: IngestEvent,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    check_api_key(x_api_key)
    now = datetime.now(ZoneInfo(TZ_NAME))
    features = build_features(payload, now)
    if payload.meta:
        # optional override for debug-only testing
        if "hour" in payload.meta:
            features["hour"] = int(payload.meta["hour"])
            features["minute_of_day"] = int(payload.meta["hour"]) * 60 + int(payload.meta.get("minute", 0))
        if "dow" in payload.meta:
            features["dow"] = int(payload.meta["dow"])
        if "person" in payload.meta:
            features["person"] = int(payload.meta["person"])
        if "go" in payload.meta:
            features["go"] = float(payload.meta["go"])
        if "home" in payload.meta:
            features["home"] = float(payload.meta["home"])
        if "work" in payload.meta:
            features["work"] = float(payload.meta["work"])
    model = get_model()
    return model.debug_score(features)

@app.get("/health")
def health():
    """Health check endpoint - simple and fast response"""
    print("[API] GET /health")
    try:
        return {"ok": True, "tz": TZ_NAME}
    except Exception as e:
        print(f"[API] /health error: {e}")
        return {"ok": False, "error": str(e)}


@app.get("/api/health")
def api_health():
    """API health check endpoint for external devices (ESP32) - no auth required"""
    print("[API] GET /api/health")
    try:
        return {"status": "ok", "service": "time-sense-backend"}
    except Exception as e:
        print(f"[API] /api/health error: {e}")
        return {"status": "error", "error": str(e)}


@app.get("/api/door/status")
def door_status():
    return {
        "ok": True,
        "state": _door_state,
        "last_open_at": _ts_to_iso(_last_open_ts),
        "last_close_at": _ts_to_iso(_last_close_ts),
        "esp32_base_url": ESP32_BASE_URL,
    }


@app.get("/api/face/status")
def face_status():
    last = get_last_face()
    if not last:
        return {"ok": True, "cached": False}
    age = time.time() - float(last.get("ts", 0))
    meta = last.get("meta") or {}
    return {
        "ok": True,
        "cached": True,
        "device_id": last.get("device_id"),
        "age_seconds": round(age, 2),
        "ttl_seconds": FACE_META_TTL_SECONDS,
        "label": meta.get("face_label"),
        "conf": meta.get("face_conf"),
    }


@app.get("/api/access")
def get_access(device_id: Optional[str] = None):
    """Get access decision for ESP32 - read-only, non-consuming.
    
    This queries the AccessState for the current device's access status.
    State automatically expires after ACCESS_TIMEOUT seconds.
    
    Multiple polls return the same result until timeout.
    
    Returns:
    {
        "access": "allow" | "deny",
        "identity": label | null
    }
    """
    print(f"[API] GET /api/access device_id={device_id}")
    try:
        access_state = get_access_state()
        result = access_state.get_current(device_id=device_id)
        print(f"[API] /api/access response: {result}")
        return result
    except Exception as e:
        print(f"[API] /api/access error: {e}")
        return {"access": "deny", "error": str(e)}


@app.get("/api/command")
def get_command(device_id: Optional[str] = None):
    """Get pending commands for ESP32 based on face recognition access.
    
    If access is allowed → send OPEN command
    If any other pending command → send that
    Otherwise → return None
    
    Returns:
    {
        "action": "open_door" | null
    }
    """
    print(f"[API] GET /api/command device_id={device_id}")
    try:
        # Check if access is allowed - consume it one time
        access_state = get_access_state()
        result = access_state.consume(device_id=device_id)
        
        if result.get("access") == "allow":
            print(f"[API] /api/command: access allowed, sending open_door")
            return {"action": "open_door"}
        
        # Access not allowed
        print(f"[API] /api/command: access denied, no action")
        return {"action": None}
    except Exception as e:
        print(f"[API] /api/command error: {e}")
        return {"action": None, "error": str(e)}


@app.post("/api/command/execute")
def command_execute(payload: dict):
    """Execute a manual command from WA bot, frontend, or other source.
    
    Expected payload:
    {
        "device_id": "esp32-1" or variant,
        "action": "open_door" | "lock" | "unlock",
        "requester": optional (who requested - "wa_bot", "frontend", etc)
    }
    
    Returns:
    { "ok": true, "action": "open_door", "queued": true }
    """
    print(f"[API] POST /api/command/execute payload={payload}")
    try:
        raw_device_id = payload.get("device_id")
        if not raw_device_id:
            return {"ok": False, "error": "device_id required"}
        
        # Validate payload
        valid, errors = validate_command_execute(payload)
        if not valid:
            print(f"[COMMAND] Validation failed: {errors}")
            return {"ok": False, "error": "; ".join(errors)}
        
        # Normalize device_id
        device_id = resolve_device_id(raw_device_id)
        action = payload.get("action")
        requester = payload.get("requester", "system")
        
        print(f"[COMMAND] Execute: {action} on {device_id} (by {requester})")
        
        # Queue the command
        queue = get_command_queue()
        queue.enqueue(device_id, Command(action=action, priority=15))
        
        # If it's open_door, also set access state for backward compatibility
        if action == "open_door":
            access_state = get_access_state()
            access_state.set_allow(
                identity="manual",
                device_id=device_id,
                source_device_id=requester
            )
        
        return {
            "ok": True,
            "action": action,
            "queued": True,
            "device_id": device_id
        }
    except Exception as e:
        print(f"[API] /api/command/execute error: {e}")
        return {"ok": False, "error": str(e)}


@app.get("/api/debug/access-state")
def debug_access_state(device_id: Optional[str] = None):
    """Debug endpoint: Get current access state for all devices (or specific device_id).
    
    Returns raw access state dict for debugging state synchronization issues.
    """
    access_state = get_access_state()
    
    if device_id:
        # Return state for specific device
        target = access_state._resolve_target_device_id(device_id=device_id)
        now = time.time()
        state = access_state._states.get(target, {})
        
        # Check if expired
        expires_at = state.get("expires_at", 0)
        is_expired = expires_at > 0 and now >= expires_at
        
        return {
            "device_id": device_id,
            "resolved_target": target,
            "now": now,
            "state": dict(state),
            "is_expired": is_expired,
            "expires_in_seconds": max(0, expires_at - now) if expires_at > 0 else None,
        }
    
    # Return all states
    now = time.time()
    all_states = {}
    for target, state in access_state.get_all_states().items():
        expires_at = state.get("expires_at", 0)
        is_expired = expires_at > 0 and now >= expires_at
        all_states[target] = {
            "state": dict(state),
            "is_expired": is_expired,
            "expires_in_seconds": max(0, expires_at - now) if expires_at > 0 else None,
        }
    
    return {
        "now": now,
        "device_states": all_states,
        "total_devices": len(all_states),
    }


@app.post("/api/sensor/update")
async def sensor_update(payload: dict):
    """Accept sensor updates from ESP32 with validation - no auth required
    
    Expected payload format (new):
    {
        "device_id": "esp32-001" or variant,
        "distance1": 15.5,
        "distance2": 20.3,
        "temperature": optional (°C)
    }
    
    Or legacy format:
    {
        "device_id": "esp32-001",
        "sensor_type": "temperature" | "motion" | "door_state",
        "value": any,
        "timestamp": optional
    }
    
    Returns:
    { "ok": true, "stored": {...} }
    """
    print(f"[API] POST /api/sensor/update payload={payload}")
    try:
        device_id = payload.get("device_id", "esp32-1")
        
        # Try new format first (with distance1, distance2)
        if "distance1" in payload or "distance2" in payload:
            # New format - validate
            valid, errors = validate_sensor_update(payload)
            if not valid:
                print(f"[SENSOR] Validation failed: {errors}")
                return {
                    "ok": False,
                    "error": "; ".join(errors)
                }
            
            # Normalize device_id
            device_id = resolve_device_id(device_id)
            
            distance1 = float(payload.get("distance1"))
            distance2 = float(payload.get("distance2"))
            temperature = float(payload.get("temperature", 0.0))
            
            print(f"[SENSOR] {device_id}: d1={distance1}cm, d2={distance2}cm, t={temperature}°C")
            
            # Store sensor data
            access_state = get_access_state()
            if device_id not in access_state._states:
                access_state._states[device_id] = {}
            
            access_state._states[device_id]["distance1"] = distance1
            access_state._states[device_id]["distance2"] = distance2
            access_state._states[device_id]["temperature"] = temperature
            access_state._states[device_id]["sensor_updated_at"] = time.time()
            
            # Also store in legacy sensor_store
            if device_id not in sensor_store:
                sensor_store[device_id] = {}
            sensor_store[device_id]["distance1"] = distance1
            sensor_store[device_id]["distance2"] = distance2
            if temperature:
                sensor_store[device_id]["temperature"] = temperature
            
            print(f"[API] /api/sensor/update OK device_id={device_id}")
            return {
                "ok": True,
                "stored": {
                    "device_id": device_id,
                    "distance1": distance1,
                    "distance2": distance2,
                    "temperature": temperature
                }
            }
        
        # Legacy format (sensor_type based)
        sensor_type = payload.get("sensor_type", "unknown")
        value = payload.get("value")
        ts = payload.get("timestamp", time.time())
        
        # Normalize device_id
        device_id = resolve_device_id(device_id)
        
        print(f"[SENSOR] {device_id} {sensor_type}={value} (legacy format)")
        
        # Store latest sensor data per device_id
        if device_id not in sensor_store:
            sensor_store[device_id] = {}
        
        sensor_store[device_id][sensor_type] = {
            "value": value,
            "ts": ts,
        }
        
        print(f"[API] /api/sensor/update OK device_id={device_id}")
        return {"ok": True, "status": "ok", "message": "sensor data received"}
    except Exception as e:
        print(f"[API] /api/sensor/update error: {e}")
        return {"ok": False, "error": str(e)}


@app.get("/api/sensor/latest")
def get_sensor_latest(device_id: str = "esp32-1"):
    """Get latest sensor data for a device
    
    Query params:
    - device_id: device identifier (default: esp32-1)
    
    Response format:
    {
        "distance1": number (cm),
        "distance2": number (cm),
        "ts": timestamp
    }
    """
    print(f"[API] GET /api/sensor/latest device_id={device_id}")
    try:
        # Get distance1 and distance2 from sensor_store
        device_data = sensor_store.get(device_id, {})
        
        # Extract distance1 and distance2 values
        distance1_data = device_data.get("distance1", {})
        distance2_data = device_data.get("distance2", {})
        
        distance1 = distance1_data.get("value")
        distance2 = distance2_data.get("value")
        ts = time.time()
        
        # Use the most recent timestamp from either sensor
        if isinstance(distance1_data.get("ts"), (int, float)):
            ts = max(ts, distance1_data.get("ts", ts))
        if isinstance(distance2_data.get("ts"), (int, float)):
            ts = max(ts, distance2_data.get("ts", ts))
        
        response = {
            "distance1": distance1,
            "distance2": distance2,
            "ts": ts,
        }
        
        print(f"[API] /api/sensor/latest OK distance1={distance1} distance2={distance2}")
        return response
    except Exception as e:
        print(f"[API] /api/sensor/latest error: {e}")
        return {"distance1": None, "distance2": None, "ts": time.time(), "error": str(e)}


def _process_face_recognition(device_id: str, label: str, confidence: float) -> dict[str, Any]:
    """Process face recognition result and update access state.
    
    Args:
        device_id: Source device ID
        label: Recognized label (identity)
        confidence: Confidence score (0-1)
    
    Returns:
        Access decision {access: allow|deny, identity: label|None}
    """
    global _last_face_result, _last_face_update_time
    
    now = time.time()
    _last_face_update_time = now
    
    # Store face result
    _last_face_result = {
        "device_id": device_id,
        "label": label,
        "confidence": confidence,
        "timestamp": now,
    }
    
    print(f"[FACE] Processing: label={label}, confidence={confidence}, threshold={FACE_CONFIDENCE_THRESHOLD}")
    
    access_state = get_access_state()
    
    # Determine access based on confidence threshold
    if confidence >= FACE_CONFIDENCE_THRESHOLD and label != "unknown":
        # High confidence - allow access
        access_state.set_allow(identity=label, device_id=device_id, source_device_id=device_id)
        result = {"access": "allow", "identity": label}
        print(f"[FACE] ACCESS ALLOWED: {label} (conf: {confidence})")
    else:
        # Low confidence or unknown - deny access
        access_state.set_deny(device_id=device_id, source_device_id=device_id)
        result = {"access": "deny", "identity": None}
        print(f"[FACE] ACCESS DENIED: {label} (conf: {confidence})")
    
    return result


@app.post("/api/face/ingest")
def ingest_face(
    payload: dict,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    """Accept face recognition results with validation and device ID normalization.
    
    Expected payload:
    {
        "device_id": "esp32-1" or "face-service" or any variant,
        "label": "saya" | "teman" | "unknown",
        "confidence": 0.95
    }
    
    Or legacy format with nested meta (for backward compatibility).
    """
    print(f"[API] POST /api/face/ingest payload={payload}")
    try:
        check_api_key(x_api_key)
        
        # Try new simple format first
        label = payload.get("label")
        confidence = payload.get("confidence")
        raw_device_id = payload.get("device_id")
        
        if label is not None and confidence is not None:
            # New simple format - validate first
            valid, errors = validate_face_ingest(payload)
            if not valid:
                print(f"[API] /api/face/ingest validation failed: {errors}")
                return {
                    "ok": False,
                    "access": "deny",
                    "error": "; ".join(errors)
                }
            
            # Normalize device_id
            device_id = resolve_device_id(raw_device_id)
            label = str(label).strip()
            confidence = float(confidence)
            
            print(f"[API] /api/face/ingest new format: raw_device={raw_device_id}, device_id={device_id}, label={label}, conf={confidence}")
            
            # Process face recognition and update access state
            result = _process_face_recognition(device_id, label, confidence)
            
            # Queue door open command if allowed
            if result["access"] == "allow":
                queue = get_command_queue()
                queue.enqueue(device_id, Command(action="open_door", priority=20))
            
            # Record event
            _record_event(
                db,
                background_tasks,
                device_id=device_id,
                raw_event="FACE_DETECTED",
                predicted_label=label,
                confidence=confidence,
                payload=payload,
            )
            
            print(f"[API] /api/face/ingest OK result={result}")
            return {"ok": True, "access": result["access"], "identity": result["identity"]}
        
        # Legacy format handling
        meta = _normalize_face_meta(payload)
        if not meta:
            print("[API] /api/face/ingest: face meta or simple payload is required")
            raise HTTPException(
                status_code=400,
                detail="Payload harus contain: device_id, label, confidence (atau format legacy dengan meta)"
            )
        
        # Legacy path (maintain backward compatibility)
        device_id = resolve_device_id(raw_device_id)
        cached = cache_face(meta, device_id=device_id)
        _log_event("face_cached", {"device_id": device_id, "label": meta.get("face_label")})
        _update_access_decision_from_face(meta, device_id=device_id)
        door_opened = _maybe_open_door(meta)
        face_label = meta.get("face_label") or "unknown"
        confidence = meta.get("face_conf")
        _record_event(
            db,
            background_tasks,
            device_id=device_id or "face-backend",
            raw_event=str(payload.get("raw_event") or "FACE_DETECTED"),
            predicted_label=str(face_label),
            confidence=float(confidence) if isinstance(confidence, (int, float)) else None,
            payload=payload,
        )
        if door_opened:
            _record_event(
                db,
                background_tasks,
                device_id=device_id or "door",
                raw_event="DOOR_OPEN_COMMAND",
                predicted_label="PINTU_BUKA",
                payload={"source": "face", "face_label": face_label},
            )
        print(f"[API] /api/face/ingest OK cached_at={cached.get('ts')}")
        return {"ok": True, "cached_at": cached.get("ts")}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[API] /api/face/ingest error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/events/ingest", response_model=EventOut)
async def ingest_event(
    payload: IngestEvent,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):

    check_api_key(x_api_key)

    now = datetime.now(ZoneInfo(TZ_NAME))
    payload_dict = payload.model_dump()

    if is_semantic_access_event(payload.raw_event):
        predicted_label = label_from_raw_event(payload.raw_event)
        attendance_state = get_attendance_state()
        attendance_state.update(
            device_id=payload.device_id,
            raw_event=payload.raw_event,
            minute_of_day=now.hour * 60 + now.minute,
            event_time=now,
            person_id=raw_event_person_id(payload.raw_event),
        )

        ev = _record_event(
            db,
            background_tasks,
            device_id=payload.device_id,
            raw_event=payload.raw_event,
            predicted_label=predicted_label,
            confidence=1.0,
            payload=payload_dict,
        )
        if ev is None:
            raise HTTPException(status_code=500, detail="failed to store event")

        door_closed = _maybe_close_door(predicted_label)
        if door_closed:
            _record_event(
                db,
                background_tasks,
                device_id=payload.device_id,
                raw_event="DOOR_CLOSE_COMMAND",
                predicted_label="PINTU_TUTUP",
                payload={"source": "esp32_event", "predicted_label": predicted_label},
            )

        return EventOut(
            id=ev.id,
            device_id=ev.device_id,
            raw_event=ev.raw_event,
            predicted_label=ev.predicted_label,
            confidence=ev.confidence,
            server_received_at=ev.server_received_at.isoformat(),
        )

    # Step 1: belum pakai model; sementara mapping sederhana
    model = get_model()

    # fitur minimal untuk model (bisa kamu tambah nanti)
    features = build_features(payload, now)

    face_result = _normalize_face_meta(payload.meta)
    face_from_meta = face_result is not None
    face_from_cache = False

    if not face_result:
        cached = get_cached_face(FACE_META_TTL_SECONDS)
        if cached:
            face_result = cached.get("meta")
            face_from_cache = True
            _log_event("face_cache_used", {"device_id": cached.get("device_id")})

    if not face_result:
        face_result = await maybe_capture_face()

    if face_result:
        if DEBUG_FLAG:
            source = "meta" if face_from_meta else ("cache" if face_from_cache else "camera")
            print(f"[FACE] capture ok ({source}):", face_result)
        if payload.meta and "person" in payload.meta:
            features["person"] = int(payload.meta["person"])
        else:
            if "face_is_me" not in face_result and "face_label" in face_result:
                face_result["face_is_me"] = int(
                    str(face_result.get("face_label")) == FACE_ME_IDENTITY
                )
            features["person"] = _coerce_int(face_result.get("face_is_me", 0))
        features["face_conf"] = face_result.get("face_conf")
        features["face_dist"] = face_result.get("face_dist")
        features["face_label"] = face_result.get("face_label")
    else:
        if not FACE_RECOGNIZE_RUNTIME_ENABLED:
            print("[FACE] skipped, proceed without face features")
        elif DEBUG_FLAG:
            print("[FACE] no face result, proceed without face features")

    person_id = None
    if payload.meta and "person" in payload.meta:
        try:
            person_id = int(payload.meta["person"])
        except Exception:
            person_id = None
    elif "person" in features:
        person_id = features.get("person")
    if person_id is not None:
        features["person"] = int(person_id)

    attendance_state = get_attendance_state()
    attendance = attendance_state.update(
        device_id=payload.device_id,
        raw_event=payload.raw_event,
        minute_of_day=features.get("minute_of_day"),
        event_time=now,
        person_id=person_id,
    )
    features["go"] = attendance.get("go")
    features["home"] = attendance.get("home")
    features["work"] = attendance.get("work")

    should_score = attendance_state.should_score_anomaly(
        features.get("go"),
        features.get("home"),
        features.get("work"),
    )

    if should_score:
        res = model.predict(features)
        predicted_label = res.label
        confidence = res.confidence
    else:
        predicted_label = _fallback_label(payload.raw_event)
        confidence = 0.0

    if DEBUG_FLAG:
        print("[MODEL] features:", features, "=>", predicted_label, confidence)

    if face_result:
        meta = dict(payload_dict.get("meta") or {})
        meta["face_recognition"] = face_result
        if face_from_cache:
            meta["face_source"] = "cache"
        payload_dict["meta"] = meta
        if not face_from_cache:
            _update_access_decision_from_face(face_result, device_id=payload.device_id)

    ev = Event(
        device_id=payload.device_id,
        raw_event=payload.raw_event,
        predicted_label=predicted_label,
        confidence=confidence,
        server_received_at=now,
        payload_json=json.dumps(payload_dict, ensure_ascii=False),
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)

    try:
        background_tasks.add_task(
            broadcast_event,
            {
                "id": ev.id,
                "device_id": ev.device_id,
                "raw_event": ev.raw_event,
                "predicted_label": ev.predicted_label,
                "confidence": ev.confidence,
                "server_received_at": ev.server_received_at.isoformat(),
            },
        )
    except Exception as e:
        print("broadcast failed:", e)

    door_closed = _maybe_close_door(predicted_label)
    if door_closed:
        _record_event(
            db,
            background_tasks,
            device_id=payload.device_id,
            raw_event="DOOR_CLOSE_COMMAND",
            predicted_label="PINTU_TUTUP",
            payload={"source": "model", "predicted_label": predicted_label},
        )

    return EventOut(
        id=ev.id,
        device_id=ev.device_id,
        raw_event=ev.raw_event,
        predicted_label=ev.predicted_label,
        confidence=ev.confidence,
        server_received_at=ev.server_received_at.isoformat(),
    )


@app.post("/api/camera/start")
def start_camera_preview(x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    check_api_key(x_api_key)
    try:
        if get_face_app() is None:
            return {"ok": False, "error": "face recognition disabled"}
        from .open_camera import start_preview_loop, preview_status
        start_preview_loop()
        return {"ok": True, "status": preview_status()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/camera/stop")
def stop_camera_preview(x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    check_api_key(x_api_key)
    try:
        from .open_camera import stop_preview_loop, preview_status
        stop_preview_loop()
        return {"ok": True, "status": preview_status()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/camera/status")
def camera_preview_status(x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    check_api_key(x_api_key)
    from .open_camera import preview_status
    return {"ok": True, "face_enabled": get_face_app() is not None, "status": preview_status()}

@app.get("/api/notifications", response_model=list[EventOut])
def get_notifications(limit: int = 50, db: Session = Depends(get_db)):
    rows = db.query(Event).order_by(Event.server_received_at.desc()).limit(limit).all()
    return [
        EventOut(
            id=r.id,
            device_id=r.device_id,
            raw_event=r.raw_event,
            predicted_label=r.predicted_label,
            confidence=r.confidence,
            server_received_at=r.server_received_at.isoformat(),
        )
        for r in rows
    ]

@app.get("/api/history", response_model=list[EventOut])
def get_history(
    limit: int = 200,
    device_id: Optional[str] = None,
    type: Optional[str] = None,  # filter predicted_label
    db: Session = Depends(get_db),
):
    q = db.query(Event)

    if device_id:
        q = q.filter(Event.device_id == device_id)

    if type:
        q = q.filter(Event.predicted_label == type)

    rows = q.order_by(Event.server_received_at.desc()).limit(limit).all()

    return [
        EventOut(
            id=r.id,
            device_id=r.device_id,
            raw_event=r.raw_event,
            predicted_label=r.predicted_label,
            confidence=r.confidence,
            server_received_at=r.server_received_at.isoformat(),
        )
        for r in rows
    ]

@app.get("/api/stream/notifications")
async def stream_notifications():
    q: asyncio.Queue = asyncio.Queue()
    subscribers.add(q)

    async def event_generator():
        try:
            # kirim "connected" event pertama (opsional)
            yield "event: ping\ndata: connected\n\n"
            while True:
                item = await q.get()
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        finally:
            subscribers.discard(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
