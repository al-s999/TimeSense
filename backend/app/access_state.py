from __future__ import annotations

import os
import threading
import time
from typing import Dict, Optional

ACCESS_DEVICE_ID = os.getenv("ACCESS_DEVICE_ID", "esp32-1").strip() or "esp32-1"
ACCESS_TIMEOUT = float(os.getenv("ACCESS_TIMEOUT", "5.0"))  # How long allow state lasts
DEBUG_ACCESS = os.getenv("DEBUG_ACCESS", "").lower() in {"1", "true", "yes"}


class AccessState:
    def __init__(self) -> None:
        self._states: Dict[str, dict] = {}  # {device_id: {access, identity, updated_at, expires_at}}
        self._lock = threading.Lock()

    def _resolve_target_device_id(
        self,
        *,
        device_id: Optional[str] = None,
        source_device_id: Optional[str] = None,
    ) -> str:
        """Resolve which device_id to use for state storage."""
        requested = str(device_id or "").strip()
        if requested:
            return requested

        source = str(source_device_id or "").strip()
        if source.lower().startswith("esp32") or source.lower().startswith("face"):
            return source

        return ACCESS_DEVICE_ID

    def set_allow(
        self,
        *,
        identity: str,
        device_id: Optional[str] = None,
        source_device_id: Optional[str] = None,
    ) -> dict:
        """Set access to ALLOW with timeout."""
        target = self._resolve_target_device_id(device_id=device_id, source_device_id=source_device_id)
        now = time.time()
        expires_at = now + ACCESS_TIMEOUT
        payload = {
            "access": "allow",
            "identity": str(identity),
            "updated_at": now,
            "expires_at": expires_at,
            "source_device_id": str(source_device_id or ""),
        }
        with self._lock:
            self._states[target] = payload
            if DEBUG_ACCESS:
                print(f"[ACCESS] set_allow for {target}: identity={identity}, expires_at={expires_at}")
            return dict(payload)

    def set_deny(
        self,
        *,
        device_id: Optional[str] = None,
        source_device_id: Optional[str] = None,
    ) -> dict:
        """Set access to DENY."""
        target = self._resolve_target_device_id(device_id=device_id, source_device_id=source_device_id)
        now = time.time()
        payload = {
            "access": "deny",
            "identity": None,
            "updated_at": now,
            "expires_at": now,  # Already expired
            "source_device_id": str(source_device_id or ""),
        }
        with self._lock:
            self._states[target] = payload
            if DEBUG_ACCESS:
                print(f"[ACCESS] set_deny for {target}")
            return dict(payload)

    def get_current(self, *, device_id: Optional[str] = None) -> dict:
        """Get current access state WITHOUT consuming it (read-only).
        
        This is the key fix: allow ESP32 to poll multiple times without
        the state being consumed/consumed after first read.
        """
        target = self._resolve_target_device_id(device_id=device_id)
        now = time.time()
        
        with self._lock:
            state = self._states.get(target, {})
            
            # Check if state is expired
            expires_at = state.get("expires_at", 0)
            if expires_at > 0 and now >= expires_at:
                if DEBUG_ACCESS:
                    print(f"[ACCESS] state for {target} expired at {expires_at}, now={now}")
                return {"access": "deny"}
            
            # Return current state without marking consumed
            if state.get("access") == "allow":
                if DEBUG_ACCESS:
                    print(f"[ACCESS] get_current for {target}: allow (expires_at={expires_at})")
                return {
                    "access": "allow",
                    "identity": str(state.get("identity") or "teman"),
                }
            
            if DEBUG_ACCESS:
                print(f"[ACCESS] get_current for {target}: deny")
            return {"access": "deny"}

    def consume(self, *, device_id: Optional[str] = None) -> dict[str, str]:
        """Get access state AND reset to deny after consumption.
        
        Use this if you want one-time access delivery.
        For most cases, use get_current() instead.
        """
        target = self._resolve_target_device_id(device_id=device_id)
        now = time.time()
        
        with self._lock:
            state = self._states.get(target)
            
            # Check if state is expired
            expires_at = state.get("expires_at", 0) if state else 0
            if expires_at > 0 and now >= expires_at:
                if DEBUG_ACCESS:
                    print(f"[ACCESS] consume for {target}: state expired")
                return {"access": "deny"}
            
            # Return allow and then reset to deny
            if state and state.get("access") == "allow":
                if DEBUG_ACCESS:
                    print(f"[ACCESS] consume for {target}: returning allow, resetting to deny")
                self._states[target] = {
                    "access": "deny",
                    "identity": None,
                    "updated_at": now,
                    "expires_at": now,
                    "source_device_id": state.get("source_device_id", ""),
                }
                return {
                    "access": "allow",
                    "identity": str(state.get("identity") or "teman"),
                }
            
            if DEBUG_ACCESS:
                print(f"[ACCESS] consume for {target}: returning deny")
            return {"access": "deny"}

    def get_all_states(self) -> Dict[str, dict]:
        """Get all states (for debugging)."""
        with self._lock:
            return dict(self._states)


_access_state_singleton: Optional[AccessState] = None


def get_access_state() -> AccessState:
    global _access_state_singleton
    if _access_state_singleton is None:
        _access_state_singleton = AccessState()
    return _access_state_singleton
