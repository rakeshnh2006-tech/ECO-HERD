"""
tools/alert_tools.py — Alert formatting and dispatch MCP tools.

Formats bilingual (Kannada + English) alerts and simulates dispatch.
All dispatched alerts are written to MemoryStore with PENDING_APPROVAL status
and an audit log entry. No alert is ever sent without forest officer approval.
"""

from __future__ import annotations

import logging
import time
from typing import Optional
from uuid import uuid4

from schemas import Alert, AlertStatus, AuditEventType, RiskLevel, RiskZone, ToolTraceEntry
from tools import Tool, TOOL_REGISTRY

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bilingual message templates
# ---------------------------------------------------------------------------

_TEMPLATES_EN: dict[RiskLevel, str] = {
    RiskLevel.HIGH: (
        "🔴 HIGH ALERT — {village} ({district}): Elephants detected {distance:.1f} km away. "
        "Do NOT go to fields or forests tonight. Keep children and livestock indoors. "
        "Contact Forest Department helpline: 1800-425-7378."
    ),
    RiskLevel.MEDIUM: (
        "🟠 CAUTION — {village} ({district}): Elephant activity reported {distance:.1f} km away. "
        "Avoid forest edges after dark. Alert your neighbours. "
        "Report sightings to forest department."
    ),
    RiskLevel.LOW: (
        "🟡 ADVISORY — {village} ({district}): Elephant movement noted in the region. "
        "Be alert while working near forest areas. Carry a torch at night."
    ),
}

# Kannada translations (simplified for demonstration)
_TEMPLATES_KN: dict[RiskLevel, str] = {
    RiskLevel.HIGH: (
        "🔴 ಹೆಚ್ಚಿನ ಎಚ್ಚರಿಕೆ — {village} ({district}): {distance:.1f} ಕಿ.ಮೀ ದೂರದಲ್ಲಿ ಆನೆಗಳು ಪತ್ತೆಯಾಗಿವೆ. "
        "ಇಂದು ರಾತ್ರಿ ಹೊಲ ಅಥವಾ ಅರಣ್ಯಕ್ಕೆ ಹೋಗಬೇಡಿ. ಮಕ್ಕಳು ಮತ್ತು ಜಾನುವಾರುಗಳನ್ನು ಒಳಗಿರಿಸಿ. "
        "ಅರಣ್ಯ ಇಲಾಖೆ ಸಹಾಯವಾಣಿ: 1800-425-7378."
    ),
    RiskLevel.MEDIUM: (
        "🟠 ಎಚ್ಚರಿಕೆ — {village} ({district}): {distance:.1f} ಕಿ.ಮೀ ದೂರದಲ್ಲಿ ಆನೆ ಚಟುವಟಿಕೆ ವರದಿಯಾಗಿದೆ. "
        "ರಾತ್ರಿ ಅರಣ್ಯದ ಅಂಚಿಗೆ ಹೋಗಬೇಡಿ. ನೆರೆಯವರಿಗೆ ತಿಳಿಸಿ."
    ),
    RiskLevel.LOW: (
        "🟡 ಸೂಚನೆ — {village} ({district}): ಪ್ರದೇಶದಲ್ಲಿ ಆನೆ ಚಲನೆ ಗಮನಿಸಲಾಗಿದೆ. "
        "ಅರಣ್ಯ ಪ್ರದೇಶದ ಸಮೀಪ ಕೆಲಸ ಮಾಡುವಾಗ ಎಚ್ಚರದಿಂದಿರಿ."
    ),
}

_RECOMMENDED_ACTIONS: dict[RiskLevel, list[str]] = {
    RiskLevel.HIGH: [
        "Stay indoors after dark",
        "Do not go to fields or forest areas tonight",
        "Keep livestock in secured shelters",
        "Light firecrackers or make noise to deter elephants if they approach",
        "Call Forest Department helpline: 1800-425-7378",
        "Report any sightings immediately to the nearest forest range office",
    ],
    RiskLevel.MEDIUM: [
        "Avoid forest edges after dark",
        "Travel in groups if going to fields",
        "Alert your neighbours",
        "Keep a torch and noise-making device handy",
        "Report sightings to forest department",
    ],
    RiskLevel.LOW: [
        "Be alert near forest areas",
        "Carry a torch and phone when going out at night",
        "Monitor local forest department updates",
    ],
}


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


# ---------------------------------------------------------------------------
# format_alert
# ---------------------------------------------------------------------------

def format_alert(
    village: str,
    district: str,
    risk_zone: RiskZone,
    distance_km: float = 5.0,
    detection_confidence: float = 1.0,
    risk_explanation: str = "",
    custom_message_en: Optional[str] = None,
    custom_message_kn: Optional[str] = None,
) -> Alert:
    """
    Format a bilingual alert for a village based on its risk zone.

    Returns an Alert with status=PENDING_APPROVAL (never auto-dispatched).
    Both detection_confidence and village_risk_score are stored as separate fields.
    """
    t0 = time.monotonic()
    level = risk_zone.risk_level

    # Build messages
    fmt_params = {
        "village": village,
        "district": district,
        "distance": distance_km,
    }

    message_en = custom_message_en or _TEMPLATES_EN.get(level, "").format(**fmt_params)
    message_kn = custom_message_kn or _TEMPLATES_KN.get(level, "").format(**fmt_params)
    actions = _RECOMMENDED_ACTIONS.get(level, [])

    # Build risk explanation if not provided
    if not risk_explanation and risk_zone.contributing_factors:
        risk_explanation = (
            f"Risk score {risk_zone.village_risk_score:.2f} based on: "
            + "; ".join(risk_zone.contributing_factors[:3])
        )

    alert = Alert(
        village=village,
        district=district,
        alert_level=level,
        village_risk_score=risk_zone.village_risk_score,
        detection_confidence=detection_confidence,
        message_en=message_en,
        message_kn=message_kn,
        recommended_actions=actions,
        risk_explanation=risk_explanation,
        status=AlertStatus.PENDING_APPROVAL,
    )

    latency = (time.monotonic() - t0) * 1000
    _trace("format_alert", f"village={village}, risk={level.value}",
           f"Alert {alert.alert_id[:8]}... created, status=PENDING_APPROVAL", latency)
    return alert


# ---------------------------------------------------------------------------
# dispatch_alert
# ---------------------------------------------------------------------------

def dispatch_alert(alert: Alert, channel: str = "console") -> dict:
    """
    Simulate alert dispatch (console log for MVP).

    IMPORTANT: This function only records the alert as PENDING_APPROVAL.
    Actual dispatch requires forest officer approval via orchestrator.approve_alert().

    Writes to MemoryStore and appends an audit log entry.
    """
    t0 = time.monotonic()
    try:
        # Write to MemoryStore as PENDING_APPROVAL
        from memory.store import store
        store.add_pending_alert(alert)

        # Audit log entry
        from audit.log import append_audit
        append_audit(
            AuditEventType.ALERT_CREATED,
            {
                "alert_id": alert.alert_id,
                "village": alert.village,
                "district": alert.district,
                "alert_level": alert.alert_level.value,
                "village_risk_score": alert.village_risk_score,
                "detection_confidence": alert.detection_confidence,
                "status": "PENDING_APPROVAL",
                "channel": channel,
            },
        )

        # Console log for MVP visibility
        logger.info(
            "[ALERT PENDING APPROVAL] Village: %s | Level: %s | Risk Score: %.2f | "
            "Detection Conf: %.2f | Channel: %s",
            alert.village, alert.alert_level.value,
            alert.village_risk_score, alert.detection_confidence, channel,
        )
        logger.info("  EN: %s", alert.message_en[:120])
        logger.info("  KN: %s", alert.message_kn[:120])

        latency = (time.monotonic() - t0) * 1000
        _trace("dispatch_alert",
               f"alert_id={alert.alert_id[:8]}, village={alert.village}",
               f"status=PENDING_APPROVAL, channel={channel}", latency)

        return {
            "alert_id": alert.alert_id,
            "village": alert.village,
            "status": "PENDING_APPROVAL",
            "channel": channel,
            "message": "Alert queued for forest officer approval before dispatch.",
        }
    except Exception as e:
        latency = (time.monotonic() - t0) * 1000
        _trace("dispatch_alert", f"village={alert.village}", "", latency, error=str(e))
        logger.error("dispatch_alert failed: %s", e)
        return {"error": str(e), "alert_id": alert.alert_id, "status": "error"}


# ---------------------------------------------------------------------------
# Register tools
# ---------------------------------------------------------------------------

TOOL_REGISTRY.update({
    "format_alert": Tool(
        name="format_alert",
        description="Format a bilingual (Kannada + English) alert for a village based on risk zone.",
        input_schema={"village": "str", "district": "str", "risk_zone": "RiskZone",
                      "distance_km": "float", "detection_confidence": "float"},
        output_schema={"type": "Alert", "status": "PENDING_APPROVAL"},
        fn=format_alert,
    ),
    "dispatch_alert": Tool(
        name="dispatch_alert",
        description="Queue an alert for forest officer approval. Does NOT dispatch without explicit approval.",
        input_schema={"alert": "Alert", "channel": "str"},
        output_schema={"type": "dict", "fields": ["alert_id", "status", "channel"]},
        fn=dispatch_alert,
    ),
})
