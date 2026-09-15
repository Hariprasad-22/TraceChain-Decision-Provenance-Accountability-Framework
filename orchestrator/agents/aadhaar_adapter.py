"""
agents/aadhaar_adapter.py
--------------------------
Adapter for the Aadhaar Verification Agent (A001).

Responsibilities:
  1. Scope the full application state to only the fields A001 is allowed
     to see (least-privilege, mirroring guardrails.scope_for_aadhar_agent).
  2. Call aadhar_verification_agent(state, orchestration_id).
  3. Normalise output keys to the orchestrator's canonical shape:
       execution, decision, evidence, accountability, provenance
  4. Override orchestration_id in the result with the one supplied by
     the orchestrator (the agent may echo the application_id; we want
     the orchestrator's real orchestration_id).
  5. Fix sequence_number = 1 (Aadhaar runs first).

The orchestrator's hasher module handles all hash-chain work separately.
"""

import sys
import importlib.util
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from .import_isolation import prepare_agent_import, restore_orchestrator_path
except ImportError:  # pragma: no cover - script-style execution from orchestrator/
    from agents.import_isolation import prepare_agent_import, restore_orchestrator_path

# Load the real Aadhaar agent module directly from its source file, avoiding
# package-name collisions caused by legacy agent folder layouts.
_ORCH_DIR = Path(__file__).resolve().parent.parent
_AADHAAR_DIR = _ORCH_DIR.parent / "agents" / "aadhar"
_AADHAAR_FILE = _AADHAAR_DIR / "aadhar_agent.py"

prepare_agent_import(_AADHAAR_DIR)
try:
    if not _AADHAAR_FILE.exists():
        raise FileNotFoundError(f"Aadhaar agent file not found at {_AADHAAR_FILE}")

    _spec = importlib.util.spec_from_file_location("tracechain_aadhar_agent", _AADHAAR_FILE)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"Could not create import spec for {_AADHAAR_FILE}")

    _aadhar_module = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_aadhar_module)
    aadhar_verification_agent = _aadhar_module.aadhar_verification_agent
finally:
    restore_orchestrator_path(_ORCH_DIR)

AGENT_ID       = "A001"
SEQUENCE_NUMBER = 1


def _scope(state: dict) -> dict:
    """
    Return only the fields the Aadhaar agent is permitted to read.
    Mirrors guardrails.scope_for_aadhar_agent + keeps application_id.
    """
    return {
        "application_id":  state["application_id"],
        "loan_amount":     state["loan_amount"],
        "applicant_name":  state["applicant_name"],
        "applicant_dob":   state.get("applicant_dob"),
        "applicant_data": {
            "aadhar_image_path": state["applicant_data"]["aadhar_image_path"]
        },
    }


def run(state: dict, orchestration_id: str) -> dict:
    """
    Execute the Aadhaar agent and return a normalised result dict.

    Returns
    -------
    dict with keys: execution, decision, evidence, accountability, provenance
    All values are plain dicts (no dataclasses).
    """
    scoped = _scope(state)
    logger.info("[A001] Running Aadhaar agent for application_id=%s", state["application_id"])

    raw = aadhar_verification_agent(scoped, orchestration_id=orchestration_id)

    # The agent returns plain dicts already for execution/decision/accountability/provenance
    # and a list of dicts for evidence.
    result = {
        "execution":      raw["execution"],
        "decision":       raw["decision"],
        "evidence":       raw["evidence"],        # list[dict]
        "accountability": raw["accountability"],
        "provenance":     raw["provenance"],
    }

    # Enforce correct metadata
    result["execution"]["agent_id"]       = AGENT_ID
    result["execution"]["orchestration_id"] = orchestration_id
    result["execution"]["sequence_number"]  = SEQUENCE_NUMBER
    result["provenance"]["orchestration_id"] = orchestration_id

    # Pass Aadhaar agent decision through unchanged — no name-match overlay.

    logger.info(
        "[A001] Done — decision=%s confidence=%.2f",
        result["decision"]["decision_output"],
        result["decision"]["confidence_score"],
    )
    return result
