"""
tests/test_e2e.py — End-to-end pipeline test.

Runs the complete sighting-to-alert workflow with mocked LLM calls and
synthetic data, then asserts every acceptance criterion from the plan.
"""

import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest

from memory.store import store as mem_store
from audit.log import read_audit_log
from schemas import (
    AlertStatus,
    AuditEventType,
    CameraTrapEvent,
    DataSource,
    Detection,
    HitlVerdict,
    RiskLevel,
    Sighting,
    WildlifeReport,
)


# ---------------------------------------------------------------------------
# Shared mocks
# ---------------------------------------------------------------------------

def _llm_wildlife():
    from llm.gateway import LLMResponse
    return MagicMock(return_value=LLMResponse(
        content='{"pattern_summary":"Active elephant movement in Kodagu-Mysuru corridor. '
                '10 sightings recorded with high confidence. Risk is elevated.", '
                '"risk_districts":["Kodagu","Mysuru","Hassan"],'
                '"confidence_scores":{"Kodagu":0.88,"Mysuru":0.75,"Hassan":0.60},'
                '"data_sources":["synthetic","open_meteo_live"],"synthetic_data_present":true}',
        model_id="ibm-granite/granite-4.2-8b",
        route_used="openrouter_granite",
        tokens_in=200, tokens_out=80, cost_usd=0.0003, is_fallback=False,
    ))


def _llm_detection_high():
    from llm.gateway import LLMResponse
    return MagicMock(return_value=LLMResponse(
        content='{"is_elephant":true,"detection_confidence":0.92,'
                '"false_alarm_flag":false,"requires_hitl_review":false,'
                '"explanation":"Clear elephant silhouette with tusks visible."}',
        model_id="google/gemini-2.5-flash",
        route_used="openrouter_gemini",
        tokens_in=80, tokens_out=40, cost_usd=0.00005, is_fallback=False,
    ))


def _llm_detection_low():
    from llm.gateway import LLMResponse
    return MagicMock(return_value=LLMResponse(
        content='{"is_elephant":false,"detection_confidence":0.42,'
                '"false_alarm_flag":true,"requires_hitl_review":true,'
                '"explanation":"Camera triggered by wind. No animal visible."}',
        model_id="google/gemini-2.5-flash",
        route_used="openrouter_gemini",
        tokens_in=70, tokens_out=35, cost_usd=0.00004, is_fallback=False,
    ))


def _llm_alert():
    from llm.gateway import LLMResponse
    return MagicMock(return_value=LLMResponse(
        content='{"message_en":"HIGH ALERT: Elephant herd detected 2.5 km from Kushalnagar. '
                'Do not go to fields tonight. Call 1800-425-7378.","message_kn":"ಹೆಚ್ಚಿನ ಎಚ್ಚರಿಕೆ: '
                'ಕುಶಾಲನಗರ ಬಳಿ ಆನೆ ಪತ್ತೆ. ಹೊಲಕ್ಕೆ ಹೋಗಬೇಡಿ.",'
                '"recommended_actions":["Stay indoors","Call helpline"],'
                '"risk_explanation":"High sighting density in Kodagu corridor with harvest crops nearby."}',
        model_id="openai/gpt-oss-20b",
        route_used="groq_direct",
        tokens_in=150, tokens_out=90, cost_usd=0.0002, is_fallback=False,
    ))


# ---------------------------------------------------------------------------
# End-to-end test class
# ---------------------------------------------------------------------------

class TestEndToEndPipeline:
    def setup_method(self):
        mem_store.reset()

    def _run_pipeline_mocked(self, detection_llm=None):
        """Run the full pipeline with mocked LLM calls."""
        import orchestrator

        def _side_effect(model_id, messages, **kwargs):
            if "granite" in model_id.lower() or "ibm" in model_id.lower():
                return _llm_wildlife()()
            elif "gemini" in model_id.lower() or "google" in model_id.lower():
                mock = detection_llm or _llm_detection_high()
                return mock()
            else:
                return _llm_alert()()

        with patch("llm.gateway.chat_completion", side_effect=_side_effect):
            report = orchestrator.run_once(hours_back=24)
        return report

    # AC-1: End-to-end sighting-to-alert workflow
    def test_e2e_pipeline_completes(self):
        report = self._run_pipeline_mocked()
        from schemas import RunReport
        assert isinstance(report, RunReport)
        assert len(report.agents_run) == 3

    # AC-1: Wildlife report generated with valid schema
    def test_wildlife_report_has_valid_schema(self):
        self._run_pipeline_mocked()
        report = mem_store.get_wildlife_report()
        assert report is not None
        assert isinstance(report, WildlifeReport)
        assert len(report.active_sightings) > 0
        assert len(report.risk_districts) > 0

    # AC-2: Data provenance labels on all records
    def test_all_sightings_have_provenance(self):
        self._run_pipeline_mocked()
        report = mem_store.get_wildlife_report()
        for s in report.active_sightings:
            assert hasattr(s, "data_source")
            assert s.data_source is not None

    def test_all_camera_events_have_provenance(self):
        self._run_pipeline_mocked()
        report = mem_store.get_wildlife_report()
        for e in report.camera_trap_events:
            assert hasattr(e, "data_source")
            assert e.data_source is not None

    # AC-3: Synthetic disclaimer present
    def test_synthetic_flag_set_on_report(self):
        self._run_pipeline_mocked()
        report = mem_store.get_wildlife_report()
        assert report.synthetic_data_present is True

    # AC-5: HITL threshold configurable
    def test_hitl_threshold_from_config(self):
        import config
        assert 0.0 <= config.HITL_CONFIDENCE_THRESHOLD <= 1.0
        assert config.HITL_CONFIDENCE_THRESHOLD == 0.70

    # AC-6: detection_confidence and village_risk_score are separate
    def test_detection_confidence_separate_from_risk_score(self):
        self._run_pipeline_mocked()
        alerts = mem_store.get_all_alerts()
        for alert in alerts:
            assert hasattr(alert, "detection_confidence")
            assert hasattr(alert, "village_risk_score")
            # They should be distinct fields (not necessarily different values)

    # AC-7: Forest officer approval required for all alerts
    def test_no_alert_dispatched_without_approval(self):
        self._run_pipeline_mocked()
        all_alerts = mem_store.get_all_alerts()
        for alert in all_alerts:
            assert alert.status == AlertStatus.PENDING_APPROVAL, (
                f"Alert {alert.alert_id} has unexpected status: {alert.status}"
            )

    # AC-8: Low-confidence detections flagged for HITL
    def test_low_confidence_detections_in_hitl_queue(self):
        self._run_pipeline_mocked(detection_llm=_llm_detection_low())
        queue = mem_store.get_hitl_queue()
        # At least one HITL item from low-confidence detection
        assert len(queue) > 0
        for item in queue:
            assert item.detection.detection_confidence < 0.70 or item.detection.false_alarm_flag

    # AC-9: Audit log entries for all events
    def test_audit_log_has_pipeline_run_entries(self):
        self._run_pipeline_mocked()
        log = read_audit_log(last_n=50)
        event_types = {e["event_type"] for e in log}
        assert AuditEventType.PIPELINE_RUN_START.value in event_types
        assert AuditEventType.PIPELINE_RUN_END.value in event_types

    def test_audit_log_has_alert_created(self):
        self._run_pipeline_mocked()
        log = read_audit_log(last_n=50)
        event_types = [e["event_type"] for e in log]
        assert AuditEventType.ALERT_CREATED.value in event_types

    def test_audit_log_has_hitl_flagged_on_low_confidence(self):
        self._run_pipeline_mocked(detection_llm=_llm_detection_low())
        log = read_audit_log(last_n=50)
        event_types = [e["event_type"] for e in log]
        assert AuditEventType.HITL_FLAGGED.value in event_types

    def test_audit_log_records_approval(self):
        self._run_pipeline_mocked()
        alerts = mem_store.get_pending_alerts()
        if alerts:
            import orchestrator
            orchestrator.approve_alert(alerts[0].alert_id, "officer-001")
            log = read_audit_log(last_n=10)
            event_types = [e["event_type"] for e in log]
            assert AuditEventType.ALERT_APPROVED.value in event_types

    def test_audit_log_records_rejection(self):
        self._run_pipeline_mocked()
        alerts = mem_store.get_pending_alerts()
        if alerts:
            import orchestrator
            orchestrator.reject_alert(alerts[0].alert_id, "officer-001", "false alarm")
            log = read_audit_log(last_n=10)
            event_types = [e["event_type"] for e in log]
            assert AuditEventType.ALERT_REJECTED.value in event_types

    # AC-10 & AC-11: Risk zones have contributing_factors (explainability)
    def test_risk_zones_have_contributing_factors(self):
        from tools.map_tools import compute_risk_zones
        sightings = [
            Sighting(lat=12.42, lon=76.52, timestamp=datetime.now(timezone.utc),
                     confidence=0.9, district="Kodagu", data_source=DataSource.SYNTHETIC)
            for _ in range(5)
        ]
        zones = compute_risk_zones(sightings)
        for zone in zones:
            assert len(zone.contributing_factors) > 0

    # AC-12: Gateway fallback works when OmniRoute unavailable
    def test_gateway_fallback_does_not_crash(self):
        from llm.gateway import chat_completion, LLMResponse
        from llm.gateway import _MODEL_ADAPTER_CACHE
        _MODEL_ADAPTER_CACHE.clear()

        with patch("config.has_omniroute_credentials", return_value=True), \
             patch("llm.gateway._try_omniroute", side_effect=Exception("OmniRoute down")), \
             patch("config.has_ibm_credentials", return_value=False), \
             patch("config.has_gemini_credentials", return_value=False), \
             patch("config.has_groq_credentials", return_value=False), \
             patch("config.GEMINI_API_KEY", ""):
            resp = chat_completion("ibm/granite-4-h-small", [{"role": "user", "content": "hi"}])
        assert resp.is_fallback is True
        assert "FALLBACK" in resp.content

    # AC-13: API failures return deterministic fallback
    def test_agent_api_failure_produces_valid_report(self):
        from agents.wildlife_data_agent import WildlifeDataAgent
        from llm.gateway import LLMResponse
        fallback_mock = MagicMock(return_value=LLMResponse(
            content="FALLBACK: LLM unavailable",
            model_id="ibm-granite/granite-4.2-8b",
            route_used="fallback",
            is_fallback=True,
        ))
        agent = WildlifeDataAgent()
        with patch("llm.gateway.chat_completion", fallback_mock):
            report = agent.run(hours_back=24)
        assert isinstance(report, WildlifeReport)
        assert len(report.pattern_summary) > 0  # fallback summary generated

    # AC-7 — Approved alert changes to DISPATCHED
    def test_approved_alert_becomes_dispatched(self):
        self._run_pipeline_mocked()
        import orchestrator
        alerts = mem_store.get_pending_alerts()
        if alerts:
            alert_id = alerts[0].alert_id
            orchestrator.approve_alert(alert_id, "officer-001")
            all_alerts = mem_store.get_all_alerts()
            approved = next((a for a in all_alerts if a.alert_id == alert_id), None)
            assert approved is not None
            assert approved.status == AlertStatus.DISPATCHED

    # AC-7 — Rejected alert is not dispatched
    def test_rejected_alert_not_dispatched(self):
        self._run_pipeline_mocked()
        import orchestrator
        alerts = mem_store.get_pending_alerts()
        if alerts:
            alert_id = alerts[0].alert_id
            orchestrator.reject_alert(alert_id, "officer-001", "test rejection")
            # Should not be in pending or dispatched as DISPATCHED
            dispatched = [a for a in mem_store.get_all_alerts()
                          if a.status == AlertStatus.DISPATCHED]
            assert all(a.alert_id != alert_id for a in dispatched)
