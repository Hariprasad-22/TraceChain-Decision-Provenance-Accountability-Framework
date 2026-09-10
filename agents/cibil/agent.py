import json
from rule_engine import cibil_decision
from vector_store import store_decision, find_similar
from llm_reasoning import generate_reasoning
from trace_bridge import build_trace_records


def cibil_agent(applicant, orchestration_id="WF-DEMO-0001"):
    score = applicant["cibil_score"]
    utilization = applicant["credit_utilization_pct"]
    dpd_history = applicant["dpd_history"]
    application_id = applicant["application_id"]

    result = cibil_decision(score, utilization, dpd_history)
    decision_output = result["decision_output"]
    confidence_score = result["confidence_score"]

    similar = find_similar(score, decision_output)
    similar_docs = similar["documents"][0] if similar["documents"] else []

    llm_result = generate_reasoning(score, utilization, decision_output, similar_docs)
    reasoning = llm_result["reasoning"]
    risk_factors = llm_result["risk_factors"]

    store_decision(application_id, score, decision_output)

    trace = build_trace_records(
        orchestration_id=orchestration_id,
        application_id=application_id,
        input_data=applicant,
        decision_output=decision_output,
        confidence_score=confidence_score,
        reasoning=reasoning,
        risk_factors=risk_factors,
        similar_cases=similar_docs,
    )

    return {
        "decision_output": decision_output,
        "confidence_score": confidence_score,
        "reasoning": reasoning,
        "risk_factors": risk_factors,
        "accountability_score": trace["accountability"].composite_risk_score,
        "risk_level": trace["accountability"].risk_level,
        "tamper_check_passed": trace["tamper_check_passed"],
    }


with open("accounts.json") as f:
    accounts = json.load(f)

for acc in accounts:
    output = cibil_agent(acc, orchestration_id=f"WF-{acc['application_id']}")
    print(acc["application_id"], "->", output["decision_output"],
          "| accountability_score:", output["accountability_score"],
          "| risk_level:", output["risk_level"])