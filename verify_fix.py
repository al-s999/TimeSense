#!/usr/bin/env python3
"""Quick test to verify access_state.py works correctly"""

import sys
sys.path.insert(0, 'backend')

from app.access_state import get_access_state

try:
    # Test 1: set_allow
    state = get_access_state()
    state.set_allow(identity='test_user', device_id='esp32-1')
    print('✓ set_allow() works')
    
    # Test 2: get_current (multiple times - KEY FIX!)
    r1 = state.get_current(device_id='esp32-1')
    r2 = state.get_current(device_id='esp32-1')
    if r1 == r2 and r1.get('access') == 'allow':
        print('✓ get_current() returns CONSISTENT result (KEY FIX!)')
    else:
        print('✗ FAILED: get_current() not consistent')
        sys.exit(1)
    
    # Test 3: consume (one-time delivery)
    r3 = state.consume(device_id='esp32-1')
    r4 = state.consume(device_id='esp32-1')
    if r3.get('access') == 'allow' and r4.get('access') == 'deny':
        print('✓ consume() one-time delivery works correctly')
    else:
        print('✗ FAILED: consume() not working')
        sys.exit(1)
    
    print('\n✓✓✓ ALL TESTS PASSED ✓✓✓')
    print('System is ready for deployment!')
    
except Exception as e:
    print(f'✗ ERROR: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
