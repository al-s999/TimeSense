import os
import json
import numpy as np
import cv2
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form
from insightface.app import FaceAnalysis

DB_DIR = "face_db"
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "embeddings.npz")
META_PATH = os.path.join(DB_DIR, "meta.json")

# --------- Load InsightFace
# Note: providers=['CPUExecutionProvider'] paling aman.
# Jika pakai GPU: providers=['CUDAExecutionProvider','CPUExecutionProvider']
app_face = FaceAnalysis(name="buffalo_l")
app_face.prepare(ctx_id=0, det_size=(640, 640))  # ctx_id=0 GPU, -1 CPU
# Kalau kamu CPU only: ganti ctx_id=-1

app = FastAPI(title="InsightFace Recognition Service")

def load_db():
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
    np.savez(DB_PATH, labels=np.array(labels, dtype=object), embeddings=embs.astype(np.float32))
    with open(META_PATH, "w") as f:
        json.dump(meta, f, indent=2)

def read_image(file_bytes: bytes):
    arr = np.frombuffer(file_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Cannot decode image")
    return img

def extract_best_face_embedding(img_bgr):
    faces = app_face.get(img_bgr)
    if not faces:
        return None, None
    # pilih face terbesar
    faces_sorted = sorted(faces, key=lambda f: (f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]), reverse=True)
    f0 = faces_sorted[0]
    emb = f0.normed_embedding.astype(np.float32)  # unit norm
    bbox = f0.bbox.astype(float).tolist()
    det_score = float(getattr(f0, "det_score", 0.0))
    return emb, {"bbox": bbox, "det_score": det_score}

def cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    # a,b unit norm -> cosine similarity = dot
    sim = float(np.dot(a, b))
    return float(1.0 - sim)

def dist_to_conf(d: float, thr_strict: float = 0.35, thr_loose: float = 0.50) -> float:
    """
    Heuristic mapping distance -> confidence.
    - d <= thr_strict => conf near 1
    - d >= thr_loose  => conf near 0
    """
    if d <= thr_strict:
        return 1.0
    if d >= thr_loose:
        return 0.0
    return float((thr_loose - d) / (thr_loose - thr_strict))

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/enroll")
async def enroll(
    identity: str = Form(...),
    image: UploadFile = File(...)
):
    """
    Register a face for an identity (e.g., 'me', 'friend_andi').
    Saves embedding into DB.
    """
    labels, embs, meta = load_db()

    img_bytes = await image.read()
    img = read_image(img_bytes)

    emb, info = extract_best_face_embedding(img)
    if emb is None:
        return {"ok": False, "error": "no_face_detected"}

    labels.append(identity)
    embs = np.vstack([embs, emb.reshape(1, -1)])

    meta["identities"].setdefault(identity, 0)
    meta["identities"][identity] += 1

    save_db(labels, embs, meta)
    return {"ok": True, "identity": identity, "count": meta["identities"][identity], "face_info": info}

@app.post("/recognize")
async def recognize(
    image: UploadFile = File(...),
    me_identity: str = Form("me"),
    thr_strict: float = Form(0.35),
    thr_loose: float = Form(0.50),
):
    """
    Recognize face from image.
    Returns label, dist, conf, flags:
      face_label, face_is_known, face_is_me, face_dist, face_conf
    """
    labels, embs, meta = load_db()

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
            "face_info": None
        }

    if len(labels) == 0:
        return {
            "ok": True,
            "face_label": "unknown",
            "face_is_known": 0,
            "face_is_me": 0,
            "face_dist": 1.0,
            "face_conf": 0.0,
            "face_info": info
        }

    # compute nearest neighbor
    # cosine distance since embeddings are unit norm
    sims = embs @ emb  # dot products
    best_idx = int(np.argmax(sims))
    best_label = labels[best_idx]
    best_dist = float(1.0 - sims[best_idx])

    conf = dist_to_conf(best_dist, thr_strict=thr_strict, thr_loose=thr_loose)
    is_known = int(best_dist <= thr_loose)
    face_label = best_label if is_known else "unknown"
    is_me = int(is_known and face_label == me_identity)

    return {
        "ok": True,
        "face_label": face_label,
        "face_is_known": is_known,
        "face_is_me": is_me,
        "face_dist": best_dist,
        "face_conf": conf,
        "face_info": info
    }
