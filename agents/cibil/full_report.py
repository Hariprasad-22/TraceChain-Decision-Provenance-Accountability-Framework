import json
from rule_engine import cibil_decision
from vector_store import store_decision, find_similar
from llm_reasoning import generate_reasoning
from trace_bridge import build_trace_records


def run_account(acc):
    application_id = acc["application_id"]
    score = acc.get("cibil_score")
    utilization = acc.get("credit_utilization_pct")
    dpd_history = acc.get("dpd_history", [])

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

    trace = build_trace_records(
        orchestration_id=f"WF-{application_id}",
        application_id=application_id,
        input_data=acc,
        decision_output=decision_output,
        confidence_score=confidence_score,
        reasoning=reasoning,
        risk_factors=risk_factors,
        similar_cases=similar_docs,
    )
    return trace


def print_account_report(account_id, acc, trace):
    exe = trace["execution"]
    dec = trace["decision"]
    ev = trace["evidence"]
    acct = trace["accountability"]
    prov = trace["provenance"]

    print("=" * 90)
    print(f"ACCOUNT ID: {account_id}   |   CIBIL SCORE: {acc.get('cibil_score', 'MISSING')}")
    print("=" * 90)

    print("\n=== AGENT_EXECUTIONS ===")
    print(f"execution_id: {exe.execution_id}")
    print(f"orchestration_id: {exe.orchestration_id}")
    print(f"agent_id: {exe.agent_id}")
    print(f"input_data: {exe.input_data}")
    print(f"output_data: {exe.output_data}")
    print(f"model_id: {exe.model_id}")
    print(f"rule_id: {exe.rule_id}")
    print(f"start_time: {exe.start_time}")
    print(f"end_time: {exe.end_time}")
    print(f"status: {exe.status}")
    print(f"sequence_number: {exe.sequence_number}")
    print(f"input_hash: {exe.input_hash}")

    print("\n=== AGENT_DECISIONS ===")
    print(f"decision_id: {dec.decision_id}")
    print(f"execution_id: {dec.execution_id}")
    print(f"decision_output: {dec.decision_output}")
    print(f"confidence_score: {dec.confidence_score}")
    print(f"reasoning: {dec.reasoning}")
    print(f"timestamp: {dec.timestamp}")

    print("\n=== EVIDENCE ===")
    if ev:
        for e in ev:
            print({
                "evidence_id": e.evidence_id,
                "execution_id": e.execution_id,
                "source": e.source,
                "document_reference": e.document_reference,
                "retrieval_score": e.retrieval_score,
                "timestamp": e.timestamp,
            })
    else:
        print("(no precedent retrieved — cold start / first record of this kind)")

    print("\n=== ACCOUNTABILITY_SCORES ===")
    print(f"score_id: {acct.score_id}")
    print(f"execution_id: {acct.execution_id}")
    print(f"impact_score: {acct.impact_score}")
    print(f"irreversibility_score: {acct.irreversibility_score}")
    print(f"explainability_score: {acct.explainability_score}")
    print(f"composite_risk_score: {acct.composite_risk_score}")
    print(f"risk_level: {acct.risk_level}")
    print(f"review_required: {acct.review_required}")
    print(f"scoring_model_version: {acct.scoring_model_version}")
    print(f"calculated_at: {acct.calculated_at}")

    print("\n=== PROVENANCE_RECORDS ===")
    print(f"record_id: {prov.record_id}")
    print(f"orchestration_id: {prov.orchestration_id}")
    print(f"execution_id: {prov.execution_id}")
    print(f"event_type: {prov.event_type}")
    print(f"input_data: {prov.input_data}")
    print(f"output_data: {prov.output_data}")
    print(f"previous_record_hash: {prov.previous_record_hash}")
    print(f"timestamp: {prov.timestamp}")
    print(f"input_hash: {prov.input_hash}")
    print(f"output_hash: {prov.output_hash}")
    print(f"record_hash: {prov.record_hash}")
    print(f"tamper_check_passed: {trace['tamper_check_passed']}")
    print()


if __name__ == "__main__":
    with open("accounts.json") as f:
        accounts = json.load(f)

    for acc in accounts:
        account_id = acc.get("account_id", acc["application_id"])
        trace = run_account(acc)
        print_account_report(account_id, acc, trace)