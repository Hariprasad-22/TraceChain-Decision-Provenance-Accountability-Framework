def check_guardrails(score, utilization_pct, dpd_history):
    # Check 1: score must exist and be a proper number
    if score is None or not isinstance(score, (int, float)):
        return {
            "decision_output": "invalid_input",
            "reasoning": f"cibil_score must be a number, got: {repr(score)}",
            "confidence_score": 1.0
        }

    # Check 2: score must be in valid range
    if score < 300 or score > 900:
        return {
            "decision_output": "invalid_score",
            "reasoning": f"Score {score} is outside the valid 300-900 range.",
            "confidence_score": 1.0
        }

    return None


def cibil_decision(score, utilization_pct, dpd_history):
    guardrail_result = check_guardrails(score, utilization_pct, dpd_history)
    if guardrail_result is not None:
        return guardrail_result

    if any(days >= 90 for days in dpd_history):
        return {
            "decision_output": "high_risk_auto",
            "reasoning": f"Applicant has an account {max(dpd_history)} days past due — automatic high risk.",
            "confidence_score": 1.0
        }

    if score < 650:
        decision = "high_risk"
        reason = f"Score {score} is below 650 — high risk."
    elif score >= 750 and utilization_pct < 75:
        decision = "verified"
        reason = f"Score {score} is strong and utilization {utilization_pct}% is healthy."
    else:
        decision = "needs_review"
        reason = f"Score {score} with utilization {utilization_pct}% needs a closer look."

    return {
        "decision_output": decision,
        "reasoning": reason,
        "confidence_score": 0.9
    }