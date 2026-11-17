"""
dashboard/app.py — HEC Early Warning System — Streamlit Dashboard.
Clay + Glassmorphism UI. No emojis — SVG/Unicode symbols only.
"""

from __future__ import annotations

import sys
import os
import logging
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
from streamlit_folium import st_folium

logging.basicConfig(level=logging.WARNING)

st.set_page_config(
    page_title="ECO-HERD — HEC Early Warning",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── Global CSS — Clay + Glassmorphism ────────────────────────────────────────
st.markdown("""
<style>
/* ── Fonts & base ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background: #0d1f17 !important;
    color: #e8f5ee !important;
}

/* ── App background ── */
.stApp {
    background: linear-gradient(135deg, #0d1f17 0%, #0f2820 50%, #0a1a12 100%) !important;
    min-height: 100vh;
}

/* ── Hide Streamlit chrome ── */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 1.5rem 2rem !important; max-width: 100% !important; }

/* ── Glass card ── */
.glass-card {
    background: rgba(255,255,255,0.05);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 20px;
    padding: 1.4rem 1.6rem;
    margin-bottom: 1rem;
    box-shadow: 0 8px 32px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.08);
}

/* ── Clay card (raised, soft shadow) ── */
.clay-card {
    background: linear-gradient(145deg, #1a3d28, #152f1f);
    border: 1px solid rgba(100,200,130,0.15);
    border-radius: 24px;
    padding: 1.4rem 1.6rem;
    margin-bottom: 1rem;
    box-shadow: 6px 6px 18px rgba(0,0,0,0.4), -2px -2px 8px rgba(255,255,255,0.03);
}

/* ── Clay metric card ── */
.metric-clay {
    background: linear-gradient(145deg, #1e4a30, #162d1e);
    border: 1px solid rgba(100,200,130,0.18);
    border-radius: 20px;
    padding: 1.2rem 1.4rem;
    text-align: center;
    box-shadow: 5px 5px 15px rgba(0,0,0,0.35), -2px -2px 6px rgba(255,255,255,0.04);
    transition: transform 0.2s;
}
.metric-clay:hover { transform: translateY(-2px); }
.metric-num { font-size: 2.2rem; font-weight: 700; color: #74d49a; line-height: 1.1; }
.metric-label { font-size: 0.75rem; font-weight: 500; color: #8ab89a; text-transform: uppercase; letter-spacing: 0.08em; margin-top: 4px; }
.metric-delta { font-size: 0.7rem; color: #f59e0b; margin-top: 2px; }

/* ── Status badge ── */
.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 100px;
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.06em;
}
.badge-high   { background: rgba(220,38,38,0.2);  color: #fca5a5; border: 1px solid rgba(220,38,38,0.4); }
.badge-medium { background: rgba(234,88,12,0.2);  color: #fdba74; border: 1px solid rgba(234,88,12,0.4); }
.badge-low    { background: rgba(202,138,4,0.2);  color: #fde047; border: 1px solid rgba(202,138,4,0.4); }
.badge-ok     { background: rgba(22,163,74,0.2);  color: #86efac; border: 1px solid rgba(22,163,74,0.4); }
.badge-pending{ background: rgba(99,102,241,0.2); color: #c4b5fd; border: 1px solid rgba(99,102,241,0.4); }

/* ── Section header ── */
.section-head {
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #74d49a;
    margin-bottom: 0.8rem;
    display: flex;
    align-items: center;
    gap: 8px;
}
.section-head::after {
    content: '';
    flex: 1;
    height: 1px;
    background: rgba(100,200,130,0.2);
}

/* ── Alert row ── */
.alert-row {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 14px;
    padding: 1rem 1.2rem;
    margin-bottom: 0.6rem;
}
.alert-en { font-size: 0.88rem; color: #d1fae5; line-height: 1.5; margin: 6px 0; }
.alert-kn { font-size: 0.85rem; color: #a7f3d0; line-height: 1.5; font-style: italic; }

/* ── Trace entry ── */
.trace-entry {
    border-left: 3px solid rgba(100,200,130,0.3);
    padding: 4px 10px;
    margin: 3px 0;
    font-size: 0.78rem;
    color: #9fbeaa;
}
.trace-entry b { color: #c8e6d4; }

/* ── Audit entry ── */
.audit-entry {
    padding: 4px 10px;
    margin: 2px 0;
    border-radius: 8px;
    font-size: 0.75rem;
}

/* ── Buttons ── */
.stButton > button {
    background: linear-gradient(145deg, #22543d, #1a3d2d) !important;
    color: #d1fae5 !important;
    border: 1px solid rgba(100,200,130,0.25) !important;
    border-radius: 12px !important;
    font-weight: 500 !important;
    font-size: 0.82rem !important;
    padding: 0.45rem 1rem !important;
    box-shadow: 3px 3px 10px rgba(0,0,0,0.3) !important;
    transition: all 0.2s !important;
}
.stButton > button:hover {
    background: linear-gradient(145deg, #276048, #1e4535) !important;
    transform: translateY(-1px) !important;
    box-shadow: 4px 6px 14px rgba(0,0,0,0.4) !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(145deg, #166534, #14532d) !important;
    border-color: rgba(134,239,172,0.4) !important;
    color: #bbf7d0 !important;
}

/* ── Inputs ── */
.stTextInput input {
    background: rgba(255,255,255,0.05) !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 10px !important;
    color: #e8f5ee !important;
    font-size: 0.82rem !important;
}

/* ── Expander ── */
.streamlit-expanderHeader {
    background: rgba(255,255,255,0.04) !important;
    border-radius: 12px !important;
    color: #c8e6d4 !important;
    font-size: 0.82rem !important;
}

/* ── Divider ── */
hr { border-color: rgba(255,255,255,0.07) !important; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(100,200,130,0.3); border-radius: 10px; }

/* ── Info / Warning / Success ── */
.stAlert { border-radius: 14px !important; }
</style>
""", unsafe_allow_html=True)


# ─── Lazy imports ──────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def _get_store():
    from memory.store import store
    return store

@st.cache_resource(show_spinner=False)
def _get_orchestrator():
    import orchestrator
    return orchestrator

def _load_risk_zones():
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
    except Exception:
        return []


store = _get_store()
orch  = _get_orchestrator()

# ─── Header ───────────────────────────────────────────────────────────────────
st.markdown("""
<div class="glass-card" style="margin-bottom:1.2rem;padding:1.2rem 1.8rem">
  <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px">
    <div>
      <div style="font-size:0.65rem;font-weight:600;letter-spacing:0.14em;color:#74d49a;text-transform:uppercase">
        Karnataka Forest Department &nbsp;·&nbsp; Agentic AI Early Warning
      </div>
      <div style="font-size:1.6rem;font-weight:700;color:#ffffff;line-height:1.2;margin-top:2px">
        ECO-HERD &nbsp;<span style="font-weight:300;color:#74d49a">Human-Elephant Conflict System</span>
      </div>
    </div>
    <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <span style="font-size:0.68rem;color:#8ab89a;background:rgba(255,255,255,0.05);
        padding:4px 12px;border-radius:100px;border:1px solid rgba(255,255,255,0.1)">
        IBM Granite 4
      </span>
      <span style="font-size:0.68rem;color:#8ab89a;background:rgba(255,255,255,0.05);
        padding:4px 12px;border-radius:100px;border:1px solid rgba(255,255,255,0.1)">
        Gemini 2.5 Flash
      </span>
      <span style="font-size:0.68rem;color:#8ab89a;background:rgba(255,255,255,0.05);
        padding:4px 12px;border-radius:100px;border:1px solid rgba(255,255,255,0.1)">
        Groq
      </span>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ─── Controls ─────────────────────────────────────────────────────────────────
ctrl1, ctrl2, ctrl3 = st.columns([2, 2, 5])
with ctrl1:
    run_clicked = st.button("▶  Run Pipeline", type="primary", use_container_width=True)
with ctrl2:
    refresh_clicked = st.button("↺  Refresh", use_container_width=True)
with ctrl3:
    last_run = store.get_last_run()
    if last_run and last_run.end_time:
        end_str = last_run.end_time.strftime("%H:%M:%S UTC")
        st.markdown(
            f"<div style='font-size:0.75rem;color:#8ab89a;padding-top:10px'>"
            f"Last run: <b style='color:#c8e6d4'>{end_str}</b> &nbsp;·&nbsp; "
            f"Agents: <b style='color:#c8e6d4'>{len(last_run.agents_run)}</b> &nbsp;·&nbsp; "
            f"Errors: <b style='color:{'#fca5a5' if last_run.errors else '#86efac'}'>{len(last_run.errors)}</b>"
            f"</div>",
            unsafe_allow_html=True
        )
    else:
        st.markdown("<div style='font-size:0.75rem;color:#8ab89a;padding-top:10px'>No pipeline run yet — click Run Pipeline to start.</div>", unsafe_allow_html=True)

if run_clicked:
    with st.spinner("Running 3-agent pipeline..."):
        try:
            report = orch.run_once(hours_back=24)
            st.success(f"Pipeline complete — {len(report.agents_run)} agents ran · {report.alerts_pending} alerts pending · {report.hitl_flagged_count} HITL flagged")
        except Exception as e:
            st.error(f"Pipeline error: {e}")
    st.rerun()

if refresh_clicked:
    st.rerun()

st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

# ─── Metrics row ──────────────────────────────────────────────────────────────
detections    = store.get_detections()
all_alerts    = store.get_all_alerts()
risk_zones    = _load_risk_zones()
confirmed     = [d for d in detections if d.is_elephant and not d.requires_hitl_review]
hitl_pending  = store.get_hitl_queue()
pending_alerts = store.get_pending_alerts()
dispatched    = [a for a in all_alerts if a.status.value == "DISPATCHED"]

m1, m2, m3, m4, m5 = st.columns(5)
metrics = [
    (str(len(detections)), "Detections", None),
    (str(len(confirmed)),  "Confirmed", None),
    (str(len(hitl_pending)), "HITL Queue", "Review needed" if hitl_pending else None),
    (str(len(pending_alerts)), "Pending Approval", "Awaiting officer" if pending_alerts else None),
    (str(len(dispatched)), "Dispatched", None),
]
for col, (num, label, delta) in zip([m1,m2,m3,m4,m5], metrics):
    delta_html = f"<div class='metric-delta'>{delta}</div>" if delta else ""
    col.markdown(
        f"<div class='metric-clay'>"
        f"<div class='metric-num'>{num}</div>"
        f"<div class='metric-label'>{label}</div>"
        f"{delta_html}"
        f"</div>",
        unsafe_allow_html=True
    )

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# ─── Main layout: Map | Agent Trace ───────────────────────────────────────────
map_col, trace_col = st.columns([3, 2], gap="medium")

with map_col:
    st.markdown("<div class='section-head'>&#9632; Karnataka Live Situation Map</div>", unsafe_allow_html=True)
    st.markdown("<div class='glass-card' style='padding:0.6rem'>", unsafe_allow_html=True)
    try:
        from dashboard.map_builder import build_map
        fmap = build_map(detections=detections, alerts=all_alerts, risk_zones=risk_zones)
        st_folium(fmap, width=None, height=500, returned_objects=[])
    except Exception as e:
        st.error(f"Map error: {e}")
        import traceback; st.code(traceback.format_exc())
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown(
        "<div style='font-size:0.68rem;color:#8ab89a;margin-top:4px;padding:0 4px'>"
        "&#9632; HIGH &nbsp;&#9632; MEDIUM &nbsp;&#9632; LOW &nbsp;·&nbsp; "
        "Forest corridors shown in green &nbsp;·&nbsp; Use layer control (top-right) to switch to Google Satellite"
        "</div>",
        unsafe_allow_html=True
    )

with trace_col:
    st.markdown("<div class='section-head'>&#9632; Agent Execution Trace</div>", unsafe_allow_html=True)
    st.markdown("<div class='glass-card' style='max-height:520px;overflow-y:auto'>", unsafe_allow_html=True)
    trace_log = store.get_tool_trace_log(last_n=20)
    if trace_log:
        for entry in reversed(trace_log):
            icon = "&#10007;" if entry.error else "&#10003;"
            icon_color = "#fca5a5" if entry.error else "#86efac"
            ts = entry.timestamp.strftime("%H:%M:%S")
            st.markdown(
                f"<div class='trace-entry'>"
                f"<span style='color:{icon_color}'>{icon}</span> "
                f"<b>{entry.tool_name}</b> "
                f"<span style='color:#6b8c76;font-size:0.7rem'>{ts}</span><br>"
                f"<span style='color:#7fa88a'>{entry.output_summary[:90]}</span>"
                f"{'<br><span style=color:#fca5a5>' + entry.error[:60] + '</span>' if entry.error else ''}"
                f"</div>",
                unsafe_allow_html=True
            )
    else:
        st.markdown("<div style='color:#6b8c76;font-size:0.8rem;padding:8px'>No tool trace yet. Run the pipeline to see activity.</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# ─── HITL Verification Queue ──────────────────────────────────────────────────
st.markdown("<div class='section-head'>&#9650; HITL Verification Queue &mdash; Low Confidence Detections</div>", unsafe_allow_html=True)

if not hitl_pending:
    st.markdown(
        "<div class='clay-card' style='color:#86efac;font-size:0.85rem'>"
        "&#10003; &nbsp; HITL queue is empty — all detections are above the confidence threshold."
        "</div>", unsafe_allow_html=True
    )
else:
    st.markdown(
        f"<div style='font-size:0.8rem;color:#fde047;margin-bottom:0.6rem'>"
        f"&#9650; &nbsp; {len(hitl_pending)} detection(s) require forest officer verification."
        f"</div>", unsafe_allow_html=True
    )
    for item in hitl_pending:
        det = item.detection
        with st.expander(
            f"Event {det.event_id[:8]}  ·  {det.nearest_village}  ·  Confidence: {int(det.detection_confidence*100)}%  ·  {det.district}",
            expanded=True
        ):
            hc1, hc2 = st.columns([3, 1])
            with hc1:
                st.markdown(
                    f"<div class='glass-card'>"
                    f"<div style='font-size:0.8rem;color:#c8e6d4;margin-bottom:6px'>"
                    f"Confidence: <b style='color:#fde047'>{det.detection_confidence:.2f}</b>"
                    f" &nbsp;/&nbsp; Threshold: <b>0.70</b>"
                    f" &nbsp;·&nbsp; In corridor: <b>{'Yes' if det.in_corridor else 'No'}</b>"
                    f" &nbsp;·&nbsp; Nearest village: <b>{det.nearest_village}</b> ({det.distance_km:.1f} km)"
                    f"</div>"
                    f"<div style='font-size:0.8rem;color:#9fbeaa;font-style:italic'>{det.explanation[:300]}</div>"
                    f"</div>", unsafe_allow_html=True
                )
            with hc2:
                officer_id = st.text_input("Officer ID", value="KFD-RO-001", key=f"hitl_o_{item.item_id}")
                if st.button("Approve Detection", key=f"hitl_a_{item.item_id}", type="primary", use_container_width=True):
                    from schemas import HitlVerdict
                    if orch.resolve_hitl(item.item_id, HitlVerdict.APPROVED, officer_id):
                        st.success("Approved.")
                        st.rerun()
                if st.button("Reject — False Alarm", key=f"hitl_r_{item.item_id}", use_container_width=True):
                    from schemas import HitlVerdict
                    if orch.resolve_hitl(item.item_id, HitlVerdict.REJECTED, officer_id, notes="Rejected via dashboard"):
                        st.info("Marked as false alarm.")
                        st.rerun()

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# ─── Pending Alerts ───────────────────────────────────────────────────────────
st.markdown("<div class='section-head'>&#9679; Pending Alerts &mdash; Awaiting Forest Officer Approval</div>", unsafe_allow_html=True)
st.markdown(
    "<div style='font-size:0.72rem;color:#8ab89a;margin-bottom:0.6rem'>"
    "No alert is dispatched without explicit forest officer approval. HITL gate is non-negotiable."
    "</div>", unsafe_allow_html=True
)

if not pending_alerts:
    st.markdown(
        "<div class='clay-card' style='color:#86efac;font-size:0.85rem'>"
        "&#10003; &nbsp; No alerts pending approval."
        "</div>", unsafe_allow_html=True
    )
else:
    st.markdown(
        f"<div style='font-size:0.8rem;color:#fde047;margin-bottom:0.6rem'>"
        f"&#9679; &nbsp; {len(pending_alerts)} alert(s) awaiting your approval before community dispatch."
        f"</div>", unsafe_allow_html=True
    )
    for alert in pending_alerts:
        level = alert.alert_level.value
        badge_cls = {"HIGH": "badge-high", "MEDIUM": "badge-medium", "LOW": "badge-low"}.get(level, "badge-ok")
        with st.expander(
            f"{level}  —  {alert.village} ({alert.district})  ·  Risk: {alert.village_risk_score:.2f}  ·  Det. Conf: {alert.detection_confidence:.2f}",
            expanded=(level == "HIGH")
        ):
            ac1, ac2 = st.columns([3, 1])
            with ac1:
                st.markdown(
                    f"<div class='glass-card'>"
                    f"<div style='margin-bottom:8px'>"
                    f"<span class='badge {badge_cls}'>{level}</span>"
                    f"<span style='font-size:0.75rem;color:#8ab89a;margin-left:10px'>"
                    f"Village Risk Score: <b style='color:#c8e6d4'>{alert.village_risk_score:.2f}</b> &nbsp;·&nbsp; "
                    f"Detection Confidence: <b style='color:#c8e6d4'>{alert.detection_confidence:.2f}</b>"
                    f"</span></div>"
                    f"<div style='font-size:0.75rem;color:#8ab89a;margin-bottom:6px;font-style:italic'>{alert.risk_explanation}</div>"
                    f"<div class='alert-en'><b style='color:#74d49a'>EN</b> &nbsp; {alert.message_en}</div>"
                    f"<div class='alert-kn'><b style='color:#74d49a'>KN</b> &nbsp; {alert.message_kn}</div>"
                    f"{''.join(f'<div style=\"font-size:0.75rem;color:#9fbeaa;margin-top:3px\">&#8226; {a}</div>' for a in alert.recommended_actions[:4])}"
                    f"</div>", unsafe_allow_html=True
                )
            with ac2:
                officer = st.text_input("Officer ID", value="KFD-RO-001", key=f"ao_{alert.alert_id}")
                if st.button("Approve & Dispatch", key=f"aa_{alert.alert_id}", type="primary", use_container_width=True):
                    if orch.approve_alert(alert.alert_id, officer):
                        st.success(f"Dispatched to {alert.village}.")
                        st.rerun()
                reject_reason = st.text_input("Rejection reason", key=f"ar_reason_{alert.alert_id}", placeholder="Optional")
                if st.button("Reject Alert", key=f"ar_{alert.alert_id}", use_container_width=True):
                    if orch.reject_alert(alert.alert_id, officer, reject_reason):
                        st.info("Rejected and logged.")
                        st.rerun()

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# ─── Audit Log ────────────────────────────────────────────────────────────────
with st.expander("Audit Log — last 10 events", expanded=False):
    from audit.log import read_audit_log
    entries = read_audit_log(last_n=10)
    if entries:
        st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
        for entry in reversed(entries):
            ts  = entry.get("timestamp", "")[:19].replace("T", " ")
            evt = entry.get("event_type", "")
            payload = entry.get("payload", {})
            colour = {
                "ALERT_APPROVED":   "#86efac",
                "ALERT_REJECTED":   "#fca5a5",
                "HITL_FLAGGED":     "#fde047",
                "HITL_RESOLVED":    "#93c5fd",
                "PIPELINE_RUN_START": "#c4b5fd",
                "PIPELINE_RUN_END":   "#c4b5fd",
                "ALERT_CREATED":    "#67e8f9",
            }.get(evt, "#6b8c76")
            detail = ""
            if "village" in payload:
                detail = f" &mdash; {payload['village']}"
            elif "detection_id" in payload:
                detail = f" &mdash; detection {str(payload.get('detection_id',''))[:8]}&hellip;"
            st.markdown(
                f"<div class='audit-entry' style='border-left:3px solid {colour}'>"
                f"<span style='color:#6b8c76;font-size:0.7rem'>{ts}</span> "
                f"<b style='color:{colour};font-size:0.75rem'>{evt}</b>"
                f"<span style='color:#8ab89a;font-size:0.72rem'>{detail}</span>"
                f"</div>",
                unsafe_allow_html=True
            )
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div style='color:#6b8c76;font-size:0.8rem;padding:8px'>No audit entries yet.</div>", unsafe_allow_html=True)

# ─── Footer ───────────────────────────────────────────────────────────────────
st.markdown(
    "<div style='text-align:center;font-size:0.65rem;color:#4a7a5a;margin-top:1.5rem;padding-top:1rem;"
    "border-top:1px solid rgba(255,255,255,0.05)'>"
    "ECO-HERD &nbsp;·&nbsp; Karnataka Forest Department &nbsp;·&nbsp; "
    "Synthetic data only &mdash; does not represent real elephant movements"
    "</div>",
    unsafe_allow_html=True
)
