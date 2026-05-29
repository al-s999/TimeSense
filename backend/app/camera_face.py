import os
import threading
import time
from typing import Dict, Any

_capture_lock = threading.Lock()
_camera_thread: threading.Thread | None = None
_camera_stop = threading.Event()
_last_frame = None
_last_frame_lock = threading.Lock()
_camera_ready = threading.Event()
_last_frame_ts = 0.0


def _require_cv2():
    try:
        import cv2  # type: ignore
    except Exception as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError("opencv-python is required for camera capture") from exc
    return cv2


def _debug_enabled() -> bool:
    return os.getenv("DEBUG", "").lower() in {"1", "true", "yes", "on"}


def _log(msg: str) -> None:
    if _debug_enabled():
        print(msg)

def _env_bool(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes", "on"}


def _get_backend_flag(cv2, name: str):
    name = (name or "").upper()
    mapping = {
        "V4L2": getattr(cv2, "CAP_V4L2", None),
        "DSHOW": getattr(cv2, "CAP_DSHOW", None),
        "MSMF": getattr(cv2, "CAP_MSMF", None),
        "AVFOUNDATION": getattr(cv2, "CAP_AVFOUNDATION", None),
    }
    return mapping.get(name)


def _open_capture(cv2, camera_index: int, width: int, height: int):
    backend = os.getenv("FACE_CAMERA_BACKEND", "").strip()
    flag = _get_backend_flag(cv2, backend)
    if flag is not None:
        cap = cv2.VideoCapture(camera_index, flag)
    else:
        cap = cv2.VideoCapture(camera_index)

    if width > 0:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    if height > 0:
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return cap


def start_camera_loop() -> None:
    global _camera_thread
    if _camera_thread and _camera_thread.is_alive():
        _log("[FACE] camera loop already running")
        return

    _camera_stop.clear()

    def _loop() -> None:
        cv2 = _require_cv2()
        camera_index = int(os.getenv("FACE_CAMERA_INDEX", "0"))
        width = int(os.getenv("FACE_CAMERA_WIDTH", "0"))
        height = int(os.getenv("FACE_CAMERA_HEIGHT", "0"))
        fps_sleep = float(os.getenv("FACE_CAMERA_SLEEP", "0.03"))
        retry_sleep = float(os.getenv("FACE_CAMERA_RETRY_SLEEP", "1.0"))
        warmup_frames = int(os.getenv("FACE_CAMERA_LOOP_WARMUP", "3"))

        while not _camera_stop.is_set():
            _camera_ready.clear()
            _log(f"[FACE] opening camera index={camera_index} width={width} height={height}")
            cap = _open_capture(cv2, camera_index, width, height)

            if not cap.isOpened():
                cap.release()
                _log("[FACE] camera loop: cannot open camera, retrying")
                time.sleep(max(retry_sleep, 0.2))
                continue

            _log("[FACE] camera loop started")
            try:
                # warmup frames to stabilize exposure
                for _ in range(max(warmup_frames, 0)):
                    ret, _ = cap.read()
                    if not ret:
                        break
                while not _camera_stop.is_set():
                    ret, frame = cap.read()
                    if ret:
                        with _last_frame_lock:
                            global _last_frame
                            _last_frame = frame
                            global _last_frame_ts
                            _last_frame_ts = time.time()
                        _camera_ready.set()
                    else:
                        _log("[FACE] camera loop: failed to read frame")
                        break
                    time.sleep(max(fps_sleep, 0.01))
            finally:
                cap.release()
                _log("[FACE] camera loop stopped")

    _camera_thread = threading.Thread(target=_loop, daemon=True)
    _camera_thread.start()


def stop_camera_loop() -> None:
    _camera_stop.set()


def _get_last_frame(timeout: float = 1.0):
    if _camera_ready.wait(timeout=timeout):
        with _last_frame_lock:
            return _last_frame
    _log("[FACE] no frame available (timeout)")
    return None


def get_latest_frame(timeout: float = 1.0):
    return _get_last_frame(timeout=timeout)


def is_camera_loop_running() -> bool:
    return bool(_camera_thread and _camera_thread.is_alive())


def capture_jpeg_bytes() -> bytes:
    cv2 = _require_cv2()
    mode = os.getenv("FACE_CAMERA_MODE", "loop")
    warmup_frames = int(os.getenv("FACE_CAMERA_WARMUP", "3"))
    frame_timeout = float(os.getenv("FACE_CAMERA_FRAME_TIMEOUT", "2.0"))
    allow_direct_fallback = _env_bool("FACE_CAMERA_DIRECT_FALLBACK", "0")

    if mode == "loop" or is_camera_loop_running():
        if not is_camera_loop_running():
            start_camera_loop()
        frame = _get_last_frame(timeout=frame_timeout)
        if frame is not None:
            ok, encoded = cv2.imencode(".jpg", frame)
            if not ok:
                raise RuntimeError("Gagal meng-encode frame kamera.")
            return encoded.tobytes()
        if not allow_direct_fallback:
            raise RuntimeError("Tidak ada frame dari camera loop (timeout).")
        _log("[FACE] loop mode fallback to direct capture")

    camera_index = int(os.getenv("FACE_CAMERA_INDEX", "0"))
    width = int(os.getenv("FACE_CAMERA_WIDTH", "0"))
    height = int(os.getenv("FACE_CAMERA_HEIGHT", "0"))

    with _capture_lock:
        _log(f"[FACE] direct capture index={camera_index} width={width} height={height} warmup={warmup_frames}")
        cap = _open_capture(cv2, camera_index, width, height)

        if not cap.isOpened():
            cap.release()
            raise RuntimeError("Camera tidak bisa dibuka.")

        frame = None
        for _ in range(max(warmup_frames, 1)):
            ret, frame = cap.read()
            if not ret:
                frame = None
                break

        cap.release()

    if frame is None:
        raise RuntimeError("Gagal mengambil frame dari kamera.")

    ok, encoded = cv2.imencode(".jpg", frame)
    if not ok:
        raise RuntimeError("Gagal meng-encode frame kamera.")

    return encoded.tobytes()


def capture_and_recognize(
    me_identity: str,
    thr_strict: float,
    thr_loose: float,
) -> Dict[str, Any]:
    from .face_router import recognize_from_bytes

    image_bytes = capture_jpeg_bytes()
    return recognize_from_bytes(
        image_bytes=image_bytes,
        me_identity=me_identity,
        thr_strict=thr_strict,
        thr_loose=thr_loose,
    )
