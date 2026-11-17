"""
config.py — Central configuration loader.

Loads all environment variables from .env at import time.
Raises EnvironmentError immediately if a required variable is missing.
All thresholds and keys are accessed through this module; no hardcoded values elsewhere.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _require(key: str) -> str:
    """Return env var value or raise a clear error if absent."""
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(
            f"Required environment variable '{key}' is not set. "
            f"Copy .env.example to .env and fill in your keys."
        )
    return value


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default)


# ---------------------------------------------------------------------------
# IBM WatsonX (Granite 4)
# ---------------------------------------------------------------------------
IBM_API_KEY: str = _optional("IBM_API_KEY")
IBM_PROJECT_ID: str = _optional("IBM_PROJECT_ID")
IBM_URL: str = _optional("IBM_URL", "https://us-south.ml.cloud.ibm.com")

# ---------------------------------------------------------------------------
# Google Gemini
# ---------------------------------------------------------------------------
GEMINI_API_KEY: str = _optional("GEMINI_API_KEY")

# ---------------------------------------------------------------------------
# Groq
# ---------------------------------------------------------------------------
GROQ_API_KEY: str = _optional("GROQ_API_KEY")

# ---------------------------------------------------------------------------
# OmniRoute LLM Gateway
# ---------------------------------------------------------------------------
OMNIROUTE_API_KEY: str = _optional("OMNIROUTE_API_KEY")
OMNIROUTE_BASE_URL: str = _optional("OMNIROUTE_BASE_URL", "https://omniroute.online/v1")

# ---------------------------------------------------------------------------
# Google Maps
# ---------------------------------------------------------------------------
GOOGLE_MAPS_API_KEY: str = _optional("GOOGLE_MAPS_API_KEY")

# ---------------------------------------------------------------------------
# HITL thresholds
# ---------------------------------------------------------------------------
# Detections with confidence below this threshold are flagged for manual review.
HITL_CONFIDENCE_THRESHOLD: float = float(_optional("HITL_CONFIDENCE_THRESHOLD", "0.70"))

# ---------------------------------------------------------------------------
# Model IDs
# ---------------------------------------------------------------------------
GRANITE_MODEL_ID: str = _optional("GRANITE_MODEL_ID", "ibm/granite-3-8b-instruct")
GEMINI_MODEL_ID: str = _optional("GEMINI_MODEL_ID", "gemini-2.0-flash")
GROQ_MODEL_ID: str = _optional("GROQ_MODEL_ID", "llama-3.3-70b-versatile")

# ---------------------------------------------------------------------------
# App settings
# ---------------------------------------------------------------------------
POLLING_INTERVAL_SECONDS: int = int(_optional("POLLING_INTERVAL_SECONDS", "300"))
DEMO_MODE: bool = _optional("DEMO_MODE", "true").lower() == "true"


def has_ibm_credentials() -> bool:
    return bool(IBM_API_KEY and IBM_PROJECT_ID)


def has_gemini_credentials() -> bool:
    return bool(GEMINI_API_KEY)


def has_groq_credentials() -> bool:
    return bool(GROQ_API_KEY)


def has_omniroute_credentials() -> bool:
    return bool(OMNIROUTE_API_KEY)
