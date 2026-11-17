"""
dashboard/map_builder.py — Folium map builder for the HEC Early Warning dashboard.

Builds a Karnataka-centered map with:
- Village markers colour-coded by village_risk_score
- Elephant detection markers with explanation popups
- Risk zone polygon overlays
- Corridor boundaries from forest_boundaries.geojson
"""

from __future__ import annotations

import logging
from typing import Optional

import folium

from schemas import Alert, AlertStatus, Detection, RiskLevel, RiskZone

logger = logging.getLogger(__name__)

# Karnataka center
_KA_CENTER = [12.5, 76.5]
_KA_ZOOM = 7

# Risk level colours
_RISK_COLOURS = {
    RiskLevel.HIGH: "#dc2626",    # red
    RiskLevel.MEDIUM: "#ea580c",  # orange
    RiskLevel.LOW: "#ca8a04",     # amber
    RiskLevel.SAFE: "#16a34a",    # green
}

_RISK_ICONS = {
    RiskLevel.HIGH: "exclamation-sign",
    RiskLevel.MEDIUM: "warning-sign",
    RiskLevel.LOW: "info-sign",
    RiskLevel.SAFE: "ok-sign",
}


def build_map(
    detections: list[Detection],
    alerts: list[Alert],
    village_geojson: Optional[dict] = None,
    risk_zones: Optional[list[RiskZone]] = None,
    corridor_geojson: Optional[dict] = None,
) -> folium.Map:
    """
    Build and return a configured Folium map.

    Parameters
    ----------
    detections   : Detection objects from Agent 2
    alerts       : Alert objects from Agent 3 (all statuses)
    village_geojson : GeoJSON FeatureCollection of villages
    risk_zones   : RiskZone list from compute_risk_zones
    corridor_geojson : GeoJSON FeatureCollection of forest/corridor boundaries
    """
    m = folium.Map(
        location=_KA_CENTER,
        zoom_start=_KA_ZOOM,
        tiles="CartoDB positron",
        control_scale=True,
    )

    # --- Layer groups ---
    corridor_layer = folium.FeatureGroup(name="Forest Corridors", show=True)
    village_layer = folium.FeatureGroup(name="Villages & Risk Zones", show=True)
    detection_layer = folium.FeatureGroup(name="Elephant Detections", show=True)
    alert_layer = folium.FeatureGroup(name="Active Alerts", show=True)

    # 1. Corridor / forest boundary polygons
    if corridor_geojson:
        _add_corridors(corridor_layer, corridor_geojson)
    else:
        try:
            from data.static.loader import load_forest_boundaries
            _add_corridors(corridor_layer, load_forest_boundaries())
        except Exception as e:
            logger.warning("Could not load corridor boundaries: %s", e)

    # 2. Village markers with risk colouring
    if village_geojson:
        risk_map = {z.village: z for z in (risk_zones or [])}
        _add_villages(village_layer, village_geojson, risk_map)
    else:
        try:
            from data.static.loader import load_village_geojson
            risk_map = {z.village: z for z in (risk_zones or [])}
            _add_villages(village_layer, load_village_geojson(), risk_map)
        except Exception as e:
            logger.warning("Could not load village data: %s", e)

    # 3. Elephant detection markers
    _add_detections(detection_layer, detections)

    # 4. Alert markers (dispatched only on map, pending shown in sidebar)
    dispatched = [a for a in alerts if a.status == AlertStatus.DISPATCHED]
    _add_alerts(alert_layer, dispatched)

    # Add layers to map
    corridor_layer.add_to(m)
    village_layer.add_to(m)
    detection_layer.add_to(m)
    alert_layer.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)

    return m


def _add_corridors(layer: folium.FeatureGroup, geojson: dict) -> None:
    """Add corridor and forest zone polygons."""
    for feat in geojson.get("features", []):
        geom = feat.get("geometry", {})
        props = feat.get("properties", {})
        name = props.get("name", "Forest Zone")
        ftype = props.get("type", "")

        colour = "#15803d" if "corridor" in ftype.lower() else "#166534"
        fill_colour = "#bbf7d0" if "corridor" in ftype.lower() else "#dcfce7"

        if geom.get("type") == "Polygon":
            coords = geom.get("coordinates", [[]])[0]
            # GeoJSON is [lon, lat] → Folium wants [lat, lon]
            latlons = [[c[1], c[0]] for c in coords]
            folium.Polygon(
                locations=latlons,
                color=colour,
                fill_color=fill_colour,
                fill_opacity=0.25,
                weight=2,
                tooltip=name,
            ).add_to(layer)
        elif geom.get("type") == "LineString":
            coords = geom.get("coordinates", [])
            latlons = [[c[1], c[0]] for c in coords]
            folium.PolyLine(
                locations=latlons,
                color="#15803d",
                weight=3,
                dash_array="8 4",
                tooltip=f"Corridor: {name}",
            ).add_to(layer)


def _add_villages(
    layer: folium.FeatureGroup,
    village_geojson: dict,
    risk_map: dict[str, RiskZone],
) -> None:
    """Add village markers colour-coded by risk level."""
    for feat in village_geojson.get("features", []):
        coords = feat.get("geometry", {}).get("coordinates", [])
        if len(coords) < 2:
            continue
        lon, lat = coords[0], coords[1]
        props = feat.get("properties", {})
        name = props.get("name", "Unknown")

        zone = risk_map.get(name)
        if zone:
            colour = _RISK_COLOURS[zone.risk_level]
            icon = _RISK_ICONS[zone.risk_level]
            popup_html = (
                f"<b>{name}</b> ({props.get('district', '')})<br>"
                f"<span style='color:{colour}'><b>Risk: {zone.risk_level.value}</b></span><br>"
                f"Risk Score: {zone.village_risk_score:.2f}<br>"
                f"<small>{zone.reason}</small><br>"
                f"<ul>{''.join(f'<li>{f}</li>' for f in zone.contributing_factors)}</ul>"
            )
        else:
            colour = "#6b7280"
            icon = "home"
            popup_html = f"<b>{name}</b> ({props.get('district', '')})<br>No risk data"

        folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"{name} — {zone.risk_level.value if zone else 'SAFE'}",
            icon=folium.Icon(color="white", icon_color=colour, icon=icon, prefix="glyphicon"),
        ).add_to(layer)


def _add_detections(layer: folium.FeatureGroup, detections: list[Detection]) -> None:
    """Add elephant detection markers (🐘 icon)."""
    for det in detections:
        if not det.is_elephant:
            continue
        conf_pct = int(det.detection_confidence * 100)
        status = "⚠️ HITL Review" if det.requires_hitl_review else "✅ Confirmed"
        popup_html = (
            f"<b>🐘 Elephant Detection</b><br>"
            f"Village: {det.nearest_village} ({det.distance_km:.1f} km)<br>"
            f"Confidence: <b>{conf_pct}%</b><br>"
            f"In corridor: {'Yes' if det.in_corridor else 'No'}<br>"
            f"Status: {status}<br>"
            f"<small><i>{det.explanation[:200]}</i></small>"
        )
        colour = "red" if det.requires_hitl_review else "darkblue"
        folium.Marker(
            location=[det.lat, det.lon],
            popup=folium.Popup(popup_html, max_width=320),
            tooltip=f"🐘 {det.nearest_village} — conf {conf_pct}%",
            icon=folium.Icon(color=colour, icon="eye-open", prefix="glyphicon"),
        ).add_to(layer)


def _add_alerts(layer: folium.FeatureGroup, dispatched_alerts: list[Alert]) -> None:
    """Add dispatched alert markers with bilingual popup."""
    # Map village name → approximate location from risk zone
    for alert in dispatched_alerts:
        try:
            from data.static.loader import load_village_geojson
            vg = load_village_geojson()
            feat = next(
                (f for f in vg["features"]
                 if f["properties"].get("name") == alert.village), None
            )
            if feat:
                coords = feat["geometry"]["coordinates"]
                lat, lon = coords[1], coords[0]
            else:
                continue
        except Exception:
            continue

        colour = _RISK_COLOURS.get(alert.alert_level, "#6b7280")
        popup_html = (
            f"<b>🚨 {alert.alert_level.value} ALERT</b><br>"
            f"Village: {alert.village} ({alert.district})<br>"
            f"Risk score: {alert.village_risk_score:.2f} | "
            f"Detection conf: {alert.detection_confidence:.2f}<br>"
            f"<b>EN:</b> {alert.message_en[:150]}<br>"
            f"<b>KN:</b> {alert.message_kn[:100]}<br>"
            f"<small><i>{alert.risk_explanation[:150]}</i></small>"
        )
        folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(popup_html, max_width=360),
            tooltip=f"🚨 {alert.village} — {alert.alert_level.value}",
            icon=folium.Icon(color="red", icon="bell", prefix="glyphicon"),
        ).add_to(layer)
