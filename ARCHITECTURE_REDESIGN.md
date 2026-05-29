# SMART DOOR - ARCHITECTURE REDESIGN

## 🎯 VISION: Single Source of Truth

**Current (BAD):**
```
State scatter across:
- ESP memory (relay state)
- Backend (access state)
- Face service (detection result)
- Frontend (last known state)
→ INCONSISTENT!
```

**New (GOOD):**
```
BACKEND = Single Source of Truth
├─ All state centralized
├─ ESP/Face/Frontend query backend
├─ Clear, consistent, auditable
```

---

## 📐 SYSTEM ARCHITECTURE

### Layer 1: Device Interface (ESP32 + Face Service)

```
┌─────────────────────────────────────────────────────────┐
│  DEVICE LAYER                                           │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Face Service              ESP32                       │
│  ├─ Detect face           ├─ Read sensors              │
│  ├─ Get confidence        ├─ Control relay             │
│  └─ POST /api/face/ingest └─ Report state              │
│                                                         │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│  BACKEND API LAYER (FastAPI)                            │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Ingest Service            Query Service               │
│  ├─ /api/face/ingest       ├─ /api/access              │
│  ├─ /api/sensor            ├─ /api/command             │
│  └─ /api/door/state        └─ /api/status              │
│                                                         │
│  Command Service           Admin Service               │
│  ├─ /api/command/execute   ├─ /api/debug/state         │
│  └─ /api/command/queue     └─ /api/history             │
│                                                         │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│  STATE LAYER (In-Memory Cache + DB)                    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  device_states[device_id]:                             │
│  ├─ access: "allow" | "deny" | "timeout"               │
│  ├─ identity: str | null                               │
│  ├─ door_state: "open" | "closed"                      │
│  ├─ updated_at: timestamp                              │
│  └─ expires_at: timestamp                              │
│                                                         │
│  sensor_data[device_id]:                               │
│  ├─ distance1: float (cm)                              │
│  ├─ distance2: float (cm)                              │
│  ├─ temperature: float (°C)                            │
│  └─ timestamp: float                                   │
│                                                         │
│  command_queue[device_id]:                             │
│  └─ [{action, priority, timestamp}, ...]               │
│                                                         │
│  events: [{type, device_id, data}, ...]                │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Layer 2: Request Flow (Detailed)

#### FACE RECOGNITION → ACCESS ALLOW

```
1. Face Service (Local Machine)
   └─ capture_and_recognize()
      └─ confidence = 1.0
         └─ label = "me"

2. POST /api/face/ingest
   ├─ Payload: {device_id, label, confidence}
   ├─ Validate: confidence >= 0.7, label != "unknown"
   └─ Response: {ok, access, identity}

3. Backend _process_face_recognition()
   ├─ Resolve device_id (canonical)
   ├─ Check confidence threshold
   ├─ If pass: set_allow(identity, expires_at=now+5s)
   ├─ Log: [FACE] ACCESS ALLOWED for device_id
   └─ Return: {access: "allow"}

4. ESP32 Polling (every 2 seconds)
   ├─ GET /api/access?device_id=esp32-1
   ├─ Backend checks: is state "allow"? expires_at > now?
   ├─ If yes: return {access: "allow", identity: "me"}
   ├─ ESP: set relay HIGH
   ├─ Log: [ESP] Relay HIGH
   └─ Door opens (physically)

5. EventStream (Optional)
   ├─ Backend broadcast: {type: "door_opened", device_id}
   ├─ Frontend: update dashboard
   └─ WA Bot: send notification
```

**Timeline:**
```
t=0.00s: Face detected
t=0.05s: POST /api/face/ingest
t=0.06s: Backend set_allow() ← STATE CHANGE
t=0.10s: ESP poll /api/access
t=0.11s: Returns allow
t=0.12s: ESP relay HIGH
t=0.20s: Door physically opens

LATENCY: 0.2 seconds (INSTANT! ✓)
```

---

#### SENSOR UPDATE → EVENT

```
1. ESP32 Sensor Reading
   ├─ distance1 = 50cm
   ├─ distance2 = 55cm
   └─ temp = 25°C

2. POST /api/sensor/update
   ├─ Payload: {device_id, distance1, distance2, temp}
   ├─ Validate: all numeric, distance 0-400cm
   └─ Response: {ok, message}

3. Backend _process_sensor_update()
   ├─ Resolve device_id
   ├─ Validate ranges (distance > 0 & < 400)
   ├─ If invalid: return {ok: false, error: "distance out of range"}
   ├─ Store in sensor_data[device_id]
   ├─ Run anomaly detection (if enabled)
   ├─ Check if crosses threshold (door trigger)
   └─ If trigger: set_deny() (door closed)

4. Event Recording
   ├─ If distance crosses threshold:
   │  └─ Create event: {type: "door_activity", data: {distance, etc}}
   ├─ Store in events table (DB)
   └─ Broadcast to frontend

5. Frontend sees update
   ├─ Subscribe to /api/stream/events
   ├─ Update live dashboard
   └─ Show sensor graph
```

---

#### WHATSAPP BOT COMMAND

```
1. User sends WhatsApp message
   ├─ "open door"
   └─ or: "lock"
   └─ or: "status"

2. WA Bot receives
   ├─ Parse message
   ├─ Determine action: open_door | lock | get_status
   ├─ Verify user authorized
   └─ Extract device_id

3. POST /api/command/execute
   ├─ Payload: {action: "open_door", device_id, requester_id}
   ├─ Backend processes
   ├─ If open_door: set_allow() temporarily
   ├─ Log: [WA_BOT] open_door triggered by user_id
   └─ Response: {ok, message}

4. ESP32 Polling
   ├─ GET /api/command?device_id=esp32-1
   ├─ Backend: check if state="allow"
   ├─ Returns: {action: "open_door"} ← consume()
   ├─ ESP: relay HIGH
   └─ Door opens

5. WA Bot Response
   ├─ Send confirmation: "Door opened for 5 seconds"
   ├─ Or error: "Device not responding"
   └─ Include timestamp
```

---

#### ERROR RECOVERY FLOW

```
SCENARIO: Backend down, ESP can't connect

1. ESP retry logic
   ├─ Attempt 1: GET /api/access (fail) → wait 1s
   ├─ Attempt 2: GET /api/access (fail) → wait 2s
   ├─ Attempt 3: GET /api/access (fail) → wait 4s
   └─ After 3 attempts: give up, wait cooldown

2. ESP fallback
   ├─ If no access from backend for N minutes:
   │  └─ Open door anyway (fail-open for safety)
   ├─ OR: keep relay state unchanged (fail-secure)
   └─ Log: [ESP] Offline mode activated

3. Frontend shows error
   ├─ If API not responding
   ├─ Show: "Backend disconnected, system in offline mode"
   ├─ Disable manual controls
   └─ Show last known state

4. Auto recovery
   ├─ When backend comes back
   ├─ ESP reconnect automatically (exponential backoff resets)
   ├─ Sync state with backend
   └─ Log: [ESP] Reconnected to backend
```

---

## 🔄 REQUEST/RESPONSE FLOWS (DETAILED)

### API #1: POST /api/face/ingest

**Purpose:** Face detection result from face service

**Request:**
```json
{
  "device_id": "esp32-1",
  "label": "me",
  "confidence": 0.95
}
```

**Validation:**
```python
errors = []
if not device_id:
    errors.append("device_id required")
if confidence < 0 or confidence > 1:
    errors.append("confidence must be 0-1")
if label == "unknown" or confidence < CONFIDENCE_THRESHOLD:
    errors.append("face not recognized or low confidence")

if errors:
    return {
        "ok": False,
        "access": "deny",
        "error": "; ".join(errors)
    }
```

**Response (Success):**
```json
{
  "ok": true,
  "access": "allow",
  "identity": "me",
  "expires_in": 5.0
}
```

**Response (Failure):**
```json
{
  "ok": false,
  "access": "deny",
  "error": "confidence < threshold (0.5 < 0.7)"
}
```

---

### API #2: GET /api/access?device_id=esp32-1

**Purpose:** Check if device is allowed access (polling)

**Response (Allowed):**
```json
{
  "access": "allow",
  "identity": "me",
  "expires_in": 3.2,
  "timestamp": 1650000000.123
}
```

**Response (Denied):**
```json
{
  "access": "deny",
  "identity": null,
  "expires_in": 0,
  "timestamp": 1650000000.456
}
```

**Response (Error):**
```json
{
  "access": "deny",
  "error": "device_id not found",
  "status": 400
}
```

---

### API #3: GET /api/command?device_id=esp32-1

**Purpose:** Get one-time command (consumes state)

**Response (Has Command):**
```json
{
  "ok": true,
  "action": "open_door",
  "priority": 10,
  "ttl": 300
}
```

**Response (No Command):**
```json
{
  "ok": true,
  "action": null
}
```

---

### API #4: POST /api/sensor/update

**Purpose:** Report sensor readings

**Request:**
```json
{
  "device_id": "esp32-1",
  "distance1": 50.5,
  "distance2": 52.3,
  "temperature": 25.4,
  "timestamp": 1650000000.123
}
```

**Validation:**
```python
def validate_sensor_update(payload):
    errors = []
    
    d1 = payload.get("distance1")
    if d1 is None or d1 < 0 or d1 > 400:
        errors.append("distance1 must be 0-400cm")
    
    d2 = payload.get("distance2")
    if d2 is None or d2 < 0 or d2 > 400:
        errors.append("distance2 must be 0-400cm")
    
    temp = payload.get("temperature")
    if temp is not None and (temp < -50 or temp > 80):
        errors.append("temperature out of range -50 to 80°C")
    
    return errors
```

**Response:**
```json
{
  "ok": true,
  "stored": {
    "distance1": 50.5,
    "distance2": 52.3,
    "temperature": 25.4
  }
}
```

---

### API #5: POST /api/door/state

**Purpose:** Report physical door state change

**Request:**
```json
{
  "device_id": "esp32-1",
  "state": "open",
  "timestamp": 1650000000.123
}
```

**Response:**
```json
{
  "ok": true,
  "previous_state": "closed"
}
```

---

### API #6: POST /api/command/execute

**Purpose:** Manual command from WA Bot or frontend

**Request:**
```json
{
  "device_id": "esp32-1",
  "action": "open_door",
  "requester": "user_123",
  "requester_type": "whatsapp_bot"
}
```

**Response:**
```json
{
  "ok": true,
  "action": "open_door",
  "queued": true,
  "message": "Command queued, will execute on next poll"
}
```

---

### API #7: GET /api/debug/access-state

**Purpose:** Debug endpoint (dev only)

**Response:**
```json
{
  "timestamp": 1650000000.123,
  "devices": {
    "esp32-1": {
      "access": "allow",
      "identity": "me",
      "updated_at": 1650000000.000,
      "expires_at": 1650000005.000,
      "expires_in": 3.2,
      "is_expired": false
    }
  }
}
```

---

## 💾 STATE STRUCTURE (Backend In-Memory)

```python
# Global state dict
_states = {
    "esp32-1": {
        # Access state
        "access": "allow",           # allow | deny
        "identity": "me",            # Who was recognized
        "updated_at": 1650000000.0,  # When state changed
        "expires_at": 1650000005.0,  # When it expires
        "source": "face",            # face | command | manual
        
        # Door state
        "door_state": "open",        # open | closed | unknown
        "door_changed_at": 1650000000.0,
        
        # Sensor data (latest)
        "distance1": 50.5,
        "distance2": 52.3,
        "temperature": 25.4,
        "sensor_updated_at": 1650000000.0,
    },
    "esp32-2": { ... }
}

# Command queue
_commands = {
    "esp32-1": [
        {
            "action": "open_door",
            "priority": 10,
            "created_at": 1650000000.0,
            "ttl": 300
        }
    ]
}

# Events (for history/dashboard)
_events = [
    {
        "id": 1,
        "timestamp": 1650000000.0,
        "device_id": "esp32-1",
        "type": "face_detected",  # face_detected | door_opened | door_closed | sensor_anomaly
        "data": {
            "identity": "me",
            "confidence": 0.95,
            "distance1": 50.5,
            "distance2": 52.3
        }
    }
]
```

---

## 🔧 BACKEND CODE STRUCTURE

```
backend/app/
├─ main.py                    # FastAPI app + routes
├─ access_state.py           # State management (FIXED)
├─ models.py                 # DB models
├─ schemas.py                # Request/response schemas
├─ db.py                     # DB connection
├─ state_manager.py          # NEW: Unified state handling
├─ command_queue.py          # NEW: Command management
├─ event_logger.py           # NEW: Event tracking
├─ sensor_handler.py         # NEW: Sensor processing
├─ validators.py             # NEW: Input validation
└─ utils.py                  # Helpers
```

---

## 📊 DEVICE STATE MACHINE

```
Initial: UNKNOWN

        ┌────────────────────────┐
        │   FACE INGEST          │
        │  (confidence >= 0.7)   │
        └───────────┬────────────┘
                    ↓
        ┌────────────────────────┐
        │   STATE = ALLOW        │
        │   expires_at = now+5s  │
        └───────────┬────────────┘
                    ↓
        ESP Polls /api/access
                    ↓
        ┌────────────────────────┐
        │   STATE = ALLOW?       │
        │   expires_at > now?    │
        └───┬─────────────────┬──┘
            │ YES             │ NO
            ↓                 ↓
        open_door      time_expired
            ↓                 ↓
        ALLOW         ┌──────────────┐
        (consume)     │ STATE=DENY   │
            ↓         └──────┬───────┘
        ┌──────────────────────────┐
        │   WAIT FOR NEXT EVENT    │
        │   (ALLOW expires OR      │
        │    New face detected)    │
        └──────────────────────────┘
```

---

## 🎯 ERROR SCENARIOS & HANDLING

### Scenario 1: Device ID Mismatch
```
Problem:
  Face service sends: device_id="face-cam-1"
  ESP queries with:   device_id="esp32-1"

Solution:
  1. Backend .env: MAP_DEVICE_ID = {"face-cam-1": "esp32-1"}
  2. _resolve_device_id() normalizes all to "esp32-1"
  3. Log: [DEVICE] Resolved face-cam-1 → esp32-1

Result: No mismatch!
```

### Scenario 2: High Latency Network
```
Problem:
  GET /api/access takes 5 seconds (network lag)

Solution:
  1. Timeout on client: requests.get(timeout=2)
  2. Retry on client: exponential backoff
  3. Backend: fast (<10ms) - just return state

Result: No timeout-induced failures!
```

### Scenario 3: Sensor Invalid Data
```
Problem:
  ESP sends: distance1=-5, distance2=500, temp="abc"

Solution:
  1. Validation returns: {ok: false, error: "distance out of range"}
  2. No data stored
  3. Log: [SENSOR] Invalid distance1=-5
  4. Increment error counter (for monitoring)

Result: Bad data never enters system!
```

---

## 🚀 DEPLOYMENT CHECKLIST

- [ ] Update backend/.env with device mappings
- [ ] Deploy new access_state.py (DONE)
- [ ] Deploy new main.py endpoints
- [ ] Test /api/face/ingest → /api/access flow
- [ ] Add retry logic to ESP32 firmware
- [ ] Test ESP poll with backoff
- [ ] Verify WA Bot integration
- [ ] Load test with multiple devices
- [ ] Monitor latency (target <100ms)
- [ ] Enable DEBUG_ACCESS=1 for first week

---

This architecture provides:
✓ Single source of truth
✓ Clear request/response contracts
✓ Error handling & validation
✓ Scalability for multiple devices
✓ Easy debugging
✓ Production ready

Next: Implementation code & ESP32 fixes

