#!/usr/bin/env python3
"""
Integration tests for backend improvements
Tests the full flow: face detection → access state → command delivery
"""

import requests
import json
import time
import sys

BASE_URL = "http://localhost:8000"
DEVICE_ID = "esp32-1"

def test_face_detection_flow():
    """Test complete flow: face detection → access allow → door command"""
    print("\n" + "="*70)
    print("TEST: Complete Face Detection Flow")
    print("="*70)
    
    # Step 1: Send face detection
    print("\n[1] Sending face detection...")
    face_payload = {
        "device_id": "face-service",  # Will be normalized
        "label": "saya",
        "confidence": 0.95
    }
    
    response = requests.post(f"{BASE_URL}/api/face/ingest", json=face_payload)
    print(f"Response: {response.status_code}")
    print(f"Body: {json.dumps(response.json(), indent=2)}")
    
    assert response.status_code == 200, "Face ingest should return 200"
    result = response.json()
    assert result.get("access") == "allow", "Face should be recognized"
    print("✓ Face detection accepted, access allowed")
    
    # Step 2: Verify command was queued
    print("\n[2] Checking command queue...")
    response = requests.get(f"{BASE_URL}/api/debug/state?device_id={DEVICE_ID}")
    debug_state = response.json()
    print(f"Debug state: {json.dumps(debug_state, indent=2)}")
    
    commands = debug_state.get("command_queue", [])
    assert len(commands) > 0, "Command should be queued"
    assert commands[0].get("action") == "open_door", "Should be open_door command"
    print(f"✓ Command queued: {commands[0].get('action')}")
    
    # Step 3: ESP32 polls for access
    print("\n[3] ESP32 polls /api/access...")
    response = requests.get(f"{BASE_URL}/api/access?device_id={DEVICE_ID}")
    access_result = response.json()
    print(f"Access result: {json.dumps(access_result, indent=2)}")
    
    assert access_result.get("access") == "allow", "Should allow access"
    print("✓ ESP32 gets access: ALLOW")
    
    # Step 4: ESP32 polls for command
    print("\n[4] ESP32 polls /api/command...")
    response = requests.get(f"{BASE_URL}/api/command?device_id={DEVICE_ID}")
    command_result = response.json()
    print(f"Command result: {json.dumps(command_result, indent=2)}")
    
    assert command_result.get("action") == "open_door", "Should get open_door"
    print("✓ ESP32 gets command: open_door")
    
    # Step 5: Verify command was consumed (dequeued)
    print("\n[5] Verifying command was consumed...")
    response = requests.get(f"{BASE_URL}/api/debug/state?device_id={DEVICE_ID}")
    debug_state2 = response.json()
    
    commands = debug_state2.get("command_queue", [])
    assert len(commands) == 0, "Command should be consumed after poll"
    print("✓ Command consumed (queue empty)")
    
    print("\n✅ Complete flow test PASSED!")
    return True

def test_device_id_normalization():
    """Test that different device IDs are normalized"""
    print("\n" + "="*70)
    print("TEST: Device ID Normalization")
    print("="*70)
    
    test_cases = [
        ("face-service", "esp32-1"),
        ("face-cam-1", "esp32-1"),
        ("esp32-1", "esp32-1"),
    ]
    
    for input_id, expected_id in test_cases:
        print(f"\n[Testing] input={input_id}, expected={expected_id}")
        
        # Send face with this device_id
        payload = {
            "device_id": input_id,
            "label": "test",
            "confidence": 0.8
        }
        
        response = requests.post(f"{BASE_URL}/api/face/ingest", json=payload)
        assert response.status_code == 200, f"Face ingest should work for {input_id}"
        
        # Check debug state
        response = requests.get(f"{BASE_URL}/api/debug/state")
        debug_state = response.json()
        
        devices = debug_state.get("devices", {})
        assert expected_id in devices, f"Should find state for {expected_id}"
        print(f"✓ Device ID {input_id} normalized to {expected_id}")
    
    print("\n✅ Device ID normalization test PASSED!")
    return True

def test_sensor_data():
    """Test sensor data validation and storage"""
    print("\n" + "="*70)
    print("TEST: Sensor Data Validation")
    print("="*70)
    
    # Valid sensor data
    print("\n[1] Sending valid sensor data...")
    sensor_payload = {
        "device_id": DEVICE_ID,
        "distance1": 15.5,
        "distance2": 20.3,
        "temperature": 25.0
    }
    
    response = requests.post(f"{BASE_URL}/api/sensor/update", json=sensor_payload)
    print(f"Response: {response.status_code}")
    result = response.json()
    print(f"Body: {json.dumps(result, indent=2)}")
    
    assert response.status_code == 200, "Sensor update should return 200"
    assert result.get("ok") == True, "Sensor update should be ok"
    print("✓ Valid sensor data accepted")
    
    # Verify data was stored
    print("\n[2] Verifying sensor data was stored...")
    response = requests.get(f"{BASE_URL}/api/debug/state?device_id={DEVICE_ID}")
    debug_state = response.json()
    print(f"State: {json.dumps(debug_state, indent=2)}")
    
    access_state = debug_state.get("access_state", {})
    assert access_state.get("distance1") == 15.5, "Distance1 should be stored"
    assert access_state.get("distance2") == 20.3, "Distance2 should be stored"
    assert access_state.get("temperature") == 25.0, "Temperature should be stored"
    print("✓ Sensor data stored correctly")
    
    # Invalid sensor data (distance too large)
    print("\n[3] Testing invalid sensor data (distance too large)...")
    invalid_payload = {
        "device_id": DEVICE_ID,
        "distance1": 500,  # > 400cm (invalid)
        "distance2": 20.3
    }
    
    response = requests.post(f"{BASE_URL}/api/sensor/update", json=invalid_payload)
    result = response.json()
    print(f"Response: {json.dumps(result, indent=2)}")
    
    assert result.get("ok") == False, "Should reject invalid data"
    assert "distance1" in result.get("error", ""), "Should indicate distance error"
    print("✓ Invalid sensor data rejected correctly")
    
    print("\n✅ Sensor data test PASSED!")
    return True

def test_manual_command_execution():
    """Test manual command execution (from WA bot, frontend)"""
    print("\n" + "="*70)
    print("TEST: Manual Command Execution")
    print("="*70)
    
    # Execute open_door command
    print("\n[1] Executing manual command...")
    command_payload = {
        "device_id": DEVICE_ID,
        "action": "open_door",
        "requester": "frontend"
    }
    
    response = requests.post(f"{BASE_URL}/api/command/execute", json=command_payload)
    print(f"Response: {response.status_code}")
    result = response.json()
    print(f"Body: {json.dumps(result, indent=2)}")
    
    assert response.status_code == 200, "Command execute should return 200"
    assert result.get("ok") == True, "Command should be queued"
    assert result.get("queued") == True, "Should be queued"
    print("✓ Manual command queued")
    
    # Verify command in queue
    print("\n[2] Verifying command in queue...")
    response = requests.get(f"{BASE_URL}/api/debug/state?device_id={DEVICE_ID}")
    debug_state = response.json()
    
    commands = debug_state.get("command_queue", [])
    assert len(commands) > 0, "Command should be in queue"
    assert commands[0].get("action") == "open_door", "Should be open_door"
    print(f"✓ Command in queue: {commands[0].get('action')}")
    
    # Invalid command
    print("\n[3] Testing invalid command...")
    invalid_payload = {
        "device_id": DEVICE_ID,
        "action": "explode"  # Invalid action
    }
    
    response = requests.post(f"{BASE_URL}/api/command/execute", json=invalid_payload)
    result = response.json()
    print(f"Response: {json.dumps(result, indent=2)}")
    
    assert result.get("ok") == False, "Should reject invalid action"
    assert "invalid action" in result.get("error", ""), "Should indicate action error"
    print("✓ Invalid command rejected correctly")
    
    print("\n✅ Manual command test PASSED!")
    return True

def test_multiple_devices():
    """Test multiple devices with different IDs"""
    print("\n" + "="*70)
    print("TEST: Multiple Devices")
    print("="*70)
    
    devices = ["esp32-1", "esp32-2", "esp32-3"]
    
    for device_id in devices:
        print(f"\n[Testing] Device: {device_id}")
        
        # Send sensor data
        payload = {
            "device_id": device_id,
            "distance1": 10.0 + int(device_id[-1]) * 5,
            "distance2": 20.0 + int(device_id[-1]) * 5
        }
        
        response = requests.post(f"{BASE_URL}/api/sensor/update", json=payload)
        assert response.json().get("ok") == True
        
        # Check state
        response = requests.get(f"{BASE_URL}/api/debug/state")
        debug_state = response.json()
        devices_in_state = debug_state.get("devices", {})
        
        assert device_id in devices_in_state, f"Device {device_id} should have state"
        print(f"✓ Device {device_id} state updated")
    
    print("\n✅ Multiple devices test PASSED!")
    return True

def main():
    """Run all integration tests"""
    print("\n" + "="*70)
    print("BACKEND INTEGRATION TESTS")
    print("="*70)
    
    # Check if backend is running
    try:
        response = requests.get(f"{BASE_URL}/api/debug/state", timeout=2)
    except:
        print("\n❌ ERROR: Backend not running at", BASE_URL)
        print("Start the backend with: cd backend && python3 -m uvicorn app.main:app --reload")
        return 1
    
    tests = [
        ("Face Detection Flow", test_face_detection_flow),
        ("Device ID Normalization", test_device_id_normalization),
        ("Sensor Data", test_sensor_data),
        ("Manual Command Execution", test_manual_command_execution),
        ("Multiple Devices", test_multiple_devices),
    ]
    
    results = []
    for name, test_fn in tests:
        try:
            passed = test_fn()
            results.append((name, passed))
        except AssertionError as e:
            print(f"\n❌ TEST FAILED: {e}")
            results.append((name, False))
        except Exception as e:
            print(f"\n❌ TEST ERROR: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nOverall: {passed_count}/{total_count} tests passed")
    
    if passed_count == total_count:
        print("\n🎉 ALL INTEGRATION TESTS PASSED!")
        return 0
    else:
        print(f"\n❌ {total_count - passed_count} test(s) failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
