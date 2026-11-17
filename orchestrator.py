"""
orchestrator.py — Pipeline orchestrator.

Wires Agent 1 → Agent 2 → Agent 3 and enforces the HITL approval gate.
All alerts are created with PENDING_APPROVAL by Agent 3 via dispatch_alert();
run_once() does NOT double-add them — it reads what's already in the store.

Usage:
    python orchestrator.py          # run once and exit
    python orchestrator.py --poll   # run on polling interval
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

import config
from audit.log import append_audit
from memory.store import store
from schemas import AuditEventType, HitlVerdict, RunReport

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ---------------------------------------------------------------------------
# Agent imports — will be replaced with real agents in Sub-Task 6.
# Each is wrapped in a try/except so the skeleton runs even before agents exist.
# ---------------------------------------------------------------------------

def _load_agents():
    agents = {}
    try:
        from agents.wildlife_data_agent import WildlifeDataAgent
        agents["wildlife"] = WildlifeDataAgent()
    except (ImportError, Exception) as e:
        logger.warning("WildlifeDataAgent not available: %s", e)
        agents["wildlife"] = None

    try:
        from agents.elephant_detection_agent import ElephantDetectionAgent
        agents["detection"] = ElephantDetectionAgent()
    except (ImportError, Exception) as e:
        logger.warning("ElephantDetectionAgent not available: %s", e)
        agents["detection"] = None

    try:
        from agents.early_warning_agent import EarlyWarningAgent
        agents["alert"] = EarlyWarningAgent()
    except (ImportError, Exception) as e:
        logger.warning("EarlyWarningAgent not available: %s", e)
        agents["alert"] = None

    return agents


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def run_once(hours_back: int = 24) -> RunReport:
    """
    Run the full agent pipeline once:
      Agent 1 (Wildlife Data) → Agent 2 (Elephant Detection) → Agent 3 (Early Warning)

    All results are written to the shared MemoryStore.
    Agent failures are caught and logged; the pipeline continues with partial results.
    Returns a RunReport summarising the run.
    """
    run_id_entry = append_audit(AuditEventType.PIPELINE_RUN_START, {"hours_back": hours_back})
    report = RunReport(start_time=datetime.now(timezone.utc))
    agents = _load_agents()

    logger.info("=== Pipeline run %s started ===", report.run_id)

    # ---- Agent 1: Wildlife Data Analysis ----
    wildlife_report = None
    if agents["wildlife"] is not None:
        try:
            logger.info("Running WildlifeDataAgent...")
            wildlife_report = agents["wildlife"].run(hours_back=hours_back)
            store.set_wildlife_report(wildlife_report)
            report.agents_run.append("WildlifeDataAgent")
            logger.info("WildlifeDataAgent completed: %d sightings", len(wildlife_report.active_sightings))
        except Exception as e:
            msg = f"WildlifeDataAgent failed: {e}"
            logger.error(msg)
            report.errors.append(msg)
            # Fall back to last known report
            wildlife_report = store.get_wildlife_report()
    else:
        logger.warning("WildlifeDataAgent skipped (not implemented yet)")
        wildlife_report = store.get_wildlife_report()

    # ---- Agent 2: Elephant Detection ----
    detections = []
    if agents["detection"] is not None and wildlife_report is not None:
        try:
            logger.info("Running ElephantDetectionAgent...")
            detections = agents["detection"].run(wildlife_report)
            store.set_detections(detections)
            report.agents_run.append("ElephantDetectionAgent")
            hitl_count = sum(1 for d in detections if d.requires_hitl_review)
            report.hitl_flagged_count = hitl_count
            logger.info(
                "ElephantDetectionAgent completed: %d detections, %d HITL flagged",
                len(detections), hitl_count,
            )
        except Exception as e:
            msg = f"ElephantDetectionAgent failed: {e}"
            logger.error(msg)
            report.errors.append(msg)
            detections = store.get_detections()
    else:
        if agents["detection"] is None:
            logger.warning("ElephantDetectionAgent skipped (not implemented yet)")
        detections = store.get_detections()

    # ---- Agent 3: Early Warning & Alert ----
    # Note: EarlyWarningAgent calls dispatch_alert() internally, which writes to
    # MemoryStore as PENDING_APPROVAL. We do NOT double-add here.
    pending_before = len(store.get_pending_alerts())
    if agents["alert"] is not None and detections:
        try:
            logger.info("Running EarlyWarningAgent...")
            # Only pass detections that are confirmed (not awaiting HITL review)
            resolved_hitl_ids = {
                item.detection.detection_id
                for item in store.get_hitl_queue()
                if item.verdict == HitlVerdict.APPROVED
            }
            confirmed_detections = [
                d for d in detections
                if not d.requires_hitl_review or d.detection_id in resolved_hitl_ids
            ]
            alerts = agents["alert"].run(confirmed_detections)
            # Agent already wrote to store via dispatch_alert; just track count
            report.agents_run.append("EarlyWarningAgent")
            report.alerts_pending = len(store.get_pending_alerts())
            new_alerts = report.alerts_pending - pending_before
            logger.info(
                "EarlyWarningAgent completed: %d new alerts pending approval", new_alerts
            )
        except Exception as e:
            msg = f"EarlyWarningAgent failed: {e}"
            logger.error(msg)
            report.errors.append(msg)
    else:
        if agents["alert"] is None:
            logger.warning("EarlyWarningAgent skipped (not implemented yet)")

    # ---- Finalise run report ----
    report.end_time = datetime.now(timezone.utc)
    from schemas import AlertStatus
    report.alerts_dispatched = len([a for a in store.get_all_alerts()
                                    if a.status == AlertStatus.DISPATCHED])
    report.alerts_pending = len(store.get_pending_alerts())

    # Accumulate token/cost from LLM call log
    totals = store.get_total_tokens()
    report.total_tokens_in = totals["tokens_in"]
    report.total_tokens_out = totals["tokens_out"]
    report.total_cost_usd = store.get_total_cost()

    store.add_run_report(report)
    append_audit(
        AuditEventType.PIPELINE_RUN_END,
        {
            "run_id": report.run_id,
            "agents_run": report.agents_run,
            "alerts_pending": report.alerts_pending,
            "hitl_flagged": report.hitl_flagged_count,
            "errors": report.errors,
        },
    )
    logger.info(
        "=== Pipeline run %s complete | agents: %s | alerts pending: %d | errors: %d ===",
        report.run_id, report.agents_run, report.alerts_pending, len(report.errors),
    )
    return report


# ---------------------------------------------------------------------------
# HITL resolution
# ---------------------------------------------------------------------------

def resolve_hitl(item_id: str, verdict: HitlVerdict, officer_id: str, notes: str = "") -> bool:
    """
    Resolve a HITL queue item.
    If approved, the detection is re-submitted to Agent 3 (if available).
    Returns True if the item was found and resolved.
    """
    item = store.resolve_hitl(item_id, verdict, officer_id, notes)
    if item is None:
        logger.warning("HITL item %s not found or already resolved", item_id)
        return False

    append_audit(
        AuditEventType.HITL_RESOLVED,
        {
            "item_id": item_id,
            "detection_id": item.detection.detection_id,
            "verdict": verdict.value,
            "officer_id": officer_id,
            "notes": notes,
        },
    )
    logger.info("HITL item %s resolved as %s by %s", item_id, verdict.value, officer_id)

    # If approved, re-run Agent 3 for this detection
    if verdict == HitlVerdict.APPROVED:
        try:
            from agents.early_warning_agent import EarlyWarningAgent
            agent = EarlyWarningAgent()
            alerts = agent.run([item.detection])
            for alert in alerts:
                store.add_pending_alert(alert)
            logger.info("Re-ran EarlyWarningAgent for approved detection; %d new alerts", len(alerts))
        except (ImportError, Exception) as e:
            logger.warning("Could not re-run EarlyWarningAgent after HITL approval: %s", e)

    return True


# ---------------------------------------------------------------------------
# Alert approval / rejection
# ---------------------------------------------------------------------------

def approve_alert(alert_id: str, officer_id: str) -> bool:
    """
    Approve a pending alert for dispatch.
    Requires explicit forest officer action — alerts are NEVER auto-dispatched.
    """
    alert = store.approve_alert(alert_id, officer_id)
    if alert is None:
        logger.warning("Alert %s not found or already actioned", alert_id)
        return False

    append_audit(
        AuditEventType.ALERT_APPROVED,
        {
            "alert_id": alert_id,
            "village": alert.village,
            "alert_level": alert.alert_level.value,
            "officer_id": officer_id,
        },
    )
    logger.info("Alert %s APPROVED by %s — village: %s", alert_id, officer_id, alert.village)
    return True


def reject_alert(alert_id: str, officer_id: str, reason: str = "") -> bool:
    """Reject a pending alert. Reason is recorded in the audit log."""
    alert = store.reject_alert(alert_id, officer_id, reason)
    if alert is None:
        logger.warning("Alert %s not found or already actioned", alert_id)
        return False

    append_audit(
        AuditEventType.ALERT_REJECTED,
        {
            "alert_id": alert_id,
            "village": alert.village,
            "officer_id": officer_id,
            "reason": reason,
        },
    )
    logger.info("Alert %s REJECTED by %s — reason: %s", alert_id, officer_id, reason)
    return True


# ---------------------------------------------------------------------------
# Polling loop
# ---------------------------------------------------------------------------

def start_polling(interval_seconds: int = config.POLLING_INTERVAL_SECONDS) -> threading.Thread:
    """Start a background thread that calls run_once() on a fixed interval."""

    def _loop():
        logger.info("Polling loop started (interval: %ds)", interval_seconds)
        while True:
            try:
                run_once()
            except Exception as e:
                logger.error("Unhandled error in polling loop: %s", e)
            time.sleep(interval_seconds)

    thread = threading.Thread(target=_loop, daemon=True, name="orchestrator-poll")
    thread.start()
    return thread


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if "--poll" in sys.argv:
        logger.info("Starting polling mode. Press Ctrl+C to stop.")
        t = start_polling()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Polling stopped.")
    else:
        report = run_once()
        logger.info(
            "Run complete. Run ID: %s | Agents run: %s | Errors: %d",
            report.run_id, report.agents_run, len(report.errors),
        )
