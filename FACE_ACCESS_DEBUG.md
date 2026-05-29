# Face Recognition Access Control - Debug Guide

## Problem Summary
Face recognition detects user correctly ("allow") but ESP32 polling `/api/access` still receives "deny".

## Root Causes Fixed

### 1. **Consume Logic Bug** ❌ FIXED
**Problem**: `consume()` marked state as consumed after first call, so second poll returned deny immediately
- Old code: `if state.get("access") == "allow" and not state.get("consumed")`
- Result: First call returns allow, second call returns deny

**Solution**: 
- Separated two methods:
  - `get_current()`: Read-only, non-consuming, returns current state
  - `consume()`: Consumes state for one-time delivery (used by `/api/command`)
- `/api/access` now uses `get_current()` → can poll multiple times
- `/api/command` uses `consume()` → one-time door open command

### 2. **State Not Persisting** ❌ FIXED
**Problem**: State might not be stored in `_states` dict

**Solution**: 
- Added debug logging with environment variable `DEBUG_ACCESS=1`
- All `set_allow()`, `set_deny()`, `get_current()`, `consume()` now log operations
- State dict shows: `{access, identity, updated_at, expires_at, source_device_id}`

### 3. **Device ID Mismatch** ❌ FIXED
**Problem**: Face service sends device_id="face-service" but ESP32 queries with device_id="esp32-1"

**Solution**:
- Improved `_resolve_target_device_id()` to handle multiple formats
- Accepts: "esp32-1", "face-service", "face-001", etc.
- Falls back to `ACCESS_DEVICE_ID` environment variable (default: "esp32-1")
- Added detailed logging of resolved device_id

### 4. **No State Timeout** ❌ FIXED
**Problem**: State stays in "allow" forever, or state doesn't auto-reset

**Solution**:
- Added `expires_at` timestamp to state
- `get_current()` checks: `if now >= expires_at: return deny`
- Timeout controlled by `ACCESS_TIMEOUT` env var (default: 5.0 seconds)
- State automatically expires without manual reset

## How to Debug

### Step 1: Enable Debug Logging
```bash
# In backend/.env
DEBUG_ACCESS=1
```

Then check backend logs:
```bash
# Terminal 1: Run backend
cd backend
python -m app.main

# Terminal 2: Run face recognition simulation
curl -X POST http://localhost:8000/api/face/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "esp32-1",
    "label": "me",
    "confidence": 0.95
  }'

# Watch backend logs for:
# [ACCESS] set_allow for esp32-1: identity=me, expires_at=1234567890.5
```

### Step 2: Check State Immediately
```bash
# Check if state was stored
curl http://localhost:8000/api/debug/access-state?device_id=esp32-1

# Should return:
{
  "device_id": "esp32-1",
  "resolved_target": "esp32-1",
  "now": 1234567890.123,
  "state": {
    "access": "allow",
    "identity": "me",
    "updated_at": 1234567890.0,
    "expires_at": 1234567895.0,
    "source_device_id": ""
  },
  "is_expired": false,
  "expires_in_seconds": 4.877
}
```

### Step 3: Poll /api/access Multiple Times
```bash
# First poll (within timeout)
curl http://localhost:8000/api/access?device_id=esp32-1
# {"access": "allow", "identity": "me"}

# Second poll (within timeout)
curl http://localhost:8000/api/access?device_id=esp32-1
# {"access": "allow", "identity": "me"}  <- SAME RESULT (not consumed!)

# Wait > 5 seconds
sleep 6

# Third poll (after timeout)
curl http://localhost:8000/api/access?device_id=esp32-1
# {"access": "deny"}  <- Auto-expired
```

### Step 4: Verify /api/command Consumes State
```bash
# Face recognition: set state to allow
curl -X POST http://localhost:8000/api/face/ingest \
  -H "Content-Type: application/json" \
  -d '{"device_id": "esp32-1", "label": "me", "confidence": 0.95}'

# /api/command returns one-time door command
curl http://localhost:8000/api/command?device_id=esp32-1
# {"action": "open_door"}

# Second call to /api/command
curl http://localhost:8000/api/command?device_id=esp32-1
# {"action": null}  <- Already consumed, returns no action

# But /api/access still works (until timeout)
curl http://localhost:8000/api/access?device_id=esp32-1
# {"access": "allow", "identity": "me"}  <- Still valid!
```

## Architecture

```
Face Recognition
       |
       | POST /api/face/ingest
       | {device_id, label, confidence}
       v
_process_face_recognition()
       |
       | access_state.set_allow(identity=label, device_id=device_id)
       |
       v
AccessState._states = {
  "esp32-1": {
    "access": "allow",
    "identity": "me",
    "updated_at": timestamp,
    "expires_at": timestamp + 5.0,
    "source_device_id": "..."
  }
}
       |
       +--------> /api/access polls every 2 seconds
       |          |
       |          v
       |          access_state.get_current(device_id=device_id)
       |          - Checks if expires_at > now
       |          - Returns current state (read-only)
       |          - Multiple polls = same result
       |
       +--------> /api/command polls once for door command
                  |
                  v
                  access_state.consume(device_id=device_id)
                  - Returns state AND resets to deny
                  - Next call = "action": null
```

## Key Changes

| File | Change | Why |
|------|--------|-----|
| `access_state.py` | Split `consume()` into `get_current()` + `consume()` | Allow polling without state being destroyed |
| `access_state.py` | Added `expires_at` timeout | Auto-expire state without manual reset |
| `access_state.py` | Added debug logging | Trace state flow for debugging |
| `main.py` | `/api/access` uses `get_current()` | Non-consuming, multiple polls work |
| `main.py` | `/api/command` uses `consume()` | One-time door open delivery |
| `main.py` | Added `/api/debug/access-state` | Real-time state inspection |

## Environment Variables

```bash
# Access control
ACCESS_DEVICE_ID=esp32-1              # Default device ID for access decisions
ACCESS_TIMEOUT=5.0                    # How long allow state lasts (seconds)
DEBUG_ACCESS=0                        # Enable detailed access state logging

# Face recognition
FACE_CONFIDENCE_THRESHOLD=0.7         # Min confidence for allow
FACE_ACCESS_TIMEOUT=5.0               # How long to remember face result

# Example .env
DEBUG_ACCESS=1
ACCESS_TIMEOUT=5.0
FACE_CONFIDENCE_THRESHOLD=0.7
```

## Testing Checklist

- [ ] Face recognition fires successfully
- [ ] `/api/face/ingest` returns `{"access": "allow", "identity": "me"}`
- [ ] `/api/debug/access-state` shows state stored with `expires_at` > now
- [ ] `/api/access` returns allow (first poll)
- [ ] `/api/access` returns allow (second poll, no timeout yet)
- [ ] `/api/command` returns `{"action": "open_door"}` (first call)
- [ ] `/api/command` returns `{"action": null}` (second call, consumed)
- [ ] Wait 5+ seconds
- [ ] `/api/access` returns deny (timeout expired)
- [ ] Device ID resolution works for both "esp32-1" and "face-service"

## Troubleshooting

### Problem: `/api/access` still returns deny after `/api/face/ingest` returns allow
1. Check device ID mismatch: `curl http://localhost:8000/api/debug/access-state`
2. Verify face_service sends correct device_id in POST
3. Check if state is expired: `"is_expired": true`?
4. Enable DEBUG_ACCESS=1 and check logs

### Problem: `/api/command` always returns "action": null
- This is correct! (state consumed after first call)
- Re-run `/api/face/ingest` to reset state
- Verify `/api/access` returns allow before calling `/api/command`

### Problem: State expires too quickly
- Check `ACCESS_TIMEOUT` env var (default 5s)
- Is system time correct on backend?
- Check for clock skew between backend and ESP32

### Problem: Multiple devices sharing state
- Check device ID resolution in logs
- Each device should have separate `_states[device_id]` entry
- Use `/api/debug/access-state` to see all device states
