"""
Builds the Aadhar agent's output in the exact shape TraceChain's relational
schema expects (see TraceChain_Schema_Design.pdf from the orchestrator
teammate) - AGENT_EXECUTIONS, AGENT_DECISIONS, EVIDENCE,
ACCOUNTABILITY_SCORES, and PROVENANCE_RECORDS - so the orchestrator can
write directly into those tables with no translation layer.

This is also the concrete, demonstrable answer to the mentor's question on
"what does tamper-evident mean here": PROVENANCE_RECORDS.input_hash /
output_hash / previous_record_hash / record_hash are computed by real code
below on every single execution, and verify_provenance_record() proves
tampering is actually detectable, not just a named column in a diagram.
"""
import hashlib
import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Optional


def _hash(payload) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


@dataclass
class ExecutionMetadata:
    """Maps to AGENT_EXECUTIONS."""
    execution_id: str
    orchestration_id: str
    agent_id: str
    input_data: dict
    output_data: dict
    model_id: str
    rule_id: str
    start_time: str
    end_time: str
    status: str
    sequence_number: int = 1
    input_hash: str = field(init=False, default="")

    def __post_init__(self):
        self.input_hash = _hash(self.input_data)


@dataclass
class AgentDecision:
    """Maps to AGENT_DECISIONS."""
    decision_id: str
    execution_id: str
    decision_output: str
    confidence_score: float
    reasoning: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class Evidence:
    """Maps to EVIDENCE. One row per retrieved policy clause."""
    evidence_id: str
    execution_id: str
    source: str
    document_reference: str
    retrieval_score: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class AccountabilityScore:
    """Maps to ACCOUNTABILITY_SCORES."""
    score_id: str
    execution_id: str
    impact_score: int
    irreversibility_score: int
    explainability_score: int
    composite_risk_score: float
    risk_level: str
    review_required: bool
    scoring_model_version: str = "tracechain-scoring-v1"
    calculated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ProvenanceRecordV2:
    """Maps to PROVENANCE_RECORDS - the tamper-evident, hash-chained
    record. previous_record_hash is None for the Aadhaar agent specifically,
    since it always runs first in the orchestration sequence (Aadhaar ->
    Payslip -> Bank -> CIBIL, per the schema's worked example)."""
    record_id: str
    orchestration_id: str
    execution_id: str
    event_type: str
    input_data: dict
    output_data: dict
    previous_record_hash: Optional[str]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    input_hash: str = field(init=False, default="")
    output_hash: str = field(init=False, default="")
    record_hash: str = field(init=False, default="")

    def __post_init__(self):
        self.input_hash = _hash(self.input_data)
        self.output_hash = _hash(self.output_data)
        # The record's own hash depends on the previous record's hash -
        # this IS the chain. Altering any past record changes its
        # output_hash, which changes every record_hash after it.
        chain_payload = {
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "previous_record_hash": self.previous_record_hash,
            "execution_id": self.execution_id,
        }
        self.record_hash = _hash(chain_payload)


def verify_provenance_record(record: ProvenanceRecordV2) -> bool:
    """Recomputes the hash chain from scratch against the record's stored
    input_data/output_data - proves tampering is actually detectable."""
    if _hash(record.input_data) != record.input_hash:
        return False
    if _hash(record.output_data) != record.output_hash:
        return False
    chain_payload = {
        "input_hash": record.input_hash,
        "output_hash": record.output_hash,
        "previous_record_hash": record.previous_record_hash,
        "execution_id": record.execution_id,
    }
    return _hash(chain_payload) == record.record_hash


def risk_level_for(composite_score_0_10: float) -> str:
    if composite_score_0_10 >= 7:
        return "High"
    if composite_score_0_10 >= 4:
        return "Medium"
    return "Low"
