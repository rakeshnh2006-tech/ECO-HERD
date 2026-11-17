"""
tests/test_tools.py — Tests for MCP tool wrappers.

Validates map_tools spatial calculations, risk zone explainability,
alert formatting, and tool execution tracing.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from memory.store import store as mem_store
from schemas import AlertStatus, DataSource, RiskLevel, RiskZone, Sighting
from datetime import datetime, timezone


def _make_sighting(lat: float, lon: float, confidence: float = 0.9) -> Sighting:
    return Sighting(
        lat=lat, lon=lon,
        timestamp=datetime.now(timezone.utc),
        confidence=confidence,
        district="Kodagu",
        data_source=DataSource.SYNTHETIC,
    )


# ---------------------------------------------------------------------------
# map_tools tests
# ---------------------------------------------------------------------------

class TestMapTools:
    def setup_method(self):
        mem_store.reset()
        from tools.map_tools import nearest_village, in_elephant_corridor, compute_risk_zones
        self.nearest_village = nearest_village
        self.in_elephant_corridor = in_elephant_corridor
        self.compute_risk_zones = compute_risk_zones

    def test_nearest_village_returns_dict(self):
        result = self.nearest_village(12.42, 76.52)
        assert isinstance(result, dict)
        assert "village_name" in result
        assert "distance_km" in result
        assert result["distance_km"] >= 0

    def test_nearest_village_known_location(self):
        """Kushalnagar is at [76.52, 12.42] — should be very close."""
        result = self.nearest_village(12.42, 76.52)
        assert result["distance_km"] < 1.0

    def test_nearest_village_traces_to_store(self):
        self.nearest_village(12.00, 76.55)
        trace = mem_store.get_tool_trace_log(last_n=5)
        tool_names = [t.tool_name for t in trace]
        assert "nearest_village" in tool_names

    def test_in_corridor_true_for_kodagu(self):
        """Point inside Kodagu Forest Zone polygon should return True."""
        # Kodagu Forest Zone: lat 11.9-12.6, lon 75.6-76.3
        result = self.in_elephant_corridor(12.3, 76.0)
        assert result is True

    def test_in_corridor_false_outside(self):
        """Point well outside any corridor should return False."""
        result = self.in_elephant_corridor(14.0, 78.0)
        assert result is False

    def test_compute_risk_zones_returns_list(self):
        sightings = [_make_sighting(12.42, 76.52), _make_sighting(12.30, 75.90)]
        result = self.compute_risk_zones(sightings)
        assert isinstance(result, list)

    def test_compute_risk_zones_sorted_by_score(self):
        """Risk zones should be sorted by village_risk_score descending."""
        sightings = [_make_sighting(12.42, 76.52, 0.9)] * 5
        result = self.compute_risk_zones(sightings)
        if len(result) >= 2:
            scores = [z.village_risk_score for z in result]
            assert scores == sorted(scores, reverse=True)

    def test_compute_risk_zones_have_contributing_factors(self):
        """Every returned RiskZone must have at least one contributing factor."""
        sightings = [_make_sighting(12.42, 76.52, 0.9)] * 3
        result = self.compute_risk_zones(sightings)
        for zone in result:
            assert len(zone.contributing_factors) > 0, f"No factors for {zone.village}"

    def test_compute_risk_zones_risk_level_matches_score(self):
        """RiskLevel must match village_risk_score threshold."""
        sightings = [_make_sighting(12.42, 76.52)] * 10  # lots of sightings → HIGH
        result = self.compute_risk_zones(sightings)
        for zone in result:
            if zone.village_risk_score >= 0.7:
                assert zone.risk_level == RiskLevel.HIGH
            elif zone.village_risk_score >= 0.4:
                assert zone.risk_level == RiskLevel.MEDIUM

    def test_compute_risk_zones_weather_boosts_score(self):
        """High rainfall should increase risk score vs no rainfall."""
        sightings = [_make_sighting(12.42, 76.52, 0.8)]
        result_no_rain = self.compute_risk_zones(sightings, weather={"rainfall_mm": 0.0})
        result_rain = self.compute_risk_zones(sightings, weather={"rainfall_mm": 10.0})
        # At least one village should have a higher score with rain
        if result_no_rain and result_rain:
            max_no_rain = max(z.village_risk_score for z in result_no_rain)
            max_rain = max(z.village_risk_score for z in result_rain)
            assert max_rain >= max_no_rain

    def test_compute_risk_zones_no_sightings_returns_empty(self):
        result = self.compute_risk_zones([])
        assert result == []

    def test_compute_risk_zones_traces_to_store(self):
        sightings = [_make_sighting(12.42, 76.52)]
        self.compute_risk_zones(sightings)
        trace = mem_store.get_tool_trace_log(last_n=10)
        tool_names = [t.tool_name for t in trace]
        assert "compute_risk_zones" in tool_names


# ---------------------------------------------------------------------------
# alert_tools tests
# ---------------------------------------------------------------------------

class TestAlertTools:
    def setup_method(self):
        mem_store.reset()
        from tools.alert_tools import format_alert, dispatch_alert
        self.format_alert = format_alert
        self.dispatch_alert = dispatch_alert

    def _make_risk_zone(self, risk_level: RiskLevel = RiskLevel.HIGH, score: float = 0.85) -> RiskZone:
        return RiskZone(
            village="Kushalnagar",
            district="Kodagu",
            lat=12.42,
            lon=76.52,
            risk_level=risk_level,
            village_risk_score=score,
            reason="Test risk zone",
            contributing_factors=["3 sightings within 5 km", "Corridor crossing detected"],
        )

    def test_format_alert_returns_alert(self):
        from schemas import Alert
        rz = self._make_risk_zone()
        alert = self.format_alert("Kushalnagar", "Kodagu", rz, distance_km=3.5, detection_confidence=0.88)
        assert isinstance(alert, Alert)

    def test_format_alert_pending_approval_status(self):
        """Alerts must NEVER be created with DISPATCHED status."""
        rz = self._make_risk_zone()
        alert = self.format_alert("Kushalnagar", "Kodagu", rz)
        assert alert.status == AlertStatus.PENDING_APPROVAL

    def test_format_alert_separate_confidence_fields(self):
        """detection_confidence and village_risk_score must be separate fields."""
        rz = self._make_risk_zone(score=0.72)
        alert = self.format_alert("Kushalnagar", "Kodagu", rz,
                                   detection_confidence=0.91, distance_km=2.0)
        assert alert.village_risk_score == 0.72
        assert alert.detection_confidence == 0.91
        assert alert.village_risk_score != alert.detection_confidence

    def test_format_alert_has_english_message(self):
        rz = self._make_risk_zone()
        alert = self.format_alert("Kushalnagar", "Kodagu", rz)
        assert len(alert.message_en) > 20
        assert "Kushalnagar" in alert.message_en

    def test_format_alert_has_kannada_message(self):
        rz = self._make_risk_zone()
        alert = self.format_alert("Kushalnagar", "Kodagu", rz)
        assert len(alert.message_kn) > 20
        # Kannada characters should be present
        assert any(ord(c) > 0x0C7F for c in alert.message_kn)

    def test_format_alert_has_risk_explanation(self):
        rz = self._make_risk_zone()
        alert = self.format_alert("Kushalnagar", "Kodagu", rz)
        assert len(alert.risk_explanation) > 10

    def test_format_alert_has_recommended_actions(self):
        rz = self._make_risk_zone(RiskLevel.HIGH)
        alert = self.format_alert("Kushalnagar", "Kodagu", rz)
        assert len(alert.recommended_actions) > 0

    def test_dispatch_alert_adds_to_pending_store(self):
        rz = self._make_risk_zone()
        alert = self.format_alert("Kushalnagar", "Kodagu", rz)
        # dispatch_alert also adds to store; test via store.get_pending_alerts
        mem_store.reset()
        result = self.dispatch_alert(alert)
        assert result["status"] == "PENDING_APPROVAL"
        # Alert should be in pending queue
        pending = mem_store.get_pending_alerts()
        assert any(a.alert_id == alert.alert_id for a in pending)

    def test_dispatch_alert_traces_to_store(self):
        rz = self._make_risk_zone()
        alert = self.format_alert("Kushalnagar", "Kodagu", rz)
        mem_store.reset()
        self.dispatch_alert(alert)
        trace = mem_store.get_tool_trace_log(last_n=5)
        tool_names = [t.tool_name for t in trace]
        assert "dispatch_alert" in tool_names

    def test_medium_risk_has_different_messages(self):
        rz_high = self._make_risk_zone(RiskLevel.HIGH, 0.85)
        rz_med = self._make_risk_zone(RiskLevel.MEDIUM, 0.55)
        alert_high = self.format_alert("TestVillage", "Kodagu", rz_high)
        alert_med = self.format_alert("TestVillage", "Kodagu", rz_med)
        assert alert_high.message_en != alert_med.message_en


# ---------------------------------------------------------------------------
# data_fetcher tests
# ---------------------------------------------------------------------------

class TestDataFetcher:
    def setup_method(self):
        mem_store.reset()
        from tools.data_fetcher import (
            get_recent_sightings, get_camera_trap_events,
            get_weather, get_village_data, get_crop_calendar
        )
        self.get_sightings = get_recent_sightings
        self.get_camera = get_camera_trap_events
        self.get_weather = get_weather
        self.get_village = get_village_data
        self.get_crop = get_crop_calendar

    def test_get_sightings_returns_list(self):
        result = self.get_sightings(n=5, seed=42)
        assert isinstance(result, list)
        assert len(result) == 5

    def test_get_sightings_traces_to_store(self):
        self.get_sightings(n=3, seed=42)
        trace = mem_store.get_tool_trace_log(last_n=5)
        assert any(t.tool_name == "get_recent_sightings" for t in trace)

    def test_get_camera_events_returns_list(self):
        result = self.get_camera(n=4, seed=42)
        assert isinstance(result, list)
        assert len(result) == 4

    def test_get_weather_returns_dict(self):
        result = self.get_weather("Kodagu")
        assert isinstance(result, dict)
        assert result["district"] == "Kodagu"
        assert "data_source" in result

    def test_get_village_returns_geojson(self):
        result = self.get_village()
        assert result["type"] == "FeatureCollection"
        assert len(result["features"]) > 0

    def test_get_crop_returns_current_month(self):
        result = self.get_crop()
        assert "current_month" in result
        assert "at_risk_crops" in result
        assert isinstance(result["at_risk_crops"], list)
