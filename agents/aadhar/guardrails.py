"""
Agent-level guardrails.

Tool validation: sanity-checks inputs (and the LLM's own output) before
they're trusted, catching malformed/out-of-range data before it propagates.

Scoped permissions: enforced structurally, not by convention - each
scope_for_* function is the ONLY way an agent receives state, and it only
hands over the specific fields that agent is allowed to see.
"""


class ValidationError(Exception):
    pass


def validate_application(data: dict):
    if not data.get("application_id"):
        raise ValidationError("missing application_id")
    if not (0 < data.get("loan_amount", 0) <= 5_000_000):
        raise ValidationError(f"loan_amount out of range: {data.get('loan_amount')}")
    if not data.get("applicant_name"):
        raise ValidationError("missing applicant_name")
    return True


def validate_credit_score(score):
    if score is None or not (300 <= score <= 850):
        raise ValidationError(f"credit_score out of valid range: {score}")
    return True


def validate_llm_output(output: dict, required_fields: list):
    """Guardrail on the LLM's own response - reject malformed structured
    output before anything downstream trusts it."""
    missing = [f for f in required_fields if f not in output]
    if missing:
        raise ValidationError(f"LLM output missing fields: {missing}")

    # Coerce null/missing confidence so downstream float/format never crashes.
    conf = output.get("confidence_score")
    if conf is None:
        output["confidence_score"] = 0.7
        conf = 0.7
    try:
        conf = float(conf)
        output["confidence_score"] = conf
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"confidence_score not numeric: {conf}") from exc
    if not (0 <= conf <= 1):
        raise ValidationError(f"confidence_score out of range: {conf}")

    if isinstance(output.get("decision_output"), str):
        output["decision_output"] = output["decision_output"].strip().lower()

    risk = output.setdefault("risk_factors", {})
    if not isinstance(risk, dict):
        risk = {}
        output["risk_factors"] = risk
    for factor, default in (("irreversibility", 4), ("impact", 5), ("explainability", 8)):
        val = risk.get(factor)
        if val is None:
            risk[factor] = default
            continue
        try:
            val = int(val)
            risk[factor] = val
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"{factor} not numeric: {val}") from exc
        if not (0 <= val <= 10):
            raise ValidationError(f"{factor} out of range: {val}")
    return True


# --- Aadhaar-specific validation ---
from datetime import date
from difflib import SequenceMatcher
from verhoeff import is_valid_aadhaar_checksum


def validate_aadhaar_format(aadhaar_number: str):
    """Hard guardrail - runs before any LLM reasoning. Per Internal KYC
    Policy Section 3.5: a format/checksum failure rejects immediately."""
    if not aadhaar_number or not is_valid_aadhaar_checksum(aadhaar_number):
        raise ValidationError(f"invalid Aadhaar number/checksum: {aadhaar_number}")
    return True


def validate_age(dob_str: str, min_age: int = 18):
    """Hard guardrail - underage applicants are rejected with no escalation
    path (Rejection Reasons R4)."""
    try:
        y, m, d = (int(x) for x in dob_str.split("-"))
        dob = date(y, m, d)
    except Exception:
        raise ValidationError(f"unparseable DOB: {dob_str}")
    age = (date.today() - dob).days // 365
    if age < min_age:
        raise ValidationError(f"applicant is under {min_age} (age {age})")
    return True


def name_similarity(name_a: str, name_b: str) -> float:
    return SequenceMatcher(None, (name_a or "").lower(), (name_b or "").lower()).ratio()


def dob_matches(dob_a: str, dob_b: str) -> bool:
    return (dob_a or "").strip() == (dob_b or "").strip()


# --- Scoped permissions ---

def scope_for_aadhar_agent(state: dict) -> dict:
    return {
        "application_id": state["application_id"],
        "loan_amount": state["loan_amount"],
        "applicant_name": state["applicant_name"],
        "applicant_dob": state.get("applicant_dob"),
        "aadhar_image_path": state["applicant_data"].get("aadhar_image_path"),
    }


def scope_for_data_verification(state: dict) -> dict:
    return {
        "application_id": state["application_id"],
        "loan_amount": state["loan_amount"],
        "applicant_name": state["applicant_name"],
        "applicant_data": state["applicant_data"],
    }


def scope_for_credit_risk(state: dict) -> dict:
    return {
        "application_id": state["application_id"],
        "loan_amount": state["loan_amount"],
        "credit_bureau_record": state["applicant_data"].get("credit_bureau_record", {}),
    }


def scope_for_fraud_aml(state: dict) -> dict:
    return {
        "application_id": state["application_id"],
        "transaction_history": state["applicant_data"].get("transaction_history", []),
        "watchlist_flags": state["applicant_data"].get("watchlist_flags", []),
    }


def scope_for_decision(state: dict) -> dict:
    # Decision agent sees ONLY the aggregated outputs of the other three -
    # never raw applicant PII. This is deliberate: the most powerful agent
    # (the one that actually decides) has the narrowest view of raw data.
    return {
        "application_id": state["application_id"],
        "loan_amount": state["loan_amount"],
        "verification": state.get("verification"),
        "credit_risk": state.get("credit_risk"),
        "fraud_check": state.get("fraud_check"),
    }
