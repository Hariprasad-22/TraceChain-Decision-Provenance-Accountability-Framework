"""
db/writer.py
------------
All PostgreSQL write functions for the TraceChain orchestrator.

Each function maps exactly to one table in tracechain_schema.sql.
The orchestrator calls these in order after each agent run.

Column rules (from schema comments):
  - AGENT_EXECUTIONS has no input_hash column (hashing is orchestrator's job)
  - PROVENANCE_RECORDS stores only hashes (no raw input/output data)
  - AGENT_DECISIONS.decision_timestamp comes from agent's decision.timestamp
  - ACCOUNTABILITY_SCORES.composite_risk_score is recomputed by orchestrator
    formula: 0.40*irreversibility + 0.35*impact + 0.25*(10-explainability)
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from db.connection import get_conn, release_conn

logger = logging.getLogger(__name__)


# ─── helpers ──────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json(obj) -> str:
    """Serialize to JSON string for JSONB columns."""
    return json.dumps(obj, default=str)


def _exec(sql: str, params: tuple) -> None:
    """Execute a single statement with auto-commit and pool release."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        release_conn(conn)


# ─── USERS ────────────────────────────────────────────────────────────────────

def write_user(user_id: str, created_at: Optional[datetime] = None) -> None:
    """
    Insert a row into USERS.
    Skips silently if the user already exists (idempotent).
    """
    sql = """
        INSERT INTO users (user_id, created_at)
        VALUES (%s, %s)
        ON CONFLICT (user_id) DO NOTHING;
    """
    _exec(sql, (user_id, created_at or _now()))
    logger.info("USERS: upserted user_id=%s", user_id)


# ─── APPLICATIONS ─────────────────────────────────────────────────────────────

def write_application(
    application_id: str,
    user_id: str,
    loan_amount: float,
    application_date: Optional[datetime] = None,
    status: str = "processing",
) -> None:
    """
    Insert a row into APPLICATIONS.
    Skips silently if application_id already exists.
    """
    sql = """
        INSERT INTO applications (application_id, user_id, loan_amount, application_date, status)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (application_id) DO NOTHING;
    """
    _exec(sql, (application_id, user_id, loan_amount, application_date or _now(), status))
    logger.info("APPLICATIONS: upserted application_id=%s", application_id)


def update_application_status(application_id: str, status: str) -> None:
    """Update the status of an existing application."""
    sql = "UPDATE applications SET status = %s WHERE application_id = %s;"
    _exec(sql, (status, application_id))
    logger.info("APPLICATIONS: updated status=%s for application_id=%s", status, application_id)


# ─── ORCHESTRATIONS ───────────────────────────────────────────────────────────

def write_orchestration(
    orchestration_id: str,
    application_id: str,
    orchestrator_version: str,
    status: str = "InProgress",
    scenario: Optional[str] = None,
    start_time: Optional[datetime] = None,
) -> None:
    """Insert a row into ORCHESTRATIONS when a pipeline run begins."""
    sql = """
        INSERT INTO orchestrations
            (orchestration_id, application_id, orchestrator_version, scenario, status, start_time)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (orchestration_id) DO NOTHING;
    """
    _exec(sql, (
        orchestration_id, application_id, orchestrator_version,
        scenario, status, start_time or _now()
    ))
    logger.info("ORCHESTRATIONS: created orchestration_id=%s", orchestration_id)


def update_orchestration(
    orchestration_id: str,
    status: str,
    end_time: Optional[datetime] = None,
) -> None:
    """Mark an orchestration as Completed/Failed with an end timestamp."""
    sql = """
        UPDATE orchestrations
        SET status = %s, end_time = %s
        WHERE orchestration_id = %s;
    """
    _exec(sql, (status, end_time or _now(), orchestration_id))
    logger.info("ORCHESTRATIONS: updated status=%s for orchestration_id=%s", status, orchestration_id)


# ─── AGENT_EXECUTIONS ─────────────────────────────────────────────────────────

def write_agent_execution(
    execution_id: str,
    orchestration_id: str,
    agent_id: str,
    sequence_number: int,
    input_data: dict,
    output_data: dict,
    model_id: str,
    rule_id: Optional[str],
    start_time: str,
    end_time: str,
    status: str,
    parent_execution_id: Optional[str] = None,
) -> None:
    """
    Insert a row into AGENT_EXECUTIONS.
    Note: no input_hash column — hashing lives in PROVENANCE_RECORDS only.
    """
    sql = """
        INSERT INTO agent_executions
            (execution_id, orchestration_id, agent_id, parent_execution_id,
             sequence_number, input_data, output_data, model_id, rule_id,
             start_time, end_time, status)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
        ON CONFLICT (execution_id) DO NOTHING;
    """
    _exec(sql, (
        execution_id, orchestration_id, agent_id, parent_execution_id,
        sequence_number, _json(input_data), _json(output_data),
        model_id, rule_id, start_time, end_time, status
    ))
    logger.info("AGENT_EXECUTIONS: wrote execution_id=%s agent_id=%s", execution_id, agent_id)


# ─── AGENT_DECISIONS ──────────────────────────────────────────────────────────

def write_agent_decision(
    decision_id: str,
    execution_id: str,
    decision_output: str,
    confidence_score: float,
    reasoning: str,
    decision_timestamp: str,
) -> None:
    """Insert a row into AGENT_DECISIONS."""
    sql = """
        INSERT INTO agent_decisions
            (decision_id, execution_id, decision_output, confidence_score,
             reasoning, decision_timestamp)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (decision_id) DO NOTHING;
    """
    _exec(sql, (
        decision_id, execution_id, decision_output,
        confidence_score, reasoning, decision_timestamp
    ))
    logger.info("AGENT_DECISIONS: wrote decision_id=%s output=%s", decision_id, decision_output)


# ─── EVIDENCE ─────────────────────────────────────────────────────────────────

def write_evidence_items(evidence_list: list[dict]) -> None:
    """
    Bulk-insert all evidence rows for one agent execution.
    Each dict should have: evidence_id, execution_id, source,
    document_reference, retrieval_score, timestamp.
    """
    if not evidence_list:
        return

    sql = """
        INSERT INTO evidence
            (evidence_id, execution_id, source, document_reference,
             retrieval_score, timestamp)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (evidence_id) DO NOTHING;
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            for item in evidence_list:
                # Clamp retrieval_score to [0.0, 1.0] to respect DB CHECK
                score = item.get("retrieval_score", 0.0)
                if score is not None:
                    score = min(1.0, max(0.0, float(score)))
                cur.execute(sql, (
                    item["evidence_id"],
                    item["execution_id"],
                    item["source"],
                    item["document_reference"],
                    score,
                    item.get("timestamp", _now()),
                ))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        release_conn(conn)
    logger.info("EVIDENCE: wrote %d items for execution_id=%s",
                len(evidence_list), evidence_list[0]["execution_id"])


# ─── ACCOUNTABILITY_SCORES ────────────────────────────────────────────────────

def write_accountability_score(
    score_id: str,
    execution_id: str,
    impact_score: int,
    irreversibility_score: int,
    explainability_score: int,
    composite_risk_score: float,
    risk_level: str,
    review_required: bool,
    scoring_model_version: str,
    calculated_at: str,
) -> None:
    """
    Insert a row into ACCOUNTABILITY_SCORES.
    composite_risk_score is always recomputed by the orchestrator
    using: 0.40*irrev + 0.35*impact + 0.25*(10-expl)
    """
    sql = """
        INSERT INTO accountability_scores
            (score_id, execution_id, irreversibility_score, impact_score,
             explainability_score, composite_risk_score, risk_level,
             review_required, scoring_model_version, calculated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (score_id) DO NOTHING;
    """
    _exec(sql, (
        score_id, execution_id, irreversibility_score, impact_score,
        explainability_score, composite_risk_score, risk_level,
        review_required, scoring_model_version, calculated_at
    ))
    logger.info("ACCOUNTABILITY_SCORES: wrote score_id=%s composite=%.2f risk=%s",
                score_id, composite_risk_score, risk_level)


# ─── FINAL_DECISIONS ──────────────────────────────────────────────────────────

def write_final_decision(
    final_decision_id: str,
    orchestration_id: str,
    answer: str,                  # 'Approved' | 'Rejected' | 'Manual Review'
    responsible_agent_id: str,
    reasoning: str,
    risk_score: float,
    decision_status: str = "Final",
    timestamp: Optional[datetime] = None,
) -> None:
    """Insert a row into FINAL_DECISIONS."""
    sql = """
        INSERT INTO final_decisions
            (final_decision_id, orchestration_id, answer, responsible_agent_id,
             reasoning, risk_score, decision_status, timestamp)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (final_decision_id) DO NOTHING;
    """
    _exec(sql, (
        final_decision_id, orchestration_id, answer, responsible_agent_id,
        reasoning, risk_score, decision_status, timestamp or _now()
    ))
    logger.info("FINAL_DECISIONS: wrote answer=%s risk_score=%.2f", answer, risk_score)


# ─── PROVENANCE_RECORDS ───────────────────────────────────────────────────────

def write_provenance_record(
    record_id: str,
    orchestration_id: str,
    execution_id: str,
    event_type: str,
    timestamp: str,
    input_hash: str,
    output_hash: str,
    previous_record_hash: Optional[str],
    record_hash: str,
) -> None:
    """
    Insert a row into PROVENANCE_RECORDS (lean hash-chain table).
    No raw input/output data stored here — only hashes.
    record_hash is computed by the orchestrator's hasher module.
    """
    sql = """
        INSERT INTO provenance_records
            (record_id, orchestration_id, execution_id, event_type,
             timestamp, input_hash, output_hash, previous_record_hash, record_hash)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (record_id) DO NOTHING;
    """
    _exec(sql, (
        record_id, orchestration_id, execution_id, event_type,
        timestamp, input_hash, output_hash, previous_record_hash, record_hash
    ))
    logger.info("PROVENANCE_RECORDS: wrote record_id=%s prev=%s",
                record_id, (previous_record_hash or "GENESIS")[:16])


# ─── AUDIT_EVENTS ─────────────────────────────────────────────────────────────

def write_audit_event(
    orchestration_id: str,
    event_type: str,
    actor: str,
    description: str,
    execution_id: Optional[str] = None,
    record_hash: Optional[str] = None,
    timestamp: Optional[datetime] = None,
) -> None:
    """Log an entry to AUDIT_EVENTS for traceability."""
    sql = """
        INSERT INTO audit_events
            (orchestration_id, execution_id, event_type, actor,
             description, timestamp, record_hash)
        VALUES (%s, %s, %s, %s, %s, %s, %s);
    """
    _exec(sql, (
        orchestration_id, execution_id, event_type, actor,
        description, timestamp or _now(), record_hash
    ))
    logger.debug("AUDIT_EVENTS: %s | %s", event_type, description[:60])
