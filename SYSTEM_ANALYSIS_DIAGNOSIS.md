# SMART DOOR SYSTEM - COMPLETE ANALYSIS & SOLUTION

## 🔴 SITUASI SAAT INI

Anda sudah memiliki:
- ✓ Face recognition service (terdeteksi: "ACCESS ALLOWED")
- ✓ Backend FastAPI (endpoints ada)
- ✓ ESP32 (bisa connect)
- ✓ Web dashboard (Next.js)
- ✓ WhatsApp bot skeleton

Tapi tidak sinkron end-to-end → pintu tidak buka!

---

## 🚨 ROOT CAUSE ANALYSIS

### Masalah #1: RACE CONDITION (KRITIS!)

**Gejala:**
```
Face detected (confidence: 1.0) → "ACCESS ALLOWED"
/api/face/ingest → returns "allow"
/api/access → returns "deny" ← MISMATCH!
```

**Penyebab #1a: State Management Broken**
```python
# OLD CODE (BEFORE FIX):
# /api/access calls:
result = access_state.consume(device_id=device_id)
# consume() marks state as consumed=True
# NEXT POLL: already consumed → returns deny
```
✓ SUDAH DIPERBAIKI dalam session ini

**Penyebab #1b: Device ID Mismatch**
```
Face service sends: device_id="face-service" 
ESP queries with: device_id="esp32-1" ← MISMATCH!
Result: ESP looks in wrong device_id entry
```

**Penyebab #1c: Timing/Ordering Issues**
```
t=0: Face ingest → set_allow()
t=0.1: ESP polls /api/access BUT state not yet written
         (race between write & read)
```

### Masalah #2: ECONNRESET / ECONNREFUSED

**Gejala:**
```
ECONNRESET / ECONNREFUSED on:
- GET /api/access
- POST /api/sensor/update
- GET /api/command
```

**Root Causes:**

1. **Blocking I/O di backend**
   ```python
   # PROBLEM: Uvicorn bisa hanya handle 1 request on default
   # Kalau ada long-running operation, next request akan hang
   ```

2. **ESP spam request tanpa backoff**
   ```python
   # ESP pseudocode:
   while True:
       requests.get('/api/access')  # SPAM! No delay!
       requests.post('/api/sensor/update')
       requests.get('/api/command')
   # Bila 50+ device seperti ini → backend overwhelmed
   ```

3. **Connection tidak di-close dengan benar**
   ```python
   # FastAPI default mungkin tidak close response dengan baik
   # Socket accumulate → memory leak → crash
   ```

4. **No connection pooling**
   ```
   ESP buat connection baru setiap request
   Backend queue tumbuh → eventually ECONNREFUSED
   ```

### Masalah #3: Sensor Data Tidak Masuk

**Gejala:**
```
POST /api/sensor/update
Response: "ok"
Database: distance1=None, distance2=None ← Not stored!
```

**Root Causes:**

1. **Payload format mismatch**
   ```python
   # ESP kirim:
   {"device_id": "esp32-1", "temp": 25}
   
   # Backend expect:
   {"device_id": "...", "sensor_type": "...", "value": ...}
   
   # Parser tidak match → data dropped
   ```

2. **Validation error, response 200 OK tapi data tidak disimpan**
   ```python
   # Handler terima request, return 200 OK
   # Tapi ada exception di validation yang di-catch silent
   # Data dropped tanpa error indication
   ```

3. **Database transaction tidak committed**
   ```python
   db.add(event)
   # Tapi forgot db.commit() → data hanya di memory, not persisted
   ```

### Masalah #4: Arsitektur State Tersebar

**Current (CHAOS):**
```
ESP State:     relay_pin=HIGH (think pintu terbuka)
Backend State: access="deny"
Face Service:  label="me", confidence=1.0
Frontend:      last_event=null

Tidak ada consensus → sistem inconsistent!
```

**Flow saat ini (UNCLEAR):**
```
Face Detection
    ↓
_post_face() → POST /api/face/ingest
    ↓
/api/face/ingest: set_allow()
    ↓
??? ESP tidak tahu ada state baru
    ↓
ESP polling /api/access setiap 2 detik (lambat!)
    ↓
Eventually: /api/access returns allow
    ↓
ESP: relay HIGH → pintu buka (DELAY!)
```

**Timeline dengan delay:**
```
t=0.0s: Face detected
t=0.5s: /api/face/ingest called
t=2.0s: ESP polls (first poll after detection)
t=2.1s: /api/access returns allow
t=2.2s: ESP set relay HIGH
t=2.3s: Door physically opens

DELAY: 2.3 detik! Terasa lambat jika user sudah di depan pintu
```

### Masalah #5: Frontend & API Routes Issues

**Error:** `ECONNREFUSED 127.0.0.1:8000`

**Root Causes:**

1. **Backend tidak running saat Next.js build**
   ```
   npm run build → fetch http://localhost:8000
   Backend tidak active → ECONNREFUSED
   ```

2. **Salah BASE_URL di client**
   ```typescript
   // lib/backend.ts mungkin hard-code:
   const BASE_URL = "http://localhost:8000"
   
   // Production:
   // Browser di: https://app.example.com
   // Tapi fetch ke: http://localhost:8000
   // CORS + local address DENIED!
   ```

3. **API route proxy tidak configured**
   ```typescript
   // /src/app/api/[...route]/route.ts
   // Seharusnya proxy ke backend
   // Tapi mungkin hardcode atau error handling jelek
   ```

### Masalah #6: WhatsApp Bot Tidak Jelas

**Current state:**
```
whatsapp-bot/ folder ada
Tapi tidak jelas:
- Apakah ambil dari /api/command?
- Atau direktnya trigger backend action?
- Flow: user → WA msg → apa? → ESP?
```

---

## 📊 DIAGNOSIS RINGKAS

| Masalah | Severity | Root Cause | Fix Priority |
|---------|----------|-----------|--------------|
| Race condition | 🔴 CRITICAL | State consumed too fast | #1 (DONE) |
| Device ID mismatch | 🔴 CRITICAL | Face vs ESP using different ID | #2 (HIGH) |
| ECONNRESET | 🟠 HIGH | Blocking I/O + no backoff | #3 (HIGH) |
| Sensor data lost | 🟠 HIGH | Validation error silent | #4 (HIGH) |
| State scattered | 🟡 MEDIUM | No single source of truth | #5 (MEDIUM) |
| Frontend errors | 🟡 MEDIUM | Wrong BASE_URL, proxy issue | #6 (MEDIUM) |
| WA bot unclear | 🟡 MEDIUM | Architecture not defined | #7 (MEDIUM) |

---

## ✅ SOLUSI OVERVIEW

### Layer 1: Fix Critical Issues (DONE + TODAY)
- ✓ State management (consume→get_current) 
- 🔨 Device ID resolution
- 🔨 Payload validation with error reporting

### Layer 2: Stabilize System (Architecture + Code)
- 🔨 State cache optimization
- 🔨 ESP retry logic + backoff
- 🔨 Non-blocking request handling
- 🔨 Connection pooling

### Layer 3: Clean Architecture (Endpoints + Flow)
- 🔨 Single source of truth
- 🔨 Clear command flow
- 🔨 WA bot integration
- 🔨 Error resilience

### Layer 4: Testing & Validation
- 🔨 Integration tests
- 🔨 Load testing
- 🔨 Deployment checklist

---

## 🎯 NEXT STEPS (TODAY)

1. ✓ State management fix (sudah done: get_current vs consume)
2. **TODAY**: Design & implement unified architecture
3. **TODAY**: Fix device ID resolution
4. **TODAY**: Add retry logic to ESP32
5. **TODAY**: Create testing suite

---

## 📐 NEW ARCHITECTURE (TO BE DESIGNED)

**Single Source of Truth: Backend State Machine**

```
┌─────────────────────────────────────────────────────┐
│  BACKEND STATE (Single Source of Truth)             │
│  ├─ device_state[esp32-1]:                          │
│  │  ├─ access: "allow" | "deny" | "timeout"        │
│  │  ├─ identity: "me" | null                        │
│  │  ├─ door_state: "open" | "closed" | "unknown"   │
│  │  ├─ updated_at: timestamp                        │
│  │  └─ expires_at: timestamp                        │
│  ├─ sensor_store[esp32-1]:                          │
│  │  ├─ distance1, distance2                         │
│  │  ├─ temperature                                  │
│  │  └─ timestamp                                    │
│  └─ command_queue[esp32-1]:                         │
│     └─ {"action": "open_door", "priority": 10}     │
└─────────────────────────────────────────────────────┘
        ↑                ↑                ↑
        │                │                │
    Face Svc         ESP32           WA Bot
    (updates          (queries       (commands)
     access)          state)
```

---

**Endpoint Design (Minimal, Clear)**

```
FACE SERVICE → Backend:
  POST /api/face/ingest {device_id, label, confidence}
  ↓ Backend updates state → access="allow", expires at t+5s

ESP32 → Backend:
  
  POLL (every 2s):
    GET /api/access?device_id=esp32-1
    ← {access, identity, expires_in}
  
  QUERY COMMAND (every 2s):
    GET /api/command?device_id=esp32-1
    ← {action: "open_door" | null}
  
  REPORT SENSOR (every 10s):
    POST /api/sensor {device_id, distance1, distance2, temp}
    ← {ok: true}
  
  REPORT DOOR STATE (on change):
    POST /api/door/state {device_id, state: "open"|"closed"}
    ← {ok: true}

WA Bot → Backend:
  POST /api/command/execute {device_id, action, requester}
  ← {ok: true, result}

Frontend → Backend:
  GET /api/state → all device states
  GET /api/history → events
  POST /api/door/action {device_id, action} → manual control
```

**No redundant endpoints!**

---

**Timeline dengan Fix:**

```
t=0.0s: Face detected (confidence 1.0)
t=0.05s: POST /api/face/ingest
         backend sets: access="allow", expires_at=t+5
t=0.1s: ESP poll /api/access
t=0.11s: Response: {access: "allow", identity: "me", expires_in: 4.9}
t=0.12s: ESP relay HIGH
t=0.15s: Door physically opens

TOTAL DELAY: 0.15s (INSTANT!)

vs OLD: 2+ detik delay
```

---

## 🔧 KEY FIXES NEEDED

### Fix #1: Device ID Resolution
```python
# Current: Chaos
# Face service: device_id from face payload (varies)
# ESP: device_id from query param (varies)
# Backend: tries to match (confusing)

# SOLUTION: Use environment configuration
# 1 device = 1 device_id everywhere
# backend/.env:
#   DEFAULT_DEVICE_ID=esp32-1
#   FACE_SERVICE_DEVICE_ID=esp32-1
# 2. Validate all inbound requests
# 3. Auto-normalize to canonical ID
```

### Fix #2: Validation with Error Response
```python
# Current:
# @app.post("/api/sensor/update")
# async def sensor_update(payload: dict):
#     try:
#         # process
#     except:
#         pass  # Silent error!
#     return {"ok": true}

# NEW:
# @app.post("/api/sensor/update")
# async def sensor_update(payload: dict):
#     try:
#         distance1 = float(payload.get("distance1"))
#         if distance1 < 0 or distance1 > 400:
#             return {"ok": false, "error": "Invalid distance"}
#     except ValueError:
#         return {"ok": false, "error": "distance1 must be number"}
#     return {"ok": true}
```

### Fix #3: ESP Retry + Backoff
```python
# ESP pseudocode:
# OLD:
# while True:
#     get /api/access
#     post /api/sensor/update
#     get /api/command

# NEW:
# def request_with_backoff(url, max_retries=3):
#     for attempt in range(max_retries):
#         try:
#             response = requests.get(url, timeout=2)
#             return response
#         except Exception as e:
#             wait = 2 ** attempt  # 1s, 2s, 4s
#             sleep(wait)
#     return None
```

### Fix #4: Non-Blocking Handlers
```python
# Current: May have blocking calls
# NEW: Use async where needed

@app.get("/api/access")
async def get_access(device_id: str):
    # No blocking DB calls, just memory access
    # Should be <10ms latency
    return state.get_current(device_id)
```

---

## 📋 FULL IMPLEMENTATION PLAN

See: ARCHITECTURE_REDESIGN.md + CODE_FIXES.md (akan dibuat next)

---

## ✅ STATUS

- ✓ Root cause analysis: DONE
- 🔨 Architecture design: NEXT
- 🔨 Code implementation: NEXT
- 🔨 Testing: NEXT

