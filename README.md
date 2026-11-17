# ECO-HERD — Human-Elephant Conflict Early Warning & Community Safety System

An Agentic AI-based early warning system for the Karnataka Forest Department.
Detects elephant movement near human settlements, predicts conflict hotspots, and issues timely bilingual (English + Kannada) community safety alerts.

Built for the **Agentic AI Hackathon — Bengaluru, Karnataka**
using **IBM Bob · IBM Granite 4 · Google Gemini 2.5 Flash · Groq · Google Maps**

---

## 🏗️ Architecture

```
Orchestrator (pipeline runner + HITL gate)
    │
    ├── Agent 1: Wildlife Data Analysis  ← IBM Granite 4 (via OpenRouter)
    ├── Agent 2: Elephant Detection       ← Google Gemini 2.5 Flash (via OpenRouter)
    └── Agent 3: Early Warning & Alert    ← Groq (openai/gpt-oss-20b)
                │
         MCP Tool Wrappers
           ├── data_fetcher  (sightings, camera traps, sensors, patrols, weather)
           ├── map_tools     (nearest_village, corridor check, risk zones)
           └── alert_tools   (bilingual EN+KN alert formatter + dispatcher)
                │
         Data Sources
           ├── Synthetic: GPS/camera/sensor/patrol feeds  ⚠️ SYNTHETIC
           └── Static: OpenStreetMap villages, forest GeoJSON, IMD weather
                │
         Streamlit Dashboard
           ├── Google Maps satellite tiles
           ├── HITL queue (low-confidence detections)
           └── Forest officer alert approval panel
```

---

## ⚠️ Synthetic Data Disclaimer

GPS collar positions, camera trap events, acoustic sensor triggers, and ranger patrol logs are **synthetically generated** for demonstration. They do not represent real elephant movements or actual field incidents.

All synthetic records carry `data_source: "synthetic"` and the dashboard shows this disclaimer prominently.

---

## 🚀 Quick Start

### 1. Prerequisites

```bash
Python 3.12+
pip
```

### 2. Clone & install

```bash
git clone https://github.com/rakeshnh2006-tech/ECO-HERD.git
cd ECO-HERD
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Fill in your API keys (see below)
```

**Required keys:**

| Variable | Provider | Purpose |
|---|---|---|
| `IBM_API_KEY` | IBM Cloud | Granite 4 via WatsonX (falls back to OpenRouter) |
| `IBM_PROJECT_ID` | IBM Cloud | WatsonX project |
| `IBM_URL` | IBM Cloud | Default: `https://us-south.ml.cloud.ibm.com` |
| `GEMINI_API_KEY` | OpenRouter | Gemini 2.5 Flash via `sk-or-v1-...` key |
| `GROQ_API_KEY` | Groq | Early warning alert generation |
| `GOOGLE_MAPS_API_KEY` | Google Cloud | Satellite map tiles in dashboard |

**Optional:**

| Variable | Default | Purpose |
|---|---|---|
| `OMNIROUTE_API_KEY` | — | OmniRoute LLM gateway (if available) |
| `HITL_CONFIDENCE_THRESHOLD` | `0.70` | Below this → manual HITL review |

### 4. Run the dashboard

```bash
streamlit run dashboard/app.py
# → http://localhost:8501
```

### 5. Run the pipeline (single pass)

```bash
python3 orchestrator.py
```

### 6. Run the demo scenario

```bash
python3 demo/scenario.py
```

### 7. Run tests

```bash
pytest tests/ -v
# 124 tests, all passing
```

---

## 🤖 Agents

| Agent | Model | Role |
|---|---|---|
| **WildlifeDataAgent** | IBM Granite 4 | Analyses GPS/camera/sensor/patrol data → wildlife report |
| **ElephantDetectionAgent** | Gemini 2.5 Flash | Classifies camera trap events → confirmed/false alarm |
| **EarlyWarningAgent** | Groq | Generates bilingual EN+KN community safety alerts |

---

## 🔒 HITL Policy (non-negotiable)

- **Every** community-wide alert requires explicit **forest officer approval** before dispatch — regardless of confidence
- Detections with `detection_confidence < HITL_CONFIDENCE_THRESHOLD` (default 0.70) are additionally flagged for manual verification
- `detection_confidence` (Agent 2) and `village_risk_score` (Agent 3) are always **separate fields**
- All approvals, rejections, and HITL events are written to `audit.jsonl` (append-only, never modified)

---

## 🗺️ Dashboard Features

- **Google Maps** satellite + hybrid + road tile layers
- **Folium** interactive map with:
  - Village markers colour-coded by risk level
  - Elephant detection pins with confidence & explanation
  - Forest corridor polygon overlays
  - Dispatched alert markers
- **HITL queue** — review flagged detections
- **Alert approval panel** — approve/reject with officer ID
- **Live LLM call log** — route, tokens, latency, cost
- **Audit trail viewer**

---

## 📁 Project Structure

```
ECO-HERD/
├── agents/
│   ├── wildlife_data_agent.py     # Agent 1 — IBM Granite 4
│   ├── elephant_detection_agent.py # Agent 2 — Gemini 2.5 Flash
│   └── early_warning_agent.py     # Agent 3 — Groq
├── llm/
│   ├── gateway.py                 # OmniRoute → direct adapters → FALLBACK
│   ├── granite_adapter.py
│   ├── gemini_adapter.py
│   └── groq_adapter.py
├── tools/
│   ├── data_fetcher.py            # 7 MCP data tools
│   ├── map_tools.py               # nearest_village, in_corridor, risk_zones
│   └── alert_tools.py             # bilingual alert formatter + dispatcher
├── data/
│   ├── synthetic/generator.py     # Deterministic synthetic feed generator
│   └── static/                    # Karnataka GeoJSON, weather CSV
├── dashboard/
│   ├── app.py                     # Streamlit app
│   └── map_builder.py             # Google Maps + Folium builder
├── memory/store.py                # Thread-safe in-memory store
├── audit/log.py                   # Append-only audit.jsonl
├── orchestrator.py                # Full pipeline + HITL gate
├── schemas.py                     # Pydantic data contracts
├── config.py                      # Env loader
├── requirements.txt
├── Procfile                       # Cloud deployment
├── runtime.txt                    # Python version
└── tests/                         # 124 unit + E2E tests
```

---

## 🛠️ Tech Stack

| Component | Technology |
|---|---|
| AI IDE | IBM Bob |
| Agent Framework | Python + ReAct pattern |
| LLMs | IBM Granite 4, Gemini 2.5 Flash, Groq |
| LLM Gateway | OmniRoute → OpenRouter → Direct → FALLBACK |
| Maps | Google Maps API + Folium |
| Frontend | Streamlit |
| Data Contracts | Pydantic v2 |
| Tests | pytest (124 passing) |
| Deployment | Streamlit Cloud / Railway / Render |

---

## ⚠️ Known Limitations

- Real-time GPS collar / camera trap API integration is post-MVP (synthetic data used)
- ChromaDB vector memory is stubbed (post-MVP)
- NeMo Guardrails not yet enabled (post-MVP)
- OmniRoute endpoint may require `www.omniroute.online` prefix depending on account
