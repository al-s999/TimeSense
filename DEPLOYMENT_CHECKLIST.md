# Deployment Checklist

## Pre-Deployment

- [ ] Review IMPLEMENTATION_COMPLETE.md
- [ ] Review FLOW_DIAGRAMS.md to understand the fix
- [ ] Read QUICK_REFERENCE.md

## Local Testing

- [ ] Syntax check: `python -m py_compile backend/app/access_state.py backend/app/main.py`
- [ ] Import check: `python3 -c "from app.access_state import get_access_state; print('✓')"`
- [ ] Build check: `npm run build`
- [ ] Run integration test: `python test_face_access.py` (must see `✓ ALL TESTS PASSED!`)

## Environment Setup

- [ ] Create/update `backend/.env`:
  ```bash
  DEBUG_ACCESS=1                    # Enable during first week
  ACCESS_DEVICE_ID=esp32-1          # Match your ESP32 device_id
  ACCESS_TIMEOUT=5.0                # Timeout for access state
  FACE_CONFIDENCE_THRESHOLD=0.7     # Min confidence
  ```

## Deployment

- [ ] Backup current backend code
- [ ] Copy modified files:
  - `backend/app/access_state.py` (NEW - complete rewrite)
  - `backend/app/main.py` (UPDATED - 3 endpoints changed)
- [ ] Copy new files:
  - `test_face_access.py`
  - `IMPLEMENTATION_COMPLETE.md`
  - `FLOW_DIAGRAMS.md`
  - `QUICK_REFERENCE.md`
  - `FACE_ACCESS_DEBUG.md`
  - `FACE_ACCESS_FIX_SUMMARY.md`

## Post-Deployment

- [ ] Restart backend service
- [ ] Check backend logs for startup errors
- [ ] Run `python test_face_access.py` to verify
- [ ] Test face recognition:
  - Person stands in front of camera
  - Check logs for "ACCESS ALLOWED: me (conf: X.X)"
- [ ] Test `/api/access`:
  - ESP32 should receive `{"access": "allow"}`
  - Multiple polls should return same result (not "deny")
- [ ] Test `/api/command`:
  - First call should return `{"action": "open_door"}`
  - Door should open
- [ ] Test auto-expiry:
  - Wait 6+ seconds after face detection
  - `/api/access` should return `{"access": "deny"}`

## Production Monitoring (First Week)

- [ ] Keep `DEBUG_ACCESS=1` enabled
- [ ] Monitor backend logs for:
  - `[ACCESS] set_allow` - Face detection working
  - `[ACCESS] get_current` - Polls working
  - `[ACCESS] consume` - Commands working
- [ ] Watch for any errors or exceptions
- [ ] Verify door opens on first face detection
- [ ] Verify door doesn't open multiple times

## Validation Tests

### Test 1: Multiple Polls Return Same Result
```bash
# Trigger face recognition
curl -X POST http://localhost:8000/api/face/ingest \
  -H "Content-Type: application/json" \
  -d '{"device_id":"esp32-1","label":"me","confidence":0.95}'

# Poll 1
curl http://localhost:8000/api/access?device_id=esp32-1
# Expected: {"access": "allow", "identity": "me"}

# Poll 2 (immediately)
curl http://localhost:8000/api/access?device_id=esp32-1
# Expected: {"access": "allow", "identity": "me"} ← SAME!
# Before fix: would be {"access": "deny"}
```

### Test 2: One-Time Command
```bash
# Trigger face recognition
curl -X POST http://localhost:8000/api/face/ingest \
  -H "Content-Type: application/json" \
  -d '{"device_id":"esp32-1","label":"me","confidence":0.95}'

# Command 1
curl http://localhost:8000/api/command?device_id=esp32-1
# Expected: {"action": "open_door"}

# Command 2 (immediately)
curl http://localhost:8000/api/command?device_id=esp32-1
# Expected: {"action": null} ← No repeat
```

### Test 3: State Auto-Expiry
```bash
# Trigger face recognition
curl -X POST http://localhost:8000/api/face/ingest \
  -H "Content-Type: application/json" \
  -d '{"device_id":"esp32-1","label":"me","confidence":0.95}'

# Poll immediately
curl http://localhost:8000/api/access?device_id=esp32-1
# Expected: {"access": "allow"}

# Wait 6 seconds
sleep 6

# Poll after timeout
curl http://localhost:8000/api/access?device_id=esp32-1
# Expected: {"access": "deny"} ← Auto-expired
```

## Rollback Plan

If issues occur:

1. **Backend crashes on startup:**
   - Check logs: `python -m py_compile backend/app/access_state.py`
   - Restore backup: `cp backup/access_state.py backend/app/`
   - Restart backend

2. **Multiple polls still return deny:**
   - Check `/api/debug/access-state` - is state stored?
   - Verify device_id matches between face service and ESP32
   - Check system time is correct
   - Enable full Python debugging: `DEBUG=1`

3. **Door opens multiple times:**
   - Verify `/api/command` returns null on second call
   - Check consume() logic is working
   - Review logs for multiple successful commands

4. **State never expires:**
   - Check system time: `date`
   - Verify `ACCESS_TIMEOUT=5.0` in `.env`
   - Restart backend after env change

## After One Week

- [ ] Disable debug logging: `DEBUG_ACCESS=0`
- [ ] Restart backend
- [ ] Run one final test: `python test_face_access.py`
- [ ] Monitor for any errors

## Troubleshooting Commands

```bash
# View all device states
curl http://localhost:8000/api/debug/access-state | jq

# View specific device
curl http://localhost:8000/api/debug/access-state?device_id=esp32-1 | jq

# Check backend health
curl http://localhost:8000/api/health

# Run full integration test
cd /path/to/project
python test_face_access.py

# Check Python syntax
python -m py_compile backend/app/access_state.py

# View backend logs
tail -f backend.log
```

## Success Criteria

✓ All tests pass
✓ Face detection works and sets "allow" state
✓ Multiple `/api/access` polls return consistent state
✓ `/api/command` returns one-time door command
✓ State auto-expires after 5 seconds
✓ Door opens correctly on face recognition
✓ Door doesn't open multiple times
✓ No errors in backend logs
✓ No performance degradation

---

## Questions Before Deployment?

- Is device_id correct in face service?
- Is device_id correct in ESP32 polling?
- Are both services using same time zone?
- Is backend system time correct?
- Are there multiple backend instances running?

---

**Ready to Deploy? Start with Local Testing section above.** ✓
