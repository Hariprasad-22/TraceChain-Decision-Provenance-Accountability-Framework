"""
cibil_agent.py — the callable agent function, matching the shape of
aadhar_verification_agent(state, orchestration_id) so both agents can be
run through the same kind of batch script.

Returns a dict with keys: execution, decision, evidence, accountability,
provenance — each JSON-serializable (dataclasses converted via asdict),
exactly matching the Aadhaar agent's output shape.
"""
import uuid
import json
import hashlib
from dataclasses import asdict
from datetime import datetime, timezone

from rule_engine import cibil_decision
from vector_store import store_decision, find_similar
from llm_reasoning import generate_reasoning
from execution_record import (
    ExecutionMetadata, AgentDecision, Evidence, AccountabilityScore,
    ProvenanceRecordV2, risk_level_for, verify_provenance_record,
)

AGENT_ID = "A004"
POLICY_VERSION = "cibil_policy_v1"


def cibil_verification_agent(state: dict, orchestration_id: str) -> dict:
    application_id = state["application_id"]
    score = state.get("cibil_score")
    utilization = state.get("credit_utilization_pct")
    dpd_history = state.get("dpd_history", [])

    start_time = datetime.now(timezone.utc).isoformat()

    result = cibil_decision(score, utilization, dpd_history)
    decision_output = result["decision_output"]
    confidence_score = result["confidence_score"]

    if decision_output in ("invalid_input", "invalid_score", "missing_data"):
        reasoning = result["reasoning"]
        risk_factors = {"irreversibility": 1, "impact": 2, "explainability": 10}
        similar_docs = []
    else:
        similar = find_similar(score, decision_output)
        similar_docs = similar["documents"][0] if similar.get("documents") else []
        llm_result = generate_reasoning(score, utilization, decision_output, similar_docs)
        reasoning = llm_result["reasoning"]
        risk_factors = llm_result["risk_factors"]
        store_decision(application_id, score, decision_output)

    end_time = datetime.now(timezone.utc).isoformat()

    output_data = {
        "decision_output": decision_output,
        "confidence_score": confidence_score,
        "reasoning": reasoning,
        "risk_factors": risk_factors,
    }

    execution_id = str(uuid.uuid4())

    execution = ExecutionMetadata(
        execution_id=execution_id,
        orchestration_id=orchestration_id,
        agent_id=AGENT_ID,
        input_data=state,
        output_data=output_data,
        model_id="rule-engine+llm-reasoning-v1",
        rule_id=POLICY_VERSION,
        start_time=start_time,
        end_time=end_time,
        status="completed",
    )

    decision = AgentDecision(
        decision_id=str(uuid.uuid4()),
        execution_id=execution_id,
        decision_output=decision_output,
        confidence_score=confidence_score,
        reasoning=reasoning,
    )

    evidence_list = [
        Evidence(
            evidence_id=str(uuid.uuid4()),
            execution_id=execution_id,
            source="chromadb:cibil_decisions",
            document_reference=case,
            retrieval_score=0.0,
        )
        for case in similar_docs
    ]

    composite = round((risk_factors["irreversibility"] + risk_factors["impact"]) / 2, 2)
    accountability = AccountabilityScore(
        score_id=str(uuid.uuid4()),
        execution_id=execution_id,
        impact_score=risk_factors["impact"],
        irreversibility_score=risk_factors["irreversibility"],
        explainability_score=risk_factors["explainability"],
        composite_risk_score=composite,
        risk_level=risk_level_for(composite),
        review_required=decision_output in ("needs_review", "high_risk_auto"),
    )

    provenance = ProvenanceRecordV2(
        record_id=str(uuid.uuid4()),
        orchestration_id=orchestration_id,
        execution_id=execution_id,
        event_type="agent_execution",
        input_data=state,
        output_data=output_data,
        previous_record_hash=None,
    )

    return {
        "execution": asdict(execution),
        "decision": asdict(decision),
        "evidence": [asdict(e) for e in evidence_list],
        "accountability": asdict(accountability),
        "provenance": asdict(provenance),
    }
