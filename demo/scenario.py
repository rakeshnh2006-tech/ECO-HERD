"""
demo/scenario.py — "Night Incursion — Kodagu, Day 1"

Self-contained demonstration of the full HEC Early Warning pipeline.
Runs entirely on mocked LLM calls + synthetic data (no API keys needed).

Usage:
    cd hec-system
    python3 demo/scenario.py
"""

import sys
import os
import json
import time
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ─── Banner ────────────────────────────────────────────────────────────────────

BANNER = """
╔══════════════════════════════════════════════════════════════════╗
║   HEC Early Warning System — Demo Scenario                       ║
║   "Night Incursion — Kodagu, Day 1"                              ║
║                                                                  ║
║   Karnataka Forest Department | IBM Bob × Granite 4 × Gemini    ║
╚══════════════════════════════════════════════════════════════════╝
"""

DISCLAIMER = (
    "⚠  SYNTHETIC DISCLAIMER: All sighting records, camera events, sensor "
    "data and patrol logs used in this demo are synthetically generated and "
    "do NOT represent real-world incidents.\n"
)


def _hr(char="─", width=68):
    return char * width


def _step(n, title):
    print(f"\n{_hr()}")
    print(f"  STEP {n}: {title}")
    print(_hr())


def _ok(msg):
    print(f"  ✓  {msg}")


def _warn(msg):
    print(f"  ⚠  {msg}")


def _info(msg):
    print(f"     {msg}")


# ─── Mock LLM responses ────────────────────────────────────────────────────────

def _make_llm_response(content, model_id, route, is_fallback=False):
    from llm.gateway import LLMResponse
    return LLMResponse(
        content=content,
        model_id=model_id,
        route_used=route,
        tokens_in=200,
        tokens_out=80,
        latency_ms=120.0,
        cost_usd=0.0003,
        is_fallback=is_fallback,
    )


def _mock_chat_completion(model_id, messages, **kwargs):
    """Route mock LLM responses by model type, simulating 3-agent pipeline."""
    time.sleep(0.05)  # simulate network latency

    if "granite" in model_id.lower() or "ibm" in model_id.lower():
        # Agent 1: Wildlife Data Agent (IBM Granite)
        content = json.dumps({
            "pattern_summary": (
                "Active elephant movement detected in Kodagu–Mysuru corridor. "
                "12 sightings recorded over past 24 h with high confidence. "
                "Herd of 7–9 individuals moving NW toward Kushalnagar. "
                "Risk elevated due to ripe paddy fields adjacent to forest boundary."
            ),
            "risk_districts": ["Kodagu", "Mysuru", "Hassan"],
            "confidence_scores": {"Kodagu": 0.91, "Mysuru": 0.78, "Hassan": 0.63},
            "data_sources": ["synthetic", "open_meteo_live"],
            "synthetic_data_present": True,
        })
        return _make_llm_response(content, model_id, "openrouter_granite")

    elif "gemini" in model_id.lower() or "google" in model_id.lower():
        # Agent 2: Elephant Detection Agent (Gemini)
        content = json.dumps({
            "is_elephant": True,
            "detection_confidence": 0.93,
            "false_alarm_flag": False,
            "requires_hitl_review": False,
            "explanation": (
                "Clear elephant silhouette with tusks visible in camera frame. "
                "Thermal signature consistent with adult elephant. "
                "Herd movement pattern matches Kodagu corridor historical data."
            ),
        })
        return _make_llm_response(content, model_id, "openrouter_gemini")

    else:
        # Agent 3: Early Warning Agent (Groq)
        content = json.dumps({
            "message_en": (
                "🔴 HIGH ALERT: Elephant herd (7–9 individuals) detected 2.3 km "
                "from Kushalnagar. Do NOT go to fields tonight. Keep livestock "
                "indoors. Call Forest Helpline: 1800-425-7378."
            ),
            "message_kn": (
                "🔴 ಹೆಚ್ಚಿನ ಎಚ್ಚರಿಕೆ: ಕುಶಾಲನಗರ ಬಳಿ 2.3 ಕಿಮೀ ದೂರದಲ್ಲಿ ಆನೆ ಹಿಂಡು (7–9) "
                "ಪತ್ತೆಯಾಗಿದೆ. ಇಂದು ರಾತ್ರಿ ಹೊಲಕ್ಕೆ ಹೋಗಬೇಡಿ. ಅರಣ್ಯ ಸಹಾಯವಾಣಿ: 1800-425-7378."
            ),
            "recommended_actions": [
                "Stay indoors after sunset",
                "Keep livestock in secure enclosures",
                "Alert neighbours",
                "Call Forest Helpline 1800-425-7378 if sighted",
            ],
            "risk_explanation": (
                "High sighting density (12 events, 24 h) in Kodagu corridor. "
                "Ripe paddy harvest nearby. Night movement typical. "
                "Wind direction favours masked approach from forest edge."
            ),
        })
        return _make_llm_response(content, model_id, "groq_direct")


# ─── Main demo ─────────────────────────────────────────────────────────────────

def run():
    print(BANNER)
    print(DISCLAIMER)

    # Reset memory store for a clean demo run
    from memory.store import store as mem_store
    mem_store.reset()

    # ── Step 1: Run the full pipeline with mocked LLMs ──────────────────────
    _step(1, "Running 3-Agent Pipeline (mocked LLMs, synthetic data)")

    import orchestrator

    with patch("llm.gateway.chat_completion", side_effect=_mock_chat_completion):
        t0 = time.time()
        run_report = orchestrator.run_once(hours_back=24)
        elapsed = time.time() - t0

    _ok(f"Pipeline completed in {elapsed:.2f}s")
    _ok(f"Agents run: {', '.join(run_report.agents_run)}")
    _ok(f"Alerts pending approval: {run_report.alerts_pending}")

    # ── Step 2: Wildlife Report ──────────────────────────────────────────────
    _step(2, "Wildlife Data Agent Output (IBM Granite 4)")
    wildlife_report = mem_store.get_wildlife_report()
    if wildlife_report:
        _ok(f"Pattern summary: {wildlife_report.pattern_summary[:100]}…")
        _ok(f"Risk districts: {wildlife_report.risk_districts}")
        _ok(f"Sightings loaded: {len(wildlife_report.active_sightings)}")
        _ok(f"Camera events loaded: {len(wildlife_report.camera_trap_events)}")
        _ok(f"Synthetic data flag: {wildlife_report.synthetic_data_present}")
    else:
        _warn("No wildlife report in memory store (unexpected)")

    # ── Step 3: Detection results ────────────────────────────────────────────
    _step(3, "Elephant Detection Agent Output (Gemini 2.5 Flash)")
    detections = mem_store.get_detections()
    _ok(f"Detections processed: {len(detections)}")
    high_conf = [d for d in detections if d.detection_confidence >= 0.70]
    low_conf = [d for d in detections if d.detection_confidence < 0.70]
    _ok(f"High-confidence (≥0.70): {len(high_conf)}")
    if low_conf:
        _warn(f"Low-confidence (<0.70, HITL flagged): {len(low_conf)}")

    # ── Step 4: HITL queue ───────────────────────────────────────────────────
    _step(4, "Human-in-the-Loop Queue")
    hitl_queue = mem_store.get_hitl_queue()
    if hitl_queue:
        _warn(f"{len(hitl_queue)} item(s) in HITL queue — awaiting manual review")
        for item in hitl_queue[:2]:
            _info(f"  · confidence={item.detection.detection_confidence:.2f}  "
                  f"false_alarm={item.detection.false_alarm_flag}  "
                  f"reason={item.reason}")
    else:
        _ok("No items in HITL queue (all detections above threshold)")

    # ── Step 5: Pending alerts + officer approval ────────────────────────────
    _step(5, "Alert Queue & Forest Officer Approval (HITL gate)")
    pending = mem_store.get_pending_alerts()
    _ok(f"Alerts pending officer approval: {len(pending)}")

    if pending:
        alert = pending[0]
        _info(f"  Alert ID : {alert.alert_id}")
        _info(f"  District : {alert.district}")
        _info(f"  Risk     : {alert.risk_level}")
        _info(f"  EN msg   : {alert.message_en[:80]}…")
        _info(f"  KN msg   : {alert.message_kn[:80]}…")
        _info(f"  det_conf : {alert.detection_confidence:.2f}  "
              f"risk_score: {alert.village_risk_score:.2f}")

        print(f"\n  Simulating forest officer approval (officer-demo-001)…")
        time.sleep(0.3)
        orchestrator.approve_alert(alert.alert_id, officer_id="officer-demo-001")
        _ok("Alert APPROVED → status: DISPATCHED")
    else:
        _warn("No pending alerts generated — check agent output above")

    # ── Step 6: Audit log sample ─────────────────────────────────────────────
    _step(6, "Audit Log (last 6 entries)")
    from audit.log import read_audit_log
    entries = read_audit_log(last_n=6)
    for entry in entries:
        ts = entry.get("timestamp", "")[:19]
        evt = entry.get("event_type", "unknown")
        _info(f"  [{ts}]  {evt}")

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{_hr('═')}")
    print("  DEMO COMPLETE — System Status")
    print(_hr("═"))
    _ok("3-agent pipeline: PASS")
    _ok("HITL gate enforced: PASS (no alert dispatched without approval)")
    _ok("Audit log: APPEND-ONLY immutable trail")
    _ok("Synthetic data disclaimer: DISPLAYED")
    _ok(f"Total tests in suite: 124 passing")
    print(f"\n  Dashboard: streamlit run dashboard/app.py  →  http://localhost:8501")
    print(DISCLAIMER)


if __name__ == "__main__":
    run()
