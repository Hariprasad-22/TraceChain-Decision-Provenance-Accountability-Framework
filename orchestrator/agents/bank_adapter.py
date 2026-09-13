"""
Adapter for the Bank Statement Analysis Agent (A003).
Connects the orchestrator directly to agents/bank_statement/bank_statement_agent.py.
"""

import json
import logging
import uuid
import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

AGENT_ID = "A003"
SEQUENCE_NUMBER = 3

_ORCH_DIR = Path(__file__).resolve().parent.parent
_BANK_AGENT_FILE = _ORCH_DIR.parent / "agents" / "bank_statement" / "bank_statement_agent.py"

_bank_agent_module = None
if _BANK_AGENT_FILE.exists():
    try:
        spec = importlib.util.spec_from_file_location("bank_statement_agent_mod", _BANK_AGENT_FILE)
        if spec and spec.loader:
            _bank_agent_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(_bank_agent_module)
            logger.info("[A003] Successfully loaded bank_statement_agent module from %s", _BANK_AGENT_FILE)
    except Exception as exc:
        logger.warning("[A003] Could not load bank_statement_agent module: %s", exc)


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


def _fallback_bank_metrics(file_path: str | Path) -> dict:
    """Fallback parser for bank statements (.csv, .xls, .xlsx) if bank_statement_agent module fails."""
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext in (".xls", ".xlsx"):
        try:
            df = pd.read_excel(path)
        except Exception:
            df = pd.read_csv(path)
    else:
        try:
            df = pd.read_csv(path)
        except Exception:
            df = pd.read_excel(path)

    if df.empty:
        raise ValueError("Bank statement file is empty")

    income_col = _first_present(df, "average_monthly_income", "monthly_income", "income", "salary", "net_income", "credit", "inflow", "deposit")
    expense_col = _first_present(df, "average_monthly_expense", "monthly_expense", "expenses", "expense", "debit", "outflow", "withdrawal")
    emi_col = _first_present(df, "emi_amount", "monthly_emi", "emi", "loan_emi")
    savings_col = _first_present(df, "savings_ratio", "savings", "monthly_savings")
    surplus_col = _first_present(df, "average_monthly_surplus", "monthly_surplus", "surplus")

    # Check if transaction-level credit/debit exist
    if "credit" in df.columns or "debit" in df.columns:
        tot_credit = float(df["credit"].sum()) if "credit" in df.columns else 0.0
        tot_debit = float(df["debit"].sum()) if "debit" in df.columns else 0.0
        # Estimate 6 months unless dated
        avg_income = tot_credit / 6.0 if tot_credit > 0 else 50000.0
        avg_expense = tot_debit / 6.0 if tot_debit > 0 else 25000.0
    else:
        avg_income = float(df[income_col].mean()) if income_col else 60000.0
        avg_expense = float(df[expense_col].mean()) if expense_col else 30000.0

    avg_surplus = float(df[surplus_col].mean()) if surplus_col else (avg_income - avg_expense)
    emi_amount = float(df[emi_col].mean()) if (emi_col and not df[emi_col].isna().all()) else 0.0
    emi_ratio = (emi_amount / avg_income) if avg_income else 0.0
    savings_ratio = float(df[savings_col].mean()) if savings_col else (max((avg_income - avg_expense - emi_amount) / avg_income, 0.0) if avg_income else 0.20)

    score = 100
    if avg_surplus < 0:
        score -= 35
    elif avg_surplus <= 10000:
        score -= 15
    if savings_ratio <= 0:
        score -= 25
    elif savings_ratio < 0.10:
        score -= 10
    if emi_ratio > 0.30:
        score -= 20
    score = max(0, score)

    decision_output = "verified" if score >= 80 else ("needs_review" if score >= 60 else "high_risk_auto")

    return {
        "average_monthly_income": avg_income,
        "average_monthly_expense": avg_expense,
        "average_monthly_surplus": avg_surplus,
        "emi_to_income_ratio": emi_ratio,
        "savings_ratio": savings_ratio,
        "income_stability": 0.85,
        "agent_score": score,
        "decision_output": decision_output,
        "confidence_score": round(score / 100, 2),
        "reasoning": (
            f"Bank statement analysis found average monthly income ₹{avg_income:,.2f}, "
            f"monthly expense ₹{avg_expense:,.2f}, surplus ₹{avg_surplus:,.2f}, "
            f"EMI ratio {emi_ratio * 100:.1f}%, and savings ratio {savings_ratio * 100:.1f}%. "
            f"Resulting bank score is {score}/100 -> {decision_output.upper()}."
        ),
        "evidence_summary": f"Income: ₹{avg_income:,.2f} | Expense: ₹{avg_expense:,.2f} | Score: {score}",
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

    now = datetime.now(timezone.utc).isoformat()
    execution_id = str(uuid.uuid4())
    decision_id = str(uuid.uuid4())
    score_id = str(uuid.uuid4())
    record_id = str(uuid.uuid4())

    raw_agent_output = None
    if _bank_agent_module and hasattr(_bank_agent_module, "bank_statement_agent"):
        try:
            raw_agent_output = _bank_agent_module.bank_statement_agent(
                {"file_path": str(csv_path)},
                orchestration_id=orchestration_id,
            )
            logger.info("[A003] Successfully processed CSV via bank_statement_agent module.")
        except Exception as exc:
            logger.warning("[A003] bank_statement_agent module failed: %s. Falling back to summary parser.", exc)

    if raw_agent_output:
        output_sec = raw_agent_output.get("output", {})
        dec_raw = output_sec.get("decision", "ELIGIBLE")
        confidence_score = float(output_sec.get("confidence", 0.95))
        agent_score = int(output_sec.get("score", 85))
        reasoning = output_sec.get("reasoning", "")
        fin_metrics = output_sec.get("financial_metrics", {})
        acc_sec = raw_agent_output.get("accountability", {})
        comp_risk = float(acc_sec.get("composite_risk_score", 2.5))
        risk_lvl = acc_sec.get("risk_level", "Low")
        review_req = bool(acc_sec.get("review_required", False))

        decision_map = {
            "ELIGIBLE": "verified",
            "REVIEW": "needs_review",
            "NOT_ELIGIBLE": "rejected",
        }
        decision_output = decision_map.get(str(dec_raw).upper(), "verified")
    else:
        metrics = _fallback_bank_metrics(csv_path)
        decision_output = metrics["decision_output"]
        confidence_score = metrics["confidence_score"]
        agent_score = metrics["agent_score"]
        reasoning = metrics["reasoning"]
        fin_metrics = {
            "average_monthly_income": metrics["average_monthly_income"],
            "average_monthly_expense": metrics["average_monthly_expense"],
            "average_monthly_surplus": metrics["average_monthly_surplus"],
            "emi_to_income_ratio": metrics["emi_to_income_ratio"],
            "savings_ratio": metrics["savings_ratio"],
            "income_stability": metrics["income_stability"],
        }
        risk_lvl = "Low" if decision_output == "verified" else ("Medium" if decision_output == "needs_review" else "High")
        comp_risk = 1.5 if decision_output == "verified" else (4.0 if decision_output == "needs_review" else 7.5)
        review_req = (decision_output == "needs_review")

    execution = {
        "execution_id": execution_id,
        "orchestration_id": orchestration_id,
        "agent_id": AGENT_ID,
        "parent_execution_id": None,
        "sequence_number": SEQUENCE_NUMBER,
        "input_data": {
            "bank_statement_file_path": str(csv_path),
            "application_id": state.get("application_id"),
        },
        "output_data": {
            "decision_output": decision_output,
            "confidence_score": confidence_score,
            "agent_score": agent_score,
            "reasoning": reasoning,
            "financial_metrics": fin_metrics,
        },
        "model_id": "bank-statement-rules-v1",
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
        "reasoning": reasoning,
        "decision_timestamp": now,
    }

    evidence = [{
        "evidence_id": str(uuid.uuid4()),
        "execution_id": execution_id,
        "source": "uploaded_bank_statement_csv",
        "document_reference": str(csv_path),
        "retrieval_score": 1.0,
        "timestamp": now,
        "evidence_data": fin_metrics,
    }]

    accountability = {
        "score_id": score_id,
        "execution_id": execution_id,
        "impact_score": 6,
        "irreversibility_score": 5,
        "explainability_score": 9,
        "composite_risk_score": comp_risk,
        "risk_level": risk_lvl,
        "review_required": review_req,
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

    logger.info("[A003] Done — decision=%s confidence=%.2f risk=%.1f", decision_output, confidence_score, comp_risk)
    return {
        "execution": execution,
        "decision": decision,
        "evidence": evidence,
        "accountability": accountability,
        "provenance": provenance,
    }
