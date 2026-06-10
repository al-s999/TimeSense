"""
DoorStateMachine — Single Source of Truth for Smart Door System.
Refactored for strict reliability, anti-spam, and specific response rules.
"""

import asyncio
import os
import time
from typing import Any, Dict, Optional

class DoorStateMachine:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()

        # ---- Persistent State ----
        self.last_identity: Optional[str] = None
        self.last_access_time: float = 0.0
        self.last_access_status: str = "deny"
        
        # ---- Door Physical State ----
        self.door_open: bool = False
        self.waiting_for_entry: bool = False
        self.system_enabled: bool = True
        self.last_open_ts: float = 0.0
        self.last_close_ts: float = 0.0

        # ---- Command State ----
        self.pending_command: Optional[str] = None
        self.command_consumed: bool = True

        # ---- Sensor State ----
        self.last_sensor: Dict[str, Any] = {
            "distance1": 0.0,
            "distance2": 0.0,
            "temperature": 0.0,
            "ts": 0.0,
        }

        # ---- Configuration ----
        self.cooldown_seconds: float = 3.0
        self.access_valid_window: float = 8.0 
        self.entry_threshold_cm: float = float(os.getenv("ENTRY_DETECT_THRESHOLD_CM", "50.0"))

    # =====================================================================
    #  ACCESS LOGIC (Strict Requirements)
    # =====================================================================
    async def process_face(self, label: str, confidence: float) -> Dict[str, Any]:
        """Dipanggil saat POST /face"""
        async with self.lock:
            now = time.time()
            
            # Rule: Confidence < 0.6 -> Deny
            if confidence < 0.6:
                print(f"FACE DETECTED: {label} (REJECTED: Low Confidence {confidence})")
                return {"ok": True, "access": "deny", "identity": None}

            # Rule: Cooldown Check
            is_in_cooldown = (now - self.last_access_time) < self.cooldown_seconds
            if is_in_cooldown:
                print(f"FACE DETECTED: {label} (COOLDOWN ACTIVE)")
                # Rule 1: Cooldown -> identity harus null
                return {"ok": True, "access": "cooldown", "identity": None}

            # Rule: Valid Grant (TIDAK menghapus identity lama saat cooldown terlewati)
            print(f"FACE DETECTED: {label} (ALLOWED)")
            self.last_identity = label
            self.last_access_time = now
            self.last_access_status = "allow"
            
            # Physical state update
            self.door_open = True
            self.waiting_for_entry = True
            self.last_open_ts = now
            
            # Command for ESP
            self.pending_command = "open_door"
            self.command_consumed = False

            return {"ok": True, "access": "allow", "identity": self.last_identity}

    def get_access_status(self) -> Dict[str, Any]:
        """Logic untuk GET /api/access"""
        now = time.time()
        elapsed = now - self.last_access_time

        # Rule 1: Cooldown -> identity null
        if elapsed < self.cooldown_seconds:
            return {"ok": True, "access": "cooldown", "identity": None}

        # Rule 1: Allow -> identity wajib ada
        if elapsed < self.access_valid_window and self.last_access_status == "allow":
            print(f"ACCESS: allow, {self.last_identity}")
            return {"ok": True, "access": "allow", "identity": self.last_identity}

        # Rule 1: Deny -> identity null
        return {"ok": True, "access": "deny", "identity": None}

    async def consume_command(self) -> Dict[str, Any]:
        """Logic untuk GET /api/command"""
        async with self.lock:
            if self.pending_command and not self.command_consumed:
                action = self.pending_command
                identity = self.last_identity
                self.command_consumed = True
                self.pending_command = None 
                
                # Rule 2: Response format {action, identity}
                print(f"COMMAND: {action}, {identity}")
                return {"action": action, "identity": identity}
            
            return {"action": None, "identity": None}

    # =====================================================================
    #  SENSOR & PHYSICAL LOGIC
    # =====================================================================
    def process_sensor(self, distance1: float, distance2: float, temperature: float = 0.0) -> Optional[str]:
        now = time.time()
        prev = dict(self.last_sensor)
        self.last_sensor = {"distance1": distance1, "distance2": distance2, "temperature": temperature, "ts": now}

        d1_active = 0 < distance1 < self.entry_threshold_cm
        d2_active = 0 < distance2 < self.entry_threshold_cm
        prev_d1_active = 0 < prev.get("distance1", 0) < self.entry_threshold_cm
        prev_d2_active = 0 < prev.get("distance2", 0) < self.entry_threshold_cm

        if d2_active and prev_d1_active and not prev_d2_active:
            return "entry_detected"
        if d1_active and prev_d2_active and not prev_d1_active:
            return "exit_detected"
        return None

    def confirm_entry(self) -> Dict[str, Any]:
        identity = self.last_identity or "unknown"
        self.door_open = False
        self.waiting_for_entry = False
        self.last_close_ts = time.time()
        self.pending_command = "close_door"
        self.command_consumed = False
        return {"identity": identity, "event": "entry_confirmed"}

    def start_exit_flow(self) -> Dict[str, Any]:
        self.door_open = True
        self.waiting_for_entry = False
        self.last_open_ts = time.time()
        self.last_identity = "someone"
        self.pending_command = "open_door"
        self.command_consumed = False
        return {"ok": True, "event": "exit_flow_started"}

    async def schedule_exit_auto_close(self, delay_seconds: float = 5.0) -> None:
        await asyncio.sleep(delay_seconds)
        async with self.lock:
            if self.door_open:
                self.door_open = False
                self.last_close_ts = time.time()
                self.pending_command = "close_door"
                self.command_consumed = False

    def get_sensor_data(self) -> Dict[str, Any]:
        return dict(self.last_sensor)



    def get_full_status(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "door_open": self.door_open,
            "last_identity": self.last_identity,
            "access_granted": self.last_access_status == "allow",
            "sensor": dict(self.last_sensor),
        }

    async def manual_command(self, action: str, identity: str = "manual") -> Dict[str, Any]:
        async with self.lock:
            now = time.time()
            self.last_identity = identity
            self.last_access_time = now
            self.last_access_status = "allow"
            self.pending_command = action
            self.command_consumed = False
            if action == "open_door":
                self.door_open = True
            elif action == "close_door":
                self.door_open = False
            return {"ok": True, "action": action, "identity": identity}

# Singleton
_instance = DoorStateMachine()
def get_door_state() -> DoorStateMachine:
    return _instance
