"""
schemas.py — Shared Pydantic data contracts.

These models are the single source of truth for data passed between:
  agents, tools, orchestrator, MemoryStore, and dashboard.

All field names, types, and defaults are defined here.
Agents and tools import from this module only — no ad-hoc dicts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DataSource(str, Enum):
    SYNTHETIC = "synthetic"
    OSM = "openstreetmap"
    IMD = "imd"
    GLOBAL_FOREST_WATCH = "global_forest_watch"
    KARNATAKA_OPEN_DATA = "karnataka_open_data"
    CAMERA_TRAP = "camera_trap"
    GPS_COLLAR = "gps_collar"
    RANGER_PATROL = "ranger_patrol"
    ACOUSTIC_SENSOR = "acoustic_sensor"
    UNKNOWN = "unknown"


class RiskLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    SAFE = "SAFE"


class AlertStatus(str, Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    DISPATCHED = "DISPATCHED"
    REJECTED = "REJECTED"


class HitlVerdict(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class AuditEventType(str, Enum):
    HITL_FLAGGED = "HITL_FLAGGED"
    HITL_RESOLVED = "HITL_RESOLVED"
    ALERT_CREATED = "ALERT_CREATED"
    ALERT_APPROVED = "ALERT_APPROVED"
    ALERT_REJECTED = "ALERT_REJECTED"
    PIPELINE_RUN_START = "PIPELINE_RUN_START"
    PIPELINE_RUN_END = "PIPELINE_RUN_END"
    AGENT_ERROR = "AGENT_ERROR"


# ---------------------------------------------------------------------------
# Raw data feed models (from synthetic generator / live feeds)
# ---------------------------------------------------------------------------

class Sighting(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    lat: float
    lon: float
    timestamp: datetime
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    source: str = ""
    district: str = ""
    notes: str = ""
    data_source: DataSource = DataSource.SYNTHETIC


class CameraTrapEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    lat: float
    lon: float
    timestamp: datetime
    image_description: str = ""
    image_b64: Optional[str] = None   # base64 image; None for MVP text-only mode
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    district: str = ""
    data_source: DataSource = DataSource.SYNTHETIC


class SensorEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    lat: float
    lon: float
    timestamp: datetime
    sensor_type: str = "acoustic"
    triggered: bool = True
    district: str = ""
    data_source: DataSource = DataSource.SYNTHETIC


class PatrolLog(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    officer_id: str
    lat: float
    lon: float
    timestamp: datetime
    notes: str = ""
    district: str = ""
    data_source: DataSource = DataSource.SYNTHETIC


# ---------------------------------------------------------------------------
# Agent output models
# ---------------------------------------------------------------------------

class WildlifeReport(BaseModel):
    """Output of Agent 1 (Wildlife Data Analysis — IBM Granite 4)."""
    analysis_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    active_sightings: list[Sighting] = []
    camera_trap_events: list[CameraTrapEvent] = []
    pattern_summary: str = ""
    risk_districts: list[str] = []
    confidence_scores: dict[str, float] = {}
    data_sources: list[str] = []
    synthetic_data_present: bool = False
    raw_llm_response: str = ""


class Detection(BaseModel):
    """Output of Agent 2 (Elephant Detection — Google Gemini), one per camera trap event."""
    detection_id: str = Field(default_factory=lambda: str(uuid4()))
    event_id: str
    is_elephant: bool
    detection_confidence: float = Field(ge=0.0, le=1.0)
    false_alarm_flag: bool = False
    nearest_village: str = ""
    distance_km: float = 0.0
    in_corridor: bool = False
    requires_hitl_review: bool = False
    explanation: str = ""          # explainability field
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    lat: float = 0.0
    lon: float = 0.0
    district: str = ""


class RiskZone(BaseModel):
    """Computed risk zone for a village, produced by map_tools.compute_risk_zones."""
    village: str
    district: str = ""
    lat: float = 0.0
    lon: float = 0.0
    risk_level: RiskLevel
    village_risk_score: float = Field(ge=0.0, le=1.0)   # separate from detection_confidence
    reason: str = ""
    contributing_factors: list[str] = []  # explainability


class Alert(BaseModel):
    """Output of Agent 3 (Early Warning — Groq), one per at-risk village."""
    alert_id: str = Field(default_factory=lambda: str(uuid4()))
    village: str
    district: str = ""
    alert_level: RiskLevel
    village_risk_score: float = Field(ge=0.0, le=1.0)   # from RiskZone
    detection_confidence: float = Field(ge=0.0, le=1.0)  # from Detection (separate)
    message_en: str = ""
    message_kn: str = ""
    recommended_actions: list[str] = []
    risk_explanation: str = ""    # explainability
    status: AlertStatus = AlertStatus.PENDING_APPROVAL
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    approved_by: Optional[str] = None
    rejection_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# HITL queue item
# ---------------------------------------------------------------------------

class HitlQueueItem(BaseModel):
    item_id: str = Field(default_factory=lambda: str(uuid4()))
    detection: Detection
    queued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    verdict: Optional[HitlVerdict] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    notes: str = ""


# ---------------------------------------------------------------------------
# Observability models
# ---------------------------------------------------------------------------

class ToolTraceEntry(BaseModel):
    tool_name: str
    input_summary: str = ""
    output_summary: str = ""
    latency_ms: float = 0.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error: Optional[str] = None


class AgentRunLog(BaseModel):
    agent_name: str
    model_id: str
    start_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    steps: list[dict[str, Any]] = []   # ReAct steps: {thought, action, observation}
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    error: Optional[str] = None


class RunReport(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    start_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    agents_run: list[str] = []
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_cost_usd: float = 0.0
    alerts_pending: int = 0
    alerts_dispatched: int = 0
    alerts_rejected: int = 0
    hitl_flagged_count: int = 0
    errors: list[str] = []


# ---------------------------------------------------------------------------
# Audit log entry
# ---------------------------------------------------------------------------

class AuditEntry(BaseModel):
    entry_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: AuditEventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = {}
