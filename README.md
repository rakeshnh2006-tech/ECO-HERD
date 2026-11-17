# Human-Elephant Conflict Early Warning & Community Safety System

An Agentic AI-based system for the Karnataka Forest Department to detect elephant movement near human settlements, predict conflict hotspots, and issue timely bilingual alerts.

Built for the **Agentic AI Hackathon — Bengaluru, Karnataka** using IBM Bob + IBM Granite 4 + Google Gemini + Groq + OmniRoute.

---

## Architecture

```
Orchestrator (pipeline runner + HITL gate)
    │
    ├── Agent 1: Wildlife Data Analysis  (IBM Granite 4)
    ├── Agent 2: Elephant Detection       (Google Gemini)
    └── Agent 3: Early Warning & Alert    (Groq)
                │
         MCP Tools (data_fetcher, map_tools, alert_tools)
                │
         Data Sources
           ├── Synthetic: GPS/camera/sensor feeds [SYNTHETIC DATA — see disclaimer]
           └── Real public: OpenStreetMap, IMD, Global Forest Watch
                │
         Streamlit Dashboard (Folium map + HITL queue + alert approval)
```

---

## ⚠️ Data Disclaimer

Real-time data feeds (GPS collar positions, camera trap events, acoustic sensor triggers, ranger patrol logs) are **generated synthetically** for demonstration purposes. They do not represent real elephant movements or actual field data.

Static reference data (village locations, forest boundaries, weather, crop calendars) is sourced from publicly available datasets (OpenStreetMap, IMD, Karnataka Open Data Portal).

All synthetic records carry `data_source: "synthetic"` and the system surfaces this disclaimer in the dashboard.

---

## Setup

### 1. Prerequisites

- Python 3.12
- pip

### 2. Install dependencies

```bash
cd hec-system
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in your API keys
```

Required keys:
- `IBM_API_KEY` + `IBM_PROJECT_ID` + `IBM_URL` — IBM WatsonX (Granite 4)
- `GEMINI_API_KEY` — Google Gemini
- `GROQ_API_KEY` — Groq
- `OMNIROUTE_API_KEY` + `OMNIROUTE_BASE_URL` — OmniRoute LLM Gateway

Optional:
- `HITL_CONFIDENCE_THRESHOLD` — detection confidence threshold for HITL review (default: `0.70`)
- `DEMO_MODE` — set `true` to run with synthetic data only, no live API calls (default: `true`)

### 4. Run the orchestrator (single pass)

```bash
cd hec-system
python orchestrator.py
```

### 5. Run the dashboard

```bash
cd hec-system
streamlit run dashboard/app.py
```

### 6. Run tests

```bash
cd hec-system
pytest tests/ -v
```

---

## HITL Policy

- **All** community-wide alerts require explicit forest officer approval before dispatch.
- Detections with `detection_confidence < HITL_CONFIDENCE_THRESHOLD` are additionally queued for manual verification of the detection itself.
- `detection_confidence` (from Agent 2) and `village_risk_score` (from Agent 3) are distinct metrics.
- Every approval and rejection is written to `audit.jsonl` (append-only, never modified).

---

## Demo Scenario

The demonstration scenario is **"Night Incursion — Kodagu, Day 1"**:

1. A synthetic elephant herd is detected crossing the Kodagu–Mysuru corridor at 22:00.
2. Agent 1 (Granite 4) consolidates sightings and patrol data.
3. Agent 2 (Gemini) classifies camera trap events; low-confidence detections enter the HITL queue.
4. The forest officer reviews and approves detections.
5. Agent 3 (Groq) generates bilingual Kannada/English safety alerts for at-risk villages.
6. The dashboard shows the approval queue; the officer approves alerts.
7. Alerts are marked DISPATCHED and appear on the Folium map.

Run it:
```bash
python demo/scenario.py
```

---

## Project Structure

```
hec-system/
├── agents/              # LLM-powered agents (Granite 4, Gemini, Groq)
├── tools/               # MCP tool wrappers (data, map, alerts)
├── data/
│   ├── synthetic/       # Deterministic synthetic feed generator
│   └── static/          # Real public dataset loaders + cached files
├── dashboard/           # Streamlit app + Folium map builder
├── memory/              # Thread-safe MemoryStore
├── llm/                 # OmniRoute gateway + provider adapters
├── audit/               # Append-only audit log
├── tests/               # Unit and E2E tests
├── demo/                # Demo scenario runner
├── orchestrator.py      # Pipeline runner + HITL gate
├── schemas.py           # Shared Pydantic data contracts
├── config.py            # Environment config loader
└── requirements.txt
```

---

## Technology Stack

| Component | Technology |
|---|---|
| AI IDE | IBM Bob |
| Language | Python 3.12 |
| LLMs | IBM Granite 4, Google Gemini, Groq |
| LLM Gateway | OmniRoute |
| Agent Communication | MCP (Model Context Protocol) |
| Frontend | Streamlit + Folium |
| Cloud | IBM Cloud (deployment target) |
| Config | `.env` files |

---

## Known Limitations

- Real-time GPS collar and camera trap feeds are not yet integrated; synthetic data is used.
- ChromaDB long-term memory is stubbed (post-MVP).
- NeMo Guardrails are not yet enabled (post-MVP).
- Deployment to IBM Cloud is a post-MVP step.
