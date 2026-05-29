from __future__ import annotations

from typing import Any, Optional

SEMANTIC_EVENT_LABELS = {
    "SAYA_MASUK": "SAYA_MASUK",
    "TEMAN_MASUK": "TEMAN_MASUK",
    "ORANG_MASUK": "ORANG_MASUK",
    "SAYA_KELUAR": "SAYA_KELUAR",
    "TEMAN_KELUAR": "TEMAN_KELUAR",
    "ORANG_KELUAR": "ORANG_KELUAR",
}

LEGACY_EVENT_LABELS = {
    "S1_S2": "ANDA_PERGI",
    "S2_S1": "ANDA_PULANG",
}

_DIRECTION_BY_RAW_EVENT = {
    "S1_S2": "OUT",
    "S2_S1": "IN",
    "SAYA_MASUK": "IN",
    "TEMAN_MASUK": "IN",
    "ORANG_MASUK": "IN",
    "SAYA_KELUAR": "OUT",
    "TEMAN_KELUAR": "OUT",
    "ORANG_KELUAR": "OUT",
}


def normalize_raw_event(raw_event: str) -> str:
    return str(raw_event or "").strip().upper()


def is_semantic_access_event(raw_event: str) -> bool:
    return normalize_raw_event(raw_event) in SEMANTIC_EVENT_LABELS


def direction_from_raw_event(raw_event: str) -> str:
    return _DIRECTION_BY_RAW_EVENT.get(normalize_raw_event(raw_event), "UNK")


def label_from_raw_event(raw_event: str) -> str:
    raw = normalize_raw_event(raw_event)
    return SEMANTIC_EVENT_LABELS.get(raw) or LEGACY_EVENT_LABELS.get(raw) or "UNKNOWN"


def raw_event_person_id(raw_event: str) -> Optional[int]:
    raw = normalize_raw_event(raw_event)
    if raw.startswith("SAYA_"):
        return 1
    if raw.startswith("TEMAN_"):
        return 2
    return None


def _truthy_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def access_identity_from_face(face_meta: Optional[dict[str, Any]], me_identity: str) -> Optional[str]:
    if not face_meta:
        return None

    label = str(face_meta.get("face_label") or "").strip()
    label_lower = label.lower()
    me_identity_lower = str(me_identity or "").strip().lower()
    is_me = _truthy_flag(face_meta.get("face_is_me")) or (
        bool(label) and label_lower == me_identity_lower
    )
    if is_me:
        return "saya"

    is_known = _truthy_flag(face_meta.get("face_is_known"))
    if is_known or (label and label_lower not in {"unknown", "unk"}):
        return "teman"

    return None
