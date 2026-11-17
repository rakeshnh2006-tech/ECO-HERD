"""
tests/test_data_layer.py — Tests for the synthetic generator and static loader.

Validates that all generated records conform to Pydantic schemas and carry
correct data_source provenance labels.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from schemas import (
    CameraTrapEvent,
    DataSource,
    PatrolLog,
    SensorEvent,
    Sighting,
)


# ---------------------------------------------------------------------------
# Synthetic generator tests
# ---------------------------------------------------------------------------

class TestSyntheticGenerator:
    def setup_method(self):
        from data.synthetic.generator import (
            SYNTHETIC_DISCLAIMER,
            generate_camera_trap_events,
            generate_night_incursion_scenario,
            generate_patrol_logs,
            generate_sensor_events,
            generate_sightings,
        )
        self.generate_sightings = generate_sightings
        self.generate_camera_trap_events = generate_camera_trap_events
        self.generate_sensor_events = generate_sensor_events
        self.generate_patrol_logs = generate_patrol_logs
        self.generate_night_incursion_scenario = generate_night_incursion_scenario
        self.SYNTHETIC_DISCLAIMER = SYNTHETIC_DISCLAIMER

    def test_sightings_count(self):
        result = self.generate_sightings(n=5, seed=1)
        assert len(result) == 5

    def test_sightings_are_sighting_instances(self):
        result = self.generate_sightings(n=3, seed=1)
        for s in result:
            assert isinstance(s, Sighting)

    def test_sightings_provenance(self):
        result = self.generate_sightings(n=5, seed=1)
        for s in result:
            assert s.data_source == DataSource.SYNTHETIC

    def test_sightings_confidence_in_range(self):
        result = self.generate_sightings(n=20, seed=42)
        for s in result:
            assert 0.0 <= s.confidence <= 1.0

    def test_sightings_lat_lon_in_karnataka(self):
        """All synthetic sightings should be within Karnataka bounds."""
        result = self.generate_sightings(n=20, seed=42)
        for s in result:
            assert 11.0 <= s.lat <= 14.0, f"lat out of range: {s.lat}"
            assert 74.5 <= s.lon <= 78.5, f"lon out of range: {s.lon}"

    def test_sightings_deterministic(self):
        """Same seed produces same output."""
        r1 = self.generate_sightings(n=5, seed=99)
        r2 = self.generate_sightings(n=5, seed=99)
        assert [s.lat for s in r1] == [s.lat for s in r2]

    def test_camera_trap_events_schema(self):
        result = self.generate_camera_trap_events(n=5, seed=42)
        for evt in result:
            assert isinstance(evt, CameraTrapEvent)
            assert evt.data_source == DataSource.SYNTHETIC
            assert 0.0 <= evt.confidence <= 1.0
            assert len(evt.image_description) > 0

    def test_sensor_events_schema(self):
        result = self.generate_sensor_events(n=4, seed=42)
        for evt in result:
            assert isinstance(evt, SensorEvent)
            assert evt.data_source == DataSource.SYNTHETIC
            assert evt.sensor_type in ["acoustic", "vibration", "infrared", "seismic"]

    def test_patrol_logs_schema(self):
        result = self.generate_patrol_logs(n=4, seed=42)
        for log in result:
            assert isinstance(log, PatrolLog)
            assert log.data_source == DataSource.SYNTHETIC
            assert log.officer_id.startswith("KFD-RO-")

    def test_disclaimer_is_non_empty(self):
        assert len(self.SYNTHETIC_DISCLAIMER) > 20
        assert "SYNTHETIC" in self.SYNTHETIC_DISCLAIMER

    def test_night_incursion_scenario_structure(self):
        scenario = self.generate_night_incursion_scenario(seed=99)
        assert "scenario_name" in scenario
        assert "sightings" in scenario
        assert "camera_trap_events" in scenario
        assert "sensor_events" in scenario
        assert "patrol_logs" in scenario
        assert "synthetic_disclaimer" in scenario

    def test_night_incursion_sightings_in_kodagu(self):
        scenario = self.generate_night_incursion_scenario(seed=99)
        for s in scenario["sightings"]:
            assert s.district == "Kodagu"
            assert s.data_source == DataSource.SYNTHETIC

    def test_night_incursion_has_ambiguous_camera_event(self):
        """Second camera event should have low confidence (< 0.70)."""
        scenario = self.generate_night_incursion_scenario(seed=99)
        events = scenario["camera_trap_events"]
        assert len(events) == 2
        assert events[1].confidence < 0.70


# ---------------------------------------------------------------------------
# Static loader tests
# ---------------------------------------------------------------------------

class TestStaticLoader:
    def setup_method(self):
        from data.static.loader import (
            load_crop_calendar,
            load_forest_boundaries,
            load_village_geojson,
            load_weather,
        )
        self.load_village_geojson = load_village_geojson
        self.load_forest_boundaries = load_forest_boundaries
        self.load_weather = load_weather
        self.load_crop_calendar = load_crop_calendar

    def test_village_geojson_structure(self):
        result = self.load_village_geojson()
        assert result["type"] == "FeatureCollection"
        assert "features" in result
        assert "data_source" in result
        assert len(result["features"]) > 0

    def test_village_geojson_has_properties(self):
        result = self.load_village_geojson()
        for feature in result["features"]:
            props = feature.get("properties", {})
            assert "name" in props
            assert "district" in props

    def test_village_geojson_district_filter(self):
        result = self.load_village_geojson(district="Kodagu")
        for feature in result["features"]:
            assert feature["properties"]["district"] == "Kodagu"

    def test_forest_boundaries_structure(self):
        result = self.load_forest_boundaries()
        assert result["type"] == "FeatureCollection"
        assert "features" in result
        assert "data_source" in result
        assert len(result["features"]) > 0

    def test_forest_boundaries_have_names(self):
        result = self.load_forest_boundaries()
        for feature in result["features"]:
            props = feature.get("properties", {})
            assert "name" in props

    def test_weather_structure(self):
        result = self.load_weather("Kodagu")
        assert result["district"] == "Kodagu"
        assert "temperature_c" in result
        assert "rainfall_mm" in result
        assert "humidity_pct" in result
        assert "data_source" in result

    def test_weather_temperature_reasonable(self):
        result = self.load_weather("Mysuru")
        assert 10.0 <= result["temperature_c"] <= 45.0

    def test_weather_all_districts(self):
        """Weather should return a valid result for all 6 districts."""
        districts = ["Hassan", "Kodagu", "Chikkamagaluru", "Mysuru", "Chamarajanagar", "Ramanagara"]
        for d in districts:
            result = self.load_weather(d)
            assert result["district"] == d
            assert "data_source" in result

    def test_crop_calendar_structure(self):
        result = self.load_crop_calendar()
        assert "calendar" in result
        assert "data_source" in result
        cal = result["calendar"]
        assert len(cal) == 12
        # All 12 months should have at least one crop
        for month, crops in cal.items():
            assert len(crops) > 0, f"No crops for month {month}"

    def test_crop_calendar_november(self):
        """November should include coffee harvest (peak HEC season)."""
        result = self.load_crop_calendar()
        november_crops = result["calendar"][11]
        assert any("coffee" in c for c in november_crops)
