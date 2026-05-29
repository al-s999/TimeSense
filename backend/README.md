## Backend Setup (FastAPI)

Requirements: Python 3.12+

```bash
cd backend
pip install -r requirements.txt
pip install "numpy<2"
uvicorn app.main:app --reload
```

## Face Backend (separate port)
```bash
cd backend
cp .env.face.example .env.face
uvicorn app.face_service:app --reload --port 8001
```

Jika ingin pakai file env khusus lain, set:
```
FACE_ENV_PATH=/path/ke/.env.face
```

Env penting (face backend):
- `FACE_WINDOW_SECONDS` (durasi observasi sebelum mengirim label)
- `FACE_WINDOW_COOLDOWN` (jeda antar kirim)
- `FACE_EARLY_CONF` + `FACE_EARLY_MIN_SECONDS` + `FACE_EARLY_STREAK` (kirim lebih cepat jika yakin)

If InsightFace fails with a NumPy>=2 error:

```bash
cd backend
./scripts/fix_env.sh
```

On Windows PowerShell:

```powershell
cd backend
.\scripts\fix_env.ps1
```
