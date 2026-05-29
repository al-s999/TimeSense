#!/usr/bin/env python3
"""
Test backend improvements: device ID resolution, validation, command queue
"""

import sys
import time
import json
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent / "backend" / "app"
sys.path.insert(0, str(backend_path.parent.parent))

from backend.app.config import resolve_device_id, DEVICE_MAPPING
from backend.app.validators import (
    validate_face_ingest,
    validate_sensor_update,
    validate_command_execute
)
from backend.app.command_queue import get_command_queue, Command

def test_device_id_resolution():
    """Test device ID normalization"""
    print("\n" + "="*60)
    print("TEST 1: Device ID Resolution")
    print("="*60)
    
    test_cases = [
        ("face-service", "esp32-1"),
        ("face-cam-1", "esp32-1"),
        ("esp32-1", "esp32-1"),
        ("ESP32-1", "esp32-1"),
        (None, "esp32-1"),
        ("unknown-device", "esp32-1"),  # unmapped falls back to default
    ]
    
    passed = 0
    for input_id, expected in test_cases:
        result = resolve_device_id(input_id)
        status = "✓ PASS" if result == expected else "✗ FAIL"
        print(f"{status}: resolve_device_id({input_id!r}) → {result!r} (expected {expected!r})")
        if result == expected:
            passed += 1
    
    print(f"\nResult: {passed}/{len(test_cases)} tests passed")
    return passed == len(test_cases)

def test_face_validation():
    """Test face ingest validation"""
    print("\n" + "="*60)
    print("TEST 2: Face Ingest Validation")
    print("="*60)
    
    # Valid payload
    valid_payload = {
        "device_id": "esp32-1",
        "label": "saya",
        "confidence": 0.95
    }
    
    is_valid, errors = validate_face_ingest(valid_payload)
    print(f"✓ Valid payload: is_valid={is_valid}, errors={errors}")
    assert is_valid, "Valid payload should pass"
    
    # Missing device_id
    missing_id = {
        "label": "saya",
        "confidence": 0.95
    }
    is_valid, errors = validate_face_ingest(missing_id)
    print(f"✓ Missing device_id: is_valid={is_valid}, errors={errors}")
    assert not is_valid and "device_id required" in errors, "Should catch missing device_id"
    
    # Invalid confidence
    invalid_conf = {
        "device_id": "esp32-1",
        "label": "saya",
        "confidence": 1.5
    }
    is_valid, errors = validate_face_ingest(invalid_conf)
    print(f"✓ Invalid confidence: is_valid={is_valid}, errors={errors}")
    assert not is_valid and "confidence must be 0-1" in str(errors), "Should catch invalid confidence"
    
    # Unknown label
    unknown_label = {
        "device_id": "esp32-1",
        "label": "unknown",
        "confidence": 0.95
    }
    is_valid, errors = validate_face_ingest(unknown_label)
    print(f"✓ Unknown label: is_valid={is_valid}, errors={errors}")
    assert not is_valid and "unknown" in str(errors), "Should catch unknown label"
    
    print("\n✓ All face validation tests passed")
    return True

def test_sensor_validation():
    """Test sensor data validation"""
    print("\n" + "="*60)
    print("TEST 3: Sensor Update Validation")
    print("="*60)
    
    # Valid payload
    valid = {
        "device_id": "esp32-1",
        "distance1": 15.5,
        "distance2": 20.3,
        "temperature": 25.0
    }
    is_valid, errors = validate_sensor_update(valid)
    print(f"✓ Valid sensor data: is_valid={is_valid}, errors={errors}")
    assert is_valid, "Valid data should pass"
    
    # Invalid distance (too large)
    invalid_dist = {
        "device_id": "esp32-1",
        "distance1": 500,  # > 400cm
        "distance2": 20.3
    }
    is_valid, errors = validate_sensor_update(invalid_dist)
    print(f"✓ Distance too large: is_valid={is_valid}, errors={errors}")
    assert not is_valid, "Should catch distance > 400cm"
    
    # Invalid temperature
    invalid_temp = {
        "device_id": "esp32-1",
        "distance1": 15.5,
        "distance2": 20.3,
        "temperature": 150  # > 80°C
    }
    is_valid, errors = validate_sensor_update(invalid_temp)
    print(f"✓ Temperature too high: is_valid={is_valid}, errors={errors}")
    assert not is_valid, "Should catch temperature > 80°C"
    
    print("\n✓ All sensor validation tests passed")
    return True

def test_command_validation():
    """Test command execution validation"""
    print("\n" + "="*60)
    print("TEST 4: Command Execution Validation")
    print("="*60)
    
    # Valid command
    valid = {
        "device_id": "esp32-1",
        "action": "open_door"
    }
    is_valid, errors = validate_command_execute(valid)
    print(f"✓ Valid command: is_valid={is_valid}, errors={errors}")
    assert is_valid, "Valid command should pass"
    
    # Invalid action
    invalid_action = {
        "device_id": "esp32-1",
        "action": "explode"
    }
    is_valid, errors = validate_command_execute(invalid_action)
    print(f"✓ Invalid action: is_valid={is_valid}, errors={errors}")
    assert not is_valid and "invalid action" in str(errors), "Should catch invalid action"
    
    # Missing device_id
    missing_id = {
        "action": "open_door"
    }
    is_valid, errors = validate_command_execute(missing_id)
    print(f"✓ Missing device_id: is_valid={is_valid}, errors={errors}")
    assert not is_valid, "Should require device_id"
    
    print("\n✓ All command validation tests passed")
    return True

def test_command_queue():
    """Test command queue functionality"""
    print("\n" + "="*60)
    print("TEST 5: Command Queue")
    print("="*60)
    
    queue = get_command_queue()
    device_id = "esp32-1"
    
    # Clear existing
    queue.clear(device_id)
    
    # Enqueue a command
    cmd = Command(action="open_door", priority=20)
    queue.enqueue(device_id, cmd)
    print(f"✓ Enqueued: {cmd.action} (priority={cmd.priority})")
    
    # Peek at queue
    peek_cmd = queue.peek(device_id)
    assert peek_cmd is not None, "Should have a command in queue"
    print(f"✓ Peek: {peek_cmd.action} (not removed)")
    
    # Peek again to verify it's still there
    peek_cmd2 = queue.peek(device_id)
    assert peek_cmd2 is not None, "Command should still be in queue after peek"
    print(f"✓ Peek again: command still there")
    
    # Dequeue (consume)
    dequeued = queue.dequeue(device_id)
    assert dequeued is not None, "Should dequeue a command"
    assert dequeued.action == "open_door", "Should be the right command"
    assert dequeued.executed_at is not None, "Should have execution time"
    print(f"✓ Dequeued: {dequeued.action} (executed_at set)")
    
    # Dequeue again (should be empty)
    empty = queue.dequeue(device_id)
    assert empty is None, "Queue should be empty"
    print(f"✓ Dequeue empty: None (queue exhausted)")
    
    # Enqueue multiple with priorities
    for i, (action, priority) in enumerate([
        ("lock", 10),
        ("open_door", 20),
        ("unlock", 15),
    ]):
        cmd = Command(action=action, priority=priority)
        queue.enqueue(device_id, cmd)
    
    # Dequeue should respect priorities (20 first)
    first = queue.dequeue(device_id)
    assert first.action == "open_door", "Should dequeue highest priority first"
    print(f"✓ Priority queue: {first.action} dequeued first (priority=20)")
    
    # Test TTL (expiration)
    queue.clear(device_id)
    cmd_ttl = Command(action="test", ttl=1)  # Expire in 1 second
    queue.enqueue(device_id, cmd_ttl)
    
    # Should be available now
    peek = queue.peek(device_id)
    assert peek is not None, "Should have command before TTL"
    print(f"✓ TTL test: command available before expiration")
    
    # Wait for TTL to expire
    time.sleep(1.1)
    peek = queue.peek(device_id)
    assert peek is None, "Command should be expired after TTL"
    print(f"✓ TTL test: command expired after 1.1s")
    
    print("\n✓ All command queue tests passed")
    return True

def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("BACKEND IMPROVEMENTS TEST SUITE")
    print("="*60)
    
    tests = [
        ("Device ID Resolution", test_device_id_resolution),
        ("Face Validation", test_face_validation),
        ("Sensor Validation", test_sensor_validation),
        ("Command Validation", test_command_validation),
        ("Command Queue", test_command_queue),
    ]
    
    results = []
    for name, test_fn in tests:
        try:
            passed = test_fn()
            results.append((name, passed))
        except Exception as e:
            print(f"\n✗ TEST FAILED: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nOverall: {passed_count}/{total_count} test suites passed")
    
    if passed_count == total_count:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n❌ {total_count - passed_count} test suite(s) failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
