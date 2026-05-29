import asyncio
import json
import os
import time
import urllib.request
import urllib.error
from pathlib import Path

from fastapi import FastAPI
from dotenv import load_dotenv

from .face_router import router as face_router, get_face_app
from .camera_face import start_camera_loop, stop_camera_loop, capture_and_recognize

_env_path = os.getenv("FACE_ENV_PATH", ".env.face")
if Path(_env_path).exists():
    load_dotenv(_env_path, override=True)
else:
    load_dotenv()

DEBUG_FLAG = os.getenv("DEBUG", "").lower() in {"1", "true", "yes", "on"}

FACE_LOOP_ENABLED = os.getenv("FACE_LOOP_ENABLED", "1").lower() in {"1", "true", "yes", "on"}
FACE_LOOP_INTERVAL = float(os.getenv("FACE_LOOP_INTERVAL", "1.0"))
FACE_WINDOW_SECONDS = float(os.getenv("FACE_WINDOW_SECONDS", "15"))
FACE_WINDOW_COOLDOWN = float(
    os.getenv("FACE_WINDOW_COOLDOWN", os.getenv("FACE_POST_MIN_INTERVAL", "1.5"))
)
FACE_POST_SEND_UNKNOWN = os.getenv("FACE_POST_SEND_UNKNOWN", "0").lower() in {"1", "true", "yes", "on"}
FACE_POST_MIN_CONF = float(os.getenv("FACE_POST_MIN_CONF", "0.5"))
FACE_EARLY_CONF = float(os.getenv("FACE_EARLY_CONF", "0.85"))
FACE_EARLY_MIN_SECONDS = float(os.getenv("FACE_EARLY_MIN_SECONDS", "3.0"))
FACE_EARLY_STREAK = int(os.getenv("FACE_EARLY_STREAK", "3"))

FACE_TARGET_URL = os.getenv("FACE_TARGET_URL", "http://localhost:8000/api/face/ingest")
FACE_TARGET_API_KEY = os.getenv("FACE_TARGET_API_KEY", "").strip()
FACE_DEVICE_ID = os.getenv("FACE_DEVICE_ID", "face-cam-1")
FACE_RAW_EVENT = os.getenv("FACE_RAW_EVENT", "FACE_DETECTED")

FACE_ME_IDENTITY = os.getenv("FACE_ME_IDENTITY", "me")
FACE_THR_STRICT = float(os.getenv("FACE_THR_STRICT", "0.35"))
FACE_THR_LOOSE = float(os.getenv("FACE_THR_LOOSE", "0.50"))

_stop_event = asyncio.Event()
_last_sent_label: str | None = None
_last_sent_conf: float | None = None
_last_sent_ts: float = 0.0
_window_start_ts: float | None = None
_window_best_label: str | None = None
_window_best_conf: float | None = None


def _log(msg: str) -> None:
    if DEBUG_FLAG:
        print(msg)

def _log_event(event: str, payload: dict | None = None) -> None:
    if not DEBUG_FLAG:
        return
    base = {"event": event, "ts": time.time()}
    if payload:
        base.update(payload)
    print(json.dumps(base, ensure_ascii=False))


def _set_window_status(start_ts: float, label: str, conf: float) -> None:
    global _window_start_ts, _window_best_label, _window_best_conf
    _window_start_ts = start_ts
    _window_best_label = label
    _window_best_conf = conf


def _clear_window_status() -> None:
    global _window_start_ts, _window_best_label, _window_best_conf
    _window_start_ts = None
    _window_best_label = None
    _window_best_conf = None


def _post_face(meta: dict) -> None:
    if not FACE_TARGET_URL:
        return
    
    face_label = str(meta.get("face_label", "unknown"))
    face_conf = meta.get("face_conf")
    conf_val = float(face_conf) if isinstance(face_conf, (int, float)) else 0.0
    
    # Validate before sending
    if not face_label or conf_val < 0:
        _log_event("face_post_skipped", {"reason": "invalid_label_or_confidence"})
        return
    
    # Simple payload format: device_id, label, confidence
    payload = {
        "device_id": FACE_DEVICE_ID,
        "label": face_label,
        "confidence": conf_val,
    }
    
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
    }
    if FACE_TARGET_API_KEY:
        headers["X-API-Key"] = FACE_TARGET_API_KEY
    
    req = urllib.request.Request(FACE_TARGET_URL, data=data, headers=headers, method="POST")
    try:
        _log_event("face_post_sending", {"label": face_label, "confidence": conf_val, "payload": payload})
        with urllib.request.urlopen(req, timeout=2.0) as _resp:
            resp_data = _resp.read().decode("utf-8")
            _log_event("face_post_ok", {"label": face_label, "confidence": conf_val, "response": resp_data})
            return
    except urllib.error.URLError as exc:
        _log_event("face_post_failed", {"error": str(exc), "label": face_label})


def _mark_post(meta: dict, reason: str) -> None:
    global _last_sent_label, _last_sent_conf, _last_sent_ts
    _last_sent_label = str(meta.get("face_label", "unknown"))
    conf = meta.get("face_conf")
    _last_sent_conf = float(conf) if isinstance(conf, (int, float)) else None
    _last_sent_ts = time.time()
    _log_event("face_post", {"reason": reason, "label": _last_sent_label, "conf": _last_sent_conf})


async def _face_loop() -> None:
    window_start: float | None = None
    best_meta: dict | None = None
    best_conf = -1.0
    best_known = False
    cooldown_until = 0.0
    streak_label: str | None = None
    streak_count = 0

    while not _stop_event.is_set():
        now = time.time()
        if now < cooldown_until:
            await asyncio.sleep(min(FACE_LOOP_INTERVAL, 0.5))
            continue
        try:
            result = await asyncio.to_thread(
                capture_and_recognize,
                FACE_ME_IDENTITY,
                FACE_THR_STRICT,
                FACE_THR_LOOSE,
            )
            ok = bool(result.get("ok"))
            if ok:
                label = str(result.get("face_label", "unknown"))
                conf = result.get("face_conf")
                conf_val = float(conf) if isinstance(conf, (int, float)) else 0.0
                is_known = label != "unknown"

                if is_known:
                    if streak_label == label:
                        streak_count += 1
                    else:
                        streak_label = label
                        streak_count = 1
                else:
                    streak_label = None
                    streak_count = 0

                if window_start is None:
                    window_start = now
                    _set_window_status(window_start, label, conf_val)
                    best_meta = result
                    best_conf = conf_val
                    best_known = is_known
                else:
                    if is_known and (not best_known or conf_val > best_conf):
                        best_meta = result
                        best_conf = conf_val
                        best_known = True
                        _set_window_status(window_start, label, conf_val)
                    elif not best_known and conf_val > best_conf:
                        best_meta = result
                        best_conf = conf_val
                        _set_window_status(window_start, label, conf_val)

                if (
                    is_known
                    and conf_val >= FACE_EARLY_CONF
                    and window_start is not None
                    and (now - window_start) >= FACE_EARLY_MIN_SECONDS
                    and streak_count >= max(1, FACE_EARLY_STREAK)
                ):
                    _post_face(result)
                    _mark_post(result, "early")
                    window_start = None
                    best_meta = None
                    best_conf = -1.0
                    best_known = False
                    streak_label = None
                    streak_count = 0
                    _clear_window_status()
                    cooldown_until = now + max(FACE_WINDOW_COOLDOWN, 0.5)
                    await asyncio.sleep(FACE_LOOP_INTERVAL)
                    continue

            if window_start and (now - window_start) >= FACE_WINDOW_SECONDS:
                if best_meta:
                    label = str(best_meta.get("face_label", "unknown"))
                    conf = best_meta.get("face_conf")
                    conf_val = float(conf) if isinstance(conf, (int, float)) else 0.0
                    can_send = True
                    if label == "unknown" and not FACE_POST_SEND_UNKNOWN:
                        can_send = False
                    if conf_val < FACE_POST_MIN_CONF and label != "unknown":
                        can_send = False
                    if can_send:
                        _post_face(best_meta)
                        _mark_post(best_meta, "window")
                window_start = None
                best_meta = None
                best_conf = -1.0
                best_known = False
                streak_label = None
                streak_count = 0
                _clear_window_status()
                cooldown_until = now + max(FACE_WINDOW_COOLDOWN, 0.5)
        except Exception as exc:
            _log_event("face_loop_error", {"error": str(exc)})
        await asyncio.sleep(FACE_LOOP_INTERVAL)


app = FastAPI(title="Time Sense Face Backend", version="0.1.0")
app.include_router(face_router)


@app.get("/health")
def health():
    return {
        "ok": True,
        "loop_enabled": FACE_LOOP_ENABLED,
        "loop_interval": FACE_LOOP_INTERVAL,
        "window_seconds": FACE_WINDOW_SECONDS,
        "last_sent_label": _last_sent_label,
        "last_sent_conf": _last_sent_conf,
        "last_sent_at": _last_sent_ts or None,
        "window_start": _window_start_ts,
        "window_best_label": _window_best_label,
        "window_best_conf": _window_best_conf,
    }


@app.on_event("startup")
async def _startup() -> None:
    if get_face_app() is None:
        _log("[FACE] app init failed")
    if FACE_LOOP_ENABLED:
        start_camera_loop()
        asyncio.create_task(_face_loop())


@app.on_event("shutdown")
async def _shutdown() -> None:
    _stop_event.set()
    try:
        stop_camera_loop()
    except Exception:
        pass
