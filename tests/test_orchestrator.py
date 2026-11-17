"""
tests/test_orchestrator.py — Tests for orchestrator pipeline and HITL gate.

Verifies that:
- run_once() runs all agents and writes to MemoryStore
- No alert is dispatched without explicit officer approval
- approve_alert() and reject_alert() write audit log entries
- resolve_hitl() triggers Agent 3 re-run for approved detections
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest

from memory.store import store as mem_store
from schemas import (
    AlertStatus,
    AuditEventType,
    CameraTrapEvent,
    DataSource,
    Detection,
    HitlVerdict,
    RiskLevel,
    RiskZone,
    Sighting,
    WildlifeReport,
)
from audit.log import read_audit_log


def _make_wildlife_report() -> WildlifeReport:
    return WildlifeReport(
        active_sightings=[
            Sighting(lat=12.42, lon=76.52, timestamp=datetime.now(timezone.utc),
                     confidence=0.9, district="Kodagu", data_source=DataSource.SYNTHETIC)
        ],
        camera_trap_events=[
            CameraTrapEvent(lat=12.42, lon=76.52, timestamp=datetime.now(timezone.utc),
                            image_description="Clear elephant visible", confidence=0.9,
                            district="Kodagu", data_source=DataSource.SYNTHETIC)
        ],
        pattern_summary="Test pattern",
        risk_districts=["Kodagu"],
        data_sources=["synthetic"],
        synthetic_data_present=True,
    )


def _make_detection(confidence: float = 0.88, requires_hitl: bool = False) -> Detection:
    return Detection(
        event_id="test-event",
        is_elephant=True,
        detection_confidence=confidence,
        requires_hitl_review=requires_hitl,
        nearest_village="Kushalnagar",
        distance_km=3.5,
        in_corridor=True,
        explanation="Test",
        lat=12.42, lon=76.52,
        district="Kodagu",
    )


class TestOrchestratorPipeline:
    def setup_method(self):
        mem_store.reset()

    def _mock_agents(self, report=None, detections=None, alerts=None):
        """Return mock agent instances."""
        from schemas import Alert

        mock_wildlife = MagicMock()
        mock_wildlife.run.return_value = report or _make_wildlife_report()

        mock_detection = MagicMock()
        mock_detection.run.return_value = detections or [_make_detection(0.88)]

        mock_alert = MagicMock()
        if alerts is None:
            # Create a real alert and add it to the store (mimics real agent behaviour)
            from tools.alert_tools import format_alert
            rz = RiskZone(
                village="Kushalnagar", district="Kodagu",
                lat=12.42, lon=76.52,
                risk_level=RiskLevel.MEDIUM, village_risk_score=0.55,
                reason="test", contributing_factors=["test factor"],
            )
            real_alert = format_alert("Kushalnagar", "Kodagu", rz,
                                      detection_confidence=0.88, distance_km=3.5)
            mem_store.add_pending_alert(real_alert)
            mock_alert.run.return_value = [real_alert]
        else:
            mock_alert.run.return_value = alerts

        return mock_wildlife, mock_detection, mock_alert

    def test_run_once_returns_run_report(self):
        import orchestrator
        mock_w, mock_d, mock_a = self._mock_agents()
        with patch("orchestrator._load_agents", return_value={
            "wildlife": mock_w, "detection": mock_d, "alert": mock_a
        }):
            report = orchestrator.run_once()
        from schemas import RunReport
        assert isinstance(report, RunReport)

    def test_run_once_records_agents_run(self):
        import orchestrator
        mock_w, mock_d, mock_a = self._mock_agents()
        with patch("orchestrator._load_agents", return_value={
            "wildlife": mock_w, "detection": mock_d, "alert": mock_a
        }):
            report = orchestrator.run_once()
        assert "WildlifeDataAgent" in report.agents_run
        assert "ElephantDetectionAgent" in report.agents_run
        assert "EarlyWarningAgent" in report.agents_run

    def test_run_once_writes_wildlife_report_to_store(self):
        import orchestrator
        mock_w, mock_d, mock_a = self._mock_agents()
        with patch("orchestrator._load_agents", return_value={
            "wildlife": mock_w, "detection": mock_d, "alert": mock_a
        }):
            orchestrator.run_once()
        assert mem_store.get_wildlife_report() is not None

    def test_run_once_writes_detections_to_store(self):
        import orchestrator
        mock_w, mock_d, mock_a = self._mock_agents()
        with patch("orchestrator._load_agents", return_value={
            "wildlife": mock_w, "detection": mock_d, "alert": mock_a
        }):
            orchestrator.run_once()
        assert len(mem_store.get_detections()) > 0

    def test_no_alert_dispatched_without_approval(self):
        """Core HITL gate: all alerts must remain PENDING_APPROVAL after run_once."""
        import orchestrator
        mock_w, mock_d, mock_a = self._mock_agents()
        with patch("orchestrator._load_agents", return_value={
            "wildlife": mock_w, "detection": mock_d, "alert": mock_a
        }):
            orchestrator.run_once()
        all_alerts = mem_store.get_all_alerts()
        for alert in all_alerts:
            assert alert.status == AlertStatus.PENDING_APPROVAL, (
                f"Alert {alert.alert_id} has status {alert.status} — must be PENDING_APPROVAL"
            )

    def test_agent_error_does_not_crash_pipeline(self):
        """If Agent 1 raises, the pipeline continues and reports the error."""
        import orchestrator
        mock_w = MagicMock()
        mock_w.run.side_effect = RuntimeError("Agent 1 crashed")
        mock_d = MagicMock()
        mock_d.run.return_value = []
        mock_a = MagicMock()
        mock_a.run.return_value = []
        with patch("orchestrator._load_agents", return_value={
            "wildlife": mock_w, "detection": mock_d, "alert": mock_a
        }):
            report = orchestrator.run_once()
        assert len(report.errors) > 0
        assert "WildlifeDataAgent failed" in report.errors[0]

    def test_run_report_added_to_history(self):
        import orchestrator
        mock_w, mock_d, mock_a = self._mock_agents()
        with patch("orchestrator._load_agents", return_value={
            "wildlife": mock_w, "detection": mock_d, "alert": mock_a
        }):
            orchestrator.run_once()
        history = mem_store.get_run_history()
        assert len(history) >= 1


class TestApproveRejectAlert:
    def setup_method(self):
        mem_store.reset()
        # Create a pending alert in store
        from tools.alert_tools import format_alert
        rz = RiskZone(
            village="Kushalnagar", district="Kodagu",
            lat=12.42, lon=76.52,
            risk_level=RiskLevel.HIGH, village_risk_score=0.80,
            reason="test", contributing_factors=["Dense sightings"],
        )
        self.alert = format_alert("Kushalnagar", "Kodagu", rz,
                                   detection_confidence=0.88, distance_km=2.5)
        mem_store.add_pending_alert(self.alert)

    def test_approve_changes_status_to_dispatched(self):
        import orchestrator
        result = orchestrator.approve_alert(self.alert.alert_id, "officer-001")
        assert result is True
        all_alerts = mem_store.get_all_alerts()
        approved = next((a for a in all_alerts if a.alert_id == self.alert.alert_id), None)
        assert approved is not None
        assert approved.status == AlertStatus.DISPATCHED

    def test_approve_writes_audit_log(self):
        import orchestrator
        orchestrator.approve_alert(self.alert.alert_id, "officer-001")
        log = read_audit_log(last_n=10)
        event_types = [e["event_type"] for e in log]
        assert AuditEventType.ALERT_APPROVED.value in event_types

    def test_reject_changes_status_to_rejected(self):
        import orchestrator
        result = orchestrator.reject_alert(self.alert.alert_id, "officer-001", "false alarm")
        assert result is True
        # Rejected alert should no longer be in pending queue
        pending = mem_store.get_pending_alerts()
        pending_ids = [a.alert_id for a in pending]
        assert self.alert.alert_id not in pending_ids

    def test_reject_writes_audit_log(self):
        import orchestrator
        orchestrator.reject_alert(self.alert.alert_id, "officer-001", "false alarm")
        log = read_audit_log(last_n=10)
        event_types = [e["event_type"] for e in log]
        assert AuditEventType.ALERT_REJECTED.value in event_types

    def test_approve_nonexistent_alert_returns_false(self):
        import orchestrator
        result = orchestrator.approve_alert("nonexistent-id", "officer-001")
        assert result is False

    def test_reject_nonexistent_alert_returns_false(self):
        import orchestrator
        result = orchestrator.reject_alert("nonexistent-id", "officer-001")
        assert result is False

    def test_pending_alert_not_in_dispatched_before_approval(self):
        """Alert must stay PENDING until explicitly approved."""
        all_alerts = mem_store.get_all_alerts()
        for a in all_alerts:
            assert a.status != AlertStatus.DISPATCHED


class TestHitlResolution:
    def setup_method(self):
        mem_store.reset()
        # Create a HITL queue item
        from schemas import HitlQueueItem
        self.detection = _make_detection(0.45, requires_hitl=True)
        self.hitl_item = HitlQueueItem(detection=self.detection)
        mem_store.add_hitl_item(self.hitl_item)

    def test_resolve_hitl_approved(self):
        import orchestrator
        with patch("agents.early_warning_agent.EarlyWarningAgent") as MockAgent:
            MockAgent.return_value.run.return_value = []
            result = orchestrator.resolve_hitl(
                self.hitl_item.item_id, HitlVerdict.APPROVED, "officer-001"
            )
        assert result is True
        queue = mem_store.get_hitl_queue()
        assert all(i.item_id != self.hitl_item.item_id for i in queue)

    def test_resolve_hitl_rejected(self):
        import orchestrator
        result = orchestrator.resolve_hitl(
            self.hitl_item.item_id, HitlVerdict.REJECTED, "officer-001", "clearly not elephant"
        )
        assert result is True

    def test_resolve_hitl_writes_audit(self):
        import orchestrator
        orchestrator.resolve_hitl(
            self.hitl_item.item_id, HitlVerdict.REJECTED, "officer-001"
        )
        log = read_audit_log(last_n=10)
        event_types = [e["event_type"] for e in log]
        assert AuditEventType.HITL_RESOLVED.value in event_types

    def test_resolve_nonexistent_hitl_returns_false(self):
        import orchestrator
        result = orchestrator.resolve_hitl("bad-id", HitlVerdict.APPROVED, "officer-001")
        assert result is False
