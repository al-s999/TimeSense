from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

_preview_thread: threading.Thread | None = None
_preview_stop = threading.Event()
_preview_lock = threading.Lock()
_preview_headless = False
_preview_last_path: Optional[str] = None
_preview_last_error: Optional[str] = None


def _require_cv2():
    try:
        import cv2  # type: ignore
    except Exception as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError("opencv-python is required for preview") from exc
    return cv2


def _require_numpy():
    try:
        import numpy as np
    except Exception as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError("numpy is required for preview") from exc
    return np


def _require_insightface():
    try:
        np = _require_numpy()
        major = int(str(np.__version__).split(".")[0])
        if major >= 2:
            print("[FIX] Run: pip install 'numpy<2' then restart server")
            raise RuntimeError(
                "NumPy>=2 detected. insightface/onnxruntime requires NumPy<2."
            )
        from insightface.app import FaceAnalysis
    except RuntimeError:
        raise
    except Exception as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError("insightface is required for preview") from exc
    return FaceAnalysis


def _debug_enabled() -> bool:
    return os.getenv("DEBUG", "").lower() in {"1", "true", "yes", "on"}


def _log(msg: str) -> None:
    if _debug_enabled():
        print(msg)


def _is_headless() -> bool:
    if os.getenv("FACE_PREVIEW_HEADLESS", "").lower() in {"1", "true", "yes", "on"}:
        return True
    if os.name == "nt":
        return False
    if os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY"):
        return False
    return True


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
_face_app_lock = threading.Lock()


def _get_face_app():
    global _face_app
    with _face_app_lock:
        if _face_app is None:
            FaceAnalysis = _require_insightface()
            app_face = FaceAnalysis(name=os.getenv("FACE_MODEL_NAME", "buffalo_l"))
            ctx_id = int(os.getenv("FACE_CTX_ID", "0"))
            try:
                app_face.prepare(ctx_id=ctx_id, det_size=(640, 640))
            except Exception:
                app_face.prepare(ctx_id=-1, det_size=(640, 640))
            _face_app = app_face
    return _face_app


def _recognize_faces(frame, labels, embs, thr_strict: float, thr_loose: float) -> List[Dict[str, Any]]:
    np = _require_numpy()
    app_face = _get_face_app()
    faces = app_face.get(frame)
    results: List[Dict[str, Any]] = []
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


def _draw_overlays(frame, faces: List[Dict[str, Any]], fps: Optional[float] = None) -> Any:
    cv2 = _require_cv2()
    for face in faces:
        bbox = face.get("bbox") or [0, 0, 0, 0]
        x1, y1, x2, y2 = [int(v) for v in bbox]
        color = (0, 200, 0) if face.get("face_is_known") else (0, 0, 200)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        lines = [
            f"label={face.get('face_label')}",
            f"known={face.get('face_is_known')} dist={face.get('face_dist'):.3f}",
            f"conf={face.get('face_conf'):.2f} det={face.get('det_score'):.2f}",
        ]
        y_text = y1 - 6
        for line in lines:
            if y_text < 10:
                y_text = y1 + 14
            cv2.putText(frame, line, (x1, y_text), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
            y_text += 14

    if fps is not None:
        cv2.putText(
            frame,
            f"FPS: {fps:.1f}",
            (10, 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 0),
            2,
            cv2.LINE_AA,
        )
    return frame


def preview_status() -> Dict[str, Any]:
    with _preview_lock:
        return {
            "running": bool(_preview_thread and _preview_thread.is_alive()),
            "headless": _preview_headless,
            "last_saved_path": _preview_last_path,
            "last_error": _preview_last_error,
        }


def start_preview_loop() -> None:
    global _preview_thread
    if _preview_thread and _preview_thread.is_alive():
        return

    _preview_stop.clear()

    def _loop() -> None:
        global _preview_headless, _preview_last_path, _preview_last_error
        cv2 = _require_cv2()
        save_interval = float(os.getenv("FACE_PREVIEW_SAVE_INTERVAL", "2.0"))
        save_path = os.getenv("FACE_PREVIEW_SAVE_PATH", "/tmp/preview.jpg")
        retry_sleep = float(os.getenv("FACE_PREVIEW_RETRY_SLEEP", "1.0"))
        thr_strict = float(os.getenv("FACE_THR_STRICT", "0.35"))
        thr_loose = float(os.getenv("FACE_THR_LOOSE", "0.50"))
        window_name = os.getenv("FACE_PREVIEW_WINDOW", "Camera")

        _preview_headless = _is_headless()
        last_save = 0.0
        fps_count = 0
        fps_last_ts = time.time()
        fps_value: Optional[float] = None
        headless_logged = False

        while not _preview_stop.is_set():
            try:
                try:
                    from .camera_face import start_camera_loop, get_latest_frame
                except Exception:  # pragma: no cover - script mode fallback
                    from camera_face import start_camera_loop, get_latest_frame
                start_camera_loop()

                labels, embs = _load_face_db()
                if not _preview_headless:
                    try:
                        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
                    except Exception as exc:
                        _preview_headless = True
                        _preview_last_error = str(exc)
                        _log(f"[CAMERA] preview headless fallback (window): {exc}")

                while not _preview_stop.is_set():
                    frame = get_latest_frame(timeout=1.0)
                    if frame is None:
                        time.sleep(0.05)
                        continue

                    try:
                        faces = _recognize_faces(frame, labels, embs, thr_strict, thr_loose)
                    except Exception as exc:
                        _preview_last_error = str(exc)
                        faces = []

                    fps_count += 1
                    now_ts = time.time()
                    if now_ts - fps_last_ts >= 1.0:
                        fps_value = fps_count / (now_ts - fps_last_ts)
                        fps_last_ts = now_ts
                        fps_count = 0

                    annotated = _draw_overlays(frame, faces, fps=fps_value)

                    if _preview_headless:
                        if now_ts - last_save >= save_interval:
                            ok = cv2.imwrite(save_path, annotated)
                            if ok:
                                last_save = now_ts
                                with _preview_lock:
                                    _preview_last_path = save_path
                                if not headless_logged:
                                    print(f"[CAMERA] headless preview saved: {save_path}")
                                    headless_logged = True
                    else:
                        try:
                            cv2.imshow(window_name, annotated)
                            if cv2.waitKey(1) & 0xFF == ord("q"):
                                _preview_stop.set()
                                break
                        except Exception as exc:
                            _preview_headless = True
                            _preview_last_error = str(exc)
                            _log(f"[CAMERA] preview fallback to headless: {exc}")

                    time.sleep(0.01)

                if not _preview_headless:
                    cv2.destroyAllWindows()
            except Exception as exc:
                _preview_last_error = str(exc)
                _log(f"[CAMERA] preview loop error: {exc}")
                time.sleep(max(retry_sleep, 0.2))

    _preview_thread = threading.Thread(target=_loop, daemon=True)
    _preview_thread.start()


def stop_preview_loop() -> None:
    _preview_stop.set()


def main() -> None:
    start_preview_loop()
    try:
        while _preview_thread and _preview_thread.is_alive():
            time.sleep(0.2)
    except KeyboardInterrupt:
        stop_preview_loop()


if __name__ == "__main__":
    main()
