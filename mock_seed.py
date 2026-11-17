"""
mock_seed.py — Seed the MemoryStore with realistic mock data.

Run this BEFORE starting the dashboard when LLM APIs are unavailable:
    python3 mock_seed.py && streamlit run dashboard/app.py

Populates:
  - 8 detections (6 confirmed, 2 HITL-flagged)
  - 2 HITL queue items (low-confidence, needs officer review)
  - 3 pending alerts (1 HIGH, 1 MEDIUM, 1 LOW)
  - 2 dispatched alerts
  - 10 tool trace entries
  - 1 completed run report
  - 10 audit log entries
"""
from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from schemas import (
    Alert, AlertStatus, Detection, HitlQueueItem, RiskLevel,
    RunReport, ToolTraceEntry,
)
from memory.store import store
from audit.log import append_audit
from schemas import AuditEventType

NOW = datetime.now(timezone.utc)

def _ago(minutes: int) -> datetime:
    return NOW - timedelta(minutes=minutes)

# ─── 1. DETECTIONS ────────────────────────────────────────────────────────────
detections_data = [
    # Confirmed elephants (is_elephant=True, requires_hitl_review=False)
    dict(event_id=str(uuid4()), is_elephant=True,  detection_confidence=0.96,
         nearest_village="Virajpet",    distance_km=3.2,  in_corridor=True,
         district="Kodagu",       lat=12.17, lon=75.80,
         explanation="High-confidence detection: adult female elephant with calf visible at known Kodagu-Hassan corridor crossing. Clear full-body view, confirmed by acoustic sensor co-trigger."),
    dict(event_id=str(uuid4()), is_elephant=True,  detection_confidence=0.91,
         nearest_village="Hunsur",      distance_km=5.8,  in_corridor=True,
         district="Mysuru",        lat=12.06, lon=76.29,
         explanation="Camera trap shows herd of 4-6 elephants crossing open ground towards farmland near Nagarhole fringe. Paddy and ragi at risk."),
    dict(event_id=str(uuid4()), is_elephant=True,  detection_confidence=0.88,
         nearest_village="Somwarpet",   distance_km=7.1,  in_corridor=True,
         district="Kodagu",       lat=12.60, lon=75.97,
         explanation="Single elephant with tusks feeding on sugarcane crop at night. Adult male confirmed by tusk silhouette. Distance to village boundary: 7.1 km."),
    dict(event_id=str(uuid4()), is_elephant=True,  detection_confidence=0.84,
         nearest_village="Kushalnagar",  distance_km=9.4,  in_corridor=False,
         district="Kodagu",       lat=12.45, lon=75.97,
         explanation="Three elephants near paddy field boundary at dusk. Herd moving north-east, away from main corridor. Risk to crops is moderate."),
    dict(event_id=str(uuid4()), is_elephant=True,  detection_confidence=0.79,
         nearest_village="Gundlupet",   distance_km=12.5, in_corridor=True,
         district="Chamarajanagar", lat=11.81, lon=76.68,
         explanation="Lone elephant near village water tank, estimated 50m from houses. Acoustic sensor triggered simultaneously. High risk of human contact."),
    dict(event_id=str(uuid4()), is_elephant=True,  detection_confidence=0.76,
         nearest_village="Belur",        distance_km=18.2, in_corridor=False,
         district="Hassan",        lat=13.16, lon=75.87,
         explanation="Adult male elephant with one tusk visible, feeding at forest edge. 18 km from Belur. Low immediate risk but corridor proximity noted."),
    # HITL-flagged (requires_hitl_review=True, below 0.70 threshold)
    dict(event_id=str(uuid4()), is_elephant=True,  detection_confidence=0.52,
         nearest_village="Madikeri",    distance_km=22.0, in_corridor=True,
         district="Kodagu",       lat=12.42, lon=75.74,
         requires_hitl_review=True,
         explanation="FALLBACK: Motion-triggered image. Unclear animal shape — partial silhouette in undergrowth near water source. Possible elephant but species unconfirmed. Requires visual verification by forest officer."),
    dict(event_id=str(uuid4()), is_elephant=True,  detection_confidence=0.44,
         nearest_village="Piriyapatna", distance_km=28.5, in_corridor=False,
         district="Mysuru",        lat=12.34, lon=76.09,
         requires_hitl_review=True,
         explanation="FALLBACK: Camera trap triggered by wind — no animal clearly visible in frame. Dung and broken branches detected nearby. Officer verification needed to rule out false alarm."),
]

detection_objects = []
for d in detections_data:
    det = Detection(
        event_id=d["event_id"],
        is_elephant=d["is_elephant"],
        detection_confidence=d["detection_confidence"],
        nearest_village=d["nearest_village"],
        distance_km=d["distance_km"],
        in_corridor=d["in_corridor"],
        district=d["district"],
        lat=d["lat"],
        lon=d["lon"],
        requires_hitl_review=d.get("requires_hitl_review", False),
        explanation=d["explanation"],
        timestamp=_ago(60),
    )
    detection_objects.append(det)

store.set_detections(detection_objects)
print(f"Seeded {len(detection_objects)} detections")

# ─── 2. HITL QUEUE ────────────────────────────────────────────────────────────
for det in detection_objects:
    if det.requires_hitl_review:
        item = HitlQueueItem(detection=det, queued_at=_ago(45))
        store.add_hitl_item(item)
        append_audit(AuditEventType.HITL_FLAGGED, {
            "detection_id": det.detection_id,
            "village": det.nearest_village,
            "confidence": det.detection_confidence,
        })

print(f"Seeded {len(store.get_hitl_queue())} HITL queue items")

# ─── 3. ALERTS ────────────────────────────────────────────────────────────────
alerts_data = [
    # HIGH — pending approval
    Alert(
        village="Gundlupet", district="Chamarajanagar",
        alert_level=RiskLevel.HIGH,
        village_risk_score=0.88,
        detection_confidence=0.79,
        status=AlertStatus.PENDING_APPROVAL,
        timestamp=_ago(30),
        message_en=(
            "URGENT: Elephant detected near Gundlupet village water tank. "
            "Lone adult male spotted approximately 50 metres from residential area. "
            "Avoid open areas after dark. Keep children and livestock indoors. "
            "Do NOT use firecrackers or lights to drive the animal away."
        ),
        message_kn=(
            "ತುರ್ತು: ಗುಂಡ್ಲುಪೇಟೆ ಗ್ರಾಮದ ನೀರಿನ ತೊಟ್ಟಿ ಬಳಿ ಆನೆ ಪತ್ತೆಯಾಗಿದೆ. "
            "ವಸತಿ ಪ್ರದೇಶದಿಂದ ಸುಮಾರು 50 ಮೀಟರ್ ದೂರದಲ್ಲಿ ಏಕಾಂಗಿ ವಯಸ್ಕ ಗಂಡು ಆನೆ ಕಂಡುಬಂದಿದೆ. "
            "ರಾತ್ರಿಯ ನಂತರ ತೆರೆದ ಪ್ರದೇಶಗಳನ್ನು ತಪ್ಪಿಸಿ."
        ),
        risk_explanation=(
            "Lone bull elephant within 50m of village water source. "
            "Night-time activity pattern increases conflict probability. "
            "No protective fencing reported in this sector."
        ),
        recommended_actions=[
            "Forest Department rapid response team deployed immediately",
            "Village PA system activated — all residents to stay indoors",
            "Torch-light and noise deterrents positioned at perimeter",
            "Block all footpaths between village and forest edge until all-clear",
        ],
    ),
    # MEDIUM — pending approval
    Alert(
        village="Virajpet", district="Kodagu",
        alert_level=RiskLevel.MEDIUM,
        village_risk_score=0.61,
        detection_confidence=0.96,
        status=AlertStatus.PENDING_APPROVAL,
        timestamp=_ago(25),
        message_en=(
            "Elephant herd detected 3.2 km from Virajpet near the Kodagu-Hassan corridor. "
            "Female with calf confirmed. Farmers with crops near the forest boundary should "
            "harvest ripe paddy and coffee today. Avoid night field-work."
        ),
        message_kn=(
            "ವಿರಾಜಪೇಟೆಯಿಂದ 3.2 ಕಿ.ಮೀ ದೂರದ ಕೊಡಗು-ಹಾಸನ ಕಾರಿಡಾರ್ ಬಳಿ ಆನೆ ಹಿಂಡು ಕಂಡುಬಂದಿದೆ. "
            "ಮರಿಯೊಂದಿಗೆ ಹೆಣ್ಣು ಆನೆ ಖಚಿತಪಡಿಸಲಾಗಿದೆ. ಕಾಡಿನ ಗಡಿ ಬಳಿ ಬೆಳೆ ಹೊಂದಿರುವ ರೈತರು "
            "ಇಂದು ಭತ್ತ ಮತ್ತು ಕಾಫಿ ಕೊಯ್ಲು ಮಾಡಬೇಕು. ರಾತ್ರಿ ಹೊಲ ಕೆಲಸ ತಪ್ಪಿಸಿ."
        ),
        risk_explanation=(
            "Female elephant with calf in corridor — higher aggression risk. "
            "Ripe paddy and coffee crops attract herds towards farmland. "
            "3.2 km distance gives 2-3 hour lead time for precautionary action."
        ),
        recommended_actions=[
            "Notify farmers within 5 km radius via SMS alert",
            "Inspect and energise solar fence along forest boundary",
            "Post forest watcher at Virajpet-Ammatti road junction overnight",
            "Advise against night travel on NH-275 segment near forest",
        ],
    ),
    # LOW — pending approval
    Alert(
        village="Belur", district="Hassan",
        alert_level=RiskLevel.LOW,
        village_risk_score=0.28,
        detection_confidence=0.76,
        status=AlertStatus.PENDING_APPROVAL,
        timestamp=_ago(20),
        message_en=(
            "Low-risk advisory: Elephant detected 18 km from Belur at forest edge. "
            "No immediate threat to village. Farmers with crops near Block 7 forest "
            "boundary are advised to remain vigilant during harvest season."
        ),
        message_kn=(
            "ಕಡಿಮೆ ಅಪಾಯದ ಸಲಹೆ: ಬೇಲೂರಿನಿಂದ 18 ಕಿ.ಮೀ ದೂರ ಕಾಡಿನ ಅಂಚಿನಲ್ಲಿ ಆನೆ ಕಂಡುಬಂದಿದೆ. "
            "ಗ್ರಾಮಕ್ಕೆ ತಕ್ಷಣದ ಅಪಾಯವಿಲ್ಲ. 7ನೇ ಬ್ಲಾಕ್ ಕಾಡಿನ ಗಡಿ ಬಳಿ ಬೆಳೆ ಹೊಂದಿರುವ "
            "ರೈತರು ಕೊಯ್ಲು ಮೌಸಮ್‌ನಲ್ಲಿ ಎಚ್ಚರಿಕೆಯಿಂದ ಇರಬೇಕು."
        ),
        risk_explanation=(
            "Single elephant 18 km away, outside corridor zone. "
            "Hassan district historically low-conflict in November. "
            "Precautionary notification only — monitor movement."
        ),
        recommended_actions=[
            "Routine forest watcher patrol on Block 7 boundary",
            "Update village panchayat of detection for local awareness",
            "No immediate emergency action required",
        ],
    ),
    # DISPATCHED — already approved
    Alert(
        village="Somwarpet", district="Kodagu",
        alert_level=RiskLevel.MEDIUM,
        village_risk_score=0.55,
        detection_confidence=0.88,
        status=AlertStatus.DISPATCHED,
        timestamp=_ago(90),
        approved_by="KFD-RO-002",
        message_en="Elephant detected near sugarcane fields 7 km from Somwarpet. Farmers advised to avoid night harvesting.",
        message_kn="ಸೊಮ್ವಾರಪೇಟೆಯಿಂದ 7 ಕಿ.ಮೀ ದೂರ ಕಬ್ಬಿನ ಹೊಲ ಬಳಿ ಆನೆ ಪತ್ತೆ. ರೈತರು ರಾತ್ರಿ ಕೊಯ್ಲು ತಪ್ಪಿಸಬೇಕು.",
        risk_explanation="Adult male near sugarcane crop. Night feeding behaviour confirmed.",
        recommended_actions=["SMS alert dispatched to 342 registered farmers", "Forest watcher deployed"],
    ),
    # DISPATCHED — already approved
    Alert(
        village="Hunsur", district="Mysuru",
        alert_level=RiskLevel.HIGH,
        village_risk_score=0.82,
        detection_confidence=0.91,
        status=AlertStatus.DISPATCHED,
        timestamp=_ago(120),
        approved_by="KFD-RO-001",
        message_en="URGENT: Elephant herd crossing towards Hunsur farmland. All residents stay indoors. Response team deployed.",
        message_kn="ತುರ್ತು: ಹುಣಸೂರು ಕೃಷಿ ಭೂಮಿ ಕಡೆ ಆನೆ ಹಿಂಡು ದಾಟುತ್ತಿದೆ. ಎಲ್ಲ ನಿವಾಸಿಗಳು ಮನೆಯಲ್ಲೇ ಇರಬೇಕು.",
        risk_explanation="Herd of 4-6 near Nagarhole fringe, paddy fields at risk.",
        recommended_actions=["Rapid response deployed", "PA system activated", "Farmers evacuated from fields"],
    ),
]

for alert in alerts_data:
    store.add_pending_alert(alert)
    append_audit(AuditEventType.ALERT_CREATED, {
        "alert_id": alert.alert_id,
        "village": alert.village,
        "level": alert.alert_level.value,
    })

# Approve the dispatched ones
for alert in alerts_data:
    if alert.status == AlertStatus.DISPATCHED:
        store.approve_alert(alert.alert_id, alert.approved_by or "KFD-RO-001")
        append_audit(AuditEventType.ALERT_APPROVED, {
            "alert_id": alert.alert_id,
            "village": alert.village,
            "officer": alert.approved_by,
        })

pending = store.get_pending_alerts()
dispatched = [a for a in store.get_all_alerts() if a.status.value == "DISPATCHED"]
print(f"Seeded {len(pending)} pending alerts, {len(dispatched)} dispatched alerts")

# ─── 4. TOOL TRACE LOG ────────────────────────────────────────────────────────
trace_entries = [
    ToolTraceEntry(tool_name="fetch_sightings",         input_summary="hours_back=24",
                   output_summary="10 sightings loaded from synthetic data store",        latency_ms=42.1,  timestamp=_ago(65)),
    ToolTraceEntry(tool_name="fetch_camera_events",     input_summary="hours_back=24",
                   output_summary="8 camera trap events retrieved, 2 flagged ambiguous",  latency_ms=38.5,  timestamp=_ago(64)),
    ToolTraceEntry(tool_name="fetch_patrol_logs",       input_summary="hours_back=24",
                   output_summary="6 patrol logs loaded, 3 with elephant activity notes", latency_ms=22.3,  timestamp=_ago(63)),
    ToolTraceEntry(tool_name="fetch_weather",           input_summary="district=Kodagu",
                   output_summary="Rainfall: 12mm, Wind: NE 14kmh, Humidity: 84%",        latency_ms=180.4, timestamp=_ago(62)),
    ToolTraceEntry(tool_name="fetch_crop_calendar",     input_summary="month=November",
                   output_summary="At-risk crops: paddy, ragi, sugarcane, coffee",        latency_ms=55.2,  timestamp=_ago(61)),
    ToolTraceEntry(tool_name="detect_elephant_presence",input_summary="event_id=cam_001, image=forest_edge",
                   output_summary="is_elephant=True, confidence=0.96, village=Virajpet",  latency_ms=1240.8,timestamp=_ago(55)),
    ToolTraceEntry(tool_name="detect_elephant_presence",input_summary="event_id=cam_002, image=herd_crossing",
                   output_summary="is_elephant=True, confidence=0.91, village=Hunsur",    latency_ms=1180.3,timestamp=_ago(54)),
    ToolTraceEntry(tool_name="compute_risk_zones",      input_summary="7 confirmed detections",
                   output_summary="3 HIGH zones, 2 MEDIUM zones, 2 LOW zones computed",   latency_ms=88.6,  timestamp=_ago(45)),
    ToolTraceEntry(tool_name="generate_alert",          input_summary="village=Gundlupet, level=HIGH",
                   output_summary="Alert created: EN + KN messages, 4 recommended actions",latency_ms=2340.1,timestamp=_ago(35)),
    ToolTraceEntry(tool_name="generate_alert",          input_summary="village=Virajpet, level=MEDIUM",
                   output_summary="Alert created: EN + KN messages, 4 recommended actions",latency_ms=2210.7,timestamp=_ago(30)),
]
for entry in trace_entries:
    store.add_tool_trace(entry)
print(f"Seeded {len(trace_entries)} tool trace entries")

# ─── 5. RUN REPORT ────────────────────────────────────────────────────────────
report = RunReport(
    run_id=str(uuid4()),
    start_time=_ago(70),
    end_time=_ago(28),
    agents_run=["WildlifeDataAgent", "ElephantDetectionAgent", "EarlyWarningAgent"],
    total_tokens_in=4820,
    total_tokens_out=1340,
    total_cost_usd=0.00047,
    alerts_pending=3,
    alerts_dispatched=2,
    alerts_rejected=0,
    hitl_flagged_count=2,
    errors=[],
)
store.add_run_report(report)
print("Seeded run report")

# ─── 6. EXTRA AUDIT ENTRIES ───────────────────────────────────────────────────
append_audit(AuditEventType.PIPELINE_RUN_START, {"run_id": report.run_id, "triggered_by": "manual"})
append_audit(AuditEventType.PIPELINE_RUN_END,   {"run_id": report.run_id, "alerts_pending": 3, "errors": 0})
append_audit(AuditEventType.ALERT_APPROVED,     {"village": "Hunsur",    "officer": "KFD-RO-001", "level": "HIGH"})
append_audit(AuditEventType.ALERT_APPROVED,     {"village": "Somwarpet", "officer": "KFD-RO-002", "level": "MEDIUM"})

print("\n✓ Mock data seeded successfully!")
print(f"  Detections : {len(store.get_detections())}")
print(f"  HITL queue : {len(store.get_hitl_queue())}")
print(f"  Pending    : {len(store.get_pending_alerts())}")
print(f"  Dispatched : {len([a for a in store.get_all_alerts() if a.status.value == 'DISPATCHED'])}")
print(f"  Trace log  : {len(store.get_tool_trace_log(last_n=50))}")
print(f"  Last run   : {store.get_last_run().end_time}")
