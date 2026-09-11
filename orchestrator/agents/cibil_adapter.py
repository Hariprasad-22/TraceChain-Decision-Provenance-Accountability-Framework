"""
agents/cibil_adapter.py
------------------------
Adapter for the CIBIL Score Agent (A004).

Responsibilities:
  1. Scope state to only the fields A004 is allowed to see.
  2. Call cibil_verification_agent(state, orchestration_id).
  3. Normalise output: the CIBIL agent already uses lowercase canonical
     keys (execution, decision, evidence, accountability, provenance)
     and returns plain dicts via asdict() — minimal work needed.
  4. Ensure agent_id = "A004" and sequence_number = 4.
  5. Inject the orchestrator's orchestration_id everywhere.

Input fields consumed by the CIBIL agent:
  - application_id
  - cibil_score          (int, 300-900)
  - credit_utilization_pct (float, 0-100)
  - dpd_history          (list[int], days past due per account)
"""

import sys
import logging
from pathlib import Path

from agents.import_isolation import prepare_agent_import, restore_orchestrator_path

logger = logging.getLogger(__name__)

# ─── path setup ───────────────────────────────────────────────────────────────
_ORCH_DIR = Path(__file__).resolve().parent.parent
_CIBIL_DIR = _ORCH_DIR.parent / "agents" / "cibil"
prepare_agent_import(_CIBIL_DIR)
try:
    from cibil_agent import cibil_verification_agent  # noqa: E402
finally:
    restore_orchestrator_path(_ORCH_DIR)

AGENT_ID        = "A004"
SEQUENCE_NUMBER = 4


def _scope(state: dict) -> dict:
    """Return only fields the CIBIL agent is allowed to see."""
    return {
        "application_id":        state["application_id"],
        "cibil_score":           state["cibil_score"],
        "credit_utilization_pct": state.get("credit_utilization_pct", 0.0),
        "dpd_history":           state.get("dpd_history", []),
    }


def run(state: dict, orchestration_id: str) -> dict:
    """
    Execute the CIBIL agent and return a normalised result dict.

    Parameters
    ----------
    state : dict
        Full application state. Must include:
          - application_id
          - cibil_score            (int)
          - credit_utilization_pct (float, optional)
          - dpd_history            (list[int], optional)
    orchestration_id : str

    Returns
    -------
    dict with keys: execution, decision, evidence, accountability, provenance
    """
    scoped = _scope(state)
    logger.info("[A004] Running CIBIL agent for application_id=%s cibil_score=%s",
                state["application_id"], state.get("cibil_score"))

    raw = cibil_verification_agent(scoped, orchestration_id=orchestration_id)

    # CIBIL agent already returns canonical keys and plain dicts
    result = {
        "execution":      raw["execution"],
        "decision":       raw["decision"],
        "evidence":       raw["evidence"],
        "accountability": raw["accountability"],
        "provenance":     raw["provenance"],
    }

    # Enforce correct metadata
    result["execution"]["agent_id"]        = AGENT_ID
    result["execution"]["orchestration_id"] = orchestration_id
    result["execution"]["sequence_number"]  = SEQUENCE_NUMBER
    result["provenance"]["orchestration_id"] = orchestration_id

    logger.info(
        "[A004] Done — decision=%s confidence=%.2f",
        result["decision"]["decision_output"],
        result["decision"]["confidence_score"],
    )
    return result
