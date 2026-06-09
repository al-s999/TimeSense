import asyncio
import json
import os
import time

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from .camera_face import capture_jpeg_bytes, get_latest_frame
from .face_detection import detect_faces, detect_faces_raw

router = APIRouter()

DB_DIR = os.getenv("FACE_DB_DIR", "face_db")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "embeddings.npz")
META_PATH = os.path.join(DB_DIR, "meta.json")

_face_app = None
_face_enabled = True
_face_disabled_reason: str | None = None


def _disable_face(reason: str) -> None:
    global _face_enabled, _face_disabled_reason, _face_app
    _face_enabled = False
    _face_disabled_reason = reason
    _face_app = None
    print(f"[FACE] disabled: {reason}")


def is_face_enabled() -> bool:
    return bool(_face_enabled)


def face_disabled_reason() -> str | None:
    return _face_disabled_reason


def _require_numpy():
    try:
        import numpy as np
    except Exception as exc:  # pragma: no cover - runtime dependency
        raise HTTPException(
            status_code=500,
            detail="numpy is required for face enrollment",
        ) from exc
    return np


def _require_cv2():
    try:
        import cv2  # type: ignore
    except Exception as exc:  # pragma: no cover - runtime dependency
        raise HTTPException(
            status_code=500,
            detail="opencv-python is required for face enrollment",
        ) from exc
    return cv2


def _require_insightface():
    try:
        np = _require_numpy()
        major = int(str(np.__version__).split(".")[0])
        if major >= 2:
            print("[FIX] Run: pip install 'numpy<2' then restart server")
            raise HTTPException(
                status_code=500,
                detail="NumPy>=2 detected. insightface/onnxruntime requires NumPy<2. "
                "Please downgrade (e.g., pip install 'numpy<2').",
            )
        from insightface.app import FaceAnalysis
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - runtime dependency
        raise HTTPException(
            status_code=500,
            detail="insightface is required for face enrollment",
        ) from exc
    return FaceAnalysis


def get_face_app():
    global _face_app
    if not _face_enabled:
        return None
    if _face_app is None:
        try:
            FaceAnalysis = _require_insightface()
            app_face = FaceAnalysis(name="buffalo_l")
            ctx_id = int(os.getenv("FACE_CTX_ID", "0"))
            try:
                app_face.prepare(ctx_id=ctx_id, det_size=(640, 640))
            except Exception:
                # Fallback to CPU if GPU is unavailable.
                app_face.prepare(ctx_id=-1, det_size=(640, 640))
            _face_app = app_face
        except HTTPException as exc:
            detail = str(exc.detail)
            if "NumPy>=2" in detail:
                _disable_face("NumPy>=2, install numpy<2 to enable")
            else:
                _disable_face(detail)
            return None
        except Exception as exc:
            _disable_face(str(exc))
            return None
    return _face_app


def load_db():
    np = _require_numpy()
    if os.path.exists(DB_PATH):
        data = np.load(DB_PATH, allow_pickle=True)
        labels = data["labels"].tolist()
        embs = data["embeddings"]
    else:
        labels, embs = [], np.zeros((0, 512), dtype=np.float32)

    if os.path.exists(META_PATH):
        with open(META_PATH, "r") as f:
            meta = json.load(f)
    else:
        meta = {"identities": {}}
    return labels, embs, meta


def save_db(labels, embs, meta):
    np = _require_numpy()
    np.savez(DB_PATH, labels=np.array(labels, dtype=object), embeddings=embs.astype(np.float32))
    with open(META_PATH, "w") as f:
        json.dump(meta, f, indent=2)


def read_image(file_bytes: bytes):
    np = _require_numpy()
    cv2 = _require_cv2()
    arr = np.frombuffer(file_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Cannot decode image")
    return img


def extract_best_face_embedding(img_bgr):
    np = _require_numpy()
    app_face = get_face_app()
    if app_face is None:
        raise HTTPException(status_code=503, detail="face recognition disabled")
    faces = app_face.get(img_bgr)
    if not faces:
        return None, None
    faces_sorted = sorted(
        faces,
        key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]),
        reverse=True,
    )
    f0 = faces_sorted[0]
    emb = f0.normed_embedding.astype(np.float32)
    bbox = f0.bbox.astype(float).tolist()
    det_score = float(getattr(f0, "det_score", 0.0))
    return emb, {"bbox": bbox, "det_score": det_score}


def dist_to_conf(d: float, thr_strict: float = 0.35, thr_loose: float = 0.50) -> float:
    if d <= thr_strict:
        return 1.0
    if d >= thr_loose:
        return 0.0
    return float((thr_loose - d) / (thr_loose - thr_strict))


def recognize_from_bytes(
    image_bytes: bytes,
    me_identity: str = "me",
    thr_strict: float = 0.35,
    thr_loose: float = 0.50,
):
    np = _require_numpy()
    labels, embs, _ = load_db()

    img = read_image(image_bytes)

    emb, info = extract_best_face_embedding(img)
    if emb is None:
        return {
            "ok": False,
            "error": "no_face_detected",
            "face_label": "unknown",
            "face_is_known": 0,
            "face_is_me": 0,
            "face_dist": 1.0,
            "face_conf": 0.0,
            "face_info": None,
        }

    if len(labels) == 0:
        return {
            "ok": True,
            "face_label": "unknown",
            "face_is_known": 0,
            "face_is_me": 0,
            "face_dist": 1.0,
            "face_conf": 0.0,
            "face_info": info,
        }

    sims = embs @ emb
    best_idx = int(np.argmax(sims))
    best_label = labels[best_idx]
    best_dist = float(1.0 - sims[best_idx])

    conf = dist_to_conf(best_dist, thr_strict=thr_strict, thr_loose=thr_loose)
    is_known = int(best_dist <= thr_loose)
    face_label = best_label if is_known else "unknown"

    return {
        "ok": True,
        "face_label": face_label,
        "face_is_known": is_known,
        "face_is_me": int(face_label == me_identity),
        "face_dist": best_dist,
        "face_conf": conf,
        "face_info": info,
    }


def _render_error_frame(message: str) -> bytes:
    np = _require_numpy()
    cv2 = _require_cv2()
    canvas = np.zeros((480, 860, 3), dtype=np.uint8)
    canvas[:] = (24, 24, 24)

    lines = [
        "Time Sense Live Preview",
        "Camera/recognition stream is not ready.",
        message[:96] or "unknown error",
    ]
    y = 90
    for idx, line in enumerate(lines):
        scale = 0.85 if idx == 0 else 0.6
        thickness = 2 if idx == 0 else 1
        cv2.putText(
            canvas,
            line,
            (28, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            (255, 255, 255),
            thickness,
            cv2.LINE_AA,
        )
        y += 48

    ok, encoded = cv2.imencode(".jpg", canvas)
    if not ok:
        raise ValueError("failed to encode error frame")
    return encoded.tobytes()


async def _live_preview_generator(
    *,
    fps: float,
    thr_strict: float,
    thr_loose: float,
):
    interval = 1.0 / max(fps, 0.001)
    detect_interval = 10.0  # Inferensi wajah setiap 10 detik agar tidak berat
    last_detect_time = 0.0
    last_detections = []

    # Import fungsi baru dari face_detection
    from .face_detection import detect_faces_only, draw_faces

    while True:
        start_time = time.time()
        try:
            # Use raw frame to avoid double encode/decode
            frame = await asyncio.to_thread(get_latest_frame, 2.0)
            if frame is not None:
                current_time = time.time()
                
                # Hanya jalankan deteksi wajah jika interval waktu telah terlampaui
                if current_time - last_detect_time >= detect_interval:
                    last_detections = await asyncio.to_thread(
                        detect_faces_only,
                        frame,
                        thr_strict=thr_strict,
                        thr_loose=thr_loose,
                    )
                    last_detect_time = current_time

                # Gambar selalu bounding box terakhir (bisa instan karena tanpa AI)
                annotated_bytes = await asyncio.to_thread(draw_faces, frame, last_detections)
            else:
                annotated_bytes = _render_error_frame("No camera frame available")
        except Exception as exc:
            annotated_bytes = _render_error_frame(str(exc))

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Cache-Control: no-cache, no-store, must-revalidate\r\n\r\n"
            + annotated_bytes
            + b"\r\n"
        )
        
        elapsed = time.time() - start_time
        sleep_time = interval - elapsed
        if sleep_time > 0:
            await asyncio.sleep(sleep_time)
        else:
            await asyncio.sleep(0.001)


@router.post("/enroll")
async def enroll(
    identity: str = Form(...),
    image: UploadFile = File(...),
):
    labels, embs, meta = load_db()

    img_bytes = await image.read()
    img = read_image(img_bytes)

    emb, info = extract_best_face_embedding(img)
    if emb is None:
        return {"ok": False, "error": "no_face_detected"}

    labels.append(identity)
    np = _require_numpy()
    embs = np.vstack([embs, emb.reshape(1, -1)])

    meta["identities"].setdefault(identity, 0)
    meta["identities"][identity] += 1

    save_db(labels, embs, meta)
    return {
        "ok": True,
        "identity": identity,
        "count": meta["identities"][identity],
        "face_info": info,
    }


@router.post("/recognize")
async def recognize(
    image: UploadFile = File(...),
    me_identity: str = Form("me"),
    thr_strict: float = Form(0.35),
    thr_loose: float = Form(0.50),
):
    np = _require_numpy()
    labels, embs, _ = load_db()

    img_bytes = await image.read()
    img = read_image(img_bytes)

    emb, info = extract_best_face_embedding(img)
    if emb is None:
        return {
            "ok": False,
            "error": "no_face_detected",
            "face_label": "unknown",
            "face_is_known": 0,
            "face_is_me": 0,
            "face_dist": 1.0,
            "face_conf": 0.0,
            "face_info": None,
        }

    if len(labels) == 0:
        return {
            "ok": True,
            "face_label": "unknown",
            "face_is_known": 0,
            "face_is_me": 0,
            "face_dist": 1.0,
            "face_conf": 0.0,
            "face_info": info,
        }

    sims = embs @ emb
    best_idx = int(np.argmax(sims))
    best_label = labels[best_idx]
    best_dist = float(1.0 - sims[best_idx])

    conf = dist_to_conf(best_dist, thr_strict=thr_strict, thr_loose=thr_loose)
    is_known = int(best_dist <= thr_loose)
    face_label = best_label if is_known else "unknown"

    return {
        "ok": True,
        "face_label": face_label,
        "face_is_known": is_known,
        "face_is_me": int(face_label == me_identity),
        "face_dist": best_dist,
        "face_conf": conf,
        "face_info": info,
    }


@router.post("/reset")
async def reset_face_database():
    """Reset face database by deleting embeddings and metadata."""
    try:
        import os
        
        # Delete embeddings file
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
            print(f"[FACE] Deleted embeddings file: {DB_PATH}")
        
        # Delete metadata file
        if os.path.exists(META_PATH):
            os.remove(META_PATH)
            print(f"[FACE] Deleted metadata file: {META_PATH}")
        
        return {"status": "success", "message": "Face database reset successfully"}
    except Exception as e:
        print(f"[FACE] Error resetting database: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reset face database: {str(e)}"
        )


@router.get("/live-preview")
async def live_preview(
    fps: float = Query(15.0, ge=0.1, le=30.0),
    thr_strict: float = Query(0.35, ge=0.0, le=1.0),
    thr_loose: float = Query(0.50, ge=0.0, le=1.0),
):
    return StreamingResponse(
        _live_preview_generator(
            fps=fps,
            thr_strict=thr_strict,
            thr_loose=thr_loose,
        ),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
