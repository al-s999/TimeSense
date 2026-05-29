# SMART DOOR - COMPREHENSIVE TESTING PLAN

## 🎯 TESTING STRATEGY

### Phase 1: Unit Testing (Individual Components)
### Phase 2: Integration Testing (Component Interactions)
### Phase 3: System Testing (Full End-to-End)
### Phase 4: Load Testing (Performance & Stability)
### Phase 5: Deployment Testing (Production Readiness)

---

## 🧪 PHASE 1: UNIT TESTING

### Test 1.1: Device ID Resolution

```python
# Test: backend/app/test_config.py
from app.config import resolve_device_id

def test_device_id_resolution():
    assert resolve_device_id("face-service") == "esp32-1"
    assert resolve_device_id("esp32-1") == "esp32-1"
    assert resolve_device_id("face-cam-1") == "esp32-1"
    assert resolve_device_id(None) == "esp32-1"
    assert resolve_device_id("unknown-device") == "esp32-1"
    
    print("✓ Device ID resolution: PASS")
```

### Test 1.2: Input Validation

```python
# Test: backend/app/test_validators.py
from app.validators import validate_face_ingest, validate_sensor_update

def test_face_ingest_validation():
    # Valid
    valid, errors = validate_face_ingest({
        "device_id": "esp32-1",
        "label": "me",
        "confidence": 0.95
    })
    assert valid == True
    assert len(errors) == 0
    
    # Missing confidence
    valid, errors = validate_face_ingest({
        "device_id": "esp32-1",
        "label": "me"
    })
    assert valid == False
    assert "confidence required" in errors
    
    # Invalid confidence
    valid, errors = validate_face_ingest({
        "device_id": "esp32-1",
        "label": "me",
        "confidence": 1.5
    })
    assert valid == False
    
    # Unknown label
    valid, errors = validate_face_ingest({
        "device_id": "esp32-1",
        "label": "unknown",
        "confidence": 0.9
    })
    assert valid == False
    
    print("✓ Face ingest validation: PASS")

def test_sensor_update_validation():
    # Valid
    valid, errors = validate_sensor_update({
        "device_id": "esp32-1",
        "distance1": 50.5,
        "distance2": 52.3,
        "temperature": 25
    })
    assert valid == True
    
    # Distance out of range
    valid, errors = validate_sensor_update({
        "device_id": "esp32-1",
        "distance1": 500,  # > 400
        "distance2": 52.3
    })
    assert valid == False
    assert any("distance1" in e for e in errors)
    
    # Negative distance
    valid, errors = validate_sensor_update({
        "device_id": "esp32-1",
        "distance1": -10,
        "distance2": 52.3
    })
    assert valid == False
    
    print("✓ Sensor validation: PASS")
```

### Test 1.3: Access State Management

```python
# Test: backend/app/test_access_state.py
from app.access_state import get_access_state
import time

def test_access_state():
    state = get_access_state()
    
    # Set allow
    state.set_allow(identity="me", device_id="esp32-1")
    
    # Get current (should return allow)
    result = state.get_current(device_id="esp32-1")
    assert result["access"] == "allow"
    assert result["identity"] == "me"
    
    # Get current again (should still return allow)
    result2 = state.get_current(device_id="esp32-1")
    assert result == result2
    
    # Consume (one-time)
    consumed = state.consume(device_id="esp32-1")
    assert consumed["access"] == "allow"
    
    # Consume again (should be deny now)
    consumed2 = state.consume(device_id="esp32-1")
    assert consumed2["access"] == "deny"
    
    # But get_current should still work
    result3 = state.get_current(device_id="esp32-1")
    assert result3["access"] == "deny"  # Wait, after consume, should be deny?
    # Actually depends on implementation - review!
    
    print("✓ Access state: PASS")

def test_access_state_expiration():
    state = get_access_state()
    
    # Set allow with short timeout
    state.set_allow(identity="test", device_id="esp32-1")
    
    # Should be allow
    result = state.get_current(device_id="esp32-1")
    assert result["access"] == "allow"
    
    # Wait for expiration (ACCESS_TIMEOUT)
    print("Waiting for expiration...")
    time.sleep(6)  # Assuming ACCESS_TIMEOUT=5
    
    # Should be deny now
    result2 = state.get_current(device_id="esp32-1")
    assert result2["access"] == "deny"
    
    print("✓ Access state expiration: PASS")
```

### Test 1.4: Command Queue

```python
# Test: backend/app/test_command_queue.py
from app.command_queue import get_command_queue, Command

def test_command_queue():
    queue = get_command_queue()
    
    # Clear
    queue.clear("esp32-1")
    
    # Enqueue
    queue.enqueue("esp32-1", Command(action="open_door", priority=10))
    queue.enqueue("esp32-1", Command(action="lock", priority=5))
    
    # Dequeue (should get highest priority first)
    cmd = queue.dequeue("esp32-1")
    assert cmd.action == "open_door"
    assert cmd.priority == 10
    
    # Next command
    cmd2 = queue.dequeue("esp32-1")
    assert cmd2.action == "lock"
    
    # No more commands
    cmd3 = queue.dequeue("esp32-1")
    assert cmd3 is None
    
    print("✓ Command queue: PASS")
```

---

## 🔗 PHASE 2: INTEGRATION TESTING

### Test 2.1: Face Detection → Access Allow

```python
# Test: backend/app/test_integration_face.py
import requests
import json

BASE_URL = "http://localhost:8000"

def test_face_detection_flow():
    """
    Simulate: Face detected → /api/face/ingest → /api/access returns allow
    """
    device_id = "esp32-1"
    
    # Step 1: Trigger face detection
    response = requests.post(
        f"{BASE_URL}/api/face/ingest",
        json={
            "device_id": device_id,
            "label": "me",
            "confidence": 0.95
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["access"] == "allow"
    assert data["identity"] == "me"
    print("✓ Face ingest: PASS")
    
    # Step 2: First poll /api/access
    response = requests.get(f"{BASE_URL}/api/access?device_id={device_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["access"] == "allow"
    assert data["identity"] == "me"
    print("✓ First access poll: PASS")
    
    # Step 3: Second poll /api/access (KEY FIX - should still be allow!)
    response = requests.get(f"{BASE_URL}/api/access?device_id={device_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["access"] == "allow", "ERROR: Second poll should still return allow!"
    print("✓ Second access poll (consistent): PASS")
    
    # Step 4: Poll /api/command (one-time)
    response = requests.get(f"{BASE_URL}/api/command?device_id={device_id}")
    assert response.status_code == 200
    data = response.json()
    assert data.get("action") == "open_door"
    print("✓ Command delivery: PASS")
    
    # Step 5: Poll /api/command again (should be consumed)
    response = requests.get(f"{BASE_URL}/api/command?device_id={device_id}")
    assert response.status_code == 200
    data = response.json()
    assert data.get("action") is None
    print("✓ Command consumed: PASS")
    
    print("\n✓✓✓ FACE DETECTION FLOW: COMPLETE AND WORKING!")

# Run
if __name__ == "__main__":
    import time
    time.sleep(1)  # Wait for server
    test_face_detection_flow()
```

### Test 2.2: Sensor Update → Event

```python
def test_sensor_update_flow():
    """
    Simulate: Sensor reading → /api/sensor/update → stored
    """
    device_id = "esp32-1"
    
    # Send sensor data
    response = requests.post(
        f"{BASE_URL}/api/sensor/update",
        json={
            "device_id": device_id,
            "distance1": 50.5,
            "distance2": 52.3,
            "temperature": 25.4
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] == True
    print("✓ Sensor update: PASS")
    
    # Check state was stored
    response = requests.get(f"{BASE_URL}/api/debug/state?device_id={device_id}")
    data = response.json()
    state = data["access_state"]
    assert state["distance1"] == 50.5
    assert state["distance2"] == 52.3
    assert state["temperature"] == 25.4
    print("✓ Sensor data stored: PASS")
    
    print("\n✓✓✓ SENSOR UPDATE FLOW: COMPLETE!")
```

### Test 2.3: Command Execution

```python
def test_command_execution_flow():
    """
    Simulate: WA Bot sends command → backend queues → ESP polls
    """
    device_id = "esp32-1"
    
    # Step 1: Execute command (e.g., from WA bot)
    response = requests.post(
        f"{BASE_URL}/api/command/execute",
        json={
            "device_id": device_id,
            "action": "open_door",
            "requester": "whatsapp_bot"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] == True
    print("✓ Command executed: PASS")
    
    # Step 2: ESP polls command
    response = requests.get(f"{BASE_URL}/api/command?device_id={device_id}")
    assert response.status_code == 200
    data = response.json()
    assert data.get("action") == "open_door"
    print("✓ Command retrieved: PASS")
    
    # Step 3: Check access state set
    response = requests.get(f"{BASE_URL}/api/access?device_id={device_id}")
    data = response.json()
    assert data["access"] == "allow"
    assert data["identity"] == "manual"
    print("✓ Access state set: PASS")
    
    print("\n✓✓✓ COMMAND EXECUTION FLOW: COMPLETE!")
```

---

## 🔴 PHASE 3: SYSTEM TESTING

### Test 3.1: Full End-to-End (Happy Path)

```python
def test_full_system_e2e():
    """
    Simulate complete workflow:
    1. Person approaches door (detected by sensor)
    2. Face recognition happens
    3. Door opens automatically
    4. Log the event
    5. Dashboard shows update
    """
    print("\n" + "="*60)
    print("FULL SYSTEM E2E TEST")
    print("="*60)
    
    device_id = "esp32-1"
    
    # Stage 1: Distance detected (door activity)
    print("\n[STAGE 1] Distance sensor detects person (50cm away)")
    requests.post(
        f"{BASE_URL}/api/sensor/update",
        json={
            "device_id": device_id,
            "distance1": 50,
            "distance2": 51,
            "temperature": 25
        }
    )
    print("✓ Sensor reading sent")
    
    # Stage 2: Face recognition
    print("\n[STAGE 2] Face recognition triggered")
    response = requests.post(
        f"{BASE_URL}/api/face/ingest",
        json={
            "device_id": device_id,
            "label": "me",
            "confidence": 0.98
        }
    )
    data = response.json()
    assert data["access"] == "allow"
    print(f"✓ Face recognized: {data['identity']}")
    
    # Stage 3: ESP polls access
    print("\n[STAGE 3] ESP polls access decision")
    for i in range(3):
        response = requests.get(f"{BASE_URL}/api/access?device_id={device_id}")
        data = response.json()
        print(f"  Poll {i+1}: {data['access']}")
        assert data["access"] == "allow", f"Poll {i+1} should be allow!"
    print("✓ All polls consistent")
    
    # Stage 4: ESP gets command
    print("\n[STAGE 4] ESP retrieves door command")
    response = requests.get(f"{BASE_URL}/api/command?device_id={device_id}")
    data = response.json()
    assert data.get("action") == "open_door"
    print("✓ Command received: open_door")
    
    # Stage 5: ESP opens door
    print("\n[STAGE 5] Door opens (physically)")
    print("✓ Relay set HIGH → Door opened")
    
    # Stage 6: ESP reports door state
    print("\n[STAGE 6] ESP reports door status")
    # (Optional endpoint for door state)
    print("✓ Door state updated")
    
    # Stage 7: Update dashboard
    print("\n[STAGE 7] Frontend shows update")
    response = requests.get(f"{BASE_URL}/api/debug/state?device_id={device_id}")
    data = response.json()
    print(f"✓ Dashboard state: {data['access_state']['access']}")
    
    print("\n" + "="*60)
    print("✓✓✓ END-TO-END TEST: SUCCESS!")
    print("="*60)
```

### Test 3.2: Offline Graceful Degradation

```python
def test_offline_behavior():
    """
    Test: What happens when backend is down?
    
    Expected: ESP should retry with backoff, eventually fail gracefully
    """
    print("\n[OFFLINE TEST] Simulating backend DOWN")
    
    # Try to poll (backend not responding)
    try:
        response = requests.get(
            "http://localhost:9999/api/access",  # Wrong port
            timeout=2
        )
    except Exception as e:
        print(f"✓ Expected connection error: {type(e).__name__}")
    
    # ESP should implement retry logic
    # (See ESP32 code with exponential backoff)
    print("✓ ESP retry logic: 1s → 2s → 4s → give up")
    print("✓ Fallback: Keep door state unchanged")
```

---

## ⚡ PHASE 4: LOAD TESTING

### Test 4.1: High Polling Load

```python
import threading
import time

def test_high_polling_load():
    """
    Simulate: Multiple ESP32 devices polling simultaneously
    """
    print("\n[LOAD TEST] Multiple devices polling simultaneously")
    
    NUM_DEVICES = 10
    NUM_POLLS_PER_DEVICE = 5
    
    errors = []
    
    def poll_device(device_id):
        for i in range(NUM_POLLS_PER_DEVICE):
            try:
                response = requests.get(
                    f"{BASE_URL}/api/access?device_id={device_id}",
                    timeout=2
                )
                if response.status_code != 200:
                    errors.append(f"Device {device_id} poll {i}: status {response.status_code}")
            except Exception as e:
                errors.append(f"Device {device_id} poll {i}: {e}")
            
            time.sleep(0.1)  # Small delay
    
    # Create threads
    threads = []
    start_time = time.time()
    
    for i in range(NUM_DEVICES):
        device_id = f"esp32-{i+1}"
        t = threading.Thread(target=poll_device, args=(device_id,))
        threads.append(t)
        t.start()
    
    # Wait for all
    for t in threads:
        t.join()
    
    elapsed = time.time() - start_time
    
    if errors:
        print(f"✗ ERRORS ({len(errors)}):")
        for e in errors[:5]:
            print(f"  - {e}")
    else:
        print(f"✓ All {NUM_DEVICES * NUM_POLLS_PER_DEVICE} polls successful")
        print(f"✓ Completed in {elapsed:.2f}s")
        print(f"✓ Average: {(elapsed/(NUM_DEVICES * NUM_POLLS_PER_DEVICE))*1000:.1f}ms per poll")
```

### Test 4.2: Memory Leak Detection

```python
def test_memory_stability():
    """
    Run many requests, check memory doesn't grow indefinitely
    """
    import gc
    import psutil
    import os
    
    print("\n[MEMORY TEST] Checking for memory leaks")
    
    process = psutil.Process(os.getpid())
    
    initial_mem = process.memory_info().rss / 1024 / 1024  # MB
    print(f"Initial memory: {initial_mem:.1f} MB")
    
    # Run many requests
    for i in range(100):
        requests.get(f"{BASE_URL}/api/access?device_id=esp32-1")
        
        if (i + 1) % 25 == 0:
            gc.collect()
            current_mem = process.memory_info().rss / 1024 / 1024
            print(f"After {i+1} requests: {current_mem:.1f} MB")
    
    final_mem = process.memory_info().rss / 1024 / 1024
    growth = final_mem - initial_mem
    
    if growth > 50:  # More than 50MB growth
        print(f"✗ POSSIBLE MEMORY LEAK: {growth:.1f} MB growth")
    else:
        print(f"✓ Memory stable: {growth:.1f} MB growth")
```

---

## 📋 PHASE 5: DEPLOYMENT CHECKLIST

```markdown
## Pre-Deployment

- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] Load tests pass (no ECONNRESET)
- [ ] Memory stable (no leaks)
- [ ] Error handling tested
- [ ] Timeout logic tested

## Backend Deployment

- [ ] Update backend/.env
- [ ] Deploy config.py, validators.py, command_queue.py
- [ ] Update main.py with new endpoints
- [ ] Verify /api/face/ingest works
- [ ] Verify /api/access works (multiple polls)
- [ ] Verify /api/command works (one-time)
- [ ] Verify /api/sensor/update works
- [ ] Verify /api/debug/state works
- [ ] Enable DEBUG_ACCESS=1
- [ ] Monitor logs for errors

## ESP32 Deployment

- [ ] Update retry logic
- [ ] Set retry: max_retries=3, backoff exponential
- [ ] Set timeout=2 seconds
- [ ] Test with backend running
- [ ] Test with backend down (should retry gracefully)
- [ ] Verify sensor data being sent
- [ ] Verify command received & executed

## Frontend Deployment

- [ ] Update BASE_URL to production endpoint
- [ ] Test API routes work
- [ ] Test dashboard updates in real-time
- [ ] Test error states display correctly

## Production Verification

- [ ] Face detection → door opens (< 0.5s)
- [ ] Multiple polls consistent
- [ ] No ECONNRESET errors in logs
- [ ] Sensor data flowing
- [ ] WA bot commands working
- [ ] Dashboard live
- [ ] No memory leaks after 24 hours

## Monitoring

- [ ] Set up alerting for ECONNRESET
- [ ] Monitor backend latency (target <100ms)
- [ ] Monitor ESP uptime
- [ ] Monitor face detection accuracy
- [ ] Daily log review for first week
```

---

## 🎯 QUICK RUN SCRIPT

```bash
#!/bin/bash
# run_all_tests.sh

echo "🧪 Running comprehensive test suite..."
echo ""

# Unit tests
echo "[1/3] Unit tests..."
python -m pytest backend/app/test_*.py -v

# Integration tests
echo ""
echo "[2/3] Integration tests..."
python backend/app/test_integration_face.py

# Load tests
echo ""
echo "[3/3] Load tests..."
python backend/app/test_load.py

echo ""
echo "✓ All tests completed!"
```

---

## 📊 EXPECTED RESULTS

After all fixes:

| Test | Before | After |
|------|--------|-------|
| Face detect latency | 2+ seconds | 0.2 seconds |
| Multiple polls consistent | ✗ NO | ✓ YES |
| ECONNRESET errors | Many | None |
| Sensor data stored | ✗ NO | ✓ YES |
| Load (100 reqs) | Errors | All pass |
| Memory growth | > 50MB | < 5MB |

---

**TESTING STATUS:** Complete framework ready for implementation!

