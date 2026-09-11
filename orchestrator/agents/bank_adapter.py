"""
agents/bank_adapter.py
-----------------------
Plug-in STUB for the Bank Statement Analysis Agent (A003).

This module is a placeholder slot that keeps the pipeline serial chain
intact (Aadhaar → Payslip → Bank → CIBIL).  When the real Bank agent
is available, replace the `run()` body below — the orchestrator's call
site does not need to change at all.

Current behaviour:
  - Returns a minimal "skipped" result so the hash chain can still pass
    a record_hash through to CIBIL.
  - Does NOT write to the DB (the orchestrator checks result["skipped"]).
  - Carries the previous_record_hash forward unchanged.

Integration checklist (when Bank agent is ready):
  [ ] Add the bank agent directory to _BANK_DIR below.
  [ ] Import the callable function (similar to aadhar_verification_agent).
  [ ] Fill in _scope() with the fields the bank agent is allowed to see.
  [ ] Remove the `skipped=True` flag from the returned dict.
  [ ] Set SEQUENCE_NUMBER = 3 (already set, nothing to change here).
"""

import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

AGENT_ID        = "A003"
SEQUENCE_NUMBER = 3

# ─── STUB result shape ────────────────────────────────────────────────────────

def _stub_result(state: dict, orchestration_id: str) -> dict:
    """
    Generate a minimal pass-through result so the chain can continue.
    The orchestrator treats skipped=True as a no-op for DB writes.
    """
    now = datetime.now(timezone.utc).isoformat()
    exec_id = str(uuid.uuid4())
    return {
        "skipped": True,
        "execution": {
            "execution_id":    exec_id,
            "orchestration_id": orchestration_id,
            "agent_id":        AGENT_ID,
            "sequence_number": SEQUENCE_NUMBER,
            "input_data":      {},
            "output_data":     {"decision_output": "skipped", "confidence_score": 0.0, "reasoning": "Bank agent not yet integrated."},
            "model_id":        "stub",
            "rule_id":         None,
            "start_time":      now,
            "end_time":        now,
            "status":          "completed",
        },
        "decision": {
            "decision_id":     str(uuid.uuid4()),
            "execution_id":    exec_id,
            "decision_output": "skipped",
            "confidence_score": 0.0,
            "reasoning":       "Bank Statement agent not yet integrated — slot reserved.",
            "timestamp":       now,
        },
        "evidence": [],
        "accountability": {
            "score_id":               str(uuid.uuid4()),
            "execution_id":           exec_id,
            "impact_score":           0,
            "irreversibility_score":  0,
            "explainability_score":   10,
            "composite_risk_score":   0.0,
            "risk_level":             "Low",
            "review_required":        False,
            "scoring_model_version":  "tracechain-scoring-v1",
            "calculated_at":          now,
        },
        "provenance": {
            "record_id":            str(uuid.uuid4()),
            "orchestration_id":     orchestration_id,
            "execution_id":         exec_id,
            "event_type":           "agent_skipped",
            "timestamp":            now,
            "input_hash":           "",
            "output_hash":          "",
            "previous_record_hash": None,
            "record_hash":          "",
        },
    }


# ─── public interface (matches all other adapters) ────────────────────────────

def run(state: dict, orchestration_id: str) -> dict:
    """
    Stub run — returns skipped result so the pipeline can continue.
    Replace this body when the real bank agent is integrated.
    """
    logger.warning("[A003] Attempting to run integrated Bank Statement agent.")

    # Helper: normalise a tracechain JSON payload into the orchestrator shape
    def _normalise_from_tracechain(tracechain: dict, orchestration_id: str) -> dict:
        records = tracechain.get("records", {})
        execs = records.get("AGENT_EXECUTIONS", [])
        decs = records.get("AGENT_DECISIONS", [])
        evs = records.get("EVIDENCE", [])
        accs = records.get("ACCOUNTABILITY_SCORES", [])
        provs = records.get("PROVENANCE_RECORDS", [])

        if not execs:
            raise ValueError("bank tracechain contains no AGENT_EXECUTIONS")

        execution = dict(execs[0])
        decision = dict(decs[0]) if decs else {
            "decision_id": "",
            "execution_id": execution.get("execution_id"),
            "decision_output": "skipped",
            "confidence_score": 0.0,
            "reasoning": "No decision produced",
            "timestamp": execution.get("end_time"),
        }
        evidence = [dict(e) for e in evs]
        accountability = dict(accs[0]) if accs else {
            "score_id": "",
            "execution_id": execution.get("execution_id"),
            "impact_score": 0,
            "irreversibility_score": 0,
            "explainability_score": 10,
            "composite_risk_score": 0.0,
            "risk_level": "Low",
            "review_required": False,
            "scoring_model_version": "tracechain-scoring-v1",
            "calculated_at": execution.get("end_time"),
        }
        if provs:
            provenance = dict(provs[0])
        else:
            provenance = {
                "record_id": "",
                "orchestration_id": orchestration_id,
                "execution_id": execution.get("execution_id"),
                "event_type": "agent_decision",
                "timestamp": execution.get("end_time"),
                "input_hash": "",
                "output_hash": "",
                "previous_record_hash": None,
                "record_hash": "",
            }

        # Enforce orchestrator metadata
        execution["agent_id"] = AGENT_ID
        execution["orchestration_id"] = orchestration_id
        execution["sequence_number"] = SEQUENCE_NUMBER
        provenance["orchestration_id"] = orchestration_id

        # Ensure IDs are UUIDs (orchestrator DB expects UUID text fields)
        def _is_uuid(val: str) -> bool:
            try:
                uuid.UUID(str(val))
                return True
            except Exception:
                return False

        old_exec_id = execution.get("execution_id")
        if not _is_uuid(old_exec_id):
            new_exec_id = str(uuid.uuid4())
        else:
            new_exec_id = str(old_exec_id)

        # replace execution IDs and generate canonical UUIDs for related IDs
        execution["execution_id"] = new_exec_id

        # normalize status to match DB constraint (lowercase)
        execution["status"] = str(execution.get("status", "completed")).lower()

        # decision IDs
        if not _is_uuid(decision.get("decision_id")):
            decision["decision_id"] = str(uuid.uuid4())
        decision["execution_id"] = new_exec_id

        # accountability
        if not _is_uuid(accountability.get("score_id")):
            accountability["score_id"] = str(uuid.uuid4())
        accountability["execution_id"] = new_exec_id

        # evidence items: ensure IDs and map to orchestrator evidence schema
        normalized_evidence = []
        for ev in evidence:
            if not _is_uuid(ev.get("evidence_id")):
                ev["evidence_id"] = str(uuid.uuid4())
            ev["execution_id"] = new_exec_id
            item = {
                "evidence_id": ev["evidence_id"],
                "execution_id": ev["execution_id"],
                "source": ev.get("source", "bank_statement"),
                "document_reference": ev.get("data_reference") or ev.get("document_reference") or "",
                "retrieval_score": ev.get("retrieval_score", 1.0),
                "timestamp": ev.get("timestamp"),
            }
            normalized_evidence.append(item)

        evidence = normalized_evidence

        # provenance
        provenance["execution_id"] = new_exec_id
        if not _is_uuid(provenance.get("record_id")):
            provenance["record_id"] = str(uuid.uuid4())

        return {
            "execution": execution,
            "decision": decision,
            "evidence": evidence,
            "accountability": accountability,
            "provenance": provenance,
        }

    # Attempt integration with the imp_docs bank_statement agent
    try:
        from agents.import_isolation import prepare_agent_import, restore_orchestrator_path
        from pathlib import Path
        import json
        import runpy

        _ORCH_DIR = Path(__file__).resolve().parent.parent
        _BANK_DIR = _ORCH_DIR.parent / "agents" / "bank_statement" / "src"

        prepare_agent_import(_BANK_DIR)
        try:
            # Try to import the tracechain module from the bank agent
            import bank_statement_tracechain as bst  # noqa: F401
        finally:
            restore_orchestrator_path(_ORCH_DIR)

        # The bank agent writes an output JSON to data/processed by default.
        output_path = (_BANK_DIR.parent / "data" / "processed" / "bank_statement_tracechain_output.json")
        tracechain = None
        if output_path.exists():
            with open(output_path, "r", encoding="utf-8") as f:
                tracechain = json.load(f)
        else:
            # Run the module to produce the output file, then load it.
            runpy.run_path(str(_BANK_DIR / "bank_statement_tracechain.py"), run_name="__main__")
            if output_path.exists():
                with open(output_path, "r", encoding="utf-8") as f:
                    tracechain = json.load(f)

        if not tracechain:
            raise RuntimeError("Could not obtain bank statement tracechain output")

        result = _normalise_from_tracechain(tracechain, orchestration_id)
        logger.info("[A003] Bank agent integrated successfully — returning real result.")
        return result

    except Exception as exc:
        logger.exception("[A003] Bank integration failed, falling back to stub: %s", exc)
        return _stub_result(state, orchestration_id)
