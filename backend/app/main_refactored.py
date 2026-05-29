"""
Time Sense Backend — Refactored main module.
All state managed via DoorStateMachine (single source of truth).
"""

import os, json, time, asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, Any, Set

from fastapi import FastAPI, Depends, HTTPException, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .db import Base, engine, get_db
from .models import Event
from .schemas import IngestEvent, EventOut
from .rds_model import get_model
from .face_router import router as face_router, get_face_app
from .face_cache import update_face as cache_face, get_face as get_cached_face, get_last_face
from .attendance_state import get_attendance_state
from .door_state import get_door_state
from .config import resolve_device_id
from dotenv import load_dotenv
from contextlib import asynccontextmanager

load_dotenv()
Base.metadata.create_all(bind=engine)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
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


def check_api_key(x_api_key: str | None):
    if API_KEY:
        if not x_api_key or x_api_key != API_KEY:
            raise HTTPException(status_code=401, detail="Invalid API key")


def _log_event(event: str, payload: dict | None = None) -> None:
    if not DEBUG_FLAG:
        return
    base = {"event": event, "ts": time.time()}
    if payload:
        base.update(payload)
    print(json.dumps(base, ensure_ascii=False))


# ---------------------------------------------------------------------------
# SSE subscribers
# ---------------------------------------------------------------------------
subscribers: Set[asyncio.Queue] = set()


async def broadcast_event(payload: dict):
    for q in list(subscribers):
        try:
            q.put_nowait(payload)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Record event helper
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Face capture helper (camera)
# ---------------------------------------------------------------------------
async def maybe_capture_face() -> Optional[dict[str, Any]]:
    global FACE_RECOGNIZE_RUNTIME_ENABLED
    if not FACE_RECOGNIZE_RUNTIME_ENABLED:
        return None
    if get_face_app() is None:
        FACE_RECOGNIZE_RUNTIME_ENABLED = False
        return None
    try:
        from .camera_face import capture_and_recognize
        return await asyncio.wait_for(
            asyncio.to_thread(capture_and_recognize, FACE_ME_IDENTITY, FACE_THR_STRICT, FACE_THR_LOOSE),
            timeout=FACE_RECOGNIZE_TIMEOUT,
        )
    except (asyncio.TimeoutError, Exception):
        return None


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global FACE_RECOGNIZE_RUNTIME_ENABLED
    get_model()
    get_attendance_state()
    get_door_state()  # Initialize singleton

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


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Time Sense Backend", version="2.0.0", lifespan=lifespan)
app.include_router(face_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if CORS_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===================================================================
#  HEALTH
# ===================================================================
@app.get("/health")
def health():
    return {"ok": True, "tz": TZ_NAME}


@app.get("/api/health")
def api_health():
    return {"status": "ok", "service": "time-sense-backend"}


# ===================================================================
#  FACE INGEST — with cooldown
# ===================================================================
@app.post("/api/face/ingest")
async def ingest_face(
    payload: dict,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    check_api_key(x_api_key)
    label = payload.get("label")
    confidence = payload.get("confidence")
    raw_device_id = payload.get("device_id")

    # Validate
    if label is None or confidence is None:
        raise HTTPException(status_code=400, detail="label and confidence required")

    try:
        confidence = float(confidence)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="confidence must be a number")

    if not raw_device_id:
        raise HTTPException(status_code=400, detail="device_id required")

    device_id = resolve_device_id(raw_device_id)
    label = str(label).strip()

    door = get_door_state()
    async with door.lock:
        # Cooldown check
        if door.is_face_cooldown(label):
            return {"ok": True, "access": "cooldown", "identity": None, "message": "face ignored (cooldown)"}

        result = door.grant_access(label, confidence, source="face")

    # Record event (outside lock)
    _record_event(
        db, background_tasks,
        device_id=device_id, raw_event="FACE_DETECTED",
        predicted_label=label, confidence=confidence, payload=payload,
    )
    _log_event("face_ingest", {"device_id": device_id, "label": label, "access": result["access"]})

    return {"ok": True, "access": result["access"], "identity": result.get("identity")}


# ===================================================================
#  ACCESS — read-only for ESP polling
# ===================================================================
@app.get("/api/access")
async def get_access(device_id: Optional[str] = None):
    door = get_door_state()
    result = door.get_access_status()
    return result


# ===================================================================
#  COMMAND — consume-once for ESP polling
# ===================================================================
@app.get("/api/command")
async def get_command(device_id: Optional[str] = None):
    door = get_door_state()
    async with door.lock:
        result = door.consume_pending_command()
    return result


# ===================================================================
#  COMMAND EXECUTE — from WA bot / dashboard
# ===================================================================
@app.post("/api/command/execute")
async def command_execute(payload: dict):
    raw_device_id = payload.get("device_id")
    action = payload.get("action")
    requester = payload.get("requester", "system")

    if not raw_device_id:
        return {"ok": False, "error": "device_id required"}

    valid_actions = {"open_door", "close_door", "enable", "disable"}
    if action not in valid_actions:
        return {"ok": False, "error": f"invalid action: {action}. Valid: {valid_actions}"}

    device_id = resolve_device_id(raw_device_id)
    door = get_door_state()

    async with door.lock:
        if action == "open_door":
            result = door.manual_open(requester=requester)
        elif action == "close_door":
            result = door.manual_close()
        elif action == "disable":
            door.system_enabled = False
            result = {"ok": True, "action": "disable"}
        elif action == "enable":
            door.system_enabled = True
            result = {"ok": True, "action": "enable"}
        else:
            result = {"ok": False, "error": "unknown action"}

    _log_event("command_execute", {"device_id": device_id, "action": action, "result": result})
    return {**result, "device_id": device_id, "action": action}


# ===================================================================
#  SENSOR UPDATE — state machine transitions
# ===================================================================
@app.post("/api/sensor/update")
async def sensor_update(payload: dict):
    device_id = resolve_device_id(payload.get("device_id", "esp32-1"))

    # Extract distances
    distance1 = payload.get("distance1")
    distance2 = payload.get("distance2")
    temperature = payload.get("temperature", 0.0)

    # Validate
    if distance1 is None or distance2 is None:
        # Legacy format fallback
        sensor_type = payload.get("sensor_type", "unknown")
        value = payload.get("value")
        door = get_door_state()
        async with door.lock:
            door.last_sensor[sensor_type] = value
            door.last_sensor["ts"] = time.time()
        return {"ok": True, "status": "ok", "message": "sensor data received (legacy)"}

    try:
        distance1 = float(distance1)
        distance2 = float(distance2)
        temperature = float(temperature)
    except (ValueError, TypeError):
        return {"ok": False, "error": "distance1/distance2 must be numbers"}

    door = get_door_state()
    event_type = None

    async with door.lock:
        event_type = door.process_sensor(distance1, distance2, temperature)

        if event_type == "entry_detected" and door.door_open:
            entry_result = door.confirm_entry()
            _log_event("entry_confirmed", {"device_id": device_id, "identity": entry_result.get("identity")})

        elif event_type == "exit_detected" and not door.door_open:
            exit_result = door.start_exit_flow()
            if exit_result.get("ok"):
                # Schedule auto-close outside lock
                asyncio.create_task(door.schedule_exit_auto_close())
                _log_event("exit_flow_started", {"device_id": device_id})

    return {
        "ok": True,
        "stored": {"device_id": device_id, "distance1": distance1, "distance2": distance2, "temperature": temperature},
        "event": event_type,
    }


# ===================================================================
#  SENSOR LATEST — never returns None
# ===================================================================
@app.get("/api/sensor/latest")
def get_sensor_latest(device_id: str = "esp32-1"):
    door = get_door_state()
    sensor = door.get_sensor_data()
    return {
        "distance1": sensor.get("distance1", 0),
        "distance2": sensor.get("distance2", 0),
        "temperature": sensor.get("temperature", 0),
        "ts": sensor.get("ts", time.time()),
    }


# ===================================================================
#  DOOR STATUS — full snapshot
# ===================================================================
@app.get("/api/door/status")
def door_status():
    door = get_door_state()
    return door.get_full_status()


# ===================================================================
#  FACE STATUS
# ===================================================================
@app.get("/api/face/status")
def face_status():
    last = get_last_face()
    if not last:
        return {"ok": True, "cached": False}
    age = time.time() - float(last.get("ts", 0))
    meta = last.get("meta") or {}
    return {
        "ok": True, "cached": True,
        "device_id": last.get("device_id"),
        "age_seconds": round(age, 2),
        "label": meta.get("face_label"),
        "conf": meta.get("face_conf"),
    }


# ===================================================================
#  MODEL
# ===================================================================
@app.get("/api/model/status")
def model_status():
    m = get_model()
    return {"enabled": m.enabled, "path": m.rds_path}


# ===================================================================
#  NOTIFICATIONS & HISTORY
# ===================================================================
@app.get("/api/notifications", response_model=list[EventOut])
def get_notifications(limit: int = 50, db: Session = Depends(get_db)):
    rows = db.query(Event).order_by(Event.server_received_at.desc()).limit(limit).all()
    return [
        EventOut(
            id=r.id, device_id=r.device_id, raw_event=r.raw_event,
            predicted_label=r.predicted_label, confidence=r.confidence,
            server_received_at=r.server_received_at.isoformat(),
        )
        for r in rows
    ]


@app.get("/api/history", response_model=list[EventOut])
def get_history(limit: int = 200, device_id: Optional[str] = None, type: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Event)
    if device_id:
        q = q.filter(Event.device_id == device_id)
    if type:
        q = q.filter(Event.predicted_label == type)
    rows = q.order_by(Event.server_received_at.desc()).limit(limit).all()
    return [
        EventOut(
            id=r.id, device_id=r.device_id, raw_event=r.raw_event,
            predicted_label=r.predicted_label, confidence=r.confidence,
            server_received_at=r.server_received_at.isoformat(),
        )
        for r in rows
    ]


# ===================================================================
#  SSE STREAM
# ===================================================================
@app.get("/api/stream/notifications")
async def stream_notifications():
    q: asyncio.Queue = asyncio.Queue()
    subscribers.add(q)

    async def event_generator():
        try:
            yield "event: ping\ndata: connected\n\n"
            while True:
                item = await q.get()
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        finally:
            subscribers.discard(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ===================================================================
#  CAMERA CONTROLS
# ===================================================================
@app.post("/api/camera/start")
def start_camera_preview(x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    check_api_key(x_api_key)
    if get_face_app() is None:
        return {"ok": False, "error": "face recognition disabled"}
    from .open_camera import start_preview_loop, preview_status
    start_preview_loop()
    return {"ok": True, "status": preview_status()}


@app.post("/api/camera/stop")
def stop_camera_preview(x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    check_api_key(x_api_key)
    from .open_camera import stop_preview_loop, preview_status
    stop_preview_loop()
    return {"ok": True, "status": preview_status()}


@app.get("/api/camera/status")
def camera_preview_status(x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    check_api_key(x_api_key)
    from .open_camera import preview_status
    return {"ok": True, "face_enabled": get_face_app() is not None, "status": preview_status()}


# ===================================================================
#  LEGACY EVENT INGEST (keep for backward compat)
# ===================================================================
def _fallback_label(raw_event: str) -> str:
    raw = str(raw_event or "").strip().upper()
    labels = {
        "SAYA_MASUK": "SAYA_MASUK", "TEMAN_MASUK": "TEMAN_MASUK", "ORANG_MASUK": "ORANG_MASUK",
        "SAYA_KELUAR": "SAYA_KELUAR", "TEMAN_KELUAR": "TEMAN_KELUAR", "ORANG_KELUAR": "ORANG_KELUAR",
        "S1_S2": "ANDA_PERGI", "S2_S1": "ANDA_PULANG",
    }
    return labels.get(raw, "UNKNOWN")


def _coerce_int(val: Any, default: int = 0) -> int:
    try:
        if val is None:
            return default
        return int(val)
    except Exception:
        return default


def _normalize_face_meta(meta: dict | None) -> Optional[dict[str, Any]]:
    if not meta:
        return None
    face_meta = meta.get("face_recognition")
    if isinstance(face_meta, dict):
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


def _validate_distance(value: Optional[float]) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        val_num = float(value)
        if val_num <= 0 or val_num > 400:
            return -1.0
        return val_num
    return 0.0


def build_features(payload: IngestEvent, now: datetime) -> dict:
    return {
        "raw_event": payload.raw_event,
        "hour": now.hour,
        "dow": now.isoweekday(),
        "minute_of_day": now.hour * 60 + now.minute,
        "device_id": payload.device_id,
        "distance1_cm": _validate_distance(payload.distance1_cm),
        "distance2_cm": _validate_distance(payload.distance2_cm),
        "rssi": payload.rssi if payload.rssi is not None else -999,
    }


def _is_semantic_access_event(raw_event: str) -> bool:
    return str(raw_event or "").strip().upper() in {
        "SAYA_MASUK", "TEMAN_MASUK", "ORANG_MASUK",
        "SAYA_KELUAR", "TEMAN_KELUAR", "ORANG_KELUAR",
    }


def _direction_from_raw_event(raw_event: str) -> str:
    mapping = {
        "S1_S2": "OUT", "S2_S1": "IN",
        "SAYA_MASUK": "IN", "TEMAN_MASUK": "IN", "ORANG_MASUK": "IN",
        "SAYA_KELUAR": "OUT", "TEMAN_KELUAR": "OUT", "ORANG_KELUAR": "OUT",
    }
    return mapping.get(str(raw_event or "").strip().upper(), "UNK")


def _raw_event_person_id(raw_event: str) -> Optional[int]:
    raw = str(raw_event or "").strip().upper()
    if raw.startswith("SAYA_"):
        return 1
    if raw.startswith("TEMAN_"):
        return 2
    return None


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

    if _is_semantic_access_event(payload.raw_event):
        predicted_label = _fallback_label(payload.raw_event)
        attendance_state = get_attendance_state()
        attendance_state.update(
            device_id=payload.device_id, raw_event=payload.raw_event,
            minute_of_day=now.hour * 60 + now.minute, event_time=now,
            person_id=_raw_event_person_id(payload.raw_event),
        )
        ev = _record_event(
            db, background_tasks, device_id=payload.device_id,
            raw_event=payload.raw_event, predicted_label=predicted_label,
            confidence=1.0, payload=payload_dict,
        )
        if ev is None:
            raise HTTPException(status_code=500, detail="failed to store event")
        return EventOut(
            id=ev.id, device_id=ev.device_id, raw_event=ev.raw_event,
            predicted_label=ev.predicted_label, confidence=ev.confidence,
            server_received_at=ev.server_received_at.isoformat(),
        )

    model = get_model()
    features = build_features(payload, now)

    face_result = _normalize_face_meta(payload.meta)
    face_from_cache = False

    if not face_result:
        cached = get_cached_face(FACE_META_TTL_SECONDS)
        if cached:
            face_result = cached.get("meta")
            face_from_cache = True

    if not face_result:
        face_result = await maybe_capture_face()

    if face_result:
        if payload.meta and "person" in payload.meta:
            features["person"] = int(payload.meta["person"])
        else:
            features["person"] = _coerce_int(face_result.get("face_is_me", 0))
        features["face_conf"] = face_result.get("face_conf")
        features["face_dist"] = face_result.get("face_dist")
        features["face_label"] = face_result.get("face_label")

    person_id = None
    if payload.meta and "person" in payload.meta:
        try:
            person_id = int(payload.meta["person"])
        except Exception:
            pass
    elif "person" in features:
        person_id = features.get("person")

    attendance_state = get_attendance_state()
    attendance = attendance_state.update(
        device_id=payload.device_id, raw_event=payload.raw_event,
        minute_of_day=features.get("minute_of_day"), event_time=now, person_id=person_id,
    )
    features["go"] = attendance.get("go")
    features["home"] = attendance.get("home")
    features["work"] = attendance.get("work")

    should_score = attendance_state.should_score_anomaly(features.get("go"), features.get("home"), features.get("work"))
    if should_score:
        res = model.predict(features)
        predicted_label = res.label
        confidence = res.confidence
    else:
        predicted_label = _fallback_label(payload.raw_event)
        confidence = 0.0

    if face_result:
        meta = dict(payload_dict.get("meta") or {})
        meta["face_recognition"] = face_result
        if face_from_cache:
            meta["face_source"] = "cache"
        payload_dict["meta"] = meta

    ev = Event(
        device_id=payload.device_id, raw_event=payload.raw_event,
        predicted_label=predicted_label, confidence=confidence,
        server_received_at=now,
        payload_json=json.dumps(payload_dict, ensure_ascii=False),
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)

    try:
        background_tasks.add_task(broadcast_event, {
            "id": ev.id, "device_id": ev.device_id, "raw_event": ev.raw_event,
            "predicted_label": ev.predicted_label, "confidence": ev.confidence,
            "server_received_at": ev.server_received_at.isoformat(),
        })
    except Exception:
        pass

    return EventOut(
        id=ev.id, device_id=ev.device_id, raw_event=ev.raw_event,
        predicted_label=ev.predicted_label, confidence=ev.confidence,
        server_received_at=ev.server_received_at.isoformat(),
    )


# ===================================================================
#  DEBUG
# ===================================================================
@app.get("/api/debug/door-state")
def debug_door_state():
    door = get_door_state()
    return door.get_full_status()
