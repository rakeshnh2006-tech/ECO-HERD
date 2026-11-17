"""
tools/data_fetcher.py — MCP data fetcher tools.

Wraps the synthetic generator and static loader behind a standard Tool interface.
Each function is registered in TOOL_REGISTRY and traces its execution to MemoryStore.
"""

from __future__ import annotations

import time
import logging
from datetime import datetime, timezone

from schemas import CameraTrapEvent, PatrolLog, SensorEvent, Sighting, ToolTraceEntry
from tools import Tool, TOOL_REGISTRY

logger = logging.getLogger(__name__)


def _trace(tool_name: str, input_summary: str, output_summary: str, latency_ms: float, error: str = None):
    """Write a tool execution trace entry to MemoryStore."""
    try:
        from memory.store import store
        store.add_tool_trace(ToolTraceEntry(
            tool_name=tool_name,
            input_summary=input_summary,
            output_summary=output_summary,
            latency_ms=round(latency_ms, 2),
            error=error,
        ))
    except Exception as e:
        logger.warning("Tool trace write failed: %s", e)


# ---------------------------------------------------------------------------
# get_recent_sightings
# ---------------------------------------------------------------------------

def get_recent_sightings(hours_back: int = 24, n: int = 10, seed: int = 42) -> list[Sighting] | dict:
    """
    Retrieve recent elephant sightings (GPS collar / field reports).
    Returns synthetic records tagged with data_source='synthetic'.
    """
    t0 = time.monotonic()
    try:
        from data.synthetic.generator import generate_sightings
        result = generate_sightings(n=n, seed=seed)
        latency = (time.monotonic() - t0) * 1000
        _trace("get_recent_sightings", f"hours_back={hours_back}, n={n}",
               f"{len(result)} sightings returned", latency)
        return result
    except Exception as e:
        latency = (time.monotonic() - t0) * 1000
        _trace("get_recent_sightings", f"hours_back={hours_back}", "", latency, error=str(e))
        logger.error("get_recent_sightings failed: %s", e)
        return {"error": str(e), "data": []}


# ---------------------------------------------------------------------------
# get_camera_trap_events
# ---------------------------------------------------------------------------

def get_camera_trap_events(hours_back: int = 24, n: int = 8, seed: int = 42) -> list[CameraTrapEvent] | dict:
    """
    Retrieve recent camera trap events.
    Returns synthetic records tagged with data_source='synthetic'.
    """
    t0 = time.monotonic()
    try:
        from data.synthetic.generator import generate_camera_trap_events
        result = generate_camera_trap_events(n=n, seed=seed)
        latency = (time.monotonic() - t0) * 1000
        _trace("get_camera_trap_events", f"hours_back={hours_back}, n={n}",
               f"{len(result)} events returned", latency)
        return result
    except Exception as e:
        latency = (time.monotonic() - t0) * 1000
        _trace("get_camera_trap_events", f"hours_back={hours_back}", "", latency, error=str(e))
        logger.error("get_camera_trap_events failed: %s", e)
        return {"error": str(e), "data": []}


# ---------------------------------------------------------------------------
# get_sensor_events
# ---------------------------------------------------------------------------

def get_sensor_events(hours_back: int = 24, n: int = 5, seed: int = 42) -> list[SensorEvent] | dict:
    """Retrieve recent acoustic/vibration sensor events."""
    t0 = time.monotonic()
    try:
        from data.synthetic.generator import generate_sensor_events
        result = generate_sensor_events(n=n, seed=seed)
        latency = (time.monotonic() - t0) * 1000
        _trace("get_sensor_events", f"hours_back={hours_back}, n={n}",
               f"{len(result)} events returned", latency)
        return result
    except Exception as e:
        latency = (time.monotonic() - t0) * 1000
        _trace("get_sensor_events", f"hours_back={hours_back}", "", latency, error=str(e))
        return {"error": str(e), "data": []}


# ---------------------------------------------------------------------------
# get_patrol_logs
# ---------------------------------------------------------------------------

def get_patrol_logs(hours_back: int = 24, n: int = 6, seed: int = 42) -> list[PatrolLog] | dict:
    """Retrieve recent ranger patrol log entries."""
    t0 = time.monotonic()
    try:
        from data.synthetic.generator import generate_patrol_logs
        result = generate_patrol_logs(n=n, seed=seed)
        latency = (time.monotonic() - t0) * 1000
        _trace("get_patrol_logs", f"hours_back={hours_back}, n={n}",
               f"{len(result)} logs returned", latency)
        return result
    except Exception as e:
        latency = (time.monotonic() - t0) * 1000
        _trace("get_patrol_logs", f"hours_back={hours_back}", "", latency, error=str(e))
        return {"error": str(e), "data": []}


# ---------------------------------------------------------------------------
# get_weather
# ---------------------------------------------------------------------------

def get_weather(district: str = "Kodagu") -> dict:
    """Retrieve current weather data for a Karnataka district."""
    t0 = time.monotonic()
    try:
        from data.static.loader import load_weather
        result = load_weather(district)
        latency = (time.monotonic() - t0) * 1000
        _trace("get_weather", f"district={district}",
               f"temp={result.get('temperature_c')}°C rain={result.get('rainfall_mm')}mm "
               f"source={result.get('data_source')}", latency)
        return result
    except Exception as e:
        latency = (time.monotonic() - t0) * 1000
        _trace("get_weather", f"district={district}", "", latency, error=str(e))
        return {"error": str(e), "district": district}


# ---------------------------------------------------------------------------
# get_village_data
# ---------------------------------------------------------------------------

def get_village_data(district: str = None) -> dict:
    """Retrieve village/settlement GeoJSON for Karnataka forest-edge districts."""
    t0 = time.monotonic()
    try:
        from data.static.loader import load_village_geojson
        result = load_village_geojson(district)
        n_features = len(result.get("features", []))
        latency = (time.monotonic() - t0) * 1000
        _trace("get_village_data", f"district={district}",
               f"{n_features} villages, source={result.get('data_source')}", latency)
        return result
    except Exception as e:
        latency = (time.monotonic() - t0) * 1000
        _trace("get_village_data", f"district={district}", "", latency, error=str(e))
        return {"error": str(e), "type": "FeatureCollection", "features": []}


# ---------------------------------------------------------------------------
# get_crop_calendar
# ---------------------------------------------------------------------------

def get_crop_calendar() -> dict:
    """Retrieve crop calendar for current month."""
    t0 = time.monotonic()
    try:
        from data.static.loader import load_crop_calendar
        result = load_crop_calendar()
        month = datetime.now(timezone.utc).month
        current_crops = result["calendar"].get(month, [])
        latency = (time.monotonic() - t0) * 1000
        _trace("get_crop_calendar", f"month={month}",
               f"at-risk crops: {', '.join(current_crops)}", latency)
        return {"current_month": month, "at_risk_crops": current_crops,
                "full_calendar": result["calendar"], "data_source": result["data_source"]}
    except Exception as e:
        latency = (time.monotonic() - t0) * 1000
        _trace("get_crop_calendar", "", "", latency, error=str(e))
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Register all tools
# ---------------------------------------------------------------------------

TOOL_REGISTRY.update({
    "get_recent_sightings": Tool(
        name="get_recent_sightings",
        description="Retrieve recent elephant sightings from GPS collars and field reports.",
        input_schema={"hours_back": "int", "n": "int", "seed": "int"},
        output_schema={"type": "list[Sighting]"},
        fn=get_recent_sightings,
    ),
    "get_camera_trap_events": Tool(
        name="get_camera_trap_events",
        description="Retrieve recent camera trap trigger events with image descriptions.",
        input_schema={"hours_back": "int", "n": "int", "seed": "int"},
        output_schema={"type": "list[CameraTrapEvent]"},
        fn=get_camera_trap_events,
    ),
    "get_sensor_events": Tool(
        name="get_sensor_events",
        description="Retrieve recent acoustic and vibration sensor trigger events.",
        input_schema={"hours_back": "int", "n": "int"},
        output_schema={"type": "list[SensorEvent]"},
        fn=get_sensor_events,
    ),
    "get_patrol_logs": Tool(
        name="get_patrol_logs",
        description="Retrieve recent ranger patrol log entries.",
        input_schema={"hours_back": "int", "n": "int"},
        output_schema={"type": "list[PatrolLog]"},
        fn=get_patrol_logs,
    ),
    "get_weather": Tool(
        name="get_weather",
        description="Get current weather (temperature, rainfall, humidity) for a Karnataka district.",
        input_schema={"district": "str"},
        output_schema={"type": "dict", "fields": ["district", "temperature_c", "rainfall_mm", "humidity_pct"]},
        fn=get_weather,
    ),
    "get_village_data": Tool(
        name="get_village_data",
        description="Get village/settlement GeoJSON for Karnataka districts.",
        input_schema={"district": "str (optional)"},
        output_schema={"type": "GeoJSON FeatureCollection"},
        fn=get_village_data,
    ),
    "get_crop_calendar": Tool(
        name="get_crop_calendar",
        description="Get current month's at-risk crops in Karnataka forest-edge districts.",
        input_schema={},
        output_schema={"type": "dict", "fields": ["current_month", "at_risk_crops"]},
        fn=get_crop_calendar,
    ),
})
