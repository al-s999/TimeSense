#!/usr/bin/env python3
"""
Test script for face recognition access control system.

Tests the full flow:
1. POST /api/face/ingest - Face recognition result
2. GET /api/access - Check access status (multiple times)
3. GET /api/debug/access-state - Verify state stored
4. GET /api/command - Get door command (one-time)
"""

import json
import time
import urllib.request
import urllib.error
import sys
from typing import Any

BASE_URL = "http://localhost:8000"
DEVICE_ID = "esp32-1"
FACE_LABEL = "me"
CONFIDENCE = 0.95

def log_step(step: int, title: str):
    """Log test step"""
    print(f"\n{'='*70}")
    print(f"STEP {step}: {title}")
    print('='*70)

def log_result(status: str, message: str):
    """Log result with status"""
    symbol = "✓" if status == "OK" else "✗" if status == "FAIL" else "ℹ"
    print(f"{symbol} {message}")

def http_request(method: str, path: str, data: dict | None = None) -> dict | None:
    """Make HTTP request"""
    url = BASE_URL + path
    headers = {"Content-Type": "application/json"}
    
    if data:
        body = json.dumps(data).encode("utf-8")
    else:
        body = None
    
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
            return resp_data
    except Exception as e:
        log_result("FAIL", f"HTTP error: {e}")
        return None

def test_flow():
    """Run complete test flow"""
    
    # Step 1: Health check
    log_step(1, "Health Check")
    health = http_request("GET", "/api/health")
    if health and health.get("status") == "ok":
        log_result("OK", "Backend is running")
    else:
        log_result("FAIL", "Backend not responding")
        return False
    
    # Step 2: Face recognition ingest
    log_step(2, "Face Recognition Ingest")
    face_payload = {
        "device_id": DEVICE_ID,
        "label": FACE_LABEL,
        "confidence": CONFIDENCE
    }
    print(f"Sending: {json.dumps(face_payload, indent=2)}")
    
    face_result = http_request("POST", "/api/face/ingest", face_payload)
    if face_result:
        print(f"Response: {json.dumps(face_result, indent=2)}")
        
        if face_result.get("access") == "allow":
            log_result("OK", f"Access granted for {face_result.get('identity')}")
        else:
            log_result("FAIL", f"Access denied: {face_result}")
            return False
    else:
        return False
    
    # Step 3: Check state immediately
    log_step(3, "Check State (Immediately After Ingest)")
    state = http_request("GET", f"/api/debug/access-state?device_id={DEVICE_ID}")
    if state:
        print(f"Response: {json.dumps(state, indent=2)}")
        
        if state.get("state", {}).get("access") == "allow":
            log_result("OK", f"State stored with identity={state['state'].get('identity')}")
            expires_in = state.get("expires_in_seconds", 0)
            log_result("INFO", f"State expires in {expires_in:.1f} seconds")
        else:
            log_result("FAIL", f"State not stored correctly: {state}")
            return False
    else:
        return False
    
    # Step 4: First /api/access poll
    log_step(4, "First Poll: /api/access")
    access1 = http_request("GET", f"/api/access?device_id={DEVICE_ID}")
    if access1:
        print(f"Response: {json.dumps(access1, indent=2)}")
        
        if access1.get("access") == "allow":
            log_result("OK", f"Access: {access1.get('access')}, Identity: {access1.get('identity')}")
        else:
            log_result("FAIL", f"Expected allow, got: {access1}")
            return False
    else:
        return False
    
    # Step 5: Second /api/access poll
    log_step(5, "Second Poll: /api/access (Without Timeout)")
    access2 = http_request("GET", f"/api/access?device_id={DEVICE_ID}")
    if access2:
        print(f"Response: {json.dumps(access2, indent=2)}")
        
        if access2.get("access") == "allow":
            log_result("OK", "State persisted - second poll returns same result!")
        else:
            log_result("FAIL", f"Expected allow, got: {access2}")
            log_result("FAIL", "STATE NOT PERSISTING BETWEEN POLLS")
            return False
    else:
        return False
    
    # Step 6: First /api/command call
    log_step(6, "First Call: /api/command (Should Get Door Command)")
    cmd1 = http_request("GET", f"/api/command?device_id={DEVICE_ID}")
    if cmd1:
        print(f"Response: {json.dumps(cmd1, indent=2)}")
        
        if cmd1.get("action") == "open_door":
            log_result("OK", "Got open_door command - state was consumed")
        else:
            log_result("FAIL", f"Expected open_door action, got: {cmd1}")
            return False
    else:
        return False
    
    # Step 7: Second /api/command call
    log_step(7, "Second Call: /api/command (Should Get No Action - Already Consumed)")
    cmd2 = http_request("GET", f"/api/command?device_id={DEVICE_ID}")
    if cmd2:
        print(f"Response: {json.dumps(cmd2, indent=2)}")
        
        if cmd2.get("action") is None:
            log_result("OK", "No action returned - state consumed correctly")
        else:
            log_result("FAIL", f"Expected null action, got: {cmd2}")
            return False
    else:
        return False
    
    # Step 8: Third /api/access poll (verify not consumed)
    log_step(8, "Third Poll: /api/access (After Command Consumed)")
    access3 = http_request("GET", f"/api/access?device_id={DEVICE_ID}")
    if access3:
        print(f"Response: {json.dumps(access3, indent=2)}")
        
        if access3.get("access") == "allow":
            log_result("OK", "ACCESS state still valid even after command consumed!")
            log_result("INFO", "This shows get_current() is independent from consume()")
        else:
            log_result("FAIL", f"Expected allow, got: {access3}")
            return False
    else:
        return False
    
    # Step 9: Wait for timeout
    log_step(9, "Wait for State Timeout (5+ seconds)")
    timeout_seconds = 6
    for i in range(timeout_seconds):
        remaining = timeout_seconds - i
        print(f"Waiting... {remaining}s remaining", end="\r")
        time.sleep(1)
    print()
    
    # Step 10: Poll after timeout
    log_step(10, "Fourth Poll: /api/access (After Timeout Expires)")
    access4 = http_request("GET", f"/api/access?device_id={DEVICE_ID}")
    if access4:
        print(f"Response: {json.dumps(access4, indent=2)}")
        
        if access4.get("access") == "deny":
            log_result("OK", "State expired automatically!")
        else:
            log_result("FAIL", f"Expected deny after timeout, got: {access4}")
            return False
    else:
        return False
    
    return True

def main():
    print("\n" + "="*70)
    print("FACE RECOGNITION ACCESS CONTROL - INTEGRATION TEST")
    print("="*70)
    print(f"Backend: {BASE_URL}")
    print(f"Device ID: {DEVICE_ID}")
    print(f"Face Label: {FACE_LABEL}")
    print(f"Confidence: {CONFIDENCE}")
    
    try:
        success = test_flow()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        return 1
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        return 1
    
    # Summary
    print("\n" + "="*70)
    if success:
        print("✓ ALL TESTS PASSED!")
        print("="*70)
        print("\nSystem is working correctly!")
        print("- Face detection sets allow state")
        print("- /api/access polls return consistent state")
        print("- /api/command provides one-time door command")
        print("- State auto-expires after timeout")
        return 0
    else:
        print("✗ TESTS FAILED!")
        print("="*70)
        print("\nDebugging tips:")
        print("1. Check backend logs for [ACCESS] debug messages")
        print("2. Enable DEBUG_ACCESS=1 in backend/.env")
        print("3. Verify device_id matches between face service and ESP32")
        print("4. Check that backend time is correct (timezone issues?)")
        return 1

if __name__ == "__main__":
    sys.exit(main())
