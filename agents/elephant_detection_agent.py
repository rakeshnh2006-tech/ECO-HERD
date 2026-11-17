"""
agents/elephant_detection_agent.py — Agent 2: Elephant Detection (Google Gemini).

ReAct loop:
  For each camera trap event → classify → enrich with spatial context → HITL flag if low confidence

Uses Google Gemini (via OpenRouter) for image description understanding + Kannada readiness.
Calls: nearest_village, in_elephant_corridor
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
    AuditEventType,
    CameraTrapEvent,
    DataSource,
    Detection,
    HitlQueueItem,
    WildlifeReport,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are the Elephant Detection Agent for the Karnataka Forest Department's
Human-Elephant Conflict Early Warning System.

Your task is to analyse camera trap event descriptions and determine:
1. Whether an elephant is present (is_elephant: true/false)
2. Your confidence level (0.0 - 1.0)
3. Whether this might be a false alarm
4. A brief explanation of your reasoning

You are an expert wildlife biologist with deep knowledge of Asian elephant behaviour.
Be conservative — if the description is ambiguous, lower your confidence score.
A confidence below 0.70 must trigger human review (requires_hitl_review: true).

Respond with a JSON object ONLY:
{
  "is_elephant": true,
  "detection_confidence": 0.92,
  "false_alarm_flag": false,
  "requires_hitl_review": false,
  "explanation": "Clear full-body adult elephant visible with characteristic trunk and ears."
}
"""

_HITL_THRESHOLD = config.HITL_CONFIDENCE_THRESHOLD


class ElephantDetectionAgent:
    """Agent 2 — Elephant Detection using Google Gemini (via OpenRouter)."""

    MODEL_ID = config.GEMINI_MODEL_ID

    def run(self, wildlife_report: WildlifeReport) -> list[Detection]:
        """
        Process each camera trap event from the wildlife report.
        Returns a list of Detection objects.
        Low-confidence detections are added to the HITL queue.
        """
        from llm.gateway import chat_completion
        from tools.map_tools import in_elephant_corridor, nearest_village
        from memory.store import store
        from audit.log import append_audit

        start_time = datetime.now(timezone.utc)
        react_steps: list[dict] = []
        detections: list[Detection] = []

        camera_events = wildlife_report.camera_trap_events
        if not camera_events:
            logger.info("ElephantDetectionAgent: no camera trap events to process")
            return []

        logger.info("ElephantDetectionAgent processing %d camera trap events", len(camera_events))

        for event in camera_events:
            detection = self._process_event(
                event, chat_completion, nearest_village, in_elephant_corridor,
                react_steps, store, append_audit
            )
            detections.append(detection)

        # Write agent run log
        agent_log = AgentRunLog(
            agent_name="ElephantDetectionAgent",
            model_id=self.MODEL_ID,
            start_time=start_time,
            end_time=datetime.now(timezone.utc),
            steps=react_steps,
            tokens_in=sum(s.get("tokens_in", 0) for s in react_steps),
            tokens_out=sum(s.get("tokens_out", 0) for s in react_steps),
            cost_usd=sum(s.get("cost_usd", 0.0) for s in react_steps),
        )
        store.add_agent_run_log(agent_log)

        confirmed = sum(1 for d in detections if d.is_elephant)
        hitl_count = sum(1 for d in detections if d.requires_hitl_review)
        logger.info(
            "ElephantDetectionAgent complete: %d/%d confirmed elephants, %d HITL flagged",
            confirmed, len(detections), hitl_count,
        )
        return detections

    def _process_event(
        self,
        event: CameraTrapEvent,
        chat_completion,
        nearest_village,
        in_elephant_corridor,
        react_steps: list,
        store,
        append_audit,
    ) -> Detection:
        """Process a single camera trap event and return a Detection."""
        # --- Spatial context ---
        village_info = nearest_village(event.lat, event.lon)
        in_corridor = in_elephant_corridor(event.lat, event.lon)

        # --- LLM classification ---
        user_message = f"""Camera trap event analysis:

Location: lat={event.lat}, lon={event.lon}, district={event.district}
Nearest village: {village_info.get('village_name', 'Unknown')} ({village_info.get('distance_km', '?')} km away)
In elephant corridor: {in_corridor}
Timestamp: {event.timestamp}
Camera confidence (sensor): {event.confidence}
Data source: {event.data_source.value}

Image description:
"{event.image_description}"

Analyse this description and respond with the JSON detection result."""

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        llm_response = chat_completion(
            self.MODEL_ID, messages, temperature=0.1,
            image_b64=event.image_b64,
        )

        react_steps.append({
            "event_id": event.id,
            "route": llm_response.route_used,
            "is_fallback": llm_response.is_fallback,
            "tokens_in": llm_response.tokens_in,
            "tokens_out": llm_response.tokens_out,
            "cost_usd": llm_response.cost_usd,
        })

        # --- Parse LLM output ---
        llm_json = _extract_detection_json(llm_response.content, event.confidence)

        # --- Determine HITL requirement ---
        # Low confidence OR fallback response → flag for review
        detection_confidence = float(llm_json.get("detection_confidence", event.confidence))
        detection_confidence = max(0.0, min(1.0, detection_confidence))
        requires_hitl = (
            detection_confidence < _HITL_THRESHOLD
            or llm_response.is_fallback
            or llm_json.get("false_alarm_flag", False)
        )

        detection = Detection(
            event_id=event.id,
            is_elephant=bool(llm_json.get("is_elephant", detection_confidence >= 0.5)),
            detection_confidence=detection_confidence,
            false_alarm_flag=bool(llm_json.get("false_alarm_flag", False)),
            nearest_village=village_info.get("village_name", "Unknown"),
            distance_km=float(village_info.get("distance_km", 0.0)),
            in_corridor=in_corridor,
            requires_hitl_review=requires_hitl,
            explanation=llm_json.get("explanation", llm_response.content[:200]),
            lat=event.lat,
            lon=event.lon,
            district=event.district,
        )

        # --- HITL queue ---
        if requires_hitl:
            hitl_item = HitlQueueItem(detection=detection)
            store.add_hitl_item(hitl_item)
            append_audit(
                AuditEventType.HITL_FLAGGED,
                {
                    "item_id": hitl_item.item_id,
                    "detection_id": detection.detection_id,
                    "event_id": event.id,
                    "detection_confidence": detection_confidence,
                    "threshold": _HITL_THRESHOLD,
                    "reason": "low_confidence" if detection_confidence < _HITL_THRESHOLD else "false_alarm_flag",
                    "explanation": detection.explanation[:200],
                },
            )
            logger.info(
                "HITL flagged: event %s, confidence=%.2f, village=%s",
                event.id[:8], detection_confidence, detection.nearest_village,
            )

        return detection


def _extract_detection_json(text: str, sensor_confidence: float = 0.5) -> dict:
    """Extract detection JSON from LLM response with fallback."""
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

    match = re.search(r"\{[\s\S]+?\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Heuristic fallback from text
    is_elephant = any(w in text.lower() for w in ["elephant", "confirmed", "positive", "detected"])
    false_alarm = any(w in text.lower() for w in ["false alarm", "not an elephant", "no animal", "wind"])
    confidence = 0.3 if false_alarm else (sensor_confidence if is_elephant else 0.4)

    return {
        "is_elephant": is_elephant and not false_alarm,
        "detection_confidence": confidence,
        "false_alarm_flag": false_alarm,
        "requires_hitl_review": confidence < _HITL_THRESHOLD,
        "explanation": text[:300] if text else "No explanation available from LLM.",
    }
