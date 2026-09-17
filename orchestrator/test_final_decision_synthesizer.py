from orchestrator.final_decision.synthesizer import _classify, synthesize
from frontend.server import friendly_error_reply


def test_classify_approved_wording():
    assert _classify("approved") == "Approved"
    assert _classify("verified") == "Approved"
    assert _classify("needs_review") == "Rejected"
    assert _classify("manual_review") == "Rejected"


def test_synthesize_honors_approved_agent_outputs():
    result = synthesize(
        agent_results=[
            {"agent_id": "A001", "decision_output": "approved", "confidence_score": 0.95, "reasoning": "Looks good", "composite_risk_score": 1.2},
            {"agent_id": "A002", "decision_output": "verified", "confidence_score": 0.92, "reasoning": "Income verified", "composite_risk_score": 2.0},
            {"agent_id": "A003", "decision_output": "verified", "confidence_score": 0.88, "reasoning": "Bank okay", "composite_risk_score": 2.5},
            {"agent_id": "A004", "decision_output": "verified", "confidence_score": 0.9, "reasoning": "CIBIL good", "composite_risk_score": 3.1},
        ],
        overall_composite=2.2,
        overall_risk_level="Low",
        responsible_agent_id="A001",
    )

    assert result["answer"] == "Approved"
    assert result["responsible_agent_id"] == "A001"


def test_friendly_error_reply_handles_missing_required_field():
    reply = friendly_error_reply("Missing required field: 'loan_amount'")
    assert "loan amount" in reply.lower()
    assert "technical issue" not in reply.lower()
