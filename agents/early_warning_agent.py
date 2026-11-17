"""
agents/early_warning_agent.py — Agent 3: Early Warning & Alert (Groq).

ReAct loop:
  For each at-risk village → compute risk → generate bilingual alert → queue for approval

Uses Groq (llama-3.3-70b-versatile) for fast real-time alert generation.
Calls: compute_risk_zones, format_alert, dispatch_alert
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import config
from schemas import (
    AgentRunLog,
    Alert,
    AlertStatus,
    AuditEventType,
    Detection,
    RiskLevel,
    RiskZone,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are the Early Warning & Alert Agent for the Karnataka Forest Department's
Human-Elephant Conflict Early Warning System.

Your task is to generate clear, actionable safety alerts for villagers and forest staff
in both ENGLISH and KANNADA when elephants are detected near human settlements.

ALERT PRINCIPLES:
- Be clear, concise, and actionable
- Avoid causing unnecessary panic — be factual
- Kannada messages must be simple and direct (avoid complex vocabulary)
- Include specific recommended actions
- State the risk level clearly

Respond with JSON ONLY:
{
  "message_en": "<English safety message>",
  "message_kn": "<Kannada safety message in Kannada script>",
  "recommended_actions": ["action1", "action2", "action3"],
  "risk_explanation": "<1-2 sentence explanation of why this risk score was assigned>"
}
"""


class EarlyWarningAgent:
    """Agent 3 — Early Warning & Alert generation using Groq."""

    MODEL_ID = config.GROQ_MODEL_ID

    def run(self, detections: list[Detection]) -> list[Alert]:
        """
        Generate alerts for all confirmed, non-HITL-pending detections.
        Returns a list of Alert objects with status=PENDING_APPROVAL.
        All alerts require forest officer approval before dispatch.
        """
        from llm.gateway import chat_completion
        from tools.map_tools import compute_risk_zones
        from tools.alert_tools import format_alert, dispatch_alert
        from tools.data_fetcher import get_weather, get_crop_calendar
        from memory.store import store

        start_time = datetime.now(timezone.utc)
        react_steps: list[dict] = []
        alerts: list[Alert] = []

        # Filter out unresolved HITL items
        confirmed = [d for d in detections if not d.requires_hitl_review and d.is_elephant]
        if not confirmed:
            logger.info("EarlyWarningAgent: no confirmed detections to process (all HITL or non-elephant)")
            return []

        logger.info("EarlyWarningAgent processing %d confirmed detections", len(confirmed))

        # Get contextual data
        top_district = confirmed[0].district if confirmed else "Kodagu"
        weather = get_weather(top_district)
        crops_data = get_crop_calendar()
        at_risk_crops = crops_data.get("at_risk_crops", []) if isinstance(crops_data, dict) else []

        # Compute risk zones from confirmed detections
        risk_zones = compute_risk_zones(
            sightings=confirmed,
            weather=weather,
            at_risk_crops=at_risk_crops,
        )

        react_steps.append({
            "step": "risk_computation",
            "confirmed_detections": len(confirmed),
            "risk_zones": len(risk_zones),
            "high_risk": sum(1 for z in risk_zones if z.risk_level == RiskLevel.HIGH),
        })

        if not risk_zones:
            logger.info("EarlyWarningAgent: no at-risk zones computed from detections")
            return []

        # Generate alert for each at-risk village
        for zone in risk_zones[:10]:  # Cap at 10 villages per run
            # Find the nearest confirmed detection to this village
            nearest_detection = _find_nearest_detection(confirmed, zone)
            detection_confidence = nearest_detection.detection_confidence if nearest_detection else 0.7
            distance_km = nearest_detection.distance_km if nearest_detection else 5.0

            # LLM call for bilingual message generation
            alert = self._generate_alert(
                zone=zone,
                detection_confidence=detection_confidence,
                distance_km=distance_km,
                weather=weather,
                at_risk_crops=at_risk_crops,
                chat_completion=chat_completion,
                react_steps=react_steps,
            )

            # Dispatch (queues as PENDING_APPROVAL, writes to store + audit)
            dispatch_alert(alert)
            alerts.append(alert)

        # Write agent run log
        agent_log = AgentRunLog(
            agent_name="EarlyWarningAgent",
            model_id=self.MODEL_ID,
            start_time=start_time,
            end_time=datetime.now(timezone.utc),
            steps=react_steps,
            tokens_in=sum(s.get("tokens_in", 0) for s in react_steps),
            tokens_out=sum(s.get("tokens_out", 0) for s in react_steps),
            cost_usd=sum(s.get("cost_usd", 0.0) for s in react_steps),
        )
        store.add_agent_run_log(agent_log)

        logger.info(
            "EarlyWarningAgent complete: %d alerts queued for approval (%d HIGH)",
            len(alerts),
            sum(1 for a in alerts if a.alert_level == RiskLevel.HIGH),
        )
        return alerts

    def _generate_alert(
        self,
        zone: RiskZone,
        detection_confidence: float,
        distance_km: float,
        weather: dict,
        at_risk_crops: list,
        chat_completion,
        react_steps: list,
    ) -> Alert:
        """Call Groq to generate bilingual alert text, then format into Alert."""
        from tools.alert_tools import format_alert

        user_message = f"""Generate a safety alert for this situation:

Village: {zone.village}
District: {zone.district}
Risk Level: {zone.risk_level.value}
Village Risk Score: {zone.village_risk_score:.2f}
Detection Confidence: {detection_confidence:.2f}
Nearest elephant detection: {distance_km:.1f} km from village
In elephant corridor: {zone.contributing_factors}

Weather context: {weather.get('temperature_c', '?')}°C, rainfall {weather.get('rainfall_mm', '?')} mm
At-risk crops this month: {', '.join(at_risk_crops[:3]) if at_risk_crops else 'None'}

Risk explanation factors:
{chr(10).join(f'- {f}' for f in zone.contributing_factors)}

Generate the alert JSON with English and Kannada messages."""

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        llm_response = chat_completion(self.MODEL_ID, messages, temperature=0.3)

        react_steps.append({
            "step": "alert_generation",
            "village": zone.village,
            "risk_level": zone.risk_level.value,
            "route": llm_response.route_used,
            "is_fallback": llm_response.is_fallback,
            "tokens_in": llm_response.tokens_in,
            "tokens_out": llm_response.tokens_out,
            "cost_usd": llm_response.cost_usd,
            "latency_ms": llm_response.latency_ms,
        })

        # Parse LLM output
        llm_json = _extract_alert_json(llm_response.content)

        # Build alert — use LLM messages if available, else template fallback via format_alert
        alert = format_alert(
            village=zone.village,
            district=zone.district,
            risk_zone=zone,
            distance_km=distance_km,
            detection_confidence=detection_confidence,
            risk_explanation=llm_json.get("risk_explanation", ""),
            custom_message_en=llm_json.get("message_en") or None,
            custom_message_kn=llm_json.get("message_kn") or None,
        )

        # Merge LLM-generated recommended actions if any
        llm_actions = llm_json.get("recommended_actions", [])
        if llm_actions:
            alert.recommended_actions = llm_actions[:6]

        return alert


def _find_nearest_detection(detections: list[Detection], zone: RiskZone) -> Optional[Detection]:
    """Find the confirmed detection nearest to the zone's village."""
    import math

    def _dist(d: Detection) -> float:
        return math.sqrt((d.lat - zone.lat) ** 2 + (d.lon - zone.lon) ** 2)

    if not detections:
        return None
    return min(detections, key=_dist)


def _extract_alert_json(text: str) -> dict:
    """Extract alert JSON from LLM response."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    for pattern in [r"```json\s*([\s\S]+?)\s*```", r"```\s*([\s\S]+?)\s*```"]:
        match = re.search(pattern, text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

    match = re.search(r"\{[\s\S]+\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return {}
