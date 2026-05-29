from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, List, Tuple


@dataclass(frozen=True)
class FaceDetection:
    bbox: List[float]
    face_label: str
    face_is_known: int
    face_dist: float
    face_conf: float
    det_score: float


def _require_cv2():
    try:
        import cv2  # type: ignore
    except Exception as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError(
            "opencv-python is required for face detection. "
            "Install it with: pip install opencv-python"
        ) from exc
    return cv2


def _require_numpy():
    try:
        import numpy as np
    except Exception as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError("numpy is required for face detection") from exc
    return np


def _require_insightface():
    try:
        np = _require_numpy()
        major = int(str(np.__version__).split(".")[0])
        if major >= 2:
            print("[FIX] Run: pip install 'numpy<2' then restart server")
            raise RuntimeError("NumPy>=2 not supported, please downgrade")
        from insightface.app import FaceAnalysis
    except RuntimeError:
        raise
    except Exception as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError("insightface is required for face detection") from exc
    return FaceAnalysis


def _load_face_db() -> Tuple[List[str], Any]:
    np = _require_numpy()
    db_dir = os.getenv("FACE_DB_DIR", "face_db")
    db_path = os.path.join(db_dir, "embeddings.npz")
    if os.path.exists(db_path):
        data = np.load(db_path, allow_pickle=True)
        labels = data["labels"].tolist()
        embs = data["embeddings"]
    else:
        labels, embs = [], np.zeros((0, 512), dtype=np.float32)
    return labels, embs


def _dist_to_conf(d: float, thr_strict: float, thr_loose: float) -> float:
    if d <= thr_strict:
        return 1.0
    if d >= thr_loose:
        return 0.0
    return float((thr_loose - d) / (thr_loose - thr_strict))


_face_app = None


def _get_face_app():
    global _face_app
    if _face_app is None:
        FaceAnalysis = _require_insightface()
        app_face = FaceAnalysis(name=os.getenv("FACE_MODEL_NAME", "buffalo_l"))
        ctx_id = int(os.getenv("FACE_CTX_ID", "0"))
        # Using 320x320 for much faster detection on CPU
        det_size = int(os.getenv("FACE_DET_SIZE", "320"))
        try:
            app_face.prepare(ctx_id=ctx_id, det_size=(det_size, det_size))
        except Exception:
            app_face.prepare(ctx_id=-1, det_size=(det_size, det_size))
        _face_app = app_face
    return _face_app


def detect_faces_raw(
    image_array: Any,
    thr_strict: float = 0.35,
    thr_loose: float = 0.50,
) -> Tuple[List[FaceDetection], bytes]:
    """
    Detect faces directly on image array (numpy) to avoid re-decoding.
    """
    cv2 = _require_cv2()
    np = _require_numpy()

    app_face = _get_face_app()
    labels, embs = _load_face_db()
    faces = app_face.get(image_array)

    detections: List[FaceDetection] = []
    annotated = image_array.copy()
    for f in faces:
        bbox = f.bbox.astype(float).tolist()
        det_score = float(getattr(f, "det_score", 0.0))
        emb = f.normed_embedding.astype(np.float32)

        if len(labels) == 0:
            face_label = "unknown"
            face_is_known = 0
            face_dist = 1.0
            face_conf = 0.0
        else:
            sims = embs @ emb
            best_idx = int(np.argmax(sims))
            best_label = labels[best_idx]
            face_dist = float(1.0 - sims[best_idx])
            face_conf = _dist_to_conf(face_dist, thr_strict, thr_loose)
            face_is_known = int(face_dist <= thr_loose)
            face_label = best_label if face_is_known else "unknown"

        detections.append(
            FaceDetection(
                bbox=bbox,
                face_label=face_label,
                face_is_known=face_is_known,
                face_dist=face_dist,
                face_conf=face_conf,
                det_score=det_score,
            )
        )

        x1, y1, x2, y2 = [int(v) for v in bbox]
        color = (0, 200, 0) if face_is_known else (0, 0, 200)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        label = f"{face_label} d={face_dist:.2f} c={face_conf:.2f} det={det_score:.2f}"
        cv2.putText(
            annotated,
            label,
            (x1, max(12, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA,
        )

    ok, encoded = cv2.imencode(".jpg", annotated)
    if not ok:
        raise ValueError("Failed to encode annotated image.")

    return detections, encoded.tobytes()


def detect_faces(
    image_bytes: bytes,
    thr_strict: float = 0.35,
    thr_loose: float = 0.50,
) -> Tuple[List[FaceDetection], bytes]:
    """
    Detect faces using InsightFace and return (detections, annotated_image_bytes).
    """
    cv2 = _require_cv2()
    np = _require_numpy()

    image_array = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if image_array is None:
        raise ValueError("Invalid image bytes.")

    return detect_faces_raw(image_array, thr_strict, thr_loose)
