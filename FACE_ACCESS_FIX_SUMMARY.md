# Face Recognition Access Control - Fix Summary

## ✓ What Was Wrong

Your system had a **critical state management bug** that prevented the ESP32 from recognizing face recognition results:

```
Face recognition: "ACCESS ALLOWED: me (conf: 1.0)" ✓
/api/face/ingest response: {"access": "allow"} ✓
/api/access response: {"access": "deny"} ✗ BUG!
```

### Root Causes

1. **Consume-Once Bug** - Once `/api/access` was polled, the state was marked as "consumed", so the next poll returned "deny"
   - Result: ESP32 polling every 2 seconds would get: allow, deny, deny, deny...
   
2. **No State Timeout** - State stayed in memory forever (or relied on fragile timestamps)
   - Result: Old face results from hours ago could still trigger doors
   
3. **No Multi-Poll Support** - State was destroyed after first read
   - Result: Second ESP32 poll always got "deny"

---

## ✓ What Was Fixed

### **New Architecture: Separate Read vs Consume**

```python
# OLD (BROKEN)
/api/access → consume() → marks consumed=True → next poll denies

# NEW (FIXED)
/api/access → get_current() → reads without consuming → multiple polls work
/api/command → consume() → one-time door command delivery
```

### **Files Modified**

#### 1. `backend/app/access_state.py` (MAJOR REWRITE)
- ✓ Split `consume()` into two methods:
  - `get_current()` - Read-only, non-consuming, for polling
  - `consume()` - Consuming version, for one-time commands
- ✓ Added `expires_at` timeout (automatic expiration)
- ✓ Added debug logging (enable with `DEBUG_ACCESS=1`)
- ✓ Improved device ID resolution for multiple formats
- ✓ Added `get_all_states()` for debugging

#### 2. `backend/app/main.py` (UPDATED ENDPOINTS)
- ✓ `/api/access` - Now uses `get_current()` (can poll infinitely)
- ✓ `/api/command` - Now uses `consume()` (one-time delivery)
- ✓ `/api/debug/access-state` - NEW debug endpoint to inspect state

#### 3. **New Debug Tools**
- ✓ `/api/debug/access-state` - Real-time state inspection
- ✓ `test_face_access.py` - Integration test script
- ✓ `FACE_ACCESS_DEBUG.md` - Comprehensive debugging guide

---

## ✓ How It Works Now

```
FACE RECOGNITION DETECTED (confidence: 0.95)
    ↓
POST /api/face/ingest
    ↓
_process_face_recognition()
    ↓
access_state.set_allow(identity="me", device_id="esp32-1", expires_in=5s)
    ↓
State stored in _states["esp32-1"] = {
    access: "allow",
    identity: "me",
    expires_at: 1234567895.0,
    ...
}
    ↓
ESP32 polls every 2 seconds:
    
POLL 1 (t=0): GET /api/access → {"access": "allow", "identity": "me"} ✓
POLL 2 (t=2): GET /api/access → {"access": "allow", "identity": "me"} ✓
POLL 3 (t=4): GET /api/access → {"access": "allow", "identity": "me"} ✓
POLL 4 (t=6): GET /api/access → {"access": "deny"} [EXPIRED]
    
ONE-TIME COMMAND:
    
COMMAND 1: GET /api/command → {"action": "open_door"} [STATE CONSUMED]
COMMAND 2: GET /api/command → {"action": null} [NO REPEAT]
```

---

## ✓ Key Improvements

| Issue | Before | After | Why |
|-------|--------|-------|-----|
| Multiple polls | 1st=allow, 2nd=deny | All=allow (until timeout) | `get_current()` doesn't consume |
| State persistence | Lost after read | Persistent until timeout | `expires_at` instead of `consumed` flag |
| Timeout | Manual/fragile | Automatic expiration | Built-in timeout check |
| One-time commands | Unclear behavior | Explicit `consume()` | Separate from polling |
| Device ID resolution | Fragile | Robust multi-format | Handles "esp32-1", "face-service", etc |
| Debugging | No visibility | `/api/debug/access-state` | See state in real-time |

---

## ✓ How to Verify the Fix

### Quick Test (5 minutes)

```bash
# Terminal 1: Start backend
cd backend
python -m app.main

# Terminal 2: Run integration test
python test_face_access.py

# Expected output:
# ✓ STEP 1: Health Check
# ✓ STEP 2: Face Recognition Ingest
# ✓ STEP 3: Check State (Immediately After Ingest)
# ✓ STEP 4: First Poll: /api/access
# ✓ STEP 5: Second Poll: /api/access (Without Timeout)
# ✓ ALL TESTS PASSED!
```

### Manual Test (step-by-step)

```bash
# 1. Trigger face recognition
curl -X POST http://localhost:8000/api/face/ingest \
  -H "Content-Type: application/json" \
  -d '{"device_id": "esp32-1", "label": "me", "confidence": 0.95}'

# Response: {"access": "allow", "identity": "me"}

# 2. Check state
curl http://localhost:8000/api/debug/access-state?device_id=esp32-1

# Response: state should show "access": "allow" and "expires_at" in future

# 3. Poll /api/access (first time)
curl http://localhost:8000/api/access?device_id=esp32-1

# Response: {"access": "allow", "identity": "me"}

# 4. Poll /api/access (second time - this is the KEY FIX)
curl http://localhost:8000/api/access?device_id=esp32-1

# Response: {"access": "allow", "identity": "me"} ← SAME RESULT!
# Before fix: this would be {"access": "deny"}
```

---

## ✓ Environment Variables

Add to `backend/.env`:

```bash
# Access control (new/improved)
DEBUG_ACCESS=1                    # Enable detailed logging
ACCESS_DEVICE_ID=esp32-1          # Default device ID
ACCESS_TIMEOUT=5.0                # How long allow state lasts

# Face recognition
FACE_CONFIDENCE_THRESHOLD=0.7     # Min confidence for access
FACE_ACCESS_TIMEOUT=5.0           # Legacy variable (now handled by AccessState)
```

---

## ✓ Testing Checklist

Before going to production, verify:

- [ ] `python test_face_access.py` passes all tests
- [ ] Face recognition detects user correctly
- [ ] `/api/access` can be polled multiple times and returns consistent result
- [ ] `/api/command` returns door command, then null on second call
- [ ] State auto-expires after 5 seconds
- [ ] Multiple devices (esp32-1, esp32-2) have separate states
- [ ] ESP32 actually opens the door when it gets open_door command
- [ ] Door doesn't open multiple times for single face detection

---

## ✓ Troubleshooting

### "Still Getting deny on first poll"
- Check `/api/debug/access-state` to see if state is stored
- Verify device_id matches: "esp32-1" in both face service and ESP32
- Check backend logs: `DEBUG_ACCESS=1` should show `[ACCESS] set_allow` message

### "Getting allow/deny/allow pattern"
- Old code is still running? Restart backend
- Multiple face services running? Kill all, start one
- Race condition? Add brief delay between polls

### "Timeout not working (state stays allow forever)"
- Check system time is correct: `date`
- Verify `ACCESS_TIMEOUT=5.0` is in `.env`
- Backend restarted after env change?

### "Device ID mismatch (face says allow, ESP32 gets deny)"
- Check face_service sends correct device_id
- Check ESP32 sends correct device_id in query param
- Use `/api/debug/access-state` to see what device_ids are stored

---

## ✓ Next Steps

1. **Deploy fixed code** - Update backend with new access_state.py and main.py
2. **Run test script** - Verify system works: `python test_face_access.py`
3. **Enable debug logging** - Set `DEBUG_ACCESS=1` for first week
4. **Monitor logs** - Watch for any `[ACCESS]` errors
5. **Test with ESP32** - Real hardware should now open door on face recognition
6. **Disable debug** - Set `DEBUG_ACCESS=0` after verification

---

## ✓ Summary

**The Problem**: State was consumed after first read, so repeated polls got deny

**The Solution**: 
- Separated read (`get_current()`) from consume (`consume()`)
- Added automatic timeout expiration
- Added comprehensive logging and debug endpoint

**The Result**:
- ✓ Multiple polls return consistent state
- ✓ One-time door command still works
- ✓ State auto-expires
- ✓ Full visibility into state transitions
- ✓ Easy to debug device ID issues

🎉 **System should now work end-to-end!**
