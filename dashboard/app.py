"""
dashboard/app.py — ECO-HERD Dashboard
Forest Intelligence · Premium enterprise design
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
    page_icon=str(Path(__file__).parent / "logo.png") if (Path(__file__).parent / "logo.png").exists() else "&#127807;",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── CSS — Forest Intelligence Theme ─────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

/* ══ Design tokens ══════════════════════════════════════════════════════════ */
:root {
    --c-dark:    #123B2A;
    --c-forest:  #246B49;
    --c-accent:  #72B788;
    --c-bg:      #F4F7F2;
    --c-card:    #FFFFFF;
    --c-soft:    #EAF4EC;
    --c-txt:     #183629;
    --c-muted:   #64776B;
    --c-border:  #D0E5D8;
    --c-amber:   #F4B942;
    --c-red:     #D93636;
    --c-blue:    #2878B8;
    --c-shadow:  rgba(18,59,42,0.08);
    --c-shadow-md: rgba(18,59,42,0.13);
    --radius-sm: 8px;
    --radius-md: 12px;
    --radius-lg: 16px;
}

/* ══ Reset & base ══════════════════════════════════════════════════════════ */
*, *::before, *::after { box-sizing: border-box; }
html, body, [class*="css"] {
    font-family: 'Inter', system-ui, -apple-system, sans-serif !important;
    color: var(--c-txt) !important;
    -webkit-font-smoothing: antialiased;
}

/* ══ App background ════════════════════════════════════════════════════════ */
.stApp {
    background-color: var(--c-bg) !important;
    min-height: 100vh;
}

/* ══ Hide Streamlit chrome ═════════════════════════════════════════════════ */
#MainMenu, footer, header { visibility: hidden; }
.block-container {
    padding: 0 1.75rem 2rem !important;
    max-width: 100% !important;
}

/* ══ GLASS CARD ════════════════════════════════════════════════════════════ */
.gc {
    background: var(--c-card);
    border: 1px solid var(--c-border);
    border-radius: var(--radius-lg);
    padding: 1.25rem 1.5rem;
    box-shadow: 0 2px 12px var(--c-shadow);
}

/* ══ CLAY CARD ═════════════════════════════════════════════════════════════ */
.cc {
    background: var(--c-card);
    border: 1px solid var(--c-border);
    border-radius: var(--radius-lg);
    padding: 1.25rem 1.5rem;
    box-shadow: 0 2px 10px var(--c-shadow);
}

/* ══ METRIC CARDS ══════════════════════════════════════════════════════════ */
.mc {
    background: var(--c-card);
    border: 1px solid var(--c-border);
    border-top: 3px solid var(--c-forest);
    border-radius: var(--radius-lg);
    padding: 1.1rem 0.9rem 1rem;
    text-align: center;
    box-shadow: 0 2px 10px var(--c-shadow);
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.mc:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 18px var(--c-shadow-md);
}
.mc-num  {
    font-size: 2.1rem;
    font-weight: 700;
    color: var(--c-dark);
    line-height: 1;
    letter-spacing: -0.02em;
}
.mc-lbl  {
    font-size: 0.63rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--c-muted);
    margin-top: 6px;
}
.mc-warn {
    font-size: 0.62rem;
    color: var(--c-amber);
    margin-top: 4px;
    font-weight: 500;
}

/* ══ BADGES ════════════════════════════════════════════════════════════════ */
.badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 100px;
    font-size: 0.63rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}
.b-high   { background: #FDEAEA; color: var(--c-red);    border: 1px solid #F5AAAA; }
.b-medium { background: #FEF6E4; color: #B8600A;         border: 1px solid #F4CA80; }
.b-low    { background: var(--c-soft); color: var(--c-forest); border: 1px solid #A8D4B4; }
.b-ok     { background: #E6F7F0; color: #1A7A4A;         border: 1px solid #80CCA4; }
.b-pend   { background: #FEF9E6; color: #A07010;         border: 1px solid #F0D88A; }

/* ══ SECTION HEADER ════════════════════════════════════════════════════════ */
.sh {
    font-size: 0.63rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--c-forest);
    margin-bottom: 0.8rem;
    padding-bottom: 0.5rem;
    display: flex;
    align-items: center;
    gap: 10px;
    border-bottom: 1px solid var(--c-border);
}
.sh::before {
    content: '';
    width: 3px;
    height: 14px;
    background: var(--c-forest);
    border-radius: 2px;
    flex-shrink: 0;
}

/* ══ TRACE ROW ═════════════════════════════════════════════════════════════ */
.tr {
    border-left: 2px solid var(--c-border);
    padding: 4px 10px;
    margin: 2px 0;
    font-size: 0.74rem;
    color: var(--c-muted);
    line-height: 1.45;
}
.tr b { color: var(--c-txt); }
.tr .ts { color: var(--c-accent); font-size: 0.67rem; }

/* ══ ALERT CARD ════════════════════════════════════════════════════════════ */
.ac {
    background: var(--c-soft);
    border: 1px solid var(--c-border);
    border-radius: var(--radius-md);
    padding: 1rem 1.2rem;
    margin-bottom: 0.5rem;
}
.ac-en     { font-size: 0.84rem; color: var(--c-txt);   line-height: 1.6; margin: 6px 0; }
.ac-kn     { font-size: 0.82rem; color: var(--c-forest); line-height: 1.6; font-style: italic; margin: 6px 0; }
.ac-action { font-size: 0.72rem; color: var(--c-muted); margin-top: 3px; }

/* ══ AUDIT ROW ═════════════════════════════════════════════════════════════ */
.aur {
    padding: 4px 10px 4px 12px;
    margin: 2px 0;
    border-radius: 6px;
    font-size: 0.72rem;
    display: flex;
    gap: 10px;
    align-items: baseline;
    background: var(--c-soft);
}
.aur .at { color: var(--c-muted); min-width: 136px; font-variant-numeric: tabular-nums; }
.aur .ae { font-weight: 600; }

/* ══ BUTTONS ═══════════════════════════════════════════════════════════════ */
.stButton > button {
    background: var(--c-card) !important;
    color: var(--c-forest) !important;
    border: 1.5px solid var(--c-border) !important;
    border-radius: var(--radius-sm) !important;
    font-weight: 500 !important;
    font-size: 0.8rem !important;
    padding: 0.42rem 1rem !important;
    box-shadow: 0 1px 4px var(--c-shadow) !important;
    transition: all 0.15s ease !important;
    width: 100%;
    letter-spacing: 0.01em;
}
.stButton > button:hover {
    background: var(--c-soft) !important;
    border-color: var(--c-accent) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 3px 10px var(--c-shadow-md) !important;
}
.stButton > button[kind="primary"] {
    background: var(--c-forest) !important;
    border-color: var(--c-forest) !important;
    color: #ffffff !important;
    box-shadow: 0 2px 8px rgba(36,107,73,0.28) !important;
}
.stButton > button[kind="primary"]:hover {
    background: var(--c-dark) !important;
    border-color: var(--c-dark) !important;
    color: #ffffff !important;
    box-shadow: 0 4px 12px rgba(18,59,42,0.32) !important;
}

/* ══ INPUTS ════════════════════════════════════════════════════════════════ */
.stTextInput > div > div > input {
    background: var(--c-card) !important;
    border: 1.5px solid var(--c-border) !important;
    border-radius: var(--radius-sm) !important;
    color: var(--c-txt) !important;
    font-size: 0.8rem !important;
    padding: 7px 10px !important;
    caret-color: var(--c-forest) !important;
    transition: border-color 0.15s, box-shadow 0.15s !important;
}
.stTextInput > div > div > input::placeholder { color: var(--c-muted) !important; }
.stTextInput > div > div > input:focus {
    border-color: var(--c-forest) !important;
    box-shadow: 0 0 0 3px rgba(36,107,73,0.1) !important;
    outline: none !important;
}
.stTextInput label { color: var(--c-muted) !important; font-size: 0.72rem !important; font-weight: 500 !important; }

/* ══ EXPANDER ══════════════════════════════════════════════════════════════ */
details > summary {
    background: var(--c-soft) !important;
    border: 1px solid var(--c-border) !important;
    border-radius: var(--radius-sm) !important;
    color: var(--c-dark) !important;
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    padding: 9px 14px !important;
    cursor: pointer;
}
.streamlit-expanderHeader {
    background: var(--c-soft) !important;
    border-radius: var(--radius-sm) !important;
    color: var(--c-dark) !important;
    font-size: 0.82rem !important;
    font-weight: 500 !important;
}
.streamlit-expanderContent {
    border: 1px solid var(--c-border) !important;
    border-top: none !important;
    border-radius: 0 0 var(--radius-sm) var(--radius-sm) !important;
    background: var(--c-card) !important;
}

/* ══ ALERTS / TOASTS ═══════════════════════════════════════════════════════ */
.stAlert { border-radius: var(--radius-md) !important; font-size: 0.82rem !important; }

/* ══ SPINNER ═══════════════════════════════════════════════════════════════ */
.stSpinner > div { border-top-color: var(--c-forest) !important; }

/* ══ SCROLLBAR ═════════════════════════════════════════════════════════════ */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: var(--c-bg); }
::-webkit-scrollbar-thumb { background: var(--c-border); border-radius: 10px; }
::-webkit-scrollbar-thumb:hover { background: var(--c-accent); }

/* ══ COLUMN GAP FIX ════════════════════════════════════════════════════════ */
[data-testid="column"] { padding: 0 6px !important; }

/* ══ RESPONSIVE ════════════════════════════════════════════════════════════ */
@media (max-width: 768px) {
    .block-container { padding: 0 0.75rem 2rem !important; }
    .mc-num { font-size: 1.6rem; }
}
</style>
""", unsafe_allow_html=True)

# ─── Bootstrap mock data ──────────────────────────────────────────────────────
# Runs once per Streamlit worker process. Seeds the store with realistic mock
# data if it is empty or only contains stale FALLBACK responses from failed
# LLM calls.  Safe to run even when real pipeline data is present — it checks
# before writing.
def _bootstrap_mock():
    try:
        from memory.store import store as _s
        dets = _s.get_detections()
        all_fallback = not dets or all("FALLBACK" in (d.explanation or "") for d in dets)
        if not all_fallback:
            return  # real data already present — do nothing
        _s.reset()
        _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _root not in sys.path:
            sys.path.insert(0, _root)
        import importlib
        if "mock_seed" in sys.modules:
            importlib.reload(sys.modules["mock_seed"])
        else:
            import mock_seed  # noqa: F401
    except Exception:
        pass

_bootstrap_mock()

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
# HEADER — deep forest green bar
# ══════════════════════════════════════════════════════════════════════════════
_logo_html = (
    f"<img src='{_LOGO_SRC}' style='"
    f"width:52px;height:52px;object-fit:contain;"
    f"border-radius:50%;border:2px solid rgba(255,255,255,0.25);"
    f"background:rgba(255,255,255,0.1);padding:3px;"
    f"flex-shrink:0"
    f"'/>"
    if _LOGO_SRC else ""
)

st.markdown(
    f"""
<div style="
    background: #123B2A;
    border-radius: 0 0 0 0;
    padding: 0.9rem 1.75rem;
    margin: 0 -1.75rem 1.25rem;
    display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
    box-shadow: 0 2px 12px rgba(18,59,42,0.18);
">
  {_logo_html}
  <div style="flex:1;min-width:200px">
    <div style="font-size:0.56rem;font-weight:600;letter-spacing:0.2em;
        color:#72B788;text-transform:uppercase;margin-bottom:2px">
      Karnataka Forest Department &nbsp;&#8231;&nbsp; Agentic AI Early Warning
    </div>
    <div style="font-size:1.45rem;font-weight:700;color:#ffffff;line-height:1.2;letter-spacing:-0.015em">
      ECO&#8209;HERD
      <span style="font-weight:300;font-size:0.9rem;color:#A8CCBB;margin-left:6px">
        Human&#8209;Elephant Conflict System
      </span>
    </div>
  </div>
  <div style="display:flex;gap:8px;align-items:center;margin-left:auto;
      background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.15);
      border-radius:100px;padding:5px 12px 5px 10px">
    <div style="width:7px;height:7px;border-radius:50%;background:#72B788;flex-shrink:0"></div>
    <span style="font-size:0.68rem;color:#A8CCBB;font-weight:500;letter-spacing:0.04em">Live</span>
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
    run_clicked = st.button("&#9654;  Run Pipeline", type="primary", use_container_width=True)
with c2:
    if st.button("&#8635;  Refresh", use_container_width=True):
        st.rerun()
with c3:
    if last_run and last_run.end_time:
        ts   = last_run.end_time.strftime("%d %b %Y &middot; %H:%M UTC")
        errs = len(last_run.errors)
        err_col = "#D93636" if errs else "#246B49"
        st.markdown(
            f"<div style='padding-top:9px;font-size:0.74rem;color:#64776B'>"
            f"Last run &nbsp;<b style='color:#183629'>{ts}</b>"
            f"&nbsp;&middot;&nbsp; {len(last_run.agents_run)} agents"
            f"&nbsp;&middot;&nbsp; <span style='color:{err_col};font-weight:600'>"
            f"{errs} error{'s' if errs!=1 else ''}</span>"
            f"</div>",
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            "<div style='padding-top:9px;font-size:0.74rem;color:#64776B'>"
            "No run yet &nbsp;&mdash;&nbsp; click <b>Run Pipeline</b> to start"
            "</div>", unsafe_allow_html=True
        )

if run_clicked:
    with st.spinner("Running 3-agent pipeline..."):
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

st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

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

st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# MAP  +  AGENT TRACE
# ══════════════════════════════════════════════════════════════════════════════
map_col, trace_col = st.columns([3, 2], gap="medium")

with map_col:
    st.markdown("<div class='sh'>Karnataka &mdash; Live Situation Map</div>", unsafe_allow_html=True)
    try:
        from dashboard.map_builder import build_map
        fmap = build_map(detections=detections, alerts=all_alerts, risk_zones=risk_zones)
        st_folium(fmap, width=None, height=500, returned_objects=[])
    except Exception as e:
        st.error(f"Map error: {e}")
        import traceback; st.code(traceback.format_exc())
    st.markdown(
        "<div style='font-size:0.62rem;color:#64776B;margin-top:8px;line-height:1.8'>"
        "&#9632; <span style='color:#D93636;font-weight:600'>HIGH</span> &ensp;"
        "&#9632; <span style='color:#F4B942;font-weight:600'>MEDIUM</span> &ensp;"
        "&#9632; <span style='color:#246B49;font-weight:600'>LOW</span>"
        "&ensp;&middot;&ensp;Green shading = forest corridors"
        "&ensp;&middot;&ensp;Layer control (top-right) for Google Satellite"
        "</div>",
        unsafe_allow_html=True
    )

with trace_col:
    st.markdown("<div class='sh'>Agent Execution Trace</div>", unsafe_allow_html=True)

    trace_log = store.get_tool_trace_log(last_n=20)

    if trace_log:
        rows = []
        seen = set()
        for entry in reversed(trace_log):
            key = (entry.tool_name, entry.output_summary[:40])
            if key in seen:
                continue
            seen.add(key)
            icon  = "&#10003;" if not entry.error else "&#10007;"
            iclr  = "#246B49"  if not entry.error else "#D93636"
            ibg   = "#E6F7F0"  if not entry.error else "#FDEAEA"
            ts    = entry.timestamp.strftime("%H:%M:%S")
            err   = (f"<div style='color:#D93636;font-size:0.68rem;margin-top:2px'>"
                     f"{entry.error[:90]}</div>") if entry.error else ""
            rows.append(
                f"<div style='border-left:3px solid {iclr};"
                f"padding:6px 10px;margin:3px 0;border-radius:0 8px 8px 0;"
                f"background:#FFFFFF;'>"
                f"<div style='display:flex;align-items:center;gap:6px'>"
                f"<span style='background:{ibg};color:{iclr};font-size:0.72rem;"
                f"width:18px;height:18px;border-radius:50%;display:inline-flex;"
                f"align-items:center;justify-content:center;flex-shrink:0'>{icon}</span>"
                f"<span style='color:#183629;font-weight:600;font-size:0.78rem'>"
                f"{entry.tool_name}</span>"
                f"<span style='color:#64776B;font-size:0.67rem;margin-left:auto'>{ts}</span>"
                f"</div>"
                f"<div style='color:#64776B;font-size:0.73rem;margin-top:3px;line-height:1.45'>"
                f"{entry.output_summary[:95]}</div>"
                f"{err}"
                f"</div>"
            )

        trace_html = (
            "<div style='"
            "background:#F4F7F2;"
            "border:1px solid #D0E5D8;"
            "border-radius:12px;"
            "padding:10px 12px;"
            "max-height:500px;"
            "overflow-y:auto;"
            "display:flex;flex-direction:column;gap:1px;"
            "'>"
            + "".join(rows) +
            "</div>"
        )
    else:
        trace_html = (
            "<div style='"
            "background:#F4F7F2;"
            "border:1px solid #D0E5D8;"
            "border-radius:12px;"
            "padding:48px 14px;"
            "text-align:center;"
            "color:#64776B;font-size:0.78rem;"
            "'>"
            "No trace yet &mdash; run the pipeline to see agent activity"
            "</div>"
        )

    st.markdown(trace_html, unsafe_allow_html=True)

st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# HITL QUEUE
# ══════════════════════════════════════════════════════════════════════════════
st.markdown(
    "<div class='sh'>HITL Verification Queue</div>",
    unsafe_allow_html=True
)

if not hitl_queue:
    st.markdown(
        "<div class='cc' style='color:#246B49;font-size:0.82rem;display:flex;align-items:center;gap:8px'>"
        "<span style='background:#E6F7F0;color:#246B49;border-radius:50%;width:22px;height:22px;"
        "display:inline-flex;align-items:center;justify-content:center;font-size:0.8rem;flex-shrink:0'>"
        "&#10003;</span>"
        "HITL queue is empty &mdash; all detections are above the confidence threshold."
        "</div>", unsafe_allow_html=True
    )
else:
    st.markdown(
        f"<div style='font-size:0.76rem;color:#B8600A;background:#FEF6E4;border:1px solid #F4CA80;"
        f"border-radius:8px;padding:8px 14px;margin-bottom:0.75rem;display:inline-flex;gap:8px;align-items:center'>"
        f"&#9650;&nbsp; <b>{len(hitl_queue)}</b> detection(s) require forest officer verification"
        f"&nbsp;(confidence threshold: 0.70)"
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
                conf_col = "#D93636" if det.detection_confidence < 0.5 else "#B8600A"
                st.markdown(
                    f"<div class='ac'>"
                    f"<div style='font-size:0.78rem;color:#64776B;margin-bottom:8px;display:flex;gap:16px;flex-wrap:wrap'>"
                    f"<span>Confidence: <b style='color:{conf_col}'>{det.detection_confidence:.2f}</b>"
                    f" <span style='color:#64776B;font-weight:400'>/ threshold 0.70</span></span>"
                    f"<span>In corridor: <b style='color:#183629'>{'Yes' if det.in_corridor else 'No'}</b></span>"
                    f"<span>Village: <b style='color:#183629'>{det.nearest_village}</b> ({det.distance_km:.1f} km)</span>"
                    f"</div>"
                    f"<div style='font-size:0.79rem;color:#183629;line-height:1.6'>"
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
                if st.button("Reject — False Alarm", key=f"hr_{item.item_id}"):
                    from schemas import HitlVerdict
                    if orch.resolve_hitl(item.item_id, HitlVerdict.REJECTED, oid, notes="Rejected via dashboard"):
                        st.info("Marked as false alarm.")
                        st.rerun()

st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# PENDING ALERTS
# ══════════════════════════════════════════════════════════════════════════════
st.markdown(
    "<div class='sh'>Pending Alerts &mdash; Forest Officer Approval</div>",
    unsafe_allow_html=True
)
st.markdown(
    "<div style='font-size:0.7rem;color:#64776B;background:#EAF4EC;border:1px solid #D0E5D8;"
    "border-radius:8px;padding:7px 14px;margin-bottom:0.9rem;display:inline-flex;gap:6px;align-items:center'>"
    "&#8212;&nbsp; No alert is dispatched without explicit forest officer approval (HITL gate, non-negotiable)"
    "</div>", unsafe_allow_html=True
)

if not pending_alerts:
    st.markdown(
        "<div class='cc' style='color:#246B49;font-size:0.82rem;display:flex;align-items:center;gap:8px'>"
        "<span style='background:#E6F7F0;color:#246B49;border-radius:50%;width:22px;height:22px;"
        "display:inline-flex;align-items:center;justify-content:center;font-size:0.8rem;flex-shrink:0'>"
        "&#10003;</span>"
        "No alerts pending approval."
        "</div>", unsafe_allow_html=True
    )
else:
    st.markdown(
        f"<div style='font-size:0.76rem;color:#B8600A;background:#FEF6E4;border:1px solid #F4CA80;"
        f"border-radius:8px;padding:8px 14px;margin-bottom:0.75rem;display:inline-flex;gap:8px;align-items:center'>"
        f"&#9679;&nbsp; <b>{len(pending_alerts)}</b> alert(s) awaiting your approval"
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
                # accent colour for the left border per alert level
                accent = {"HIGH": "#D93636", "MEDIUM": "#F4B942", "LOW": "#246B49"}.get(level, "#246B49")
                st.markdown(
                    f"<div class='ac' style='border-left:4px solid {accent}'>"
                    # top row — badge + scores
                    f"<div style='display:flex;align-items:center;gap:10px;margin-bottom:10px;flex-wrap:wrap'>"
                    f"<span class='badge {badge_cls}'>{level}</span>"
                    f"<span style='font-size:0.72rem;color:#64776B'>"
                    f"Village Risk Score <b style='color:#183629'>{alert.village_risk_score:.2f}</b>"
                    f"&nbsp;&middot;&nbsp;"
                    f"Detection Confidence <b style='color:#183629'>{alert.detection_confidence:.2f}</b>"
                    f"</span></div>"
                    # risk explanation
                    f"<div style='font-size:0.73rem;color:#64776B;margin-bottom:9px;line-height:1.55'>"
                    f"{alert.risk_explanation}</div>"
                    # EN message
                    f"<div class='ac-en'>"
                    f"<span style='font-size:0.6rem;font-weight:700;letter-spacing:0.1em;"
                    f"color:#246B49;text-transform:uppercase;margin-right:8px;"
                    f"background:#EAF4EC;border:1px solid #A8D4B4;border-radius:4px;padding:1px 6px'>EN</span>"
                    f"{alert.message_en}</div>"
                    # KN message
                    f"<div class='ac-kn'>"
                    f"<span style='font-size:0.6rem;font-weight:700;letter-spacing:0.1em;"
                    f"color:#2878B8;text-transform:uppercase;margin-right:8px;font-style:normal;"
                    f"background:#E8F2FA;border:1px solid #A0C4E8;border-radius:4px;padding:1px 6px'>KN</span>"
                    f"{alert.message_kn}</div>"
                    # recommended actions
                    f"<div style='margin-top:10px;padding-top:10px;border-top:1px solid #D0E5D8'>"
                    + "".join(
                        f"<div class='ac-action'>&#8250;&nbsp; {a}</div>"
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

st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# AUDIT LOG
# ══════════════════════════════════════════════════════════════════════════════
with st.expander("Audit Log — last 10 events", expanded=False):
    from audit.log import read_audit_log
    entries = read_audit_log(last_n=10)
    if entries:
        COLOURS = {
            "ALERT_APPROVED":    "#246B49",
            "ALERT_REJECTED":    "#D93636",
            "HITL_FLAGGED":      "#F4B942",
            "HITL_RESOLVED":     "#2878B8",
            "PIPELINE_RUN_START":"#64776B",
            "PIPELINE_RUN_END":  "#246B49",
            "ALERT_CREATED":     "#2878B8",
        }
        st.markdown("<div class='gc' style='padding:0.6rem 0.8rem'>", unsafe_allow_html=True)
        for entry in reversed(entries):
            ts      = entry.get("timestamp", "")[:19].replace("T", " ")
            evt     = entry.get("event_type", "")
            payload = entry.get("payload", {})
            colour  = COLOURS.get(evt, "#64776B")
            detail  = ""
            if "village" in payload:
                detail = f"&nbsp;&mdash;&nbsp;{payload['village']}"
            elif "detection_id" in payload:
                detail = f"&nbsp;&mdash;&nbsp;detection {str(payload.get('detection_id',''))[:8]}&hellip;"
            st.markdown(
                f"<div class='aur' style='border-left:3px solid {colour}'>"
                f"<span class='at'>{ts}</span>"
                f"<span class='ae' style='color:{colour}'>{evt}</span>"
                f"<span style='color:#64776B;font-size:0.7rem'>{detail}</span>"
                f"</div>",
                unsafe_allow_html=True
            )
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.markdown(
            "<div style='color:#64776B;font-size:0.78rem;padding:10px'>No audit entries yet.</div>",
            unsafe_allow_html=True
        )

# ══════════════════════════════════════════════════════════════════════════════
# FOOTER
# ══════════════════════════════════════════════════════════════════════════════
st.markdown(
    "<div style='text-align:center;font-size:0.6rem;color:#64776B;"
    "margin-top:2.5rem;padding-top:1rem;"
    "border-top:1px solid #D0E5D8'>"
    "ECO&#8209;HERD &nbsp;&middot;&nbsp; Karnataka Forest Department &nbsp;&middot;&nbsp; "
    "Synthetic data only &mdash; does not represent real elephant movements"
    "</div>",
    unsafe_allow_html=True
)
