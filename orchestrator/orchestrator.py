"""
orchestrator/orchestrator.py
-----------------------------
TraceChain Orchestrator — the central coordinator for the loan
approval pipeline.

Pipeline order (serial, fixed):
    1. Aadhaar Verification Agent  (A001)
    2. Payslip Income Agent        (A002)
    3. Bank Statement Agent        (A003) ← stub, skipped until integrated
    4. CIBIL Score Agent           (A004)

Orchestrator responsibilities:
    ✓ Validate incoming application state
    ✓ Write USERS / APPLICATIONS / ORCHESTRATIONS rows
    ✓ Scope input and invoke each agent in order
    ✓ Recompute tamper-evident hash chain (previous_record_hash linking)
    ✓ Write all 5 TraceChain tables per agent: AGENT_EXECUTIONS,
      AGENT_DECISIONS, EVIDENCE, ACCOUNTABILITY_SCORES, PROVENANCE_RECORDS
    ✓ Normalise composite_risk_score to canonical formula across agents
    ✓ Compute overall accountability score (equal-weight average)
    ✓ Synthesize final loan decision with full reasoning
    ✓ Write FINAL_DECISIONS and mark ORCHESTRATIONS as Completed
    ✓ Write AUDIT_EVENTS throughout for traceability
    ✓ Return structured result to caller (UI-ready dict)

Public API:
    run_pipeline(state: dict) -> dict
    validate_state(state: dict) -> None   (raises ValueError on bad input)
"""

import logging
import uuid
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# ─── load env ─────────────────────────────────────────────────────────────────
_env_candidates = [
    Path(__file__).resolve().parents[1] / ".env",
    Path(__file__).resolve().parent / ".env",
]
for candidate in _env_candidates:
    if candidate.exists():
        load_dotenv(candidate)
        break

# Ensure agent LLM clients see the same Gemini credentials.
_gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if _gemini_key:
    os.environ.setdefault("GEMINI_API_KEY", _gemini_key)
    os.environ.setdefault("GOOGLE_API_KEY", _gemini_key)
os.environ.setdefault("GEMINI_MODEL", os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

ORCHESTRATOR_VERSION = os.getenv("ORCHESTRATOR_VERSION", "v1.0.0")

# ─── internal imports ─────────────────────────────────────────────────────────
try:
    from .db import writer as db
    from .chain.hasher import recompute_provenance_chain, verify_chain
    from .scoring.overall_score import (
        compute_overall, normalise_agent_score, determine_responsible_agent
    )
    from .final_decision.synthesizer import synthesize
    from .agents import aadhaar_adapter, payslip_adapter, bank_adapter, cibil_adapter
except ImportError:  # pragma: no cover - script-style execution from orchestrator/
    from db import writer as db
    from chain.hasher import recompute_provenance_chain, verify_chain
    from scoring.overall_score import (
        compute_overall, normalise_agent_score, determine_responsible_agent
    )
    from final_decision.synthesizer import synthesize
    from agents import aadhaar_adapter, payslip_adapter, bank_adapter, cibil_adapter

# ─── logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("orchestrator")


# ─── required state fields ────────────────────────────────────────────────────

_REQUIRED_TOP_LEVEL = [
    "user_id", "application_id", "loan_amount",
    "applicant_name", "applicant_data",
]
_REQUIRED_APPLICANT_DATA = ["aadhar_image_path", "payslip_file_path", "bank_statement_file_path"]
_REQUIRED_CIBIL = ["cibil_score"]
# Numeric IDs must be >= 100001 (sequential from the frontend counter).
_USER_ID_RE = re.compile(r"^\d+$")
_APPLICATION_ID_RE = re.compile(r"^APP-(\d+)$")
_MIN_ID = 100001


# ─── state validation ─────────────────────────────────────────────────────────

def _validate_uploaded_file(field_name: str, file_path: Optional[str]) -> None:
    if not file_path:
        raise ValueError(f"Missing applicant_data field: '{field_name}'")

    path = Path(file_path)
    if not path.exists():
        raise ValueError(f"Missing uploaded file: '{field_name}' does not exist at '{path}'")
    if not path.is_file():
        raise ValueError(f"Missing uploaded file: '{field_name}' is not a valid file at '{path}'")


def validate_state(state: dict) -> None:
    """
    Validate the application state before the pipeline starts.
    Raises ValueError with a clear message on the first missing/invalid field.
    """
    for field in _REQUIRED_TOP_LEVEL:
        if field not in state or state[field] is None:
            raise ValueError(f"Missing required field: '{field}'")

    user_id = str(state.get("user_id", ""))
    if not _USER_ID_RE.fullmatch(user_id) or int(user_id) < _MIN_ID:
        raise ValueError(f"user_id must start from 100001, got: {user_id}")

    application_id = str(state.get("application_id", ""))
    app_match = _APPLICATION_ID_RE.fullmatch(application_id)
    if not app_match or int(app_match.group(1)) < _MIN_ID:
        raise ValueError(f"application_id must start from APP-100001, got: {application_id}")

    loan = state.get("loan_amount", 0)
    if not (0 < float(loan) <= 5_000_000):
        raise ValueError(f"loan_amount out of range (0, 5000000]: got {loan}")

    applicant_data = state["applicant_data"]
    for field in _REQUIRED_APPLICANT_DATA:
        if not applicant_data.get(field):
            raise ValueError(f"Missing applicant_data field: '{field}'")
        _validate_uploaded_file(field, applicant_data.get(field))

    for field in _REQUIRED_CIBIL:
        if field not in state or state[field] is None:
            raise ValueError(f"Missing CIBIL field: '{field}'")

    cibil = state.get("cibil_score")
    if cibil is not None and not (300 <= int(cibil) <= 900):
        raise ValueError(f"cibil_score must be 300–900, got: {cibil}")


# ─── DB write helper ──────────────────────────────────────────────────────────

def _write_agent_result(
    result: dict,
    orchestration_id: str,
    sequence_number: int,
    provenance_override: dict,
) -> None:
    """
    Write all 5 TraceChain tables for one agent execution.

    Parameters
    ----------
    result              : normalised agent result dict
    orchestration_id    : str
    sequence_number     : 1-4
    provenance_override : the recomputed provenance dict from hasher
    """
    exec_meta     = result["execution"]
    decision_data = result["decision"]
    evidence_list = result["evidence"]
    acc_data      = result["accountability"]

    execution_id = exec_meta["execution_id"]

    # 1. AGENT_EXECUTIONS
    db.write_agent_execution(
        execution_id=execution_id,
        orchestration_id=orchestration_id,
        agent_id=exec_meta["agent_id"],
        sequence_number=sequence_number,
        input_data=exec_meta.get("input_data", {}),
        output_data=exec_meta.get("output_data", {}),
        model_id=exec_meta.get("model_id", "unknown"),
        rule_id=exec_meta.get("rule_id"),
        start_time=exec_meta.get("start_time"),
        end_time=exec_meta.get("end_time"),
        status=exec_meta.get("status", "completed"),
    )

    # 2. AGENT_DECISIONS
    conf_raw = decision_data.get("confidence_score")
    try:
        confidence_score = float(conf_raw if conf_raw is not None else 0.0)
    except (TypeError, ValueError):
        confidence_score = 0.0
    db.write_agent_decision(
        decision_id=decision_data["decision_id"],
        execution_id=execution_id,
        decision_output=decision_data["decision_output"],
        confidence_score=confidence_score,
        reasoning=decision_data["reasoning"],
        decision_timestamp=decision_data.get("timestamp", datetime.now(timezone.utc).isoformat()),
    )

    # 3. EVIDENCE (may be empty)
    if evidence_list:
        db.write_evidence_items(evidence_list)

    # 4. ACCOUNTABILITY_SCORES (normalised composite formula)
    norm_acc = normalise_agent_score(acc_data)
    db.write_accountability_score(
        score_id=acc_data["score_id"],
        execution_id=execution_id,
        impact_score=int(norm_acc["impact_score"]),
        irreversibility_score=int(norm_acc["irreversibility_score"]),
        explainability_score=int(norm_acc["explainability_score"]),
        composite_risk_score=float(norm_acc["composite_risk_score"]),
        risk_level=norm_acc["risk_level"],
        review_required=bool(norm_acc["review_required"]),
        scoring_model_version=str(acc_data.get("scoring_model_version", "tracechain-score-v1"))[:20],
        calculated_at=acc_data.get("calculated_at", datetime.now(timezone.utc).isoformat()),
    )

    # 5. PROVENANCE_RECORDS (orchestrator-recomputed chain)
    db.write_provenance_record(
        record_id=provenance_override["record_id"],
        orchestration_id=orchestration_id,
        execution_id=execution_id,
        event_type=provenance_override.get("event_type", "agent_decision"),
        timestamp=provenance_override.get("timestamp", datetime.now(timezone.utc).isoformat()),
        input_hash=provenance_override["input_hash"],
        output_hash=provenance_override["output_hash"],
        previous_record_hash=provenance_override["previous_record_hash"],
        record_hash=provenance_override["record_hash"],
    )


# ─── main pipeline ────────────────────────────────────────────────────────────

def run_pipeline(state: dict) -> dict:
    """
    Execute the full TraceChain loan approval pipeline.

    Parameters
    ----------
    state : dict
        Application state. Required fields:

        Top-level:
            user_id             str      e.g. '100001'
            application_id      str      e.g. 'APP-100001'
            loan_amount         float    e.g. 150000.0
            applicant_name      str      e.g. 'Udyati Seth'
            applicant_dob       str      (optional) e.g. '1995-01-15'
            cibil_score         int      300-900
            credit_utilization_pct  float   (optional, default 0.0)
            dpd_history         list[int] (optional, default [])
            declared_monthly_income float   (optional, payslip income)

        applicant_data (dict):
            aadhar_image_path   str   path to Aadhaar image file
            payslip_file_path   str   path to payslip PDF file
            scenario            str   (optional) payslip scenario key
            gender              str   (optional)
            address             str   (optional)

    Returns
    -------
    dict
        loan_decision           str   'Approved' | 'Rejected'
        overall_accountability  dict  composite score + risk level
        agent_breakdown         list  per-agent decision + scores + reasoning
        reasoning               str   full synthesized explanation
        chain_verified          bool  tamper-check result
        orchestration_id        str
        application_id          str
        error                   str   (only present if pipeline failed)
    """
    pipeline_start = datetime.now(timezone.utc)

    # ── 0. Validate ────────────────────────────────────────────────────────────
    try:
        validate_state(state)
    except ValueError as exc:
        logger.error("State validation failed: %s", exc)
        return {"error": str(exc), "loan_decision": "Rejected"}

    # ── Resolve or create user_id & application_id via DB check ─────────────
    try:
        user_id, application_id = db.get_or_create_user_and_application(
            applicant_name=state.get("applicant_name"),
            requested_user_id=state.get("user_id"),
            requested_app_id=state.get("application_id"),
        )
        state["user_id"] = user_id
        state["application_id"] = application_id
    except Exception as exc:
        logger.warning("DB user resolution failed, falling back to state values: %s", exc)
        user_id = state["user_id"]
        application_id = state["application_id"]

    orchestration_id = f"ORC-{application_id}-{uuid.uuid4().hex[:8].upper()}"

    logger.info("=" * 60)
    logger.info("Pipeline START  user_id=%s  application_id=%s  orchestration_id=%s",
                user_id, application_id, orchestration_id)
    logger.info("=" * 60)

    # ── 1. Write USERS / APPLICATIONS / ORCHESTRATIONS ────────────────────────
    db.write_user(user_id, applicant_name=state.get("applicant_name"))
    db.write_application(
        application_id=application_id,
        user_id=user_id,
        loan_amount=float(state["loan_amount"]),
        status="processing",
    )
    db.write_orchestration(
        orchestration_id=orchestration_id,
        application_id=application_id,
        orchestrator_version=ORCHESTRATOR_VERSION,
        status="InProgress",
        start_time=pipeline_start,
    )
    db.write_audit_event(
        orchestration_id=orchestration_id,
        event_type="pipeline_started",
        actor="orchestrator",
        description=f"Pipeline started for application_id={application_id} "
                    f"loan_amount={state['loan_amount']}",
    )

    # ── state tracking across agents ──────────────────────────────────────────
    previous_record_hash: Optional[str] = None   # the hash chain carrier
    provenance_chain: list[dict] = []             # for end-of-pipeline chain verify
    active_agent_results: list[dict] = []         # skip stubs
    all_accountabilities: list[dict] = []

    # ── AGENT EXECUTION SEQUENCE ──────────────────────────────────────────────
    agents = [
        ("A001", aadhaar_adapter, 1),
        ("A002", payslip_adapter, 2),
        ("A003", bank_adapter,    3),  # stub — no DB write
        ("A004", cibil_adapter,   4),
    ]

    for agent_id, adapter, seq_num in agents:
        logger.info("─── Agent %s (seq=%d) ───────────────────────────", agent_id, seq_num)

        try:
            result = adapter.run(state, orchestration_id)
        except Exception as exc:
            logger.error("[%s] Agent raised exception: %s", agent_id, exc, exc_info=True)
            db.update_orchestration(orchestration_id, status="Failed")
            db.write_audit_event(
                orchestration_id=orchestration_id,
                event_type="agent_error",
                actor=agent_id,
                description=f"Agent {agent_id} failed: {exc}",
            )
            return {
                "error": f"Agent {agent_id} failed: {exc}",
                "loan_decision": "Rejected",
                "orchestration_id": orchestration_id,
                "application_id": application_id,
            }

        # ── Bank stub: skip DB write, carry hash forward unchanged ────────────
        if result.get("skipped"):
            logger.info("[%s] Skipped (stub) — hash chain carries forward.", agent_id)
            db.write_audit_event(
                orchestration_id=orchestration_id,
                event_type="agent_skipped",
                actor=agent_id,
                description=f"Agent {agent_id} skipped (not yet integrated).",
            )
            continue   # previous_record_hash stays the same for CIBIL

        # ── Recompute provenance hash chain ───────────────────────────────────
        execution_id = result["execution"]["execution_id"]
        provenance   = recompute_provenance_chain(
            agent_result=result,
            previous_record_hash=previous_record_hash,
            execution_id=execution_id,
        )

        # ── Write all 5 tables to PostgreSQL ──────────────────────────────────
        _write_agent_result(
            result=result,
            orchestration_id=orchestration_id,
            sequence_number=seq_num,
            provenance_override=provenance,
        )

        # ── Audit trail ───────────────────────────────────────────────────────
        try:
            conf = float((result.get("decision") or {}).get("confidence_score") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        db.write_audit_event(
            orchestration_id=orchestration_id,
            execution_id=execution_id,
            event_type="agent_decision",
            actor=agent_id,
            description=(
                f"Agent {agent_id} decided: "
                f"{result['decision']['decision_output']} "
                f"(confidence={conf:.0%})"
            ),
            record_hash=provenance["record_hash"],
        )

        # ── Thread the hash forward ───────────────────────────────────────────
        previous_record_hash = provenance["record_hash"]
        provenance_chain.append(provenance)

        # ── Collect for scoring + synthesis ──────────────────────────────────
        norm_acc = normalise_agent_score(result["accountability"])
        output_data = (result.get("execution") or {}).get("output_data") or {}
        active_agent_results.append({
            "agent_id":            agent_id,
            "decision_output":     result["decision"]["decision_output"],
            "confidence_score":    result["decision"]["confidence_score"],
            "reasoning":           result["decision"]["reasoning"],
            "composite_risk_score": norm_acc["composite_risk_score"],
            "name_mismatch":       bool(output_data.get("name_mismatch")),
            "name_mismatch_reason": output_data.get("name_mismatch_reason"),
        })
        all_accountabilities.append(norm_acc)

        logger.info(
            "[%s] Written to DB. record_hash=%s",
            agent_id, provenance["record_hash"][:20],
        )

    # ── 3. Overall Accountability Score ───────────────────────────────────────
    overall = compute_overall(all_accountabilities)
    logger.info(
        "Overall score: %.2f (%s) from %d agents",
        overall["overall_composite"], overall["overall_risk_level"], overall["agent_count"],
    )

    # ── 4. Responsible Agent ──────────────────────────────────────────────────
    responsible_agent = determine_responsible_agent(active_agent_results)

    # ── 5. Final Decision ─────────────────────────────────────────────────────
    final = synthesize(
        agent_results=active_agent_results,
        overall_composite=overall["overall_composite"],
        overall_risk_level=overall["overall_risk_level"],
        responsible_agent_id=responsible_agent,
    )

    # Name mismatch on any document agent → final Rejected, that agent drives.
    # Agent decision_output values themselves are left unchanged in the breakdown.
    mismatch_driver = next((a for a in active_agent_results if a.get("name_mismatch")), None)
    if mismatch_driver:
        responsible_agent = mismatch_driver["agent_id"]
        mismatch_reason = mismatch_driver.get("name_mismatch_reason") or (
            "The name does not match the inputs given."
        )
        final["answer"] = "Rejected"
        final["responsible_agent_id"] = responsible_agent
        final["reasoning"] = (
            f"The application was rejected because the name does not match the inputs given. "
            f"Driving agent: {responsible_agent}.\n\n{mismatch_reason}"
        )
        logger.info(
            "Final decision overridden to Rejected by name mismatch on %s",
            responsible_agent,
        )

    final_decision_id = str(uuid.uuid4())
    db.write_final_decision(
        final_decision_id=final_decision_id,
        orchestration_id=orchestration_id,
        answer=final["answer"],
        responsible_agent_id=responsible_agent,
        reasoning=final["reasoning"],
        risk_score=final["risk_score"],
        decision_status=final["decision_status"],
        timestamp=final["timestamp"],
    )

    # ── 6. Update Application + Orchestration status ──────────────────────────
    answer_to_status = {
        "Approved": "approved",
        "Rejected": "rejected",
        "Manual Review": "rejected",  # legacy: treat review as rejected
    }
    db.update_application_status(application_id, answer_to_status.get(final["answer"], "rejected"))
    db.update_orchestration(orchestration_id, status="Completed")

    # ── 7. Verify the full hash chain ─────────────────────────────────────────
    chain_ok = verify_chain(provenance_chain)

    # ── 8. Final audit ────────────────────────────────────────────────────────
    db.write_audit_event(
        orchestration_id=orchestration_id,
        event_type="pipeline_completed",
        actor="orchestrator",
        description=(
            f"Pipeline completed. Final decision: {final['answer']}. "
            f"Overall risk: {overall['overall_composite']:.2f}/10 ({overall['overall_risk_level']}). "
            f"Chain verified: {chain_ok}."
        ),
    )

    logger.info("=" * 60)
    logger.info("Pipeline COMPLETE  decision=%s  chain_ok=%s",
                final["answer"], chain_ok)
    logger.info("=" * 60)

    # ── 9. Return structured result ───────────────────────────────────────────
    return {
        "loan_decision":        final["answer"],
        "reasoning":            final["reasoning"],
        "agent_breakdown":      final["agent_breakdown"],
        "overall_accountability": {
            "composite_score": overall["overall_composite"],
            "risk_level":      overall["overall_risk_level"],
            "agent_count":     overall["agent_count"],
        },
        "chain_verified":     chain_ok,
        "orchestration_id":   orchestration_id,
        "application_id":     application_id,
        "final_decision_id":  final_decision_id,
        "responsible_agent":  responsible_agent,
    }
