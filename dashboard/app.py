"""
dashboard/app.py — HEC Early Warning System — Streamlit Dashboard.

Layout:
  - Header with last-run timestamp
  - Main: two-column [map | agent trace + cost]
  - Below: HITL verification queue (Approve / Reject)
  - Below: Pending alerts approval queue (Approve / Reject)
  - Expandable: Audit log tail

Run with:
    streamlit run dashboard/app.py
"""

from __future__ import annotations

import sys
import os
import time
import logging
from datetime import datetime, timezone

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
from streamlit_folium import st_folium

logging.basicConfig(level=logging.WARNING)

st.set_page_config(
    page_title="🐘 HEC Early Warning System — Karnataka",
    page_icon="🐘",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Lazy imports (avoid blocking on startup if modules have issues)
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def _get_store():
    from memory.store import store
    return store


@st.cache_resource(show_spinner=False)
def _get_orchestrator():
    import orchestrator
    return orchestrator


def _load_risk_zones():
    """Compute current risk zones from store detections."""
    try:
        from tools.map_tools import compute_risk_zones
        from tools.data_fetcher import get_weather, get_crop_calendar
        store = _get_store()
        detections = store.get_detections()
        confirmed = [d for d in detections if d.is_elephant and not d.requires_hitl_review]
        if not confirmed:
            return []
        weather = get_weather()
        crops = get_crop_calendar()
        at_risk_crops = crops.get("at_risk_crops", []) if isinstance(crops, dict) else []
        return compute_risk_zones(confirmed, weather=weather, at_risk_crops=at_risk_crops)
    except Exception as e:
        st.warning(f"Could not compute risk zones: {e}")
        return []


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.markdown(
    """
    <div style="background:#1e3a5f;padding:12px 20px;border-radius:6px;margin-bottom:12px">
        <h2 style="color:white;margin:0">🐘 Human-Elephant Conflict Early Warning System</h2>
        <p style="color:#93c5fd;margin:2px 0 0">Karnataka Forest Department — Agentic AI System</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Synthetic data disclaimer
from data.synthetic.generator import SYNTHETIC_DISCLAIMER
st.info(SYNTHETIC_DISCLAIMER)

store = _get_store()
orch = _get_orchestrator()

# ---------------------------------------------------------------------------
# Controls row
# ---------------------------------------------------------------------------

col_run, col_refresh, col_status = st.columns([2, 2, 4])
with col_run:
    if st.button("▶️ Run Agents Now", type="primary", use_container_width=True):
        with st.spinner("Running pipeline…"):
            try:
                report = orch.run_once(hours_back=24)
                st.success(
                    f"Pipeline complete — {len(report.agents_run)} agents, "
                    f"{report.alerts_pending} alerts pending, "
                    f"cost ${report.total_cost_usd:.4f}"
                )
            except Exception as e:
                st.error(f"Pipeline error: {e}")

with col_refresh:
    if st.button("🔄 Refresh Dashboard", use_container_width=True):
        st.rerun()

with col_status:
    last_run = store.get_last_run()
    if last_run:
        end_str = last_run.end_time.strftime("%H:%M:%S UTC") if last_run.end_time else "running…"
        st.caption(
            f"Last run: {end_str} | "
            f"Agents: {', '.join(last_run.agents_run) or 'none'} | "
            f"Tokens: {last_run.total_tokens_in + last_run.total_tokens_out:,} | "
            f"Cost: ${last_run.total_cost_usd:.4f}"
        )
    else:
        st.caption("No pipeline run yet. Click 'Run Agents Now' to start.")

st.divider()

# ---------------------------------------------------------------------------
# Main two-column layout: Map | Agent Trace
# ---------------------------------------------------------------------------

map_col, trace_col = st.columns([3, 2])

with map_col:
    st.subheader("🗺️ Karnataka — Live Situation Map")

    detections = store.get_detections()
    all_alerts = store.get_all_alerts()
    risk_zones = _load_risk_zones()

    try:
        from dashboard.map_builder import build_map
        fmap = build_map(
            detections=detections,
            alerts=all_alerts,
            risk_zones=risk_zones,
        )
        st_folium(fmap, width=None, height=520, returned_objects=[])
    except Exception as e:
        st.error(f"Map error: {e}")
        import traceback
        st.code(traceback.format_exc())

    # Map legend
    st.markdown(
        """
        <div style="font-size:12px;color:#6b7280;margin-top:4px">
        🔴 HIGH risk &nbsp;|&nbsp; 🟠 MEDIUM risk &nbsp;|&nbsp; 🟡 LOW risk &nbsp;|&nbsp;
        🐘 Elephant detection &nbsp;|&nbsp; 🚨 Dispatched alert &nbsp;|&nbsp;
        🟢 Forest corridor
        </div>
        """,
        unsafe_allow_html=True,
    )

with trace_col:
    st.subheader("🤖 Agent Execution Trace")

    trace_log = store.get_tool_trace_log(last_n=20)
    if trace_log:
        for entry in reversed(trace_log):
            icon = "❌" if entry.error else "✅"
            ts = entry.timestamp.strftime("%H:%M:%S")
            st.markdown(
                f"<div style='font-size:12px;border-left:3px solid #3b82f6;"
                f"padding:4px 8px;margin:2px 0;background:#f8fafc'>"
                f"<b>{icon} {entry.tool_name}</b> <span style='color:#9ca3af'>{ts}</span><br>"
                f"<span style='color:#374151'>{entry.output_summary[:80]}</span>"
                f"{'<br><span style=color:#ef4444>' + entry.error[:60] + '</span>' if entry.error else ''}"
                f"</div>",
                unsafe_allow_html=True,
            )
    else:
        st.caption("No tool trace yet. Run the agents to see activity.")

    st.divider()
    st.subheader("💰 Cost & Token Summary")
    llm_log = store.get_llm_call_log(last_n=20)
    if llm_log:
        total_cost = store.get_total_cost()
        totals = store.get_total_tokens()
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Cost", f"${total_cost:.5f}")
        c2.metric("Tokens In", f"{totals['tokens_in']:,}")
        c3.metric("Tokens Out", f"{totals['tokens_out']:,}")

        # Last few LLM calls
        for call in reversed(llm_log[-5:]):
            route = call.get("route_used", "?")
            fb = " 🔄 fallback" if call.get("is_fallback") else ""
            st.markdown(
                f"<div style='font-size:11px;color:#6b7280'>"
                f"<b>{call.get('model_id','?')[:30]}</b> via {route}{fb} — "
                f"{call.get('tokens_in',0)}+{call.get('tokens_out',0)} tokens, "
                f"${call.get('cost_usd',0):.5f}, {call.get('latency_ms',0):.0f}ms"
                f"</div>",
                unsafe_allow_html=True,
            )
    else:
        st.caption("No LLM calls yet.")

st.divider()

# ---------------------------------------------------------------------------
# Detection stats row
# ---------------------------------------------------------------------------

confirmed = [d for d in detections if d.is_elephant and not d.requires_hitl_review]
hitl_pending = [d for d in detections if d.requires_hitl_review]
pending_alerts = store.get_pending_alerts()
dispatched_count = sum(1 for a in all_alerts if a.status.value == "DISPATCHED")

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("🐘 Detections", len(detections))
m2.metric("✅ Confirmed", len(confirmed))
m3.metric("⚠️ HITL Queue", len(hitl_pending), delta="needs review" if hitl_pending else None)
m4.metric("🔔 Pending Alerts", len(pending_alerts), delta="needs approval" if pending_alerts else None)
m5.metric("📢 Dispatched", dispatched_count)

st.divider()

# ---------------------------------------------------------------------------
# HITL Verification Queue
# ---------------------------------------------------------------------------

st.subheader("⚠️ HITL Verification Queue — Low Confidence Detections")
hitl_queue = store.get_hitl_queue()

if not hitl_queue:
    st.success("✅ HITL queue is empty — no detections require manual review.")
else:
    st.warning(f"{len(hitl_queue)} detection(s) require forest officer verification before alerts can be generated.")
    for item in hitl_queue:
        det = item.detection
        with st.expander(
            f"🔍 Event {det.event_id[:8]}… | Village: {det.nearest_village} | "
            f"Confidence: {int(det.detection_confidence*100)}% | "
            f"District: {det.district}",
            expanded=True,
        ):
            hcol1, hcol2 = st.columns([3, 1])
            with hcol1:
                st.markdown(f"**Detection confidence:** `{det.detection_confidence:.2f}` (threshold: `{0.70}`)")
                st.markdown(f"**In corridor:** {'Yes ✓' if det.in_corridor else 'No'}")
                st.markdown(f"**Nearest village:** {det.nearest_village} ({det.distance_km:.1f} km)")
                st.markdown(f"**Explanation:** _{det.explanation[:300]}_")
            with hcol2:
                officer_id = st.text_input("Officer ID", value="KFD-RO-001",
                                            key=f"hitl_officer_{item.item_id}")
                if st.button("✅ Approve Detection", key=f"hitl_approve_{item.item_id}",
                             type="primary", use_container_width=True):
                    from schemas import HitlVerdict
                    success = orch.resolve_hitl(item.item_id, HitlVerdict.APPROVED, officer_id)
                    if success:
                        st.success("Detection approved — Agent 3 will generate an alert.")
                        time.sleep(0.5)
                        st.rerun()
                if st.button("❌ Reject (False Alarm)", key=f"hitl_reject_{item.item_id}",
                             use_container_width=True):
                    from schemas import HitlVerdict
                    success = orch.resolve_hitl(item.item_id, HitlVerdict.REJECTED, officer_id,
                                                notes="Rejected via dashboard")
                    if success:
                        st.info("Detection marked as false alarm.")
                        time.sleep(0.5)
                        st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Pending Alerts — Forest Officer Approval Queue
# ---------------------------------------------------------------------------

st.subheader("🔔 Pending Alerts — Awaiting Forest Officer Approval")
st.caption("⚠️ No alert is dispatched without explicit forest officer approval.")

if not pending_alerts:
    st.success("✅ No alerts pending approval.")
else:
    st.warning(f"{len(pending_alerts)} alert(s) awaiting your approval before community dispatch.")
    for alert in pending_alerts:
        level_emoji = {"HIGH": "🔴", "MEDIUM": "🟠", "LOW": "🟡"}.get(alert.alert_level.value, "⚪")
        with st.expander(
            f"{level_emoji} {alert.alert_level.value} — {alert.village} ({alert.district}) | "
            f"Risk: {alert.village_risk_score:.2f} | Det. Conf: {alert.detection_confidence:.2f}",
            expanded=alert.alert_level.value == "HIGH",
        ):
            acol1, acol2 = st.columns([3, 1])
            with acol1:
                st.markdown(f"**Risk explanation:** _{alert.risk_explanation}_")
                st.markdown(f"**English message:**\n> {alert.message_en}")
                st.markdown(f"**Kannada message:**\n> {alert.message_kn}")
                if alert.recommended_actions:
                    st.markdown("**Recommended actions:**")
                    for action in alert.recommended_actions[:4]:
                        st.markdown(f"- {action}")
            with acol2:
                st.markdown(f"**Village Risk Score:** `{alert.village_risk_score:.2f}`")
                st.markdown(f"**Detection Confidence:** `{alert.detection_confidence:.2f}`")
                officer = st.text_input("Officer ID", value="KFD-RO-001",
                                         key=f"alert_officer_{alert.alert_id}")
                if st.button("📢 Approve & Dispatch", key=f"alert_approve_{alert.alert_id}",
                             type="primary", use_container_width=True):
                    success = orch.approve_alert(alert.alert_id, officer)
                    if success:
                        st.success(f"Alert dispatched to {alert.village}!")
                        time.sleep(0.5)
                        st.rerun()
                reject_reason = st.text_input("Reject reason (optional)",
                                               key=f"alert_reject_reason_{alert.alert_id}")
                if st.button("🚫 Reject Alert", key=f"alert_reject_{alert.alert_id}",
                             use_container_width=True):
                    success = orch.reject_alert(alert.alert_id, officer, reject_reason)
                    if success:
                        st.info("Alert rejected and recorded in audit log.")
                        time.sleep(0.5)
                        st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Audit Log Viewer
# ---------------------------------------------------------------------------

with st.expander("📋 Audit Log (last 10 entries)", expanded=False):
    from audit.log import read_audit_log
    entries = read_audit_log(last_n=10)
    if entries:
        for entry in reversed(entries):
            ts = entry.get("timestamp", "")[:19].replace("T", " ")
            evt = entry.get("event_type", "")
            payload = entry.get("payload", {})

            colour = {
                "ALERT_APPROVED": "#16a34a",
                "ALERT_REJECTED": "#dc2626",
                "HITL_FLAGGED": "#ca8a04",
                "HITL_RESOLVED": "#2563eb",
                "PIPELINE_RUN_START": "#7c3aed",
                "PIPELINE_RUN_END": "#7c3aed",
                "ALERT_CREATED": "#0891b2",
            }.get(evt, "#6b7280")

            detail = ""
            if "village" in payload:
                detail = f" — {payload['village']}"
            elif "detection_id" in payload:
                detail = f" — detection {str(payload.get('detection_id', ''))[:8]}…"

            st.markdown(
                f"<div style='font-size:12px;padding:3px 8px;border-left:3px solid {colour}'>"
                f"<span style='color:#9ca3af'>{ts}</span> "
                f"<b style='color:{colour}'>{evt}</b>{detail}"
                f"</div>",
                unsafe_allow_html=True,
            )
    else:
        st.caption("No audit log entries yet.")

# ---------------------------------------------------------------------------
# Auto-refresh footer
# ---------------------------------------------------------------------------

st.markdown("---")
st.caption("🔄 Dashboard auto-refreshes every 30 seconds. Data sources: synthetic feeds + OpenStreetMap + IMD.")

# Auto-refresh every 30 seconds
time.sleep(30)
st.rerun()
