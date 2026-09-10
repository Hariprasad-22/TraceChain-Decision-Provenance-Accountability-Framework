"""
Common execution-record module for TraceChain.

Used by:
    - Aadhaar Agent
    - Payslip / Income Verification Agent
    - Bank Agent
    - CIBIL Agent

Every agent can create:
    AGENT_EXECUTIONS
    AGENT_DECISIONS
    EVIDENCE
    ACCOUNTABILITY_SCORES
    PROVENANCE_RECORDS

The provenance record is hash-chained so that tampering
with input/output data can be detected.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


# =========================================================
# COMMON UTILITIES
# =========================================================

def _now_iso():
    """Return current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _hash(payload) -> str:
    """Create deterministic SHA-256 hash."""
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            default=str
        ).encode()
    ).hexdigest()


# =========================================================
# 1. AGENT_EXECUTIONS
# =========================================================

@dataclass
class ExecutionMetadata:
    """
    Common execution information for any agent.

    Works for:
        Aadhaar
        Payslip
        Bank
        CIBIL
    """

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

    input_hash: str = field(
        init=False,
        default=""
    )

    def __post_init__(self):
        self.input_hash = _hash(self.input_data)


# =========================================================
# 2. AGENT_DECISIONS
# =========================================================

@dataclass
class AgentDecision:
    """
    Decision made by an agent.

    Example:

        Aadhaar -> verified
        Payslip -> rejected
        Bank -> verified
        CIBIL -> eligible
    """

    decision_id: str
    execution_id: str

    decision_output: str

    confidence_score: float

    reasoning: str

    timestamp: str = field(
        default_factory=_now_iso
    )


# =========================================================
# 3. EVIDENCE
# =========================================================

@dataclass
class Evidence:
    """
    Evidence retrieved/used by an agent.

    One Evidence object represents one policy/document
    reference supporting the decision.

    retrieval_score:
        Normalized relevance indicator calculated by the
        application from the ChromaDB distance.

    retrieval_distance:
        Original distance returned by ChromaDB.
    """

    evidence_id: str
    execution_id: str

    source: str
    document_reference: str

    retrieval_score: float

    timestamp: str = field(
        default_factory=_now_iso
    )

    retrieval_distance: Optional[float] = None


# =========================================================
# 4. ACCOUNTABILITY_SCORES
# =========================================================

@dataclass
class AccountabilityScore:
    """
    Risk/accountability information for an agent decision.
    """

    score_id: str
    execution_id: str

    impact_score: int
    irreversibility_score: int
    explainability_score: int

    composite_risk_score: float

    risk_level: str

    review_required: bool

    scoring_model_version: str = "tracechain-scoring-v1"

    calculated_at: str = field(
        default_factory=_now_iso
    )


# =========================================================
# 5. PROVENANCE_RECORDS
# =========================================================

@dataclass
class ProvenanceRecordV2:
    """
    Tamper-evident provenance record.

    previous_record_hash:
        None for the first agent.

        For subsequent agents, store the previous
        agent's record_hash.

    Example:

        Aadhaar
            previous = None
            record_hash = AAA

        Payslip
            previous = AAA
            record_hash = BBB

        Bank
            previous = BBB
            record_hash = CCC

        CIBIL
            previous = CCC
            record_hash = DDD
    """

    record_id: str

    orchestration_id: str
    execution_id: str

    event_type: str

    input_data: dict
    output_data: dict

    previous_record_hash: Optional[str]

    timestamp: str = field(
        default_factory=_now_iso
    )

    input_hash: str = field(
        init=False,
        default=""
    )

    output_hash: str = field(
        init=False,
        default=""
    )

    record_hash: str = field(
        init=False,
        default=""
    )

    def __post_init__(self):

        # -------------------------------------------------
        # Hash of agent input
        # -------------------------------------------------

        self.input_hash = _hash(
            self.input_data
        )

        # -------------------------------------------------
        # Hash of agent output
        # -------------------------------------------------

        self.output_hash = _hash(
            self.output_data
        )

        # -------------------------------------------------
        # Hash-chain payload
        # -------------------------------------------------

        chain_payload = {
            "input_hash": self.input_hash,

            "output_hash": self.output_hash,

            "previous_record_hash":
                self.previous_record_hash,

            "execution_id":
                self.execution_id,
        }

        # -------------------------------------------------
        # Final tamper-evident hash
        # -------------------------------------------------

        self.record_hash = _hash(
            chain_payload
        )


# =========================================================
# PROVENANCE VERIFICATION
# =========================================================

def verify_provenance_record(
    record: ProvenanceRecordV2
) -> bool:
    """
    Recalculate the stored hashes.

    Returns:
        True  -> record is valid
        False -> record was modified/tampered
    """

    # -----------------------------------------------------
    # Check input hash
    # -----------------------------------------------------

    if _hash(record.input_data) != record.input_hash:
        return False

    # -----------------------------------------------------
    # Check output hash
    # -----------------------------------------------------

    if _hash(record.output_data) != record.output_hash:
        return False

    # -----------------------------------------------------
    # Recreate chain payload
    # -----------------------------------------------------

    chain_payload = {
        "input_hash": record.input_hash,

        "output_hash": record.output_hash,

        "previous_record_hash":
            record.previous_record_hash,

        "execution_id":
            record.execution_id,
    }

    # -----------------------------------------------------
    # Check record hash
    # -----------------------------------------------------

    return (
        _hash(chain_payload)
        == record.record_hash
    )


# =========================================================
# RISK LEVEL
# =========================================================

def risk_level_for(
    composite_score_0_10: float
) -> str:
    """
    Convert a 0-10 composite score into a risk level.
    """

    if composite_score_0_10 >= 7:
        return "High"

    if composite_score_0_10 >= 4:
        return "Medium"

    return "Low"


# =========================================================
# PRINT ALL RECORDS
# =========================================================

def print_execution_records(records: dict):
    """
    Print records in the same format for every agent.
    """

    # -----------------------------------------------------
    # AGENT_EXECUTIONS
    # -----------------------------------------------------

    print("\n=== AGENT_EXECUTIONS ===")

    execution = records["AGENT_EXECUTIONS"]

    for key, value in execution.__dict__.items():

        print(
            f"  {key}: {value}"
        )

    # -----------------------------------------------------
    # AGENT_DECISIONS
    # -----------------------------------------------------

    print("\n=== AGENT_DECISIONS ===")

    decision = records["AGENT_DECISIONS"]

    for key, value in decision.__dict__.items():

        print(
            f"  {key}: {value}"
        )

    # -----------------------------------------------------
    # EVIDENCE
    # -----------------------------------------------------

    print("\n=== EVIDENCE ===")

    evidence_list = records["EVIDENCE"]

    for evidence in evidence_list:

        print(
            " ",
            evidence.__dict__
        )

    # -----------------------------------------------------
    # ACCOUNTABILITY_SCORES
    # -----------------------------------------------------

    print("\n=== ACCOUNTABILITY_SCORES ===")

    score = records["ACCOUNTABILITY_SCORES"]

    for key, value in score.__dict__.items():

        print(
            f"  {key}: {value}"
        )

    # -----------------------------------------------------
    # PROVENANCE_RECORDS
    # -----------------------------------------------------

    print("\n=== PROVENANCE_RECORDS ===")

    provenance = records["PROVENANCE_RECORDS"]

    for key, value in provenance.__dict__.items():

        print(
            f"  {key}: {value}"
        )

    # -----------------------------------------------------
    # TAMPER CHECK
    # -----------------------------------------------------

    verified = verify_provenance_record(
        provenance
    )

    print(
        "\n[tamper-check] "
        "recomputed hash chain matches stored record: "
        f"{verified}"
    )