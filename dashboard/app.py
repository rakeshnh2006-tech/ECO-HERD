"""
dashboard/app.py — ECO-HERD Dashboard
Pista green + amber yellow · Clay + Glassmorphism · Clean layout
"""
from __future__ import annotations
import sys, os, logging, base64
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
from streamlit_folium import st_folium

logging.basicConfig(level=logging.WARNING)

# ── Load logo as base64 for inline embedding ──────────────────────────────────
def _logo_b64() -> str:
    try:
        logo_path = Path(__file__).parent / "logo.png"
        return base64.b64encode(logo_path.read_bytes()).decode()
    except Exception:
        return ""

_LOGO = _logo_b64()
_LOGO_SRC = f"data:image/png;base64,{_LOGO}" if _LOGO else ""

st.set_page_config(
    page_title="ECO-HERD — Early Warning",
    page_icon=str(Path(__file__).parent / "logo.png") if (Path(__file__).parent / "logo.png").exists() else "🌿",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

/* ── Reset & base ── */
*, *::before, *::after { box-sizing: border-box; }
html, body, [class*="css"] {
    font-family: 'Inter', system-ui, sans-serif !important;
    color: #f0faf2 !important;
}

/* ── App BG — deep pista-black ── */
.stApp {
    background: radial-gradient(ellipse at 20% 0%, #0e2b1a 0%, #07160e 60%, #040d08 100%) !important;
    min-height: 100vh;
}

/* ── Hide chrome ── */
#MainMenu, footer, header { visibility: hidden; }
.block-container {
    padding: 1.2rem 1.8rem 2rem !important;
    max-width: 100% !important;
}

/* ═══════════════════════════════
   GLASS CARD
═══════════════════════════════ */
.gc {
    background: rgba(180,255,180,0.045);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid rgba(180,255,180,0.12);
    border-radius: 18px;
    padding: 1.2rem 1.4rem;
    box-shadow: 0 4px 24px rgba(0,0,0,0.35),
                inset 0 1px 0 rgba(255,255,255,0.06);
}

/* ═══════════════════════════════
   CLAY CARD — raised tactile
═══════════════════════════════ */
.cc {
    background: linear-gradient(145deg, #1a4228, #102a18);
    border: 1px solid rgba(166,255,140,0.14);
    border-radius: 20px;
    padding: 1.2rem 1.4rem;
    box-shadow: 5px 5px 16px rgba(0,0,0,0.45),
                -2px -2px 7px rgba(166,255,140,0.04);
}

/* ═══════════════════════════════
   METRIC CARDS
═══════════════════════════════ */
.mc {
    background: linear-gradient(150deg, #1c472b 0%, #0f2a19 100%);
    border: 1px solid rgba(166,255,140,0.15);
    border-radius: 16px;
    padding: 1rem 0.8rem;
    text-align: center;
    box-shadow: 4px 4px 14px rgba(0,0,0,0.4),
                -1px -1px 5px rgba(166,255,140,0.04);
    transition: transform 0.18s ease, box-shadow 0.18s ease;
}
.mc:hover {
    transform: translateY(-3px);
    box-shadow: 6px 8px 20px rgba(0,0,0,0.5);
}
.mc-num  { font-size: 2rem; font-weight: 700; color: #b6f7a0; line-height: 1; }
.mc-lbl  { font-size: 0.65rem; font-weight: 600; letter-spacing: 0.1em;
           text-transform: uppercase; color: #7bbf88; margin-top: 5px; }
.mc-warn { font-size: 0.62rem; color: #f5c842; margin-top: 3px; }

/* ═══════════════════════════════
   BADGES
═══════════════════════════════ */
.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 100px;
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}
.b-high   { background: rgba(239,68,68,0.18);  color: #fca5a5; border: 1px solid rgba(239,68,68,0.35); }
.b-medium { background: rgba(245,158,11,0.18); color: #fcd34d; border: 1px solid rgba(245,158,11,0.35); }
.b-low    { background: rgba(166,255,140,0.12); color: #b6f7a0; border: 1px solid rgba(166,255,140,0.3); }
.b-ok     { background: rgba(52,211,153,0.15); color: #6ee7b7; border: 1px solid rgba(52,211,153,0.3); }
.b-pend   { background: rgba(245,196,30,0.15); color: #f5c842; border: 1px solid rgba(245,196,30,0.35); }

/* ═══════════════════════════════
   SECTION HEADER
═══════════════════════════════ */
.sh {
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: #b6f7a0;
    margin-bottom: 0.75rem;
    display: flex;
    align-items: center;
    gap: 10px;
}
.sh::after {
    content: '';
    flex: 1;
    height: 1px;
    background: linear-gradient(90deg, rgba(166,255,140,0.25), transparent);
}

/* ═══════════════════════════════
   TRACE ROW
═══════════════════════════════ */
.tr {
    border-left: 2px solid rgba(166,255,140,0.25);
    padding: 3px 10px;
    margin: 2px 0;
    font-size: 0.75rem;
    color: #90b898;
    line-height: 1.4;
}
.tr b { color: #c8e6cc; }
.tr .ts { color: #4d7a56; font-size: 0.68rem; }

/* ═══════════════════════════════
   ALERT CARD
═══════════════════════════════ */
.ac {
    background: rgba(166,255,140,0.03);
    border: 1px solid rgba(166,255,140,0.09);
    border-radius: 14px;
    padding: 1rem 1.2rem;
    margin-bottom: 0.5rem;
}
.ac-en { font-size: 0.85rem; color: #d4f5d8; line-height: 1.55; margin: 5px 0; }
.ac-kn { font-size: 0.82rem; color: #9fd8a4; line-height: 1.55; font-style: italic; margin: 5px 0; }
.ac-action { font-size: 0.72rem; color: #7bbf88; margin-top: 2px; }

/* ═══════════════════════════════
   AUDIT ROW
═══════════════════════════════ */
.aur {
    padding: 3px 10px 3px 12px;
    margin: 2px 0;
    border-radius: 6px;
    font-size: 0.72rem;
    display: flex;
    gap: 8px;
    align-items: baseline;
}
.aur .at { color: #4d7a56; min-width: 130px; }
.aur .ae { font-weight: 600; }

/* ═══════════════════════════════
   BUTTONS
═══════════════════════════════ */
.stButton > button {
    background: linear-gradient(145deg, #1e5c34, #163f24) !important;
    color: #c8f5cc !important;
    border: 1px solid rgba(166,255,140,0.22) !important;
    border-radius: 10px !important;
    font-weight: 500 !important;
    font-size: 0.8rem !important;
    padding: 0.4rem 1rem !important;
    box-shadow: 3px 3px 10px rgba(0,0,0,0.35) !important;
    transition: all 0.18s !important;
    width: 100%;
}
.stButton > button:hover {
    background: linear-gradient(145deg, #256e3d, #1b4d2b) !important;
    transform: translateY(-1px) !important;
    box-shadow: 4px 5px 14px rgba(0,0,0,0.45) !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(145deg, #1f6b38, #165229) !important;
    border-color: rgba(182,247,160,0.35) !important;
    color: #d4f5d8 !important;
}

/* ═══════════════════════════════
   INPUTS
═══════════════════════════════ */
.stTextInput > div > div > input {
    background: #ffffff !important;
    border: 1px solid rgba(166,255,140,0.3) !important;
    border-radius: 9px !important;
    color: #0f2a19 !important;
    font-size: 0.8rem !important;
    padding: 6px 10px !important;
    caret-color: #0f2a19 !important;
}
.stTextInput > div > div > input::placeholder {
    color: #7a9e7e !important;
}
.stTextInput > div > div > input:focus {
    border-color: rgba(166,255,140,0.6) !important;
    box-shadow: 0 0 0 2px rgba(166,255,140,0.12) !important;
    outline: none !important;
}
.stTextInput label { color: #7bbf88 !important; font-size: 0.72rem !important; }

/* ═══════════════════════════════
   EXPANDER
═══════════════════════════════ */
details > summary {
    background: rgba(166,255,140,0.04) !important;
    border: 1px solid rgba(166,255,140,0.1) !important;
    border-radius: 10px !important;
    color: #b6f7a0 !important;
    font-size: 0.8rem !important;
    padding: 8px 12px !important;
    cursor: pointer;
}
.streamlit-expanderHeader {
    background: rgba(166,255,140,0.04) !important;
    border-radius: 10px !important;
    color: #b6f7a0 !important;
    font-size: 0.8rem !important;
}
.streamlit-expanderContent {
    border: 1px solid rgba(166,255,140,0.08) !important;
    border-top: none !important;
    border-radius: 0 0 10px 10px !important;
    background: rgba(0,0,0,0.15) !important;
}

/* ═══════════════════════════════
   ALERTS / TOASTS
═══════════════════════════════ */
.stAlert {
    border-radius: 12px !important;
    font-size: 0.82rem !important;
}

/* ═══════════════════════════════
   SPINNER
═══════════════════════════════ */
.stSpinner > div { border-top-color: #b6f7a0 !important; }

/* ═══════════════════════════════
   SCROLLBAR
═══════════════════════════════ */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(166,255,140,0.25); border-radius: 10px; }

/* ═══════════════════════════════
   COLUMN GAP FIX
═══════════════════════════════ */
[data-testid="column"] { padding: 0 6px !important; }
</style>
""", unsafe_allow_html=True)

# ─── Helpers ──────────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def _get_store():
    from memory.store import store
    return store

@st.cache_resource(show_spinner=False)
def _get_orchestrator():
    import orchestrator
    return orchestrator

def _load_risk_zones(store, confirmed):
    try:
        from tools.map_tools import compute_risk_zones
        from tools.data_fetcher import get_weather, get_crop_calendar
        if not confirmed:
            return []
        weather = get_weather()
        crops = get_crop_calendar()
        at_risk_crops = crops.get("at_risk_crops", []) if isinstance(crops, dict) else []
        return compute_risk_zones(confirmed, weather=weather, at_risk_crops=at_risk_crops)
    except Exception:
        return []

def _badge(level):
    cls = {"HIGH": "b-high", "MEDIUM": "b-medium", "LOW": "b-low"}.get(level, "b-ok")
    return f"<span class='badge {cls}'>{level}</span>"

store = _get_store()
orch  = _get_orchestrator()

# ─── Pull live data once ───────────────────────────────────────────────────────
detections     = store.get_detections()
all_alerts     = store.get_all_alerts()
confirmed      = [d for d in detections if d.is_elephant and not d.requires_hitl_review]
hitl_queue     = store.get_hitl_queue()
pending_alerts = store.get_pending_alerts()
dispatched     = [a for a in all_alerts if a.status.value == "DISPATCHED"]
risk_zones     = _load_risk_zones(store, confirmed)
last_run       = store.get_last_run()

# ══════════════════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════════════════
_logo_html = (
    f"<img src='{_LOGO_SRC}' style='"
    f"width:72px;height:72px;object-fit:contain;"
    f"border-radius:50%;border:2px solid rgba(166,255,140,0.25);"
    f"background:rgba(255,255,255,0.08);padding:4px;"
    f"box-shadow:0 0 16px rgba(166,255,140,0.2);"
    f"flex-shrink:0"
    f"'/>"
    if _LOGO_SRC else ""
)

st.markdown(
    f"""
<div style="
    background: linear-gradient(135deg, rgba(26,66,40,0.92) 0%, rgba(10,30,16,0.97) 100%);
    backdrop-filter: blur(24px);
    border: 1px solid rgba(166,255,140,0.15);
    border-radius: 20px;
    padding: 1rem 1.6rem;
    margin-bottom: 1rem;
    box-shadow: 0 6px 28px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.05);
    display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
">
  {_logo_html}
  <div style="flex:1;min-width:200px">
    <div style="font-size:0.58rem;font-weight:700;letter-spacing:0.18em;
        color:#b6f7a0;text-transform:uppercase;margin-bottom:3px">
      Karnataka Forest Department &nbsp;&#183;&nbsp; Agentic AI Early Warning
    </div>
    <div style="font-size:1.5rem;font-weight:700;color:#ffffff;line-height:1.2;letter-spacing:-0.01em">
      ECO&#8209;HERD
      <span style="font-weight:300;font-size:0.95rem;color:#8ed4a0">
        &nbsp;Human&#8209;Elephant Conflict System
      </span>
    </div>
  </div>
  <div style="display:flex;gap:8px;align-items:center;margin-left:auto">
    <div style="width:8px;height:8px;border-radius:50%;background:#b6f7a0;
        box-shadow:0 0 10px #b6f7a0"></div>
    <span style="font-size:0.68rem;color:#7bbf88;font-weight:500">Live</span>
  </div>
</div>
""",
    unsafe_allow_html=True
)

# ══════════════════════════════════════════════════════════════════════════════
# CONTROLS BAR
# ══════════════════════════════════════════════════════════════════════════════
c1, c2, c3 = st.columns([1.5, 1.5, 6])
with c1:
    run_clicked = st.button("▶  Run Pipeline", type="primary", use_container_width=True)
with c2:
    if st.button("↺  Refresh", use_container_width=True):
        st.rerun()
with c3:
    if last_run and last_run.end_time:
        ts = last_run.end_time.strftime("%d %b %Y · %H:%M UTC")
        errs = len(last_run.errors)
        err_col = "#fca5a5" if errs else "#b6f7a0"
        st.markdown(
            f"<div style='padding-top:9px;font-size:0.74rem;color:#7bbf88'>"
            f"Last run &nbsp;<b style='color:#d4f5d8'>{ts}</b>"
            f"&nbsp;·&nbsp; {len(last_run.agents_run)} agents"
            f"&nbsp;·&nbsp; <span style='color:{err_col}'>{errs} error{'s' if errs!=1 else ''}</span>"
            f"</div>",
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            "<div style='padding-top:9px;font-size:0.74rem;color:#4d7a56'>"
            "No run yet &nbsp;&#8212;&nbsp; click Run Pipeline to start"
            "</div>", unsafe_allow_html=True
        )

if run_clicked:
    with st.spinner("Running 3-agent pipeline…"):
        try:
            report = orch.run_once(hours_back=24)
            st.success(
                f"Pipeline complete — {len(report.agents_run)} agents · "
                f"{report.alerts_pending} alerts pending · "
                f"{report.hitl_flagged_count} HITL flagged"
            )
        except Exception as e:
            st.error(f"Pipeline error: {e}")
    st.rerun()

st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# METRIC ROW  — 5 cards
# ══════════════════════════════════════════════════════════════════════════════
metrics = [
    (len(detections),     "Detections",      None),
    (len(confirmed),      "Confirmed",        None),
    (len(hitl_queue),     "HITL Queue",       "Review needed" if hitl_queue else None),
    (len(pending_alerts), "Pending Approval", "Needs officer"  if pending_alerts else None),
    (len(dispatched),     "Dispatched",       None),
]
cols = st.columns(5, gap="small")
for col, (num, lbl, warn) in zip(cols, metrics):
    warn_html = f"<div class='mc-warn'>&#9650; {warn}</div>" if warn else ""
    col.markdown(
        f"<div class='mc'>"
        f"<div class='mc-num'>{num}</div>"
        f"<div class='mc-lbl'>{lbl}</div>"
        f"{warn_html}"
        f"</div>",
        unsafe_allow_html=True
    )

st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# MAP  +  AGENT TRACE
# ══════════════════════════════════════════════════════════════════════════════
map_col, trace_col = st.columns([3, 2], gap="medium")

with map_col:
    st.markdown("<div class='sh'>&#9632; Karnataka — Live Situation Map</div>", unsafe_allow_html=True)
    try:
        from dashboard.map_builder import build_map
        fmap = build_map(detections=detections, alerts=all_alerts, risk_zones=risk_zones)
        st_folium(fmap, width=None, height=500, returned_objects=[])
    except Exception as e:
        st.error(f"Map error: {e}")
        import traceback; st.code(traceback.format_exc())
    st.markdown(
        "<div style='font-size:0.62rem;color:#4d7a56;margin-top:6px;line-height:1.7'>"
        "&#9632; <span style='color:#fca5a5'>HIGH</span> &ensp;"
        "&#9632; <span style='color:#fcd34d'>MEDIUM</span> &ensp;"
        "&#9632; <span style='color:#b6f7a0'>LOW</span>"
        "&ensp;&#183;&ensp;Green = forest corridors"
        "&ensp;&#183;&ensp;Layer control (top-right) for Google Satellite"
        "</div>",
        unsafe_allow_html=True
    )

with trace_col:
    st.markdown("<div class='sh'>&#9632; Agent Execution Trace</div>", unsafe_allow_html=True)

    # Build entire trace as one HTML block so it stays inside the card
    trace_log = store.get_tool_trace_log(last_n=20)

    if trace_log:
        # Group by agent run — dedupe repetitive tool pairs into clean steps
        rows = []
        seen = set()
        for entry in reversed(trace_log):
            key = (entry.tool_name, entry.output_summary[:40])
            if key in seen:
                continue
            seen.add(key)
            icon  = "&#10003;" if not entry.error else "&#10007;"
            iclr  = "#b6f7a0"  if not entry.error else "#fca5a5"
            ts    = entry.timestamp.strftime("%H:%M:%S")
            err   = (f"<div style='color:#fca5a5;font-size:0.68rem;margin-top:1px'>"
                     f"{entry.error[:80]}</div>") if entry.error else ""
            rows.append(
                f"<div style='border-left:2px solid rgba(166,255,140,0.2);"
                f"padding:5px 10px;margin:3px 0;border-radius:0 8px 8px 0;"
                f"background:rgba(166,255,140,0.02)'>"
                f"<span style='color:{iclr};font-size:0.8rem'>{icon}</span>"
                f"&nbsp;<span style='color:#c8e6cc;font-weight:600;font-size:0.78rem'>"
                f"{entry.tool_name}</span>"
                f"&nbsp;<span style='color:#3d6645;font-size:0.68rem'>{ts}</span>"
                f"<div style='color:#6b9972;font-size:0.74rem;margin-top:1px'>"
                f"{entry.output_summary[:90]}</div>"
                f"{err}"
                f"</div>"
            )

        trace_html = (
            "<div style='"
            "background:rgba(180,255,180,0.03);"
            "border:1px solid rgba(180,255,180,0.1);"
            "border-radius:16px;"
            "padding:12px 14px;"
            "max-height:500px;"
            "overflow-y:auto;"
            "'>"
            + "".join(rows) +
            "</div>"
        )
    else:
        trace_html = (
            "<div style='"
            "background:rgba(180,255,180,0.03);"
            "border:1px solid rgba(180,255,180,0.1);"
            "border-radius:16px;"
            "padding:40px 14px;"
            "text-align:center;"
            "color:#3d6645;font-size:0.78rem;"
            "'>"
            "&#9632; No trace yet &mdash; run the pipeline to see activity"
            "</div>"
        )

    st.markdown(trace_html, unsafe_allow_html=True)

st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# HITL QUEUE
# ══════════════════════════════════════════════════════════════════════════════
st.markdown(
    "<div class='sh'>&#9650; HITL Verification Queue</div>",
    unsafe_allow_html=True
)

if not hitl_queue:
    st.markdown(
        "<div class='cc' style='color:#b6f7a0;font-size:0.82rem'>"
        "&#10003;&nbsp; HITL queue is empty — all detections above the confidence threshold."
        "</div>", unsafe_allow_html=True
    )
else:
    st.markdown(
        f"<div style='font-size:0.76rem;color:#f5c842;margin-bottom:0.6rem'>"
        f"&#9650;&nbsp; {len(hitl_queue)} detection(s) require forest officer verification"
        f"&nbsp;(threshold: 0.70)"
        f"</div>", unsafe_allow_html=True
    )
    for item in hitl_queue:
        det = item.detection
        with st.expander(
            f"Event {det.event_id[:8]}  ·  {det.nearest_village}  ·  "
            f"Conf {int(det.detection_confidence*100)}%  ·  {det.district}",
            expanded=True
        ):
            left, right = st.columns([3, 1], gap="medium")
            with left:
                st.markdown(
                    f"<div class='ac'>"
                    f"<div style='font-size:0.78rem;color:#b6f7a0;margin-bottom:6px'>"
                    f"Confidence: <b style='color:#f5c842'>{det.detection_confidence:.2f}</b>"
                    f"&nbsp;/&nbsp;threshold 0.70"
                    f"&nbsp;&nbsp;&#183;&nbsp;&nbsp;In corridor: <b>{'Yes' if det.in_corridor else 'No'}</b>"
                    f"&nbsp;&nbsp;&#183;&nbsp;&nbsp;Village: <b>{det.nearest_village}</b> ({det.distance_km:.1f} km)"
                    f"</div>"
                    f"<div style='font-size:0.78rem;color:#7bbf88;line-height:1.5'>"
                    f"{det.explanation[:300]}"
                    f"</div>"
                    f"</div>",
                    unsafe_allow_html=True
                )
            with right:
                oid = st.text_input("Officer ID", value="KFD-RO-001", key=f"ho_{item.item_id}")
                if st.button("Approve Detection", key=f"ha_{item.item_id}", type="primary"):
                    from schemas import HitlVerdict
                    if orch.resolve_hitl(item.item_id, HitlVerdict.APPROVED, oid):
                        st.success("Approved.")
                        st.rerun()
                if st.button("Reject  — False Alarm", key=f"hr_{item.item_id}"):
                    from schemas import HitlVerdict
                    if orch.resolve_hitl(item.item_id, HitlVerdict.REJECTED, oid, notes="Rejected via dashboard"):
                        st.info("Marked as false alarm.")
                        st.rerun()

st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# PENDING ALERTS
# ══════════════════════════════════════════════════════════════════════════════
st.markdown(
    "<div class='sh'>&#9679; Pending Alerts &mdash; Forest Officer Approval</div>",
    unsafe_allow_html=True
)
st.markdown(
    "<div style='font-size:0.68rem;color:#4d7a56;margin-bottom:0.7rem'>"
    "&#8212;&nbsp; No alert is dispatched without explicit forest officer approval (HITL gate, non-negotiable)"
    "</div>", unsafe_allow_html=True
)

if not pending_alerts:
    st.markdown(
        "<div class='cc' style='color:#b6f7a0;font-size:0.82rem'>"
        "&#10003;&nbsp; No alerts pending approval."
        "</div>", unsafe_allow_html=True
    )
else:
    st.markdown(
        f"<div style='font-size:0.76rem;color:#f5c842;margin-bottom:0.6rem'>"
        f"&#9679;&nbsp; {len(pending_alerts)} alert(s) awaiting your approval"
        f"</div>", unsafe_allow_html=True
    )
    for alert in pending_alerts:
        level = alert.alert_level.value
        badge_cls = {"HIGH": "b-high", "MEDIUM": "b-medium", "LOW": "b-low"}.get(level, "b-ok")
        with st.expander(
            f"{level}  ·  {alert.village}, {alert.district}"
            f"  ·  Risk {alert.village_risk_score:.2f}"
            f"  ·  Conf {alert.detection_confidence:.2f}",
            expanded=(level == "HIGH")
        ):
            left, right = st.columns([3, 1], gap="medium")
            with left:
                st.markdown(
                    f"<div class='ac'>"
                    # top row — badge + scores
                    f"<div style='display:flex;align-items:center;gap:10px;margin-bottom:8px'>"
                    f"<span class='badge {badge_cls}'>{level}</span>"
                    f"<span style='font-size:0.72rem;color:#7bbf88'>"
                    f"Village Risk Score <b style='color:#d4f5d8'>{alert.village_risk_score:.2f}</b>"
                    f"&nbsp;&nbsp;&#183;&nbsp;&nbsp;"
                    f"Detection Confidence <b style='color:#d4f5d8'>{alert.detection_confidence:.2f}</b>"
                    f"</span></div>"
                    # risk explanation
                    f"<div style='font-size:0.72rem;color:#7bbf88;margin-bottom:7px;'>"
                    f"{alert.risk_explanation}</div>"
                    # EN message
                    f"<div class='ac-en'>"
                    f"<span style='font-size:0.63rem;font-weight:700;letter-spacing:0.08em;"
                    f"color:#b6f7a0;text-transform:uppercase;margin-right:8px'>EN</span>"
                    f"{alert.message_en}</div>"
                    # KN message
                    f"<div class='ac-kn'>"
                    f"<span style='font-size:0.63rem;font-weight:700;letter-spacing:0.08em;"
                    f"color:#b6f7a0;text-transform:uppercase;margin-right:8px;font-style:normal'>KN</span>"
                    f"{alert.message_kn}</div>"
                    # actions
                    f"<div style='margin-top:8px;padding-top:8px;border-top:1px solid rgba(166,255,140,0.08)'>"
                    + "".join(
                        f"<div class='ac-action'>&#8250; {a}</div>"
                        for a in alert.recommended_actions[:4]
                    ) +
                    f"</div>"
                    f"</div>",
                    unsafe_allow_html=True
                )
            with right:
                st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
                officer = st.text_input("Officer ID", value="KFD-RO-001", key=f"ao_{alert.alert_id}")
                if st.button("Approve & Dispatch", key=f"aa_{alert.alert_id}", type="primary"):
                    if orch.approve_alert(alert.alert_id, officer):
                        st.success(f"Dispatched to {alert.village}.")
                        st.rerun()
                st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
                reason = st.text_input("Reject reason", key=f"rr_{alert.alert_id}", placeholder="Optional")
                if st.button("Reject Alert", key=f"ra_{alert.alert_id}"):
                    if orch.reject_alert(alert.alert_id, officer, reason):
                        st.info("Rejected and logged.")
                        st.rerun()

st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# AUDIT LOG
# ══════════════════════════════════════════════════════════════════════════════
with st.expander("Audit Log — last 10 events", expanded=False):
    from audit.log import read_audit_log
    entries = read_audit_log(last_n=10)
    if entries:
        COLOURS = {
            "ALERT_APPROVED":    "#b6f7a0",
            "ALERT_REJECTED":    "#fca5a5",
            "HITL_FLAGGED":      "#f5c842",
            "HITL_RESOLVED":     "#93c5fd",
            "PIPELINE_RUN_START":"#c4b5fd",
            "PIPELINE_RUN_END":  "#c4b5fd",
            "ALERT_CREATED":     "#67e8f9",
        }
        st.markdown("<div class='gc' style='padding:0.8rem 1rem'>", unsafe_allow_html=True)
        for entry in reversed(entries):
            ts      = entry.get("timestamp", "")[:19].replace("T", " ")
            evt     = entry.get("event_type", "")
            payload = entry.get("payload", {})
            colour  = COLOURS.get(evt, "#4d7a56")
            detail  = ""
            if "village" in payload:
                detail = f"&nbsp;&mdash;&nbsp;{payload['village']}"
            elif "detection_id" in payload:
                detail = f"&nbsp;&mdash;&nbsp;detection {str(payload.get('detection_id',''))[:8]}&hellip;"
            st.markdown(
                f"<div class='aur' style='border-left:2px solid {colour}'>"
                f"<span class='at'>{ts}</span>"
                f"<span class='ae' style='color:{colour}'>{evt}</span>"
                f"<span style='color:#7bbf88;font-size:0.7rem'>{detail}</span>"
                f"</div>",
                unsafe_allow_html=True
            )
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.markdown(
            "<div style='color:#3d6645;font-size:0.78rem;padding:8px'>No audit entries yet.</div>",
            unsafe_allow_html=True
        )

# ══════════════════════════════════════════════════════════════════════════════
# FOOTER
# ══════════════════════════════════════════════════════════════════════════════
st.markdown(
    "<div style='text-align:center;font-size:0.6rem;color:#2d5235;"
    "margin-top:2rem;padding-top:0.8rem;"
    "border-top:1px solid rgba(166,255,140,0.07)'>"
    "ECO&#8209;HERD &nbsp;&#183;&nbsp; Karnataka Forest Department &nbsp;&#183;&nbsp; "
    "Synthetic data only &mdash; does not represent real elephant movements"
    "</div>",
    unsafe_allow_html=True
)
