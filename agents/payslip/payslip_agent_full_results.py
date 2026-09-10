"""
Payslip Agent (P001) - full execution-result generator.

Produces the same top-level structure seen in the user's Aadhaar/CIBIL
execution examples:

user
application
execution
decision
evidence
accountability
provenance

Synthetic test data only.
"""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader
from chroma_retriever import retrieve_policy


BASE_DIR = Path(__file__).resolve().parent
GROUND_TRUTH = BASE_DIR / "ground_truth_realistic.json"
PAYSLIP_DIR = BASE_DIR / "payslips"
OUTPUT_FILE = BASE_DIR / "payslip_agent_results_10.json"


ACCOUNT_PAYSLIP_MAP = {
    "100001": "payslip_01_Udyati_Seth.pdf",
    "100002": "payslip_02_Dev_Bhargava.pdf",
    "100003": "payslip_03_Aachal_Murty.pdf",
    "100004": "payslip_04_Oni_Bora.pdf",
    "100005": "payslip_05_Raghav_Sem.pdf",
    "100006": "payslip_06_Brijesh_Dhingra.pdf",
    "100007": "payslip_07_Joshua_Sule.pdf",
    "100008": "payslip_08_Ikbal_Barad.pdf",
    "100009": "payslip_09_Simon_Jani.pdf",
    "100010": "payslip_10_Ganga_Vig.pdf",
}

SCENARIOS = {
    "100001": ("1st execution - everything correct", "everything_correct"),
    "100002": ("2nd execution - income overstated", "income_overstated"),
    "100003": ("3rd execution - name mismatch", "name_mismatch"),
    "100004": ("4th execution - payslip too old", "payslip_too_old"),
    "100005": ("5th execution - everything correct", "everything_correct"),
    "100006": ("6th execution - everything correct", "everything_correct"),
    "100007": ("7th execution - income overstated", "income_overstated"),
    "100008": ("8th execution - name mismatch", "name_mismatch"),
    "100009": ("9th execution - payslip too old", "payslip_too_old"),
    "100010": ("10th execution - everything correct", "everything_correct"),
}

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def make_hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()

def load_accounts():
    if not GROUND_TRUTH.exists():
        raise FileNotFoundError(f"Missing: {GROUND_TRUTH}")
    with open(GROUND_TRUTH, "r", encoding="utf-8") as f:
        rows = json.load(f)
    if len(rows) < 10:
        raise ValueError("ground_truth_realistic.json needs at least 10 records.")
    return {f"{100000+i}": row for i, row in enumerate(rows[:10], start=1)}

def pdf_text(pdf_path):
    reader = PdfReader(str(pdf_path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)

def line_value(text, label):
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    for i, line in enumerate(lines):
        if line.lower().startswith(label.lower()):
            if ":" in line:
                v = line.split(":", 1)[1].strip()
                if v:
                    return v
            if i + 1 < len(lines):
                return lines[i + 1].strip()
    return None

def money_value(text, label):
    import re
    pattern = re.escape(label) + r"\s*[:\-]?\s*(?:₹\s*)?([\d,]+(?:\.\d+)?)"
    m = re.search(pattern, text, flags=re.IGNORECASE)
    if not m:
        return None
    return float(m.group(1).replace(",", ""))

def parse_payslip(pdf_path):
    text = pdf_text(pdf_path)
    return {
        "name": line_value(text, "Employee Name"),
        "dob": line_value(text, "Date of Birth"),
        "employee_id": line_value(text, "Employee ID"),
        "gross_salary": money_value(text, "Gross Salary"),
        "total_deductions": money_value(text, "Total Deductions"),
        "net_salary": money_value(text, "NET SALARY PAYABLE"),
        "pay_period": "01-Aug-2026 to 31-Aug-2026",
        "pay_date": "31-Aug-2026",
    }

def decision_for(scenario, name_match, dob_match, salary_valid, net_salary):
    if scenario == "everything_correct":
        if name_match and dob_match and salary_valid:
            return {
                "decision_output": "verified",
                "confidence_score": 0.95,
                "reasoning": (
                    "The employee name and date of birth match the Aadhaar "
                    "reference, the salary calculation is internally consistent, "
                    "and no verification discrepancy was detected."
                ),
                "risk_factors": {"irreversibility": 2, "impact": 3, "explainability": 10},
            }
        return {
            "decision_output": "needs_review",
            "confidence_score": 0.70,
            "reasoning": (
                "The payslip could not be fully verified against the Aadhaar "
                "reference or salary calculation."
            ),
            "risk_factors": {"irreversibility": 4, "impact": 5, "explainability": 8},
        }

    if scenario == "income_overstated":
        return {
            "decision_output": "rejected",
            "confidence_score": 0.97,
            "reasoning": (
                "The declared monthly income is higher than the "
                f"payslip-supported net income of ₹{net_salary:,.2f}."
            ),
            "risk_factors": {"irreversibility": 6, "impact": 7, "explainability": 9},
        }

    if scenario == "name_mismatch":
        return {
            "decision_output": "needs_review",
            "confidence_score": 0.90,
            "reasoning": (
                "The applicant name does not match the employee name on the "
                "submitted payslip/Aadhaar reference. Manual review is required "
                "to rule out identity mismatch or document manipulation."
            ),
            "risk_factors": {"irreversibility": 5, "impact": 7, "explainability": 8},
        }

    if scenario == "payslip_too_old":
        return {
            "decision_output": "rejected",
            "confidence_score": 0.96,
            "reasoning": (
                "The submitted payslip is outside the permitted verification "
                "period and should be rejected or reviewed according to policy."
            ),
            "risk_factors": {"irreversibility": 5, "impact": 6, "explainability": 9},
        }

    return {
        "decision_output": "needs_review",
        "confidence_score": 0.50,
        "reasoning": "Manual review is required.",
        "risk_factors": {"irreversibility": 5, "impact": 5, "explainability": 8},
    }

def get_evidence(execution_id, scenario):
    queries = {
        "everything_correct": (
            "Verify employee identity, date of birth, required payslip "
            "information and mathematical salary consistency."
        ),
        "income_overstated": (
            "Declared monthly income is higher than the income supported by the payslip."
        ),
        "name_mismatch": (
            "Applicant name does not match employee name on the payslip."
        ),
        "payslip_too_old": (
            "Payslip is older than the permitted verification period."
        ),
    }
    results = retrieve_policy(queries.get(scenario, queries["everything_correct"]), n_results=3)
    evidence = []
    for item in results:
        distance = item.get("distance")
        score = 1 / (1 + distance) if distance is not None else 0.0
        evidence.append({
            "evidence_id": str(uuid.uuid4()),
            "execution_id": execution_id,
            "source": "Payslip ChromaDB",
            "document_reference": item.get("source", "unknown_policy"),
            "retrieval_score": round(score, 4),
            "timestamp": now_iso(),
        })
    return evidence

def build_result(account_id, account, execution_number):
    pdf_path = PAYSLIP_DIR / ACCOUNT_PAYSLIP_MAP[account_id]
    if not pdf_path.exists():
        raise FileNotFoundError(f"Missing payslip: {pdf_path}")

    label, scenario = SCENARIOS[account_id]
    payslip = parse_payslip(pdf_path)

    name_match = (
        account["name"].strip().lower()
        == (payslip["name"] or "").strip().lower()
    )
    dob_match = account["dob"] == payslip["dob"]

    gross = payslip["gross_salary"]
    deductions = payslip["total_deductions"]
    net = payslip["net_salary"]

    salary_valid = (
        gross is not None and deductions is not None and net is not None
        and abs((gross - deductions) - net) < 0.01
    )

    declared_income = net
    applicant_name = account["name"]

    if scenario == "income_overstated" and net is not None:
        declared_income = net + 10000
    elif scenario == "name_mismatch":
        applicant_name = "Different Applicant"

    execution_id = str(uuid.uuid4())
    application_id = f"APP-{account_id}"
    orchestration_id = f"WF-APP-{account_id}"
    start_time = now_iso()

    input_data = {
        "application_id": application_id,
        "applicant_ref_id": account_id,
        "account_id": account_id,
        "applicant_name": applicant_name,
        "loan_amount": 150000.0,
        "declared_monthly_income": declared_income,
        "payslip_file": pdf_path.name,
        "extracted": {
            "name": account["name"],
            "dob": account["dob"],
            "gender": account["gender"],
            "address": account["address"],
            "aadhaar_number": account["aadhaar_number"],
        },
        "payslip": payslip,
        "validation": {
            "name_match": name_match,
            "dob_match": dob_match,
            "salary_math_valid": salary_valid,
        },
        "scenario": scenario,
    }

    dec = decision_for(
        scenario,
        name_match,
        dob_match,
        salary_valid,
        net or 0.0,
    )

    output_data = {
        "decision_output": dec["decision_output"],
        "confidence_score": dec["confidence_score"],
        "reasoning": dec["reasoning"],
        "risk_factors": dec["risk_factors"],
    }

    input_hash = make_hash(input_data)
    output_hash = make_hash(output_data)
    end_time = now_iso()

    evidence = get_evidence(execution_id, scenario)

    factors = dec["risk_factors"]
    composite = round(
        (
            factors["impact"]
            + factors["irreversibility"]
            + (10 - factors["explainability"])
        ) / 3,
        2,
    )

    risk_level = (
        "High" if composite >= 7
        else "Medium" if composite >= 4
        else "Low"
    )

    accountability = {
        "score_id": str(uuid.uuid4()),
        "execution_id": execution_id,
        "impact_score": factors["impact"],
        "irreversibility_score": factors["irreversibility"],
        "explainability_score": factors["explainability"],
        "composite_risk_score": composite,
        "risk_level": risk_level,
        "review_required": dec["decision_output"] in {
            "rejected", "needs_review", "manual_review"
        },
        "scoring_model_version": "tracechain-scoring-v1",
        "calculated_at": end_time,
    }

    provenance_payload = {
        "input_hash": input_hash,
        "output_hash": output_hash,
        "previous_record_hash": None,
        "execution_id": execution_id,
    }

    record_hash = make_hash(provenance_payload)

    return {
        "user": {
            "user_id": account_id,
            "created_at": start_time,
        },
        "application": {
            "application_id": application_id,
            "user_id": account_id,
            "loan_amount": 150000,
            "application_date": start_time,
            "status": "processing",
        },
        "execution": {
            "execution_id": execution_id,
            "orchestration_id": orchestration_id,
            "agent_id": "P001",
            "input_data": input_data,
            "output_data": output_data,
            "model_id": "rule-engine+llm-reasoning-v1",
            "rule_id": "payslip_policy_v1",
            "start_time": start_time,
            "end_time": end_time,
            "status": "completed",
            "sequence_number": 1,
            "input_hash": input_hash,
        },
        "decision": {
            "decision_id": str(uuid.uuid4()),
            "execution_id": execution_id,
            "decision_output": dec["decision_output"],
            "confidence_score": dec["confidence_score"],
            "reasoning": dec["reasoning"],
            "timestamp": end_time,
        },
        "evidence": evidence,
        "accountability": accountability,
        "provenance": {
            "record_id": str(uuid.uuid4()),
            "orchestration_id": orchestration_id,
            "execution_id": execution_id,
            "event_type": "agent_execution",
            "input_data": input_data,
            "output_data": output_data,
            "previous_record_hash": None,
            "timestamp": end_time,
            "input_hash": input_hash,
            "output_hash": output_hash,
            "record_hash": record_hash,
            "tamper_check_passed": True,
        },
    }

def print_result(num, account_id, result):
    print()
    print("=" * 90)
    print(f"EXECUTION {num} - {SCENARIOS[account_id][0].upper()}")
    print("=" * 90)
    print(f"ACCOUNT ID: APP-{account_id}")
    print(f"DECISION: {result['decision']['decision_output']} "
          f"(confidence: {result['decision']['confidence_score']})")
    print(f"RISK LEVEL: {result['accountability']['risk_level']} "
          f"composite: {result['accountability']['composite_risk_score']} "
          f"review_required: {result['accountability']['review_required']}")
    print(f"TAMPER CHECK: {result['provenance']['tamper_check_passed']}")

def main():
    accounts = load_accounts()

    print()
    print("=" * 90)
    print("PAYSLIP AGENT (P001) - FULL EXECUTION OUTPUT")
    print("=" * 90)

    all_results = []

    for num, account_id in enumerate(ACCOUNT_PAYSLIP_MAP, start=1):
        result = build_result(
            account_id,
            accounts[account_id],
            num,
        )
        all_results.append(result)
        print_result(num, account_id, result)

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            all_results,
            f,
            indent=2,
            ensure_ascii=False,
        )

    print()
    print("=" * 90)
    print("Saved all 10 full schema-shaped payslip results")
    print(f"to {OUTPUT_FILE}")
    print("=" * 90)

if __name__ == "__main__":
    main()
