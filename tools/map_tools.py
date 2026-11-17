"""
tools/map_tools.py — Spatial / map MCP tools.

Provides nearest-village lookup, corridor intersection check,
and risk zone computation with explainable contributing factors.
All results are traced to MemoryStore.
"""

from __future__ import annotations

import logging
import math
import time
from typing import Optional

from schemas import Detection, RiskLevel, RiskZone, Sighting, ToolTraceEntry
from tools import Tool, TOOL_REGISTRY

logger = logging.getLogger(__name__)


def _trace(tool_name: str, input_summary: str, output_summary: str, latency_ms: float, error: str = None):
    try:
        from memory.store import store
        store.add_tool_trace(ToolTraceEntry(
            tool_name=tool_name,
            input_summary=input_summary,
            output_summary=output_summary,
            latency_ms=round(latency_ms, 2),
            error=error,
        ))
    except Exception:
        pass


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in km between two lat/lon points."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------------------------------------------------------------------------
# nearest_village
# ---------------------------------------------------------------------------

def nearest_village(lat: float, lon: float, village_geojson: Optional[dict] = None) -> dict:
    """
    Find the nearest village to a given lat/lon.
    Returns {village_name, district, distance_km, lat, lon}.
    Falls back to loading the committed village GeoJSON if none is provided.
    """
    t0 = time.monotonic()
    try:
        if village_geojson is None:
            from data.static.loader import load_village_geojson
            village_geojson = load_village_geojson()

        features = village_geojson.get("features", [])
        if not features:
            return {"village_name": "Unknown", "district": "", "distance_km": 0.0, "lat": lat, "lon": lon}

        best = None
        best_dist = float("inf")
        for feat in features:
            coords = feat.get("geometry", {}).get("coordinates", [])
            if len(coords) >= 2:
                vlon, vlat = coords[0], coords[1]
                d = _haversine_km(lat, lon, vlat, vlon)
                if d < best_dist:
                    best_dist = d
                    best = feat

        props = best.get("properties", {}) if best else {}
        result = {
            "village_name": props.get("name", "Unknown"),
            "district": props.get("district", ""),
            "distance_km": round(best_dist, 2),
            "lat": lat,
            "lon": lon,
        }
        latency = (time.monotonic() - t0) * 1000
        _trace("nearest_village", f"lat={lat}, lon={lon}",
               f"{result['village_name']} ({result['distance_km']} km)", latency)
        return result
    except Exception as e:
        latency = (time.monotonic() - t0) * 1000
        _trace("nearest_village", f"lat={lat}, lon={lon}", "", latency, error=str(e))
        return {"village_name": "Unknown", "district": "", "distance_km": 0.0, "lat": lat, "lon": lon,
                "error": str(e)}


# ---------------------------------------------------------------------------
# in_elephant_corridor
# ---------------------------------------------------------------------------

def in_elephant_corridor(lat: float, lon: float, corridor_geojson: Optional[dict] = None) -> bool:
    """
    Check if a lat/lon falls within a known elephant corridor polygon.
    Uses simple bounding-box + point-in-polygon check.
    """
    t0 = time.monotonic()
    try:
        if corridor_geojson is None:
            from data.static.loader import load_forest_boundaries
            corridor_geojson = load_forest_boundaries()

        features = corridor_geojson.get("features", [])
        for feat in features:
            geom = feat.get("geometry", {})
            if geom.get("type") == "Polygon":
                coords = geom.get("coordinates", [[]])[0]
                if _point_in_polygon(lat, lon, coords):
                    latency = (time.monotonic() - t0) * 1000
                    name = feat.get("properties", {}).get("name", "corridor")
                    _trace("in_elephant_corridor", f"lat={lat}, lon={lon}",
                           f"True — inside {name}", latency)
                    return True

        latency = (time.monotonic() - t0) * 1000
        _trace("in_elephant_corridor", f"lat={lat}, lon={lon}", "False", latency)
        return False
    except Exception as e:
        latency = (time.monotonic() - t0) * 1000
        _trace("in_elephant_corridor", f"lat={lat}, lon={lon}", "False (error)", latency, error=str(e))
        return False


def _point_in_polygon(lat: float, lon: float, polygon_coords: list) -> bool:
    """
    Ray-casting point-in-polygon test.
    polygon_coords: list of [lon, lat] pairs (GeoJSON order).
    """
    inside = False
    n = len(polygon_coords)
    j = n - 1
    for i in range(n):
        xi, yi = polygon_coords[i][0], polygon_coords[i][1]  # lon, lat
        xj, yj = polygon_coords[j][0], polygon_coords[j][1]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


# ---------------------------------------------------------------------------
# compute_risk_zones
# ---------------------------------------------------------------------------

def compute_risk_zones(
    sightings: list,
    village_geojson: Optional[dict] = None,
    corridor_geojson: Optional[dict] = None,
    weather: Optional[dict] = None,
    at_risk_crops: Optional[list] = None,
) -> list[RiskZone]:
    """
    Compute risk zones for each village given recent sightings.

    Risk score formula (0.0 – 1.0):
      base = number of sightings within 10 km / 5 (capped at 1.0)
      + 0.15 if any sighting is in a corridor
      + 0.10 if distance < 3 km for the closest sighting
      + 0.10 if rainfall > 5 mm (elephants move more)
      + 0.05 if at-risk crops are present (harvest season)
      capped at 1.0

    Returns a list of RiskZone with contributing_factors for explainability.
    """
    t0 = time.monotonic()
    try:
        if village_geojson is None:
            from data.static.loader import load_village_geojson
            village_geojson = load_village_geojson()

        if corridor_geojson is None:
            from data.static.loader import load_forest_boundaries
            corridor_geojson = load_forest_boundaries()

        # Normalise sightings — accept Sighting objects or plain dicts
        sight_points: list[tuple[float, float, float]] = []
        for s in sightings:
            if hasattr(s, "lat"):
                sight_points.append((s.lat, s.lon, getattr(s, "confidence", 1.0)))
            elif isinstance(s, dict) and "lat" in s:
                sight_points.append((s["lat"], s["lon"], s.get("confidence", 1.0)))

        features = village_geojson.get("features", [])
        risk_zones: list[RiskZone] = []

        for feat in features:
            coords = feat.get("geometry", {}).get("coordinates", [])
            if len(coords) < 2:
                continue
            vlon, vlat = coords[0], coords[1]
            props = feat.get("properties", {})
            village_name = props.get("name", "Unknown")
            district = props.get("district", "")

            # Compute distances to all sightings
            distances = [_haversine_km(vlat, vlon, slat, slon)
                         for slat, slon, _ in sight_points]
            nearby = [d for d in distances if d <= 10.0]
            closest = min(distances) if distances else 999.0

            contributing_factors: list[str] = []
            score = 0.0

            # Factor 1: sighting density
            density_score = min(len(nearby) / 5.0, 1.0)
            if density_score > 0:
                score += density_score * 0.6
                contributing_factors.append(
                    f"{len(nearby)} sighting(s) within 10 km (density score: {density_score:.2f})"
                )

            # Factor 2: corridor proximity
            any_in_corridor = any(
                in_elephant_corridor(slat, slon, corridor_geojson)
                for slat, slon, _ in sight_points
                if _haversine_km(vlat, vlon, slat, slon) <= 15.0
            )
            if any_in_corridor:
                score += 0.15
                contributing_factors.append("Sighting detected within known elephant corridor")

            # Factor 3: very close sighting
            if closest <= 3.0:
                score += 0.10
                contributing_factors.append(f"Nearest sighting is {closest:.1f} km from village")

            # Factor 4: rainfall (elephants move more in wet conditions)
            if weather and isinstance(weather, dict):
                rainfall = weather.get("rainfall_mm", 0.0)
                if rainfall > 5.0:
                    score += 0.10
                    contributing_factors.append(f"High rainfall ({rainfall} mm) increases movement")

            # Factor 5: harvest season
            if at_risk_crops:
                score += 0.05
                contributing_factors.append(
                    f"Harvest season crops present: {', '.join(at_risk_crops[:3])}"
                )

            score = min(round(score, 3), 1.0)

            # Map score to risk level
            if score >= 0.7:
                risk_level = RiskLevel.HIGH
            elif score >= 0.4:
                risk_level = RiskLevel.MEDIUM
            elif score >= 0.1:
                risk_level = RiskLevel.LOW
            else:
                risk_level = RiskLevel.SAFE

            if risk_level in (RiskLevel.HIGH, RiskLevel.MEDIUM, RiskLevel.LOW):
                reason = f"{risk_level.value} risk: score {score:.2f} based on {len(contributing_factors)} factor(s)"
                risk_zones.append(RiskZone(
                    village=village_name,
                    district=district,
                    lat=vlat,
                    lon=vlon,
                    risk_level=risk_level,
                    village_risk_score=score,
                    reason=reason,
                    contributing_factors=contributing_factors,
                ))

        # Sort by risk score descending
        risk_zones.sort(key=lambda z: z.village_risk_score, reverse=True)

        latency = (time.monotonic() - t0) * 1000
        high_count = sum(1 for z in risk_zones if z.risk_level == RiskLevel.HIGH)
        _trace("compute_risk_zones",
               f"{len(sightings)} sightings, {len(features)} villages",
               f"{len(risk_zones)} at-risk zones ({high_count} HIGH)", latency)
        return risk_zones

    except Exception as e:
        latency = (time.monotonic() - t0) * 1000
        _trace("compute_risk_zones", f"{len(sightings)} sightings", "", latency, error=str(e))
        logger.error("compute_risk_zones failed: %s", e)
        return []


# ---------------------------------------------------------------------------
# Register tools
# ---------------------------------------------------------------------------

TOOL_REGISTRY.update({
    "nearest_village": Tool(
        name="nearest_village",
        description="Find the nearest village/settlement to a lat/lon point.",
        input_schema={"lat": "float", "lon": "float"},
        output_schema={"type": "dict", "fields": ["village_name", "district", "distance_km"]},
        fn=nearest_village,
    ),
    "in_elephant_corridor": Tool(
        name="in_elephant_corridor",
        description="Check if a lat/lon point falls within a known elephant movement corridor.",
        input_schema={"lat": "float", "lon": "float"},
        output_schema={"type": "bool"},
        fn=in_elephant_corridor,
    ),
    "compute_risk_zones": Tool(
        name="compute_risk_zones",
        description="Compute village risk scores from sightings with explainable contributing factors.",
        input_schema={"sightings": "list[Sighting]", "village_geojson": "dict (optional)"},
        output_schema={"type": "list[RiskZone]"},
        fn=compute_risk_zones,
    ),
})
