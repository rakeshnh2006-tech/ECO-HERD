"""
agents/wildlife_data_agent.py — Agent 1: Wildlife Data Analysis (IBM Granite 4).

ReAct loop:
  Thought → Tool Call → Observation → ... → Final Answer (WildlifeReport)

Uses IBM Granite 4 (ibm/granite-4-h-small) via the LLM gateway.
Calls: get_recent_sightings, get_camera_trap_events, get_sensor_events,
       get_patrol_logs, get_weather, get_village_data, get_crop_calendar
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

import config
from schemas import (
    CameraTrapEvent,
    DataSource,
    Sighting,
    WildlifeReport,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ReAct system prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a wildlife data analysis API for the Karnataka Forest Department's
Human-Elephant Conflict (HEC) Early Warning System.

You receive a data summary and must return ONLY a valid JSON object — no prose, no markdown fences, no preamble, no explanation.

The JSON must match this schema:
{{
  "pattern_summary": "<2-3 sentence analysis of elephant movement patterns and risk>",
  "risk_districts": ["Kodagu", "Mysuru"],
  "confidence_scores": {{"Kodagu": 0.85, "Mysuru": 0.70}},
  "data_sources": ["synthetic"],
  "synthetic_data_present": true
}}

Rules:
- Output ONLY the JSON object, nothing else.
- pattern_summary must be an informative 2-3 sentence analysis, NOT a placeholder.
- risk_districts and confidence_scores must reflect the actual data provided.
- synthetic_data_present is always true for this system.
"""

_TOOL_DESCRIPTIONS = """
- get_recent_sightings(hours_back=24, n=10): Returns recent GPS collar / field sightings
- get_camera_trap_events(hours_back=24, n=8): Returns camera trap events with image descriptions
- get_sensor_events(hours_back=24, n=5): Returns acoustic/vibration sensor triggers
- get_patrol_logs(hours_back=24, n=6): Returns ranger patrol log entries
- get_weather(district="Kodagu"): Returns temperature, rainfall, humidity for a district
- get_village_data(district=null): Returns village GeoJSON for Karnataka
- get_crop_calendar(): Returns current month's at-risk crops
"""


class AgentOutputError(Exception):
    pass


class WildlifeDataAgent:
    """Agent 1 — Wildlife Data Analysis using IBM Granite 4."""

    MODEL_ID = config.GRANITE_MODEL_ID

    def run(self, hours_back: int = 24) -> WildlifeReport:
        """
        Run the wildlife data analysis ReAct loop.
        Returns a validated WildlifeReport.
        Falls back to a data-driven report if LLM is unavailable.
        """
        from llm.gateway import chat_completion
        from tools.data_fetcher import (
            get_camera_trap_events,
            get_crop_calendar,
            get_patrol_logs,
            get_recent_sightings,
            get_sensor_events,
            get_village_data,
            get_weather,
        )
        from memory.store import store

        start_time = datetime.now(timezone.utc)
        react_steps: list[dict] = []
        data_sources: set[str] = set()

        # --- Collect raw data via tools ---
        sightings = get_recent_sightings(hours_back=hours_back, n=10)
        camera_events = get_camera_trap_events(hours_back=hours_back, n=8)
        sensor_events = get_sensor_events(hours_back=hours_back, n=5)
        patrol_logs = get_patrol_logs(hours_back=hours_back, n=6)

        # Collect data sources from tool results
        for item in (sightings if isinstance(sightings, list) else []):
            if hasattr(item, "data_source"):
                data_sources.add(item.data_source.value)

        # Get the most active district from sightings
        district_counts: dict[str, int] = {}
        if isinstance(sightings, list):
            for s in sightings:
                d = getattr(s, "district", "")
                if d:
                    district_counts[d] = district_counts.get(d, 0) + 1
        top_district = max(district_counts, key=district_counts.get) if district_counts else "Kodagu"

        weather = get_weather(top_district)
        villages = get_village_data()
        crops = get_crop_calendar()

        if isinstance(weather, dict) and "data_source" in weather:
            data_sources.add(weather.get("data_source", "unknown"))
        if isinstance(villages, dict) and "data_source" in villages:
            data_sources.add(villages.get("data_source", "unknown"))
        if isinstance(crops, dict) and "data_source" in crops:
            data_sources.add(crops.get("data_source", "unknown"))

        # --- Build context for LLM ---
        n_sightings = len(sightings) if isinstance(sightings, list) else 0
        n_camera = len(camera_events) if isinstance(camera_events, list) else 0
        n_sensors = len(sensor_events) if isinstance(sensor_events, list) else 0
        n_patrol = len(patrol_logs) if isinstance(patrol_logs, list) else 0

        # Summarise camera descriptions for the LLM
        cam_summary = ""
        if isinstance(camera_events, list):
            descriptions = [getattr(e, "image_description", "") for e in camera_events[:4]]
            cam_summary = "; ".join(d[:80] for d in descriptions if d)

        at_risk_crops = crops.get("at_risk_crops", []) if isinstance(crops, dict) else []

        # Build a tightly structured prompt so Granite outputs valid JSON directly
        _ds_json = json.dumps(sorted(data_sources))
        _top = sorted(district_counts.items(), key=lambda x: -x[1])[:4]
        _conf_example = ", ".join(
            f'"{d}": {min(0.95, 0.5 + c * 0.05):.2f}' for d, c in _top
        )
        _top3_districts = [d for d, _ in _top[:3]]
        user_message = (
            f"Elephant activity data for Karnataka ({hours_back}h window):\n"
            f"Sightings: {n_sightings} | Top districts: "
            + ", ".join(f"{d} ({c})" for d, c in _top[:3]) + "\n"
            f"Camera events: {n_camera} | Sensors: {n_sensors} | Patrols: {n_patrol}\n"
            f"Weather ({top_district}): {weather.get('temperature_c','N/A')}°C, "
            f"rain {weather.get('rainfall_mm','N/A')}mm\n"
            f"At-risk crops: {', '.join(at_risk_crops[:3])}\n"
            f"Camera descriptions: {cam_summary[:150]}\n\n"
            "Write a JSON object with these exact keys and types:\n"
            "- pattern_summary: string (2-3 sentences about movement patterns and risk)\n"
            f"- risk_districts: {json.dumps(_top3_districts)}\n"
            f"- confidence_scores: {{{_conf_example}}}\n"
            f"- data_sources: {_ds_json}\n"
            "- synthetic_data_present: true\n\n"
            "Only output the JSON. Start with { and end with }."
        )

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        react_steps.append({"step": "data_collection", "sightings": n_sightings,
                             "camera_events": n_camera, "top_district": top_district})

        # --- LLM call ---
        llm_response = chat_completion(self.MODEL_ID, messages, temperature=0.2)
        react_steps.append({"step": "llm_analysis", "route": llm_response.route_used,
                             "is_fallback": llm_response.is_fallback,
                             "tokens_in": llm_response.tokens_in,
                             "tokens_out": llm_response.tokens_out})

        # --- Parse LLM output ---
        llm_json = _extract_json_from_response(llm_response.content)

        # --- Build WildlifeReport ---
        pattern_summary = llm_json.get("pattern_summary", _fallback_summary(district_counts, n_sightings))
        risk_districts = llm_json.get("risk_districts", list(district_counts.keys())[:3])
        confidence_scores = llm_json.get("confidence_scores", {d: 0.7 for d in risk_districts})

        # Clamp confidence scores
        confidence_scores = {k: max(0.0, min(1.0, float(v))) for k, v in confidence_scores.items()}

        synthetic_present = any("synthetic" in ds for ds in data_sources)

        report = WildlifeReport(
            timestamp=start_time,
            active_sightings=sightings if isinstance(sightings, list) else [],
            camera_trap_events=camera_events if isinstance(camera_events, list) else [],
            pattern_summary=pattern_summary,
            risk_districts=risk_districts[:6],
            confidence_scores=confidence_scores,
            data_sources=list(data_sources),
            synthetic_data_present=synthetic_present,
            raw_llm_response=llm_response.content[:500],
        )

        # --- Write to MemoryStore ---
        from schemas import AgentRunLog
        agent_log = AgentRunLog(
            agent_name="WildlifeDataAgent",
            model_id=self.MODEL_ID,
            start_time=start_time,
            end_time=datetime.now(timezone.utc),
            steps=react_steps,
            tokens_in=llm_response.tokens_in,
            tokens_out=llm_response.tokens_out,
            cost_usd=llm_response.cost_usd,
        )
        store.add_agent_run_log(agent_log)

        logger.info(
            "WildlifeDataAgent complete: %d sightings, risk districts: %s, route: %s",
            len(report.active_sightings), report.risk_districts, llm_response.route_used,
        )
        return report


def _extract_json_from_response(text: str) -> dict:
    """Extract the first valid JSON object from LLM response text."""
    # Try direct JSON parse first
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Look for JSON block in markdown
    for pattern in [r"```json\s*([\s\S]+?)\s*```", r"```\s*([\s\S]+?)\s*```"]:
        match = re.search(pattern, text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

    # Find first {...} block
    match = re.search(r"\{[\s\S]+\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    logger.warning("Could not extract JSON from LLM response — using fallback")
    return {}


def _fallback_summary(district_counts: dict, n_sightings: int) -> str:
    top = sorted(district_counts.items(), key=lambda x: -x[1])[:3]
    districts_str = ", ".join(f"{d} ({c} sightings)" for d, c in top)
    return (
        f"Wildlife data analysis identified {n_sightings} elephant observations across Karnataka "
        f"forest-edge districts. Highest activity recorded in: {districts_str}. "
        f"Recommend elevated monitoring in these areas."
    )
