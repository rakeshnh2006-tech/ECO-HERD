"""
tests/test_agents.py — Tests for all three agents using mocked LLM gateway.

Verifies schema validation, HITL flagging, provenance, and fallback behaviour
without making real API calls.
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
    Sighting,
    WildlifeReport,
)


def _make_camera_event(confidence: float = 0.9, desc: str = "Clear elephant visible") -> CameraTrapEvent:
    return CameraTrapEvent(
        lat=12.42, lon=76.52,
        timestamp=datetime.now(timezone.utc),
        image_description=desc,
        confidence=confidence,
        district="Kodagu",
        data_source=DataSource.SYNTHETIC,
    )


def _make_detection(confidence: float = 0.85, requires_hitl: bool = False) -> Detection:
    return Detection(
        event_id="test-event-1",
        is_elephant=True,
        detection_confidence=confidence,
        requires_hitl_review=requires_hitl,
        nearest_village="Kushalnagar",
        distance_km=3.5,
        in_corridor=True,
        explanation="Test detection",
        lat=12.42, lon=76.52,
        district="Kodagu",
    )


def _llm_mock_wildlife():
    """Mock LLM response for WildlifeDataAgent."""
    from llm.gateway import LLMResponse
    return MagicMock(return_value=LLMResponse(
        content='{"pattern_summary": "Test pattern", "risk_districts": ["Kodagu"], '
                '"confidence_scores": {"Kodagu": 0.85}, "data_sources": ["synthetic"], '
                '"synthetic_data_present": true}',
        model_id="ibm/granite-4-h-small",
        route_used="ibm_granite_direct",
        tokens_in=100, tokens_out=50, cost_usd=0.0001, is_fallback=False,
    ))


def _llm_mock_detection(confidence: float = 0.88, is_elephant: bool = True):
    """Mock LLM response for ElephantDetectionAgent."""
    from llm.gateway import LLMResponse
    return MagicMock(return_value=LLMResponse(
        content=f'{{"is_elephant": {str(is_elephant).lower()}, "detection_confidence": {confidence}, '
                f'"false_alarm_flag": false, "requires_hitl_review": {str(confidence < 0.70).lower()}, '
                f'"explanation": "Test explanation"}}',
        model_id="gemini-2.0-flash",
        route_used="openrouter_gemini",
        tokens_in=80, tokens_out=40, cost_usd=0.00005, is_fallback=False,
    ))


def _llm_mock_alert():
    """Mock LLM response for EarlyWarningAgent."""
    from llm.gateway import LLMResponse
    return MagicMock(return_value=LLMResponse(
        content='{"message_en": "HIGH ALERT: Elephants detected near Kushalnagar. Stay indoors.", '
                '"message_kn": "ಹೆಚ್ಚಿನ ಎಚ್ಚರಿಕೆ: ಆನೆಗಳು ಕುಶಾಲನಗರ ಬಳಿ ಪತ್ತೆಯಾಗಿವೆ. ಒಳಗಿರಿ.", '
                '"recommended_actions": ["Stay indoors", "Call helpline"], '
                '"risk_explanation": "High sighting density in corridor zone"}',
        model_id="llama-3.3-70b-versatile",
        route_used="groq_direct",
        tokens_in=120, tokens_out=80, cost_usd=0.0002, is_fallback=False,
    ))


# ---------------------------------------------------------------------------
# WildlifeDataAgent tests
# ---------------------------------------------------------------------------

class TestWildlifeDataAgent:
    def setup_method(self):
        mem_store.reset()

    def test_returns_wildlife_report(self):
        from agents.wildlife_data_agent import WildlifeDataAgent
        agent = WildlifeDataAgent()
        with patch("llm.gateway.chat_completion", _llm_mock_wildlife()):
            report = agent.run(hours_back=24)
        assert isinstance(report, WildlifeReport)

    def test_report_has_sightings(self):
        from agents.wildlife_data_agent import WildlifeDataAgent
        agent = WildlifeDataAgent()
        with patch("llm.gateway.chat_completion", _llm_mock_wildlife()):
            report = agent.run(hours_back=24)
        assert len(report.active_sightings) > 0

    def test_report_has_risk_districts(self):
        from agents.wildlife_data_agent import WildlifeDataAgent
        agent = WildlifeDataAgent()
        with patch("llm.gateway.chat_completion", _llm_mock_wildlife()):
            report = agent.run(hours_back=24)
        assert len(report.risk_districts) > 0

    def test_report_has_data_sources(self):
        from agents.wildlife_data_agent import WildlifeDataAgent
        agent = WildlifeDataAgent()
        with patch("llm.gateway.chat_completion", _llm_mock_wildlife()):
            report = agent.run(hours_back=24)
        assert len(report.data_sources) > 0

    def test_report_synthetic_flag(self):
        from agents.wildlife_data_agent import WildlifeDataAgent
        agent = WildlifeDataAgent()
        with patch("llm.gateway.chat_completion", _llm_mock_wildlife()):
            report = agent.run(hours_back=24)
        assert report.synthetic_data_present is True

    def test_fallback_still_returns_report(self):
        """Even if LLM returns a fallback, a valid report should be built from data."""
        from agents.wildlife_data_agent import WildlifeDataAgent
        from llm.gateway import LLMResponse
        fallback = MagicMock(return_value=LLMResponse(
            content="FALLBACK: LLM unavailable",
            model_id="ibm/granite-4-h-small",
            route_used="fallback",
            is_fallback=True,
        ))
        agent = WildlifeDataAgent()
        with patch("llm.gateway.chat_completion", fallback):
            report = agent.run(hours_back=24)
        assert isinstance(report, WildlifeReport)
        assert len(report.pattern_summary) > 0

    def test_agent_run_log_written_to_store(self):
        from agents.wildlife_data_agent import WildlifeDataAgent
        agent = WildlifeDataAgent()
        with patch("llm.gateway.chat_completion", _llm_mock_wildlife()):
            agent.run(hours_back=24)
        logs = mem_store.get_agent_run_logs()
        assert any(l.agent_name == "WildlifeDataAgent" for l in logs)

    def test_confidence_scores_clamped(self):
        from agents.wildlife_data_agent import WildlifeDataAgent
        from llm.gateway import LLMResponse
        # Return scores outside 0-1 range
        bad_scores = MagicMock(return_value=LLMResponse(
            content='{"pattern_summary": "Test", "risk_districts": ["Kodagu"], '
                    '"confidence_scores": {"Kodagu": 1.5, "Hassan": -0.2}, '
                    '"data_sources": ["synthetic"], "synthetic_data_present": true}',
            model_id="ibm/granite-4-h-small", route_used="mock", is_fallback=False,
        ))
        agent = WildlifeDataAgent()
        with patch("llm.gateway.chat_completion", bad_scores):
            report = agent.run()
        for score in report.confidence_scores.values():
            assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# ElephantDetectionAgent tests
# ---------------------------------------------------------------------------

class TestElephantDetectionAgent:
    def setup_method(self):
        mem_store.reset()

    def _make_report(self, events=None) -> WildlifeReport:
        return WildlifeReport(
            active_sightings=[],
            camera_trap_events=events if events is not None else [_make_camera_event(0.9)],
            pattern_summary="Test",
            risk_districts=["Kodagu"],
            data_sources=["synthetic"],
            synthetic_data_present=True,
        )

    def test_returns_detections_list(self):
        from agents.elephant_detection_agent import ElephantDetectionAgent
        agent = ElephantDetectionAgent()
        report = self._make_report()
        with patch("llm.gateway.chat_completion", _llm_mock_detection(0.88)):
            detections = agent.run(report)
        assert isinstance(detections, list)
        assert len(detections) == 1

    def test_high_confidence_not_hitl_flagged(self):
        from agents.elephant_detection_agent import ElephantDetectionAgent
        agent = ElephantDetectionAgent()
        report = self._make_report([_make_camera_event(0.92)])
        with patch("llm.gateway.chat_completion", _llm_mock_detection(0.92)):
            detections = agent.run(report)
        assert detections[0].requires_hitl_review is False

    def test_low_confidence_hitl_flagged(self):
        from agents.elephant_detection_agent import ElephantDetectionAgent
        agent = ElephantDetectionAgent()
        report = self._make_report([_make_camera_event(0.45, "unclear shape")])
        with patch("llm.gateway.chat_completion", _llm_mock_detection(0.45)):
            detections = agent.run(report)
        assert detections[0].requires_hitl_review is True

    def test_hitl_item_written_to_store(self):
        from agents.elephant_detection_agent import ElephantDetectionAgent
        agent = ElephantDetectionAgent()
        report = self._make_report([_make_camera_event(0.45, "unclear")])
        with patch("llm.gateway.chat_completion", _llm_mock_detection(0.45)):
            agent.run(report)
        queue = mem_store.get_hitl_queue()
        assert len(queue) == 1

    def test_detection_has_explanation(self):
        from agents.elephant_detection_agent import ElephantDetectionAgent
        agent = ElephantDetectionAgent()
        report = self._make_report()
        with patch("llm.gateway.chat_completion", _llm_mock_detection(0.88)):
            detections = agent.run(report)
        assert len(detections[0].explanation) > 0

    def test_detection_has_nearest_village(self):
        from agents.elephant_detection_agent import ElephantDetectionAgent
        agent = ElephantDetectionAgent()
        report = self._make_report()
        with patch("llm.gateway.chat_completion", _llm_mock_detection(0.88)):
            detections = agent.run(report)
        assert detections[0].nearest_village != ""

    def test_separate_confidence_fields(self):
        """detection_confidence must be a separate field from village_risk_score (checked later)."""
        from agents.elephant_detection_agent import ElephantDetectionAgent
        agent = ElephantDetectionAgent()
        report = self._make_report()
        with patch("llm.gateway.chat_completion", _llm_mock_detection(0.88)):
            detections = agent.run(report)
        d = detections[0]
        assert hasattr(d, "detection_confidence")
        assert 0.0 <= d.detection_confidence <= 1.0

    def test_fallback_response_triggers_hitl(self):
        """A fallback LLM response must flag the detection for HITL review."""
        from agents.elephant_detection_agent import ElephantDetectionAgent
        from llm.gateway import LLMResponse
        fallback = MagicMock(return_value=LLMResponse(
            content="FALLBACK: LLM unavailable",
            model_id="gemini-2.0-flash",
            route_used="fallback",
            is_fallback=True,
        ))
        agent = ElephantDetectionAgent()
        report = self._make_report()
        with patch("llm.gateway.chat_completion", fallback):
            detections = agent.run(report)
        assert detections[0].requires_hitl_review is True

    def test_no_events_returns_empty(self):
        from agents.elephant_detection_agent import ElephantDetectionAgent
        agent = ElephantDetectionAgent()
        report = self._make_report(events=[])
        with patch("llm.gateway.chat_completion", _llm_mock_detection()):
            detections = agent.run(report)
        assert detections == []


# ---------------------------------------------------------------------------
# EarlyWarningAgent tests
# ---------------------------------------------------------------------------

class TestEarlyWarningAgent:
    def setup_method(self):
        mem_store.reset()

    def test_returns_alerts_list(self):
        from agents.early_warning_agent import EarlyWarningAgent
        agent = EarlyWarningAgent()
        detections = [_make_detection(0.88)]
        with patch("llm.gateway.chat_completion", _llm_mock_alert()):
            alerts = agent.run(detections)
        assert isinstance(alerts, list)

    def test_all_alerts_pending_approval(self):
        """No alert must ever have DISPATCHED status after agent run."""
        from agents.early_warning_agent import EarlyWarningAgent
        agent = EarlyWarningAgent()
        detections = [_make_detection(0.88)]
        with patch("llm.gateway.chat_completion", _llm_mock_alert()):
            alerts = agent.run(detections)
        for alert in alerts:
            assert alert.status == AlertStatus.PENDING_APPROVAL

    def test_hitl_detections_excluded(self):
        """Detections with requires_hitl_review=True must not generate alerts."""
        from agents.early_warning_agent import EarlyWarningAgent
        agent = EarlyWarningAgent()
        detections = [_make_detection(0.45, requires_hitl=True)]  # HITL flagged
        with patch("llm.gateway.chat_completion", _llm_mock_alert()):
            alerts = agent.run(detections)
        assert alerts == []

    def test_alerts_have_english_message(self):
        from agents.early_warning_agent import EarlyWarningAgent
        agent = EarlyWarningAgent()
        detections = [_make_detection(0.88)]
        with patch("llm.gateway.chat_completion", _llm_mock_alert()):
            alerts = agent.run(detections)
        for alert in alerts:
            assert len(alert.message_en) > 10

    def test_alerts_have_kannada_message(self):
        from agents.early_warning_agent import EarlyWarningAgent
        agent = EarlyWarningAgent()
        detections = [_make_detection(0.88)]
        with patch("llm.gateway.chat_completion", _llm_mock_alert()):
            alerts = agent.run(detections)
        for alert in alerts:
            assert len(alert.message_kn) > 10

    def test_village_risk_score_and_detection_confidence_separate(self):
        """village_risk_score and detection_confidence must be distinct fields."""
        from agents.early_warning_agent import EarlyWarningAgent
        agent = EarlyWarningAgent()
        detections = [_make_detection(0.88)]
        with patch("llm.gateway.chat_completion", _llm_mock_alert()):
            alerts = agent.run(detections)
        for alert in alerts:
            assert hasattr(alert, "village_risk_score")
            assert hasattr(alert, "detection_confidence")

    def test_alerts_written_to_pending_store(self):
        from agents.early_warning_agent import EarlyWarningAgent
        agent = EarlyWarningAgent()
        detections = [_make_detection(0.88)]
        with patch("llm.gateway.chat_completion", _llm_mock_alert()):
            agent.run(detections)
        pending = mem_store.get_pending_alerts()
        assert len(pending) > 0

    def test_no_confirmed_detections_returns_empty(self):
        from agents.early_warning_agent import EarlyWarningAgent
        agent = EarlyWarningAgent()
        with patch("llm.gateway.chat_completion", _llm_mock_alert()):
            alerts = agent.run([])
        assert alerts == []

    def test_agent_run_log_written_to_store(self):
        from agents.early_warning_agent import EarlyWarningAgent
        agent = EarlyWarningAgent()
        detections = [_make_detection(0.88)]
        with patch("llm.gateway.chat_completion", _llm_mock_alert()):
            agent.run(detections)
        logs = mem_store.get_agent_run_logs()
        assert any(l.agent_name == "EarlyWarningAgent" for l in logs)
