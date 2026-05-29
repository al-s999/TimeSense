# Face Recognition Access Control - Flow Diagrams

## Problem: Old Code (BROKEN)

```
Face Detected (conf: 0.95)
       ↓
POST /api/face/ingest
       ↓
_process_face_recognition()
       ↓
access_state.set_allow(identity="me", device_id="esp32-1")
       ↓
_states["esp32-1"] = {
  "access": "allow",
  "identity": "me",
  "consumed": False,  ← This is the problem!
  "timestamp": 1234567890
}
       ↓
ESP32 Polling Every 2 Seconds:
       ↓
POLL #1 (t=0):
  GET /api/access
       ↓
  access_state.consume(device_id="esp32-1")
       ↓
  if state["consumed"] == False:
    state["consumed"] = True  ← MARK AS CONSUMED!
    return {"access": "allow"}
       ↓
  Response: {"access": "allow"} ✓
       ↓
POLL #2 (t=2):
  GET /api/access
       ↓
  access_state.consume(device_id="esp32-1")
       ↓
  if state["consumed"] == False:  ← OOPS! Already consumed!
    ...
  return {"access": "deny"}
       ↓
  Response: {"access": "deny"} ✗ BUG!
       ↓
POLL #3 (t=4): {"access": "deny"} ✗
POLL #4 (t=6): {"access": "deny"} ✗

RESULT: Door never opens! (only first poll got allow)
```

---

## Solution: New Code (FIXED)

```
Face Detected (conf: 0.95)
       ↓
POST /api/face/ingest
       ↓
_process_face_recognition()
       ↓
access_state.set_allow(identity="me", device_id="esp32-1")
       ↓
_states["esp32-1"] = {
  "access": "allow",
  "identity": "me",
  "updated_at": 1234567890.0,
  "expires_at": 1234567895.0,  ← NEW: Auto-expiry time
  "source_device_id": "..."
}
       ↓
ESP32 Polling Every 2 Seconds:
       ↓
POLL #1 (t=0):
  GET /api/access
       ↓
  access_state.get_current(device_id="esp32-1")  ← NEW: Non-consuming!
       ↓
  now = 1234567890.5
  expires_at = 1234567895.0
  if now < expires_at:
    return state (WITHOUT marking consumed)
       ↓
  Response: {"access": "allow", "identity": "me"} ✓
       ↓
POLL #2 (t=2):
  GET /api/access
       ↓
  access_state.get_current(device_id="esp32-1")  ← Same method!
       ↓
  now = 1234567892.5
  expires_at = 1234567895.0
  if now < expires_at:
    return state (state UNCHANGED!)
       ↓
  Response: {"access": "allow", "identity": "me"} ✓ FIXED!
       ↓
POLL #3 (t=4): {"access": "allow"} ✓
       ↓
POLL #4 (t=6):
  now = 1234567896.5
  expires_at = 1234567895.0
  if now >= expires_at:
    return {"access": "deny"}  ← Auto-expired!
       ↓
  Response: {"access": "deny"} ✓ (timeout)

RESULT: Door opens correctly! (all polls until timeout return allow)
```

---

## State Lifecycle (NEW IMPLEMENTATION)

```
                        set_allow()
                           ↓
        ┌──────────────────────────────────────┐
        │                                      │
    [ALLOW STATE]                              │
    ├─ access: "allow"                         │
    ├─ identity: "me"                          │
    ├─ expires_at: T+5s                        │
    └─ consumed: false
        │
        ├─── get_current() ─→ {"access": "allow"}
        │   (read-only, state unchanged)
        │
        ├─── get_current() ─→ {"access": "allow"}
        │   (read-only, state unchanged)
        │
        ├─── get_current() ─→ {"access": "allow"}
        │   (read-only, state unchanged)
        │
        ├─── consume() ──→ {"access": "allow"}
        │   (one-time delivery, state→consumed)
        │
        ├─── consume() ──→ {"action": null}
        │   (already consumed, no action)
        │
        └─ TIME PASSES 5+ SECONDS
              ↓
        [EXPIRED STATE]
    ├─ access: "deny"  (auto-expired)
    └─ expires_at: past
        │
        └─── get_current() ─→ {"access": "deny"}
            (expired)
```

---

## Request Flow Comparison

### OLD CODE (BROKEN)
```
ESP32                Backend
  │                    │
  ├─ GET /api/access ──→ consume() → mark consumed
  │                    │
  │ ←── {"access":"allow"} ──┤
  │                    │
  ├─ GET /api/access ──→ consume() → state already consumed
  │                    │
  │ ←── {"access":"deny"} ──┤  ✗ WRONG!
```

### NEW CODE (FIXED)
```
ESP32                Backend
  │                    │
  ├─ GET /api/access ──→ get_current() → read without consuming
  │                    │
  │ ←── {"access":"allow"} ──┤
  │                    │
  ├─ GET /api/access ──→ get_current() → read without consuming
  │                    │
  │ ←── {"access":"allow"} ──┤  ✓ CORRECT!
  │                    │
  ├─ GET /api/access ──→ get_current() → read without consuming
  │                    │
  │ ←── {"access":"allow"} ──┤  ✓ CORRECT!
  │                    │
  ├─ GET /api/command ──→ consume() → one-time door delivery
  │                    │
  │ ←── {"action":"open_door"} ──┤
```

---

## Time-based Expiration (NEW)

```
FACE DETECTED at t=0
  ↓
set_allow() → expires_at = 0 + 5.0 = 5.0
  ↓
┌──────────────────────────────────────────────┐
│                                              │
│  ALLOW STATE VALID (state is fresh)          │
│  ├─ t=0.0: allow  ✓                          │
│  ├─ t=1.0: allow  ✓                          │
│  ├─ t=2.0: allow  ✓                          │
│  ├─ t=3.0: allow  ✓                          │
│  ├─ t=4.0: allow  ✓                          │
│  ├─ t=4.9: allow  ✓ (last valid moment)      │
│  │                                           │
│  └─ t=5.0: deny   ✗ (EXPIRED - now >= expires_at)
│  │                                           │
│  ├─ t=6.0: deny   ✗                          │
│  ├─ t=10.0: deny  ✗                          │
│                                              │
└──────────────────────────────────────────────┘

No manual reset needed - automatic based on time!
```

---

## State Persistence Comparison

### OLD (BROKEN) - Uses Consumption Flag
```
Poll 1: state.consumed = False → return allow, set consumed=True
Poll 2: state.consumed = True → return deny
Poll 3: state.consumed = True → return deny

Problem: One poll "uses up" the state
```

### NEW (FIXED) - Uses Timeout
```
Poll 1 @ t=0: now(0) < expires(5) → return allow
Poll 2 @ t=2: now(2) < expires(5) → return allow
Poll 3 @ t=4: now(4) < expires(5) → return allow
Poll 4 @ t=6: now(6) >= expires(5) → return deny

Problem solved: Multiple polls work until time expires
```

---

## Device State Management (Multiple Devices)

```
In-Memory State Store: _states dict

_states = {
  "esp32-1": {
    "access": "allow",
    "identity": "me",
    "expires_at": 1234567895.0,
    ...
  },
  "esp32-2": {
    "access": "deny",
    "identity": null,
    "expires_at": 1234567890.0,
    ...
  },
  "face-service": {
    "access": "allow",
    "identity": "friend",
    "expires_at": 1234567900.0,
    ...
  }
}

Device Resolution:
  _resolve_target_device_id("esp32-1") → "esp32-1"
  _resolve_target_device_id("face-service") → "face-service"
  _resolve_target_device_id(None) → "esp32-1" (default)
```

---

## Endpoint Behavior Summary

### `/api/access` (Non-Consuming Read)
```
Purpose: ESP32 polls to check if access is allowed
Method: GET
Query: device_id=esp32-1
Returns: {"access": "allow"|"deny", "identity": "..."}

Behavior:
  1st poll @ t=0 → {"access": "allow"}
  2nd poll @ t=2 → {"access": "allow"}  ← Key fix!
  3rd poll @ t=4 → {"access": "allow"}
  4th poll @ t=6 → {"access": "deny"}   ← Auto-expired

Can be polled infinitely without consuming state
```

### `/api/command` (One-Time Consuming)
```
Purpose: Get one-time door open command
Method: GET
Query: device_id=esp32-1
Returns: {"action": "open_door"|null}

Behavior:
  1st call → {"action": "open_door"}  (state consumed)
  2nd call → {"action": null}         (no more commands)

Must call get_current() or re-ingest face to get new command
```

### `/api/debug/access-state` (Inspection)
```
Purpose: Debug state synchronization issues
Method: GET
Query: device_id=esp32-1 (optional)
Returns: Full state dict with timing information

Useful for:
  - Verify state is stored
  - Check expires_at timestamp
  - See all devices in system
  - Debug device ID mismatches
```

---

## Key Changes Summary

| Component | Old | New | Benefit |
|-----------|-----|-----|---------|
| State flag | `consumed` (boolean) | `expires_at` (timestamp) | Auto-expiry, multiple reads |
| Read method | `consume()` destroys | `get_current()` preserves | Polling works correctly |
| Command method | `consume()` destroys | `consume()` one-time | Clear semantics |
| Timeout | Manual/fragile | Automatic in get_current() | Always works |
| Debug | No visibility | `/api/debug/access-state` | Easy troubleshooting |

---

## The Root Insight

**Problem**: Tried to use same method for two different needs
- "Is access allowed?" (polling - needs to read multiple times)
- "Get door command" (one-time - needs to deliver once)

**Solution**: Use different methods for different semantics
- `get_current()` - For polling (read-only)
- `consume()` - For one-time commands (destructive)

**Result**: Each use case works correctly ✓
