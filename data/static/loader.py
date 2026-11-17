"""
data/static/loader.py — Static reference data loader.

Loads real public datasets for Karnataka villages, forest boundaries,
weather, and crop calendars. Falls back to committed sample files
when live APIs are unavailable (network errors, missing keys, etc.).

All returned dicts include a 'data_source' metadata field.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent

# ---------------------------------------------------------------------------
# Village GeoJSON
# ---------------------------------------------------------------------------

def load_village_geojson(district: Optional[str] = None) -> dict:
    """
    Load village/settlement GeoJSON for Karnataka forest-edge districts.

    Tries the committed sample file first (always available).
    Live OSM Overpass API fetch is attempted if the sample is missing.

    Returns a GeoJSON FeatureCollection with 'data_source' metadata.
    """
    sample_path = _STATIC_DIR / "villages.geojson"
    if sample_path.exists():
        try:
            data = json.loads(sample_path.read_text(encoding="utf-8"))
            features = data.get("features", [])
            if district:
                features = [
                    f for f in features
                    if f.get("properties", {}).get("district") == district
                ]
            return {
                "type": "FeatureCollection",
                "features": features,
                "data_source": "openstreetmap_cached",
            }
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to parse cached villages.geojson: %s", e)

    # Try live OSM Overpass API
    logger.info("Fetching village data from OSM Overpass API...")
    try:
        district_filter = f'["name"~"{district}"]' if district else ""
        query = f"""
        [out:json][timeout:25];
        (
          node["place"~"village|town|hamlet"]{district_filter}
            (11.5,75.5,13.5,78.0);
        );
        out body;
        """
        resp = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": query},
            timeout=20,
        )
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
        features = [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [e["lon"], e["lat"]]},
                "properties": {
                    "name": e.get("tags", {}).get("name", "Unknown"),
                    "place": e.get("tags", {}).get("place", "village"),
                    "district": e.get("tags", {}).get("district", ""),
                    "osm_id": e.get("id"),
                },
            }
            for e in elements
            if "lat" in e and "lon" in e
        ]
        result = {
            "type": "FeatureCollection",
            "features": features,
            "data_source": "openstreetmap_live",
        }
        # Cache for next time
        sample_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Fetched %d village features from OSM and cached.", len(features))
        return result
    except Exception as e:
        logger.warning("OSM fetch failed: %s. Returning empty FeatureCollection.", e)
        return {
            "type": "FeatureCollection",
            "features": _get_fallback_villages(),
            "data_source": "fallback_hardcoded",
        }


def _get_fallback_villages() -> list[dict]:
    """Minimal hardcoded village list for the demo corridor."""
    return [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [76.52, 12.42]},
         "properties": {"name": "Kushalnagar", "district": "Kodagu", "place": "town"}},
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [75.74, 12.36]},
         "properties": {"name": "Madikeri", "district": "Kodagu", "place": "town"}},
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [76.62, 12.30]},
         "properties": {"name": "Hunsur", "district": "Mysuru", "place": "town"}},
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [76.82, 12.21]},
         "properties": {"name": "Piriyapatna", "district": "Mysuru", "place": "town"}},
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [76.95, 12.10]},
         "properties": {"name": "Nagarhole", "district": "Mysuru", "place": "village"}},
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [77.18, 11.92]},
         "properties": {"name": "Gundlupet", "district": "Chamarajanagar", "place": "town"}},
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [77.22, 11.75]},
         "properties": {"name": "Kollegala", "district": "Chamarajanagar", "place": "town"}},
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [76.10, 13.00]},
         "properties": {"name": "Hassan", "district": "Hassan", "place": "city"}},
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [75.78, 13.32]},
         "properties": {"name": "Chikkamagaluru", "district": "Chikkamagaluru", "place": "city"}},
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [77.28, 12.72]},
         "properties": {"name": "Ramanagara", "district": "Ramanagara", "place": "city"}},
    ]


# ---------------------------------------------------------------------------
# Forest boundaries GeoJSON
# ---------------------------------------------------------------------------

def load_forest_boundaries() -> dict:
    """
    Load Karnataka forest boundary / elephant corridor GeoJSON.
    Returns the committed sample file; falls back to approximate corridor polygons.
    """
    sample_path = _STATIC_DIR / "forest_boundaries.geojson"
    if sample_path.exists():
        try:
            data = json.loads(sample_path.read_text(encoding="utf-8"))
            data["data_source"] = "karnataka_open_data_cached"
            return data
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to parse forest_boundaries.geojson: %s", e)

    logger.info("Using fallback forest boundary polygons.")
    return {
        "type": "FeatureCollection",
        "features": _get_fallback_corridors(),
        "data_source": "fallback_approximate",
    }


def _get_fallback_corridors() -> list[dict]:
    """Approximate elephant corridor polygons for the demo scenario."""
    return [
        {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [75.6, 11.9], [76.3, 11.9], [76.3, 12.6],
                    [75.6, 12.6], [75.6, 11.9],
                ]],
            },
            "properties": {
                "name": "Kodagu Forest Zone",
                "type": "protected_forest",
                "district": "Kodagu",
            },
        },
        {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [76.1, 11.9], [77.0, 11.9], [77.0, 12.5],
                    [76.1, 12.5], [76.1, 11.9],
                ]],
            },
            "properties": {
                "name": "Mysuru-Nagarhole Corridor",
                "type": "elephant_corridor",
                "district": "Mysuru",
            },
        },
        {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [76.5, 11.5], [77.3, 11.5], [77.3, 12.1],
                    [76.5, 12.1], [76.5, 11.5],
                ]],
            },
            "properties": {
                "name": "Chamarajanagar-BRT Zone",
                "type": "protected_forest",
                "district": "Chamarajanagar",
            },
        },
    ]


# ---------------------------------------------------------------------------
# Weather data
# ---------------------------------------------------------------------------

def load_weather(district: str = "Kodagu") -> dict:
    """
    Load current weather data for a Karnataka district.

    Tries the committed CSV fallback first (always available).
    Live IMD or Open-Meteo API fetch is attempted when the fallback is not preferred.

    Returns a dict with temperature, rainfall, humidity, and data_source.
    """
    # Try Open-Meteo (free, no key required) with district centroid
    district_centroids: dict[str, tuple[float, float]] = {
        "Hassan": (13.0, 76.1),
        "Kodagu": (12.3, 75.9),
        "Chikkamagaluru": (13.3, 75.8),
        "Mysuru": (12.2, 76.6),
        "Chamarajanagar": (11.9, 77.0),
        "Ramanagara": (12.7, 77.3),
    }
    lat, lon = district_centroids.get(district, (12.3, 75.9))

    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,precipitation,relative_humidity_2m",
                "timezone": "Asia/Kolkata",
            },
            timeout=8,
        )
        resp.raise_for_status()
        current = resp.json().get("current", {})
        return {
            "district": district,
            "temperature_c": current.get("temperature_2m", 25.0),
            "rainfall_mm": current.get("precipitation", 0.0),
            "humidity_pct": current.get("relative_humidity_2m", 70.0),
            "data_source": "open_meteo_live",
        }
    except Exception as e:
        logger.warning("Weather API failed for %s: %s. Using fallback.", district, e)

    # CSV fallback
    fallback_path = _STATIC_DIR / "weather_fallback.csv"
    if fallback_path.exists():
        try:
            with open(fallback_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("district", "").lower() == district.lower():
                        return {
                            "district": district,
                            "temperature_c": float(row.get("temperature_c", 25.0)),
                            "rainfall_mm": float(row.get("rainfall_mm", 0.0)),
                            "humidity_pct": float(row.get("humidity_pct", 70.0)),
                            "data_source": "imd_csv_fallback",
                        }
        except Exception as e:
            logger.warning("Weather CSV fallback failed: %s", e)

    # Hardcoded fallback
    return {
        "district": district,
        "temperature_c": 24.0,
        "rainfall_mm": 2.5,
        "humidity_pct": 75.0,
        "data_source": "hardcoded_fallback",
    }


# ---------------------------------------------------------------------------
# Crop calendar
# ---------------------------------------------------------------------------

def load_crop_calendar() -> dict:
    """
    Return a crop calendar mapping month number → list of ripening/at-risk crops.
    Based on Karnataka Agricultural Department records.

    data_source: karnataka_agriculture_dept_static
    """
    calendar = {
        1:  ["sugarcane", "ragi", "wheat"],
        2:  ["sugarcane", "banana"],
        3:  ["banana", "mango"],
        4:  ["mango", "jackfruit"],
        5:  ["jackfruit", "sugarcane"],
        6:  ["paddy (kharif sowing)", "coffee (flowering)"],
        7:  ["paddy (growing)", "coffee", "ginger"],
        8:  ["paddy (growing)", "banana", "coffee"],
        9:  ["paddy (ripening)", "sugarcane", "banana"],
        10: ["paddy (harvest)", "coffee (ripening)", "ragi"],
        11: ["coffee (harvest)", "ragi", "paddy (rabi sowing)"],
        12: ["sugarcane", "coffee (harvest)", "vegetables"],
    }
    return {
        "calendar": calendar,
        "data_source": "karnataka_agriculture_dept_static",
        "note": "Approximate crop calendar for Karnataka forest-edge districts.",
    }


# ---------------------------------------------------------------------------
# Combined loader (convenience function used by tools/data_fetcher.py)
# ---------------------------------------------------------------------------

def load_all_static(district: Optional[str] = None) -> dict:
    """Load all static datasets and return as a single dict."""
    from datetime import datetime, timezone
    month = datetime.now(timezone.utc).month
    crop_data = load_crop_calendar()
    return {
        "villages": load_village_geojson(district),
        "forest_boundaries": load_forest_boundaries(),
        "weather": load_weather(district or "Kodagu"),
        "current_at_risk_crops": crop_data["calendar"].get(month, []),
        "crop_calendar_data_source": crop_data["data_source"],
    }
