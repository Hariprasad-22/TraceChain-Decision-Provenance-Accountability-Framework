import uuid
from datetime import datetime, timezone

from execution_record import (
    ExecutionMetadata, AgentDecision, Evidence, AccountabilityScore,
    ProvenanceRecordV2, risk_level_for, verify_provenance_record,
)

AGENT_ID = "A004"  # CIBIL Score Agent

_last_record_hash = None


def build_trace_records(orchestration_id: str, application_id: str, input_data: dict,
                         decision_output: str, confidence_score: float, reasoning: str,
                         risk_factors: dict, similar_cases: list):
    global _last_record_hash

    execution_id = str(uuid.uuid4())
    start_time = datetime.now(timezone.utc).isoformat()
    output_data = {
        "decision_output": decision_output,
        "confidence_score": confidence_score,
        "reasoning": reasoning,
        "risk_factors": risk_factors,
    }
    end_time = datetime.now(timezone.utc).isoformat()

    execution = ExecutionMetadata(
        execution_id=execution_id,
        orchestration_id=orchestration_id,
        agent_id=AGENT_ID,
        input_data=input_data,
        output_data=output_data,
        model_id="rule-engine+llm-reasoning-v1",
        rule_id="cibil_policy_v1",
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
        for case in similar_cases
    ]

    composite = round(
    (risk_factors["irreversibility"] + risk_factors["impact"]) / 2, 2
)
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
    input_data=input_data,
    output_data=output_data,
    previous_record_hash=None,
)

    return {
        "execution": execution,
        "decision": decision,
        "evidence": evidence_list,
        "accountability": accountability,
        "provenance": provenance,
        "tamper_check_passed": verify_provenance_record(provenance),
    }