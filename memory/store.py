"""
memory/store.py — Thread-safe in-process MemoryStore.

Holds the current pipeline state shared between agents, orchestrator, and dashboard.
All reads and writes are protected by a threading.Lock.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Optional

from schemas import (
    Alert,
    AlertStatus,
    AgentRunLog,
    Detection,
    HitlQueueItem,
    HitlVerdict,
    RunReport,
    ToolTraceEntry,
    WildlifeReport,
)


class MemoryStore:
    """Singleton-style in-process store. Import the module-level `store` instance."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

        # Agent outputs
        self._wildlife_report: Optional[WildlifeReport] = None
        self._detections: list[Detection] = []
        self._pending_alerts: list[Alert] = []
        self._dispatched_alerts: list[Alert] = []

        # HITL queue
        self._hitl_queue: list[HitlQueueItem] = []

        # Observability
        self._tool_trace_log: list[ToolTraceEntry] = []
        self._agent_run_logs: list[AgentRunLog] = []
        self._run_history: list[RunReport] = []

        # LLM cost tracking
        self._llm_call_log: list[dict] = []

    # ------------------------------------------------------------------
    # Wildlife report
    # ------------------------------------------------------------------

    def set_wildlife_report(self, report: WildlifeReport) -> None:
        with self._lock:
            self._wildlife_report = report

    def get_wildlife_report(self) -> Optional[WildlifeReport]:
        with self._lock:
            return self._wildlife_report

    # ------------------------------------------------------------------
    # Detections
    # ------------------------------------------------------------------

    def set_detections(self, detections: list[Detection]) -> None:
        with self._lock:
            self._detections = list(detections)

    def get_detections(self) -> list[Detection]:
        with self._lock:
            return list(self._detections)

    # ------------------------------------------------------------------
    # Alerts
    # ------------------------------------------------------------------

    def add_pending_alert(self, alert: Alert) -> None:
        with self._lock:
            self._pending_alerts.append(alert)

    def get_pending_alerts(self) -> list[Alert]:
        with self._lock:
            return [a for a in self._pending_alerts if a.status == AlertStatus.PENDING_APPROVAL]

    def get_all_alerts(self) -> list[Alert]:
        with self._lock:
            return list(self._pending_alerts) + list(self._dispatched_alerts)

    def approve_alert(self, alert_id: str, officer_id: str) -> Optional[Alert]:
        with self._lock:
            for alert in self._pending_alerts:
                if alert.alert_id == alert_id:
                    alert.status = AlertStatus.DISPATCHED
                    alert.approved_by = officer_id
                    self._dispatched_alerts.append(alert)
                    self._pending_alerts.remove(alert)
                    return alert
        return None

    def reject_alert(self, alert_id: str, officer_id: str, reason: str = "") -> Optional[Alert]:
        with self._lock:
            for alert in self._pending_alerts:
                if alert.alert_id == alert_id:
                    alert.status = AlertStatus.REJECTED
                    alert.approved_by = officer_id
                    alert.rejection_reason = reason
                    self._pending_alerts.remove(alert)
                    return alert
        return None

    def clear_alerts(self) -> None:
        with self._lock:
            self._pending_alerts = []
            self._dispatched_alerts = []

    # ------------------------------------------------------------------
    # HITL queue
    # ------------------------------------------------------------------

    def add_hitl_item(self, item: HitlQueueItem) -> None:
        with self._lock:
            self._hitl_queue.append(item)

    def get_hitl_queue(self) -> list[HitlQueueItem]:
        with self._lock:
            return [i for i in self._hitl_queue if i.verdict is None]

    def resolve_hitl(
        self,
        item_id: str,
        verdict: HitlVerdict,
        officer_id: str,
        notes: str = "",
    ) -> Optional[HitlQueueItem]:
        with self._lock:
            for item in self._hitl_queue:
                if item.item_id == item_id and item.verdict is None:
                    item.verdict = verdict
                    item.resolved_by = officer_id
                    item.resolved_at = datetime.now(timezone.utc)
                    item.notes = notes
                    return item
        return None

    # ------------------------------------------------------------------
    # Tool trace log
    # ------------------------------------------------------------------

    def add_tool_trace(self, entry: ToolTraceEntry) -> None:
        with self._lock:
            self._tool_trace_log.append(entry)
            # Keep last 200 entries
            if len(self._tool_trace_log) > 200:
                self._tool_trace_log = self._tool_trace_log[-200:]

    def get_tool_trace_log(self, last_n: int = 20) -> list[ToolTraceEntry]:
        with self._lock:
            return list(self._tool_trace_log[-last_n:])

    # ------------------------------------------------------------------
    # Agent run logs
    # ------------------------------------------------------------------

    def add_agent_run_log(self, log: AgentRunLog) -> None:
        with self._lock:
            self._agent_run_logs.append(log)

    def get_agent_run_logs(self) -> list[AgentRunLog]:
        with self._lock:
            return list(self._agent_run_logs)

    # ------------------------------------------------------------------
    # Run history
    # ------------------------------------------------------------------

    def add_run_report(self, report: RunReport) -> None:
        with self._lock:
            self._run_history.append(report)
            if len(self._run_history) > 50:
                self._run_history = self._run_history[-50:]

    def get_run_history(self, last_n: int = 10) -> list[RunReport]:
        with self._lock:
            return list(self._run_history[-last_n:])

    def get_last_run(self) -> Optional[RunReport]:
        with self._lock:
            return self._run_history[-1] if self._run_history else None

    # ------------------------------------------------------------------
    # LLM call log (cost/token tracking)
    # ------------------------------------------------------------------

    def log_llm_call(self, entry: dict) -> None:
        with self._lock:
            self._llm_call_log.append(entry)
            if len(self._llm_call_log) > 500:
                self._llm_call_log = self._llm_call_log[-500:]

    def get_llm_call_log(self, last_n: int = 50) -> list[dict]:
        with self._lock:
            return list(self._llm_call_log[-last_n:])

    def get_total_cost(self) -> float:
        with self._lock:
            return sum(e.get("cost_usd", 0.0) for e in self._llm_call_log)

    def get_total_tokens(self) -> dict:
        with self._lock:
            return {
                "tokens_in": sum(e.get("tokens_in", 0) for e in self._llm_call_log),
                "tokens_out": sum(e.get("tokens_out", 0) for e in self._llm_call_log),
            }

    # ------------------------------------------------------------------
    # Reset (for testing)
    # ------------------------------------------------------------------

    def reset(self) -> None:
        with self._lock:
            self._wildlife_report = None
            self._detections = []
            self._pending_alerts = []
            self._dispatched_alerts = []
            self._hitl_queue = []
            self._tool_trace_log = []
            self._agent_run_logs = []
            self._run_history = []
            self._llm_call_log = []


# Module-level singleton instance used by all components
store = MemoryStore()
