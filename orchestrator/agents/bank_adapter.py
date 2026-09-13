"""Adapter for the Bank Statement Analysis Agent (A003)."""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

AGENT_ID = "A003"
SEQUENCE_NUMBER = 3


def _safe_float(value):
    if value is None or value == "":
        return 0.0
    if isinstance(value, str):
        cleaned = value.replace(",", "").replace("₹", "").replace("%", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return 0.0
    return float(value)


def _first_present(df, *candidates):
    for candidate in candidates:
        if candidate in df.columns:
            return candidate
    return None


def _bank_metrics_from_csv(csv_path: str | Path) -> dict:
    df = pd.read_csv(csv_path)
    if df.empty:
        raise ValueError("Bank CSV is empty")

    income_col = _first_present(df, "average_monthly_income", "monthly_income", "income", "salary", "net_income")
    expense_col = _first_present(df, "average_monthly_expense", "monthly_expense", "expenses", "expense")
    emi_col = _first_present(df, "emi_amount", "monthly_emi", "emi", "loan_emi")
    savings_col = _first_present(df, "savings_ratio", "savings", "monthly_savings")
    surplus_col = _first_present(df, "average_monthly_surplus", "monthly_surplus", "surplus")

    avg_income = float(df[income_col].mean()) if income_col else 0.0
    avg_expense = float(df[expense_col].mean()) if expense_col else 0.0
    if surplus_col:
        avg_surplus = float(df[surplus_col].mean())
    else:
        avg_surplus = avg_income - avg_expense

    if emi_col:
        emi_amount = float(df[emi_col].mean()) if not df[emi_col].isna().all() else 0.0
    else:
        emi_amount = 0.0
    emi_ratio = (emi_amount / avg_income) if avg_income else 0.0

    if savings_col:
        savings_ratio = float(df[savings_col].mean())
    else:
        savings_ratio = max((avg_income - avg_expense - emi_amount) / avg_income, 0.0) if avg_income else 0.0

    income_stability = 0.75
    for possible in ("income_stability", "stability_score"):
        if possible in df.columns:
            income_stability = float(df[possible].mean())
            break

    negative_surplus_flag = int(avg_surplus < 0)
    low_surplus_flag = int(avg_surplus >= 0 and avg_surplus <= 10000)
    high_emi_flag = int(emi_ratio > 0.30)
    negative_savings_flag = int(savings_ratio <= 0)
    low_savings_flag = int(savings_ratio > 0 and savings_ratio < 0.10)
    excessive_expense_flag = int(avg_expense > avg_income)
    high_cash_withdrawal_flag = int((df[[c for c in df.columns if "cash" in c.lower() or "withdraw" in c.lower()]].sum().sum() if any("cash" in c.lower() or "withdraw" in c.lower() for c in df.columns) else 0) > 0)

    score = 100
    if negative_surplus_flag:
        score -= 35
    elif low_surplus_flag:
        score -= 15
    if negative_savings_flag:
        score -= 25
    elif low_savings_flag:
        score -= 10
    if high_emi_flag:
        score -= 20
    if excessive_expense_flag:
        score -= 20
    if high_cash_withdrawal_flag:
        score -= 10
    score = max(0, score)

    if score >= 80:
        decision_output = "verified"
    elif score >= 60:
        decision_output = "needs_review"
    else:
        decision_output = "high_risk_auto"

    evidence_text = (
        f"Average monthly income: INR {avg_income:.2f} | "
        f"Average monthly expense: INR {avg_expense:.2f} | "
        f"Average monthly surplus: INR {avg_surplus:.2f} | "
        f"EMI-to-income ratio: {emi_ratio * 100:.2f}% | "
        f"Savings ratio: {savings_ratio * 100:.2f}% | "
        f"Income stability: {income_stability:.2f}"
    )

    return {
        "average_monthly_income": avg_income,
        "average_monthly_expense": avg_expense,
        "average_monthly_surplus": avg_surplus,
        "emi_to_income_ratio": emi_ratio,
        "savings_ratio": savings_ratio,
        "income_stability": income_stability,
        "agent_score": score,
        "decision_output": decision_output,
        "confidence_score": round(score / 100, 2),
        "reasoning": (
            "Bank statement analysis reviewed the uploaded statement summary and found "
            f"average monthly income of INR {avg_income:.2f}, average monthly expense of INR {avg_expense:.2f}, "
            f"and average monthly surplus of INR {avg_surplus:.2f}. "
            f"The EMI-to-income ratio is {emi_ratio * 100:.2f}% and the savings ratio is {savings_ratio * 100:.2f}%. "
            f"The resulting bank score is {score}/100, which leads to a {decision_output.upper()} decision."
        ),
        "evidence_summary": evidence_text,
    }


def _scope(state: dict) -> dict:
    applicant_data = state.get("applicant_data", {})
    return {
        "application_id": state.get("application_id"),
        "user_id": state.get("user_id"),
        "loan_amount": state.get("loan_amount"),
        "bank_statement_file_path": applicant_data.get("bank_statement_file_path"),
    }


def run(state: dict, orchestration_id: str) -> dict:
    logger.info("[A003] Running Bank Statement agent for application_id=%s", state.get("application_id"))
    scoped = _scope(state)
    csv_path = scoped.get("bank_statement_file_path")

    if not csv_path:
        raise ValueError("Missing bank_statement_file_path in applicant_data")

    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Bank statement CSV not found at {csv_path}")

    metrics = _bank_metrics_from_csv(csv_path)
    now = datetime.now(timezone.utc).isoformat()
    execution_id = str(uuid.uuid4())
    decision_id = str(uuid.uuid4())
    score_id = str(uuid.uuid4())
    record_id = str(uuid.uuid4())

    decision_output = metrics["decision_output"]
    confidence_score = metrics["confidence_score"]
    risk_level = "Low" if decision_output == "verified" else "Medium" if decision_output == "needs_review" else "High"
    composite_risk = 1.5 if decision_output == "verified" else 4.0 if decision_output == "needs_review" else 7.5

    execution = {
        "execution_id": execution_id,
        "orchestration_id": orchestration_id,
        "agent_id": AGENT_ID,
        "parent_execution_id": None,
        "sequence_number": SEQUENCE_NUMBER,
        "input_data": {"bank_statement_file_path": str(csv_path), "application_id": state.get("application_id")},
        "output_data": {
            "decision_output": decision_output,
            "confidence_score": confidence_score,
            "agent_score": metrics["agent_score"],
            "reasoning": metrics["reasoning"],
        },
        "model_id": "bank-statements-rule-v1",
        "model_version": "1.0",
        "rule_id": "bank-affordability-rules-v1",
        "rule_version": "1.0",
        "start_time": now,
        "end_time": now,
        "status": "completed",
    }

    decision = {
        "decision_id": decision_id,
        "execution_id": execution_id,
        "decision_output": decision_output,
        "confidence_score": confidence_score,
        "reasoning": metrics["reasoning"],
        "decision_timestamp": now,
    }

    evidence = [{
        "evidence_id": str(uuid.uuid4()),
        "execution_id": execution_id,
        "source": "uploaded_bank_statement_csv",
        "document_reference": str(csv_path),
        "retrieval_score": 1.0,
        "timestamp": now,
        "evidence_data": {
            "average_monthly_income": metrics["average_monthly_income"],
            "average_monthly_expense": metrics["average_monthly_expense"],
            "average_monthly_surplus": metrics["average_monthly_surplus"],
            "emi_to_income_ratio": metrics["emi_to_income_ratio"],
            "savings_ratio": metrics["savings_ratio"],
            "income_stability": metrics["income_stability"],
        },
    }]

    accountability = {
        "score_id": score_id,
        "execution_id": execution_id,
        "impact_score": 6,
        "irreversibility_score": 5,
        "explainability_score": 9,
        "composite_risk_score": composite_risk,
        "risk_level": risk_level,
        "review_required": decision_output == "needs_review",
        "scoring_model_version": "tracechain-scoring-v1",
        "calculated_at": now,
    }

    provenance = {
        "record_id": record_id,
        "orchestration_id": orchestration_id,
        "execution_id": execution_id,
        "event_type": "agent_decision",
        "timestamp": now,
        "input_hash": "",
        "output_hash": "",
        "previous_record_hash": None,
        "record_hash": "",
    }

    logger.info("[A003] Done — decision=%s confidence=%.2f", decision_output, confidence_score)
    return {
        "execution": execution,
        "decision": decision,
        "evidence": evidence,
        "accountability": accountability,
        "provenance": provenance,
    }
