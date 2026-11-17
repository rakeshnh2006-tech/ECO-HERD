"""
audit/log.py — Append-only HITL and pipeline audit log.

Writes one JSON line per event to audit.jsonl in the project root.
This log is immutable: entries are never updated, only appended.

Usage:
    from audit.log import append_audit
    from schemas import AuditEventType
    append_audit(AuditEventType.ALERT_APPROVED, {"alert_id": "...", "officer_id": "..."})
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path

from schemas import AuditEntry, AuditEventType

_AUDIT_FILE = Path(__file__).parent.parent / "audit.jsonl"
_lock = threading.Lock()


def append_audit(event_type: AuditEventType, payload: dict) -> AuditEntry:
    """Append a single audit entry to audit.jsonl and return the entry."""
    entry = AuditEntry(event_type=event_type, payload=payload)
    line = json.dumps(
        {
            "entry_id": entry.entry_id,
            "event_type": entry.event_type.value,
            "timestamp": entry.timestamp.isoformat(),
            "payload": entry.payload,
        }
    )
    with _lock:
        with open(_AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    return entry


def read_audit_log(last_n: int = 50) -> list[dict]:
    """Read the last N entries from audit.jsonl."""
    if not _AUDIT_FILE.exists():
        return []
    with _lock:
        lines = _AUDIT_FILE.read_text(encoding="utf-8").strip().splitlines()
    tail = lines[-last_n:] if len(lines) > last_n else lines
    entries = []
    for line in tail:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries
