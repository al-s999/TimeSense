from __future__ import annotations

import argparse
import os
import time
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


def _require_cv2():
    try:
        import cv2  # type: ignore
    except Exception as exc:
        raise RuntimeError("opencv-python is required") from exc
    return cv2


def _require_numpy():
    try:
        import numpy as np
    except Exception as exc:
        raise RuntimeError("numpy is required") from exc
    return np


def _require_insightface():
    try:
        from insightface.app import FaceAnalysis
    except Exception as exc:
        raise RuntimeError("insightface is required for local mode") from exc
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


def _recognize_local(frame, app_face, labels, embs, thr_strict: float, thr_loose: float):
    np = _require_numpy()
    faces = app_face.get(frame)
    results = []
    for f in faces:
        emb = f.normed_embedding.astype(np.float32)
        bbox = f.bbox.astype(float).tolist()
        det_score = float(getattr(f, "det_score", 0.0))
        if len(labels) == 0:
            face_label = "unknown"
            face_dist = 1.0
            face_conf = 0.0
            face_is_known = 0
        else:
            sims = embs @ emb
            best_idx = int(np.argmax(sims))
            best_label = labels[best_idx]
            face_dist = float(1.0 - sims[best_idx])
            face_conf = _dist_to_conf(face_dist, thr_strict, thr_loose)
            face_is_known = int(face_dist <= thr_loose)
            face_label = best_label if face_is_known else "unknown"
        results.append(
            {
                "bbox": bbox,
                "face_label": face_label,
                "face_is_known": face_is_known,
                "face_dist": face_dist,
                "face_conf": face_conf,
                "det_score": det_score,
            }
        )
    return results


def _backend_recognize(url: str, jpeg_bytes: bytes, me_identity: str, thr_strict: float, thr_loose: float):
    boundary = "----boundary-time-sense"
    parts = []
    parts.append(
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="me_identity"\r\n\r\n{me_identity}\r\n'
    )
    parts.append(
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="thr_strict"\r\n\r\n{thr_strict}\r\n'
    )
    parts.append(
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="thr_loose"\r\n\r\n{thr_loose}\r\n'
    )
    parts.append(
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="image"; filename="frame.jpg"\r\n'
        "Content-Type: image/jpeg\r\n\r\n"
    )
    body = "".join(parts).encode("utf-8") + jpeg_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=2.0) as resp:
        data = resp.read()
    import json

    payload = json.loads(data.decode("utf-8"))
    if not payload.get("ok"):
        return []
    info = payload.get("face_info") or {}
    bbox = info.get("bbox")
    det_score = info.get("det_score", 0.0)
    if not bbox:
        return []
    return [
        {
            "bbox": bbox,
            "face_label": payload.get("face_label", "unknown"),
            "face_is_known": payload.get("face_is_known", 0),
            "face_dist": float(payload.get("face_dist", 1.0)),
            "face_conf": float(payload.get("face_conf", 0.0)),
            "det_score": float(det_score or 0.0),
        }
    ]


def _draw_overlays(frame, faces: List[Dict[str, Any]], fps: Optional[float]):
    cv2 = _require_cv2()
    for face in faces:
        bbox = face.get("bbox") or [0, 0, 0, 0]
        x1, y1, x2, y2 = [int(v) for v in bbox]
        color = (0, 200, 0) if face.get("face_is_known") else (0, 0, 200)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        lines = [
            f"face_label={face.get('face_label')}",
            f"face_is_known={face.get('face_is_known')} face_dist={face.get('face_dist'):.3f}",
            f"face_conf={face.get('face_conf'):.2f} det_score={face.get('det_score'):.2f}",
        ]
        y_text = y1 - 6
        for line in lines:
            if y_text < 10:
                y_text = y1 + 14
            cv2.putText(frame, line, (x1, y_text), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
            y_text += 14
    if fps is not None:
        cv2.putText(frame, f"FPS: {fps:.1f}", (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
    return frame


def _open_capture(cv2, camera_index: int, width: int, height: int, backend: str):
    backend = (backend or "").upper()
    flag = getattr(cv2, f"CAP_{backend}", None) if backend else None
    if flag is not None:
        cap = cv2.VideoCapture(camera_index, flag)
    else:
        cap = cv2.VideoCapture(camera_index)
    if width > 0:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    if height > 0:
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return cap


def main() -> int:
    parser = argparse.ArgumentParser(description="Camera preview with face overlays.")
    parser.add_argument("--width", type=int, default=1920, help="Frame width (default: 1920)")
    parser.add_argument("--height", type=int, default=1080, help="Frame height (default: 1080)")
    parser.add_argument("--camera-index", type=int, default=0, help="Camera index (default: 0)")
    parser.add_argument("--backend", type=str, default="", help="OpenCV backend (e.g. V4L2, DSHOW)")
    parser.add_argument("--detect-every", type=int, default=3, help="Run detection every N frames")
    parser.add_argument("--det-size", type=int, default=640, help="InsightFace det_size (local mode)")
    parser.add_argument("--backend-url", type=str, default="", help="Use backend /recognize endpoint")
    parser.add_argument("--me-identity", type=str, default="me", help="Backend me_identity")
    parser.add_argument("--thr-strict", type=float, default=0.35, help="Face strict threshold")
    parser.add_argument("--thr-loose", type=float, default=0.50, help="Face loose threshold")
    args = parser.parse_args()

    cv2 = _require_cv2()
    cap = _open_capture(cv2, args.camera_index, args.width, args.height, args.backend)
    if not cap.isOpened():
        print("[CAMERA] failed to open camera")
        return 1

    app_face = None
    labels = []
    embs = None
    if not args.backend_url:
        FaceAnalysis = _require_insightface()
        app_face = FaceAnalysis(name="buffalo_l")
        try:
            app_face.prepare(ctx_id=0, det_size=(args.det_size, args.det_size))
        except Exception:
            app_face.prepare(ctx_id=-1, det_size=(args.det_size, args.det_size))
        labels, embs = _load_face_db()

    window_name = "Camera"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    fps_count = 0
    fps_last = time.time()
    fps_value: Optional[float] = None
    last_faces: List[Dict[str, Any]] = []
    frame_idx = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("[CAMERA] failed to read frame")
                break

            if frame_idx % max(args.detect_every, 1) == 0:
                try:
                    if args.backend_url:
                        ok, encoded = cv2.imencode(".jpg", frame)
                        if ok:
                            last_faces = _backend_recognize(
                                args.backend_url,
                                encoded.tobytes(),
                                args.me_identity,
                                args.thr_strict,
                                args.thr_loose,
                            )
                        else:
                            last_faces = []
                    else:
                        last_faces = _recognize_local(frame, app_face, labels, embs, args.thr_strict, args.thr_loose)
                except Exception as exc:
                    print(f"[CAMERA] recognize error: {exc}")
                    last_faces = []

            fps_count += 1
            now_ts = time.time()
            if now_ts - fps_last >= 1.0:
                fps_value = fps_count / (now_ts - fps_last)
                fps_last = now_ts
                fps_count = 0

            annotated = _draw_overlays(frame, last_faces, fps_value)
            cv2.imshow(window_name, annotated)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

            frame_idx += 1
    finally:
        cap.release()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
