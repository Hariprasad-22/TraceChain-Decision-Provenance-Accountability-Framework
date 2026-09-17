import json
import os
import uuid
from pathlib import Path
from datetime import datetime, timezone

from pypdf import PdfReader

from chroma_retriever import retrieve_policy
from execution_record import (
    ExecutionMetadata,
    AgentDecision,
    Evidence,
    AccountabilityScore,
    ProvenanceRecordV2,
    risk_level_for,
    print_execution_records,
)

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

BASE_DIR = Path(__file__).resolve().parent
GROUND_TRUTH_FILE = BASE_DIR / "ground_truth_realistic.json"
PAYSLIP_DIR = BASE_DIR / "payslips"

MIN_EMI_PERCENT = 30.0
MAX_EMI_PERCENT = 50.0
MAX_TENURE_MONTHS = 60
ANNUAL_INTEREST_RATE = 12.0
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
VERSION = "PAYSLIP-LLM-RAG-REASONING-V2-REJECT-BELOW-30"

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


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_records():
    if not GROUND_TRUTH_FILE.exists():
        raise FileNotFoundError(f"Reference file not found:\n{GROUND_TRUTH_FILE}")
    with open(GROUND_TRUTH_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def extract_pdf_text(pdf_path):
    reader = PdfReader(str(pdf_path))
    texts = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            texts.append(text)
    return "\n".join(texts)


def extract_field(text, label):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if line.lower().startswith(label.lower()):
            if ":" in line:
                value = line.split(":", 1)[1].strip()
                if value:
                    return value
            if index + 1 < len(lines):
                return lines[index + 1].strip()
    return None


def extract_money(text, label):
    import re
    pattern = (
        re.escape(label)
        + r"\s*[:\-]?\s*(?:₹\s*)?"
        + r"([\d,]+(?:\.\d+)?)"
    )
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def parse_payslip(pdf_path):
    text = extract_pdf_text(pdf_path)
    return {
        "employee_name": extract_field(text, "Employee Name"),
        "dob": extract_field(text, "Date of Birth"),
        "employee_id": extract_field(text, "Employee ID"),
        "gross_salary": extract_money(text, "Gross Salary"),
        "total_deductions": extract_money(text, "Total Deductions"),
        "net_salary": extract_money(text, "NET SALARY PAYABLE"),
        "pay_period": extract_field(text, "Pay Period"),
        "pay_date": extract_field(text, "Pay Date"),
    }


def verify_identity(aadhaar_record, payslip):
    aadhaar_name = aadhaar_record["name"].strip().lower()
    payslip_name = (payslip["employee_name"] or "").strip().lower()
    aadhaar_dob = aadhaar_record["dob"]
    payslip_dob = payslip["dob"] or ""
    name_match = aadhaar_name == payslip_name
    dob_match = aadhaar_dob == payslip_dob
    return {
        "name_match": name_match,
        "dob_match": dob_match,
        "identity_verified": name_match and dob_match,
    }


def verify_salary(payslip):
    gross = payslip["gross_salary"]
    deductions = payslip["total_deductions"]
    net = payslip["net_salary"]
    if gross is None or deductions is None or net is None:
        return {"salary_math_valid": False, "calculated_net_salary": None}
    calculated_net = gross - deductions
    return {
        "salary_math_valid": abs(calculated_net - net) < 0.01,
        "calculated_net_salary": round(calculated_net, 2),
    }


def get_positive_float(prompt):
    while True:
        try:
            value = float(input(prompt).strip())
            if value <= 0:
                raise ValueError
            return value
        except ValueError:
            print("Please enter a valid positive number.")


def get_tenure(prompt):
    while True:
        try:
            value = int(input(prompt).strip())
            if value <= 0 or value > MAX_TENURE_MONTHS:
                raise ValueError
            return value
        except ValueError:
            print(f"Please enter a whole number from 1 to {MAX_TENURE_MONTHS}.")


def calculate_emi(loan_amount, repayment_months, annual_interest_rate):
    monthly_rate = annual_interest_rate / 12 / 100
    if monthly_rate == 0:
        return round(loan_amount / repayment_months, 2)
    factor = (1 + monthly_rate) ** repayment_months
    emi = loan_amount * monthly_rate * factor / (factor - 1)
    return round(emi, 2)


def classify_emi(emi, net_salary):
    percent = (emi / net_salary) * 100
    if percent < MIN_EMI_PERCENT:
        return percent, "below_30_percent"
    if percent <= MAX_EMI_PERCENT:
        return percent, "within_30_to_50_percent"
    return percent, "above_50_percent"


def retrieve_payslip_policies():
    query = """
    Payslip verification for a loan application: employee identity
    verification against Aadhaar reference, date of birth matching,
    salary consistency, gross salary minus deductions equals net salary,
    income verification, loan affordability, EMI calculation, and review.
    Retrieve policies relevant to payslip validation, identity verification,
    income verification, and affordability. The configured project rule is:
    below 30% EMI-to-salary = rejected, 30%-50% = verified, above 50% = rejected.
    """
    return retrieve_policy(query=query, n_results=3)


def generate_llm_reasoning(facts, chroma_results):
    """LLM explains the deterministic result; it never makes the decision."""
    if OpenAI is None:
        raise RuntimeError("OpenAI SDK not installed. Run: python -m pip install openai")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to the PyCharm Run Configuration "
            "or set it in the same terminal before running."
        )

    policy_evidence = []
    for result in chroma_results:
        distance = result["distance"]
        policy_evidence.append({
            "document_reference": result["source"],
            "retrieval_score": round(1 / (1 + distance), 4),
            "policy_text": result["document"],
        })

    payload = {
        "deterministic_facts": facts,
        "retrieved_policy_evidence": policy_evidence,
    }

    instructions = """
You are the explanation component of a Payslip Verification Agent.

The deterministic rule engine has ALREADY calculated the final decision.
Your job is ONLY to explain why that decision was reached.

Rules:
- Never change or override the deterministic decision.
- Never invent facts or policy requirements.
- Use only the supplied facts and retrieved policy evidence.
- Treat ChromaDB results as supporting policy evidence.
- The configured 30%-50% EMI range is a project rule, not a universal banking rule.
- EMI below 30% -> rejected because it is below the configured minimum.
- EMI from 30% through 50% -> verified.
- EMI above 50% -> rejected because it exceeds the configured maximum.
- Clearly distinguish facts from policy-based conclusions.

Explain in this order:
1. Identity: name and DOB comparison with the Aadhaar reference.
2. Salary: gross salary, deductions, and net salary consistency.
3. Loan affordability: loan amount, tenure, EMI, and EMI percentage of salary.
4. Policy grounding: mention the retrieved policy documents that support the checks.
5. Final decision: explain why the deterministic engine produced the supplied decision.

Write 4-6 concise audit-friendly sentences.
Return only the explanation.
"""

    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=OPENAI_MODEL,
        instructions=instructions,
        input=json.dumps(payload, ensure_ascii=False, indent=2),
    )

    reasoning = (response.output_text or "").strip()
    if not reasoning:
        raise RuntimeError("OpenAI returned empty reasoning.")
    return reasoning


def generate_fallback_reasoning(facts):
    identity = facts["identity"]
    salary = facts["salary_verification"]
    loan_amount = facts["requested_loan_amount"]
    tenure = facts["repayment_period_months"]
    emi = facts["calculated_emi"]
    emi_percent = facts["emi_percent_of_salary"]
    affordability = facts["affordability_status"]
    decision = facts["deterministic_decision"]

    identity_text = (
        "the employee name and DOB match the Aadhaar reference"
        if identity["identity_verified"]
        else "the employee identity does not fully match the Aadhaar reference"
    )
    salary_text = (
        "the gross salary minus deductions matches the stated net salary"
        if salary["salary_math_valid"]
        else "the salary components are not mathematically consistent"
    )

    if affordability == "below_30_percent":
        affordability_text = "the EMI is below the configured 30% minimum, so the application is rejected"
    elif affordability == "above_50_percent":
        affordability_text = "the EMI exceeds the configured 50% maximum, so the application is rejected"
    else:
        affordability_text = "the EMI falls within the configured 30%-50% range"

    return (
        f"The payslip shows that {identity_text}, and {salary_text}. "
        f"For the requested loan of ₹{loan_amount:,.2f} over {tenure} months, "
        f"the calculated EMI is ₹{emi:,.2f}, which is {emi_percent:.2f}% of the "
        f"verified net monthly salary. {affordability_text}, so the deterministic "
        f"decision is {decision.upper()}. The 30%-50% affordability range is a "
        f"configured project rule."
    )


def select_account():
    print("\nAvailable accounts:\n")
    for account_id, filename in ACCOUNT_PAYSLIP_MAP.items():
        print(f"  {account_id} -> {filename}")
    print()
    while True:
        account_id = input("Enter account ID: ").strip()
        if account_id in ACCOUNT_PAYSLIP_MAP:
            return account_id
        print("Invalid account ID. Use 100001 to 100010.")


def run_single_test(account_id):
    records = load_records()
    account_index = int(account_id) - 100001
    if account_index < 0 or account_index >= len(records):
        raise ValueError("No reference record found for this account.")

    aadhaar_record = records[account_index]
    payslip_path = PAYSLIP_DIR / ACCOUNT_PAYSLIP_MAP[account_id]
    if not payslip_path.exists():
        raise FileNotFoundError(f"Payslip not found:\n{payslip_path}")

    print("\n" + "=" * 70)
    print("SINGLE PAYSLIP VERIFICATION")
    print("=" * 70)
    print(f"\nAccount ID       : {account_id}")
    print(f"Aadhaar Name     : {aadhaar_record['name']}")
    print(f"Payslip          : {payslip_path.name}")

    print("\nReading payslip...")
    payslip = parse_payslip(payslip_path)

    print("\nExtracted Payslip Data:")
    print(f"  Employee Name  : {payslip['employee_name']}")
    print(f"  DOB            : {payslip['dob']}")
    print(f"  Employee ID    : {payslip['employee_id']}")
    print(f"  Gross Salary   : {payslip['gross_salary']}")
    print(f"  Deductions     : {payslip['total_deductions']}")
    print(f"  Net Salary     : {payslip['net_salary']}")
    print(f"  Pay Period     : {payslip['pay_period']}")
    print(f"  Pay Date       : {payslip['pay_date']}")

    identity = verify_identity(aadhaar_record, payslip)
    salary = verify_salary(payslip)
    verified_net_salary = payslip["net_salary"]
    if verified_net_salary is None or verified_net_salary <= 0:
        raise ValueError("Net salary could not be extracted from payslip.")

    print("\nLoan Affordability Details")
    print(f"  EMI affordability range : {MIN_EMI_PERCENT:.0f}% - {MAX_EMI_PERCENT:.0f}% of net salary")
    print(f"  Maximum tenure           : {MAX_TENURE_MONTHS} months (5 years)")
    print(f"  Demo interest rate       : {ANNUAL_INTEREST_RATE:.2f}% p.a.")

    loan_amount = get_positive_float("  Enter requested loan amount (₹): ")
    repayment_months = get_tenure("  Enter repayment tenure in months (1-60): ")

    emi = calculate_emi(loan_amount, repayment_months, ANNUAL_INTEREST_RATE)
    affordability_ratio, affordability_status = classify_emi(emi, verified_net_salary)
    max_affordable_monthly_payment = verified_net_salary * MAX_EMI_PERCENT / 100
    affordability_passed = affordability_status == "within_30_to_50_percent"

    print("\nCalculated EMI")
    print(f"  Verified Net Salary   : ₹{verified_net_salary:,.2f}")
    print(f"  Loan Amount           : ₹{loan_amount:,.2f}")
    print(f"  Tenure                : {repayment_months} months")
    print(f"  Monthly EMI           : ₹{emi:,.2f}")
    print(f"  EMI / Salary          : {affordability_ratio:.2f}%")
    print(f"  Allowed EMI Range     : {MIN_EMI_PERCENT:.0f}% - {MAX_EMI_PERCENT:.0f}%")

    if affordability_status == "within_30_to_50_percent":
        print("  Affordability Status   : PASSED")
    elif affordability_status == "below_30_percent":
        print("  Affordability Status   : REJECTED - BELOW 30%")
    else:
        print("  Affordability Status   : FAILED - ABOVE 50%")

    # Deterministic rule engine decides first.
    if not identity["identity_verified"]:
        decision_output = "needs_review"
        confidence = 0.90
    elif not salary["salary_math_valid"]:
        decision_output = "needs_review"
        confidence = 0.85
    elif affordability_status == "above_50_percent":
        decision_output = "rejected"
        confidence = 0.96
    elif affordability_status == "below_30_percent":
        decision_output = "rejected"
        confidence = 0.94
    else:
        decision_output = "verified"
        confidence = 0.95

    print("\nRetrieving policy evidence from ChromaDB...")
    chroma_results = retrieve_payslip_policies()

    facts = {
        "identity": identity,
        "salary_verification": salary,
        "verified_net_salary": verified_net_salary,
        "requested_loan_amount": loan_amount,
        "repayment_period_months": repayment_months,
        "annual_interest_rate": ANNUAL_INTEREST_RATE,
        "calculated_emi": emi,
        "emi_percent_of_salary": round(affordability_ratio, 2),
        "affordability_status": affordability_status,
        "configured_affordability_range": f"{MIN_EMI_PERCENT:.0f}% to {MAX_EMI_PERCENT:.0f}%",
        "maximum_allowed_emi": round(max_affordable_monthly_payment, 2),
        "deterministic_decision": decision_output,
        "deterministic_confidence": confidence,
        "decision_rule": "below 30% = rejected; 30%-50% = verified; above 50% = rejected",
    }

    print("\nGenerating LLM reasoning...")
    try:
        llm_reasoning = generate_llm_reasoning(facts, chroma_results)
        llm_status = "generated"
    except Exception as exc:
        llm_reasoning = generate_fallback_reasoning(facts)
        llm_status = "fallback"
        print(f"[LLM WARNING] {exc}")

    print("\nLLM Reasoning:")
    print(f"  {llm_reasoning}")

    execution_id = str(uuid.uuid4())
    decision_id = str(uuid.uuid4())
    record_id = str(uuid.uuid4())
    orchestration_id = f"WF-APP-{account_id}"
    start_time = now_iso()

    input_data = {
        "application_id": f"APP-{account_id}",
        "applicant_ref_id": account_id,
        "account_id": account_id,
        "applicant_name": aadhaar_record["name"],
        "loan_amount": loan_amount,
        "declared_monthly_income": verified_net_salary,
        "minimum_emi_percent": MIN_EMI_PERCENT,
        "maximum_emi_percent": MAX_EMI_PERCENT,
        "annual_interest_rate": ANNUAL_INTEREST_RATE,
        "repayment_period_months": repayment_months,
        "payslip_file": payslip_path.name,
        "extracted": payslip,
        "validation": {
            "name_match": identity["name_match"],
            "dob_match": identity["dob_match"],
            "identity_verified": identity["identity_verified"],
            "salary_math_valid": salary["salary_math_valid"],
            "calculated_net_salary": salary["calculated_net_salary"],
        },
        "affordability_check": {
            "verified_net_monthly_salary": verified_net_salary,
            "requested_loan_amount": loan_amount,
            "repayment_period_months": repayment_months,
            "calculated_monthly_emi": emi,
            "minimum_emi_percent": MIN_EMI_PERCENT,
            "maximum_emi_percent": MAX_EMI_PERCENT,
            "maximum_allowed_emi": round(max_affordable_monthly_payment, 2),
            "emi_percent_of_salary": round(affordability_ratio, 2),
            "affordability_status": affordability_status,
            "affordability_passed": affordability_passed,
        },
    }

    output_data = {
        "decision_output": decision_output,
        "confidence_score": confidence,
        "reasoning_source": "OpenAI LLM grounded in deterministic facts + ChromaDB policy evidence",
        "llm_model": OPENAI_MODEL,
        "llm_status": llm_status,
        "llm_reasoning": llm_reasoning,
        "validation_results": {
            "name_match": identity["name_match"],
            "dob_match": identity["dob_match"],
            "identity_verified": identity["identity_verified"],
            "salary_math_valid": salary["salary_math_valid"],
        },
        "affordability_results": {
            "requested_loan_amount": loan_amount,
            "verified_net_monthly_salary": verified_net_salary,
            "repayment_period_months": repayment_months,
            "calculated_monthly_emi": emi,
            "minimum_emi_percent": MIN_EMI_PERCENT,
            "maximum_emi_percent": MAX_EMI_PERCENT,
            "maximum_allowed_emi": round(max_affordable_monthly_payment, 2),
            "emi_percent_of_salary": round(affordability_ratio, 2),
            "affordability_status": affordability_status,
            "affordability_passed": affordability_passed,
        },
        "risk_factors": {
            "irreversibility": 2 if decision_output == "verified" else (5 if decision_output == "needs_review" else 7),
            "impact": 3 if decision_output == "verified" else (7 if decision_output == "needs_review" else 8),
            "explainability": 10 if decision_output == "verified" else 8,
        },
    }

    end_time = now_iso()

    execution = ExecutionMetadata(
        execution_id=execution_id,
        orchestration_id=orchestration_id,
        agent_id="P001",
        input_data=input_data,
        output_data=output_data,
        model_id=f"rule-engine+{OPENAI_MODEL}",
        rule_id="payslip_policy_v1",
        start_time=start_time,
        end_time=end_time,
        status="completed",
        sequence_number=1,
    )

    decision = AgentDecision(
        decision_id=decision_id,
        execution_id=execution_id,
        decision_output=decision_output,
        confidence_score=confidence,
        reasoning=llm_reasoning,
    )

    if decision_output == "verified":
        impact, irreversibility, explainability = 3, 2, 10
    elif decision_output == "needs_review":
        impact, irreversibility, explainability = 7, 5, 8
    else:
        impact, irreversibility, explainability = 8, 7, 9

    composite = round(
        (impact + irreversibility + (10 - explainability)) / 3,
        2
    )

    accountability = AccountabilityScore(
        score_id=str(uuid.uuid4()),
        execution_id=execution_id,
        impact_score=impact,
        irreversibility_score=irreversibility,
        explainability_score=explainability,
        composite_risk_score=composite,
        risk_level=risk_level_for(composite),
        review_required=decision_output != "verified",
    )

    evidence_records = []
    for result in chroma_results:
        distance = result["distance"]
        evidence_records.append(
            Evidence(
                evidence_id=str(uuid.uuid4()),
                execution_id=execution_id,
                source="Payslip ChromaDB",
                document_reference=result["source"],
                retrieval_score=round(1 / (1 + distance), 4),
                retrieval_distance=round(distance, 4),
            )
        )

    provenance = ProvenanceRecordV2(
        record_id=record_id,
        orchestration_id=orchestration_id,
        execution_id=execution_id,
        event_type="agent_execution",
        input_data=input_data,
        output_data=output_data,
        previous_record_hash=None,
    )

    print_execution_records({
        "AGENT_EXECUTIONS": execution,
        "AGENT_DECISIONS": decision,
        "EVIDENCE": evidence_records,
        "ACCOUNTABILITY_SCORES": accountability,
        "PROVENANCE_RECORDS": provenance,
    })

    print("\n" + "=" * 70)
    print(f"FINAL RESULT: {decision_output.upper()}")
    print("=" * 70)


if __name__ == "__main__":
    print(f"[VERSION] {VERSION}")
    try:
        run_single_test(select_account())
    except Exception as error:
        print("\nERROR:")
        print(error)
