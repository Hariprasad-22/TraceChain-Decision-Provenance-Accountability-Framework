"""
TraceChain provenance schema.

Defines the decision-provenance record every agent writes, plus the
risk-scoring formula. Hashing/chaining lives in chain.py.
"""
import hashlib
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

from scoring import score_decision


@dataclass
class InputRef:
    summary: str
    input_hash: str


@dataclass
class RuleOrModel:
    id: str
    version: str


@dataclass
class RiskFactors:
    irreversibility: int  # 0-10: how hard is this to undo?
    impact: int           # 0-10: how much does it affect operations/safety?
    explainability: int   # 0-10: how well can we justify the decision?


@dataclass
class ProvenanceRecord:
    decision_id: str
    chain_id: str
    agent_id: str
    agent_type: str
    input_ref: InputRef
    rule_or_model: RuleOrModel
    decision_output: str
    confidence_score: float
    risk_factors: RiskFactors
    upstream_decision_id: Optional[str] = None
    human_override: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    risk_score: int = field(init=False, default=0)
    needs_human_review: bool = field(init=False, default=False)
    risk_reason: str = field(init=False, default="")
    prev_record_hash: Optional[str] = None
    record_hash: str = field(init=False, default="")

    def __post_init__(self):
        breakdown = score_decision(
            self.risk_factors.irreversibility,
            self.risk_factors.impact,
            self.risk_factors.explainability,
        )
        self.risk_score = breakdown.risk_score
        self.needs_human_review = breakdown.needs_human_review
        self.risk_reason = breakdown.reason

    def _canonical_payload(self) -> dict:
        """Everything except record_hash - this is what gets hashed."""
        d = asdict(self)
        d.pop("record_hash", None)
        return d

    def finalize(self, prev_hash: Optional[str]) -> "ProvenanceRecord":
        """Set prev_record_hash and compute this record's own hash.
        Call exactly once, after every other field is set."""
        self.prev_record_hash = prev_hash
        payload = json.dumps(self._canonical_payload(), sort_keys=True).encode()
        self.record_hash = hashlib.sha256(payload).hexdigest()
        return self

    def to_dict(self) -> dict:
        return asdict(self)


def new_id() -> str:
    return str(uuid.uuid4())


def hash_input(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
