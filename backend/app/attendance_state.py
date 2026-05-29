from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

from .event_logic import direction_from_raw_event as shared_direction_from_raw_event


def _bool_env(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes", "on"}


def direction_from_raw_event(raw_event: str) -> str:
    return shared_direction_from_raw_event(raw_event)


@dataclass
class AttendanceRecord:
    last_go_minute: Optional[int] = None
    last_home_minute: Optional[int] = None
    last_event_time: Optional[datetime] = None
    last_direction: Optional[str] = None


class AttendanceState:
    def __init__(self) -> None:
        self._states: Dict[str, AttendanceRecord] = {}
        self._lock = threading.Lock()

    def _make_key(self, device_id: str, person_id: Optional[int]) -> str:
        person_key = "unknown" if person_id is None else str(person_id)
        return f"{device_id}::{person_key}"

    def compute_work(self, go_minute: int, home_minute: int) -> int:
        if go_minute is None or home_minute is None:
            return 0
        work = int(home_minute) - int(go_minute)
        if work < 0:
            work += 24 * 60
        return int(work)

    def update(
        self,
        *,
        device_id: str,
        raw_event: str,
        minute_of_day: Optional[int] = None,
        event_time: Optional[datetime] = None,
        person_id: Optional[int] = None,
    ) -> Dict[str, Optional[int]]:
        direction = direction_from_raw_event(raw_event)
        if minute_of_day is None and event_time is not None:
            minute_of_day = int(event_time.hour) * 60 + int(event_time.minute)

        with self._lock:
            key = self._make_key(device_id, person_id)
            state = self._states.get(key)
            if state is None:
                state = AttendanceRecord()
                self._states[key] = state

            go_val: Optional[int] = None
            home_val: Optional[int] = None
            work_val: Optional[int] = None

            if direction == "OUT":
                if minute_of_day is not None:
                    state.last_go_minute = int(minute_of_day)
                    go_val = int(minute_of_day)
            elif direction == "IN":
                if minute_of_day is not None:
                    state.last_home_minute = int(minute_of_day)
                    home_val = int(minute_of_day)
                if state.last_go_minute is not None and state.last_direction == "OUT":
                    go_val = int(state.last_go_minute)
                    if home_val is not None:
                        work_val = self.compute_work(go_val, home_val)

            state.last_event_time = event_time or state.last_event_time
            state.last_direction = direction

        return {"go": go_val, "home": home_val, "work": work_val}

    def should_score_anomaly(
        self,
        go_minute: Optional[int],
        home_minute: Optional[int],
        work_minute: Optional[int],
    ) -> bool:
        allow_partial = _bool_env("ANOMALY_SCORE_PARTIAL", "0")
        if allow_partial:
            return go_minute is not None or home_minute is not None or work_minute is not None
        return go_minute is not None and home_minute is not None and work_minute is not None


_attendance_singleton: Optional[AttendanceState] = None


def get_attendance_state() -> AttendanceState:
    global _attendance_singleton
    if _attendance_singleton is None:
        _attendance_singleton = AttendanceState()
    return _attendance_singleton
