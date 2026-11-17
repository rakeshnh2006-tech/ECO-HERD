"""
data/synthetic/generator.py — Deterministic synthetic data generator.

Produces realistic but entirely synthetic wildlife observation records
for the Karnataka forest-edge districts. Every record carries
data_source: DataSource.SYNTHETIC.

IMPORTANT: This is NOT real sensor data. All records are computer-generated
for demonstration and testing purposes only.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from schemas import (
    CameraTrapEvent,
    DataSource,
    PatrolLog,
    SensorEvent,
    Sighting,
)

# ---------------------------------------------------------------------------
# Disclaimer (must be surfaced in dashboard and agent outputs)
# ---------------------------------------------------------------------------

SYNTHETIC_DISCLAIMER = (
    "⚠️  SYNTHETIC DATA: Real-time feed records (sightings, camera trap events, "
    "sensor triggers, patrol logs) are computer-generated for demonstration purposes. "
    "They do NOT represent actual elephant movements or real field observations."
)

# ---------------------------------------------------------------------------
# Geographic bounding boxes for Karnataka forest-edge districts
# Format: (district_name, lat_min, lat_max, lon_min, lon_max)
# ---------------------------------------------------------------------------

DISTRICT_BOUNDS: list[tuple[str, float, float, float, float]] = [
    ("Hassan",          12.9, 13.4, 75.9, 76.5),
    ("Kodagu",          11.9, 12.6, 75.6, 76.3),
    ("Chikkamagaluru",  12.9, 13.6, 75.5, 76.1),
    ("Mysuru",          11.9, 12.5, 76.1, 77.0),
    ("Chamarajanagar",  11.5, 12.1, 76.5, 77.3),
    ("Ramanagara",      12.5, 13.0, 77.0, 77.5),
]

# Elephant corridors — approximate polyline waypoints within districts
# Used to generate camera trap events close to known movement paths
CORRIDOR_HOTSPOTS: list[tuple[float, float, str]] = [
    (12.42, 76.00, "Kodagu-Hassan corridor"),
    (11.95, 76.80, "Mysuru-Chamarajanagar corridor"),
    (12.30, 75.90, "Kodagu forest edge"),
    (12.10, 76.95, "Nagarhole fringe"),
    (11.75, 77.10, "BRT wildlife sanctuary boundary"),
    (12.55, 76.20, "Chikkamagaluru-Hassan fringe"),
    (12.80, 75.70, "Chikkamagaluru forest edge"),
    (13.10, 76.30, "Hassan interior"),
]

# Common image descriptions for camera trap events
_IMAGE_DESCRIPTIONS = [
    "Large pachyderm silhouette visible at forest edge, estimated adult bull.",
    "Partial flank and trunk visible in undergrowth near water source.",
    "Herd of 4-6 elephants crossing open ground towards farmland.",
    "Single elephant with tusks feeding on sugarcane crop at night.",
    "Motion-triggered image: unclear animal shape, possible elephant.",
    "Two adults with one juvenile crossing dry stream bed.",
    "Broken fence and large footprints; no animal visible in frame.",
    "Clear full-body view of adult female elephant, possibly with calf.",
    "Night image: eye shine and partial outline, species unconfirmed.",
    "Three elephants near paddy field boundary at dusk.",
    "Lone elephant near village water tank, estimated 50m from houses.",
    "Camera trap triggered by wind; no animal visible (possible false alarm).",
    "Adult male elephant with one tusk visible, feeding at forest edge.",
    "Elephant dung and broken branches detected; no animal in frame.",
    "High-confidence sighting: adult female with calf at known corridor crossing.",
]

# Patrol officer IDs
_OFFICER_IDS = [
    "KFD-RO-001", "KFD-RO-002", "KFD-RO-003",
    "KFD-RO-004", "KFD-RO-005", "KFD-RO-006",
]

# Patrol notes
_PATROL_NOTES = [
    "Fresh elephant tracks observed near village boundary.",
    "Crop damage (ragi field) reported by farmer. Evidence consistent with elephant.",
    "Villager reported hearing elephant calls during night. No visual confirmation.",
    "Inspection of solar fence: 3 panels damaged, likely by elephant.",
    "Routine patrol: no signs of elephant activity in this sector.",
    "Footprints leading towards farmland observed near forest boundary.",
    "Water source (tank) shows signs of elephant activity — disturbed banks.",
    "Dung piles (fresh) found 200m from village. Alerted local panchayat.",
    "No incidents to report in this sector.",
    "Camera trap SD card collected. Device functional.",
]


def _rng(seed: Optional[int]) -> random.Random:
    return random.Random(seed)


def _random_time(rng: random.Random, hours_back: int = 24) -> datetime:
    """Return a random timezone-aware UTC datetime within the last `hours_back` hours."""
    offset_seconds = rng.randint(0, hours_back * 3600)
    return datetime.now(timezone.utc) - timedelta(seconds=offset_seconds)


def _random_district(rng: random.Random) -> tuple[str, float, float, float, float]:
    return rng.choice(DISTRICT_BOUNDS)


def _random_lat_lon_in_district(
    rng: random.Random, district: tuple[str, float, float, float, float]
) -> tuple[float, float]:
    _, lat_min, lat_max, lon_min, lon_max = district
    lat = round(rng.uniform(lat_min, lat_max), 5)
    lon = round(rng.uniform(lon_min, lon_max), 5)
    return lat, lon


def _near_corridor(rng: random.Random, jitter: float = 0.05) -> tuple[float, float, str]:
    """Return a lat/lon near a known corridor hotspot."""
    hotspot = rng.choice(CORRIDOR_HOTSPOTS)
    lat = round(hotspot[0] + rng.uniform(-jitter, jitter), 5)
    lon = round(hotspot[1] + rng.uniform(-jitter, jitter), 5)
    return lat, lon, hotspot[2]


# ---------------------------------------------------------------------------
# Generator functions
# ---------------------------------------------------------------------------

def generate_sightings(n: int = 10, seed: Optional[int] = 42) -> list[Sighting]:
    """
    Generate `n` synthetic elephant sighting records across Karnataka
    forest-edge districts.
    """
    rng = _rng(seed)
    sightings: list[Sighting] = []
    for _ in range(n):
        district_tuple = _random_district(rng)
        district_name = district_tuple[0]
        lat, lon = _random_lat_lon_in_district(rng, district_tuple)
        confidence = round(rng.uniform(0.45, 1.0), 2)
        sighting = Sighting(
            lat=lat,
            lon=lon,
            timestamp=_random_time(rng),
            confidence=confidence,
            source="synthetic_gps_collar",
            district=district_name,
            notes=f"Synthetic GPS collar ping — {district_name} sector",
            data_source=DataSource.SYNTHETIC,
        )
        sightings.append(sighting)
    return sightings


def generate_camera_trap_events(
    n: int = 8, seed: Optional[int] = 42
) -> list[CameraTrapEvent]:
    """
    Generate `n` synthetic camera trap events, biased towards corridor hotspots.
    Roughly 15% are ambiguous (potential false alarms).
    """
    rng = _rng(seed)
    events: list[CameraTrapEvent] = []
    for i in range(n):
        # 70% near corridor hotspots, 30% random in district
        if rng.random() < 0.7:
            lat, lon, corridor_name = _near_corridor(rng)
            district = next(
                (d[0] for d in DISTRICT_BOUNDS
                 if d[1] <= lat <= d[2] and d[3] <= lon <= d[4]),
                "Unknown",
            )
        else:
            district_tuple = _random_district(rng)
            district = district_tuple[0]
            lat, lon = _random_lat_lon_in_district(rng, district_tuple)

        # Ambiguous images get lower confidence
        desc = rng.choice(_IMAGE_DESCRIPTIONS)
        is_ambiguous = "unconfirmed" in desc or "false alarm" in desc or "unclear" in desc
        confidence = round(rng.uniform(0.30, 0.65) if is_ambiguous else rng.uniform(0.60, 1.0), 2)

        event = CameraTrapEvent(
            lat=lat,
            lon=lon,
            timestamp=_random_time(rng),
            image_description=desc,
            confidence=confidence,
            district=district,
            data_source=DataSource.SYNTHETIC,
        )
        events.append(event)
    return events


def generate_sensor_events(
    n: int = 5, seed: Optional[int] = 42
) -> list[SensorEvent]:
    """
    Generate `n` synthetic acoustic/vibration sensor trigger events.
    """
    rng = _rng(seed)
    sensor_types = ["acoustic", "vibration", "infrared", "seismic"]
    events: list[SensorEvent] = []
    for _ in range(n):
        lat, lon, _ = _near_corridor(rng, jitter=0.08)
        district = next(
            (d[0] for d in DISTRICT_BOUNDS
             if d[1] <= lat <= d[2] and d[3] <= lon <= d[4]),
            "Unknown",
        )
        event = SensorEvent(
            lat=lat,
            lon=lon,
            timestamp=_random_time(rng),
            sensor_type=rng.choice(sensor_types),
            triggered=rng.random() > 0.15,  # 85% genuine trigger, 15% spurious
            district=district,
            data_source=DataSource.SYNTHETIC,
        )
        events.append(event)
    return events


def generate_patrol_logs(
    n: int = 6, seed: Optional[int] = 42
) -> list[PatrolLog]:
    """
    Generate `n` synthetic ranger patrol log entries.
    """
    rng = _rng(seed)
    logs: list[PatrolLog] = []
    for _ in range(n):
        district_tuple = _random_district(rng)
        district_name = district_tuple[0]
        lat, lon = _random_lat_lon_in_district(rng, district_tuple)
        log = PatrolLog(
            officer_id=rng.choice(_OFFICER_IDS),
            lat=lat,
            lon=lon,
            timestamp=_random_time(rng),
            notes=rng.choice(_PATROL_NOTES),
            district=district_name,
            data_source=DataSource.SYNTHETIC,
        )
        logs.append(log)
    return logs


# ---------------------------------------------------------------------------
# Scenario-specific generator (used by demo/scenario.py)
# ---------------------------------------------------------------------------

def generate_night_incursion_scenario(seed: int = 99) -> dict:
    """
    "Night Incursion — Kodagu, Day 1" demonstration scenario.

    Generates a coherent synthetic dataset representing an elephant herd
    crossing the Kodagu-Mysuru corridor at ~22:00 local time.
    Returns all feed types as a dict.
    """
    rng = _rng(seed)
    base_time = datetime.now(timezone.utc).replace(hour=16, minute=0, second=0, microsecond=0)
    # Kodagu-Mysuru corridor centroid
    corridor_lat, corridor_lon = 12.00, 76.55

    def _corridor_point(offset_lat: float = 0.0, offset_lon: float = 0.0) -> tuple[float, float]:
        return (
            round(corridor_lat + offset_lat + rng.uniform(-0.01, 0.01), 5),
            round(corridor_lon + offset_lon + rng.uniform(-0.01, 0.01), 5),
        )

    # 3 GPS collar pings tracking herd movement
    sightings = []
    for i, (dlat, dlon, minutes_offset) in enumerate([
        (0.0, 0.0, 0),
        (0.03, 0.04, 45),
        (0.07, 0.08, 90),
    ]):
        lat, lon = _corridor_point(dlat, dlon)
        sightings.append(Sighting(
            lat=lat,
            lon=lon,
            timestamp=base_time + timedelta(minutes=minutes_offset),
            confidence=round(rng.uniform(0.80, 0.98), 2),
            source="gps_collar_KA_H3",
            district="Kodagu",
            notes="Collar ping — herd KA-H3 tracked through Kodagu-Mysuru corridor",
            data_source=DataSource.SYNTHETIC,
        ))

    # 2 camera trap events (one clear, one ambiguous)
    camera_events = [
        CameraTrapEvent(
            lat=round(corridor_lat + 0.05, 5),
            lon=round(corridor_lon + 0.05, 5),
            timestamp=base_time + timedelta(minutes=50),
            image_description="Herd of 4-6 elephants crossing open ground towards farmland.",
            confidence=0.92,
            district="Kodagu",
            data_source=DataSource.SYNTHETIC,
        ),
        CameraTrapEvent(
            lat=round(corridor_lat + 0.09, 5),
            lon=round(corridor_lon + 0.09, 5),
            timestamp=base_time + timedelta(minutes=70),
            image_description="Night image: eye shine and partial outline, species unconfirmed.",
            confidence=0.48,
            district="Mysuru",
            data_source=DataSource.SYNTHETIC,
        ),
    ]

    # 1 acoustic sensor trigger
    sensor_events = [
        SensorEvent(
            lat=round(corridor_lat + 0.06, 5),
            lon=round(corridor_lon + 0.07, 5),
            timestamp=base_time + timedelta(minutes=55),
            sensor_type="acoustic",
            triggered=True,
            district="Kodagu",
            data_source=DataSource.SYNTHETIC,
        ),
    ]

    # 1 patrol log
    patrol_logs = [
        PatrolLog(
            officer_id="KFD-RO-003",
            lat=round(corridor_lat + 0.02, 5),
            lon=round(corridor_lon + 0.02, 5),
            timestamp=base_time + timedelta(minutes=20),
            notes="Fresh elephant tracks observed near village boundary.",
            district="Kodagu",
            data_source=DataSource.SYNTHETIC,
        ),
    ]

    return {
        "scenario_name": "Night Incursion — Kodagu, Day 1",
        "sightings": sightings,
        "camera_trap_events": camera_events,
        "sensor_events": sensor_events,
        "patrol_logs": patrol_logs,
        "synthetic_disclaimer": SYNTHETIC_DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# CLI: generate and save sample files
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    from pathlib import Path

    out_dir = Path(__file__).parent

    def _serialize(records):
        return [r.model_dump(mode="json") for r in records]

    files = {
        "sample_sightings.json": generate_sightings(15, seed=42),
        "sample_camera_events.json": generate_camera_trap_events(10, seed=42),
        "sample_sensor_events.json": generate_sensor_events(8, seed=42),
        "sample_patrol_logs.json": generate_patrol_logs(8, seed=42),
    }

    for filename, records in files.items():
        path = out_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_serialize(records), f, indent=2, default=str)
        print(f"Written: {path} ({len(records)} records)")

    # Also save night incursion scenario
    scenario = generate_night_incursion_scenario()
    scenario_out = {
        k: _serialize(v) if isinstance(v, list) else v
        for k, v in scenario.items()
    }
    path = out_dir / "sample_night_incursion.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(scenario_out, f, indent=2, default=str)
    print(f"Written: {path}")
    print(f"\n{SYNTHETIC_DISCLAIMER}")
