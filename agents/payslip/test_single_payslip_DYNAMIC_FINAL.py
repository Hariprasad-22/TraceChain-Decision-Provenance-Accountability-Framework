import json
import uuid
import os
from pathlib import Path
from datetime import datetime, timezone

from pypdf import PdfReader

from chroma_retriever import retrieve_policy

# =========================================================
# OPENAI LLM REASONING
# =========================================================

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

OPENAI_MODEL = "gpt-5.6-luna"


def generate_llm_reasoning(facts, chroma_results):
    """
    The rule engine makes the final decision.
    OpenAI only explains the deterministic result using the
    verified facts and retrieved ChromaDB policy evidence.
    """
    if OpenAI is None:
        return (
            "LLM unavailable: OpenAI SDK is not installed. "
            "Run: python -m pip install openai"
        )

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        return (
            "LLM unavailable: OPENAI_API_KEY is not set. "
            "Set it in the PyCharm Terminal or Run Configuration."
        )

    policy_evidence = []
    for result in chroma_results:
        policy_evidence.append({
            "source": result.get("source"),
            "document": result.get("document"),
            "distance": result.get("distance"),
        })

    prompt_data = {
        "deterministic_facts": facts,
        "policy_evidence": policy_evidence,
        "instruction": (
            "Explain the deterministic decision. Do not change or override "
            "the decision. Do not invent facts. Mention identity verification, "
            "salary consistency, loan amount, tenure, EMI, EMI percentage, "
            "and the affordability rule. The configured project rule is: "
            "EMI below 30% = REJECTED, EMI from 30% through 50% = VERIFIED, "
            "EMI above 50% = REJECTED."
        ),
    }

    try:
        client = OpenAI(api_key=api_key)

        response = client.responses.create(
            model=OPENAI_MODEL,
            instructions=(
                "You are the explanation component of a payslip verification "
                "agent. The deterministic rule engine has already made the "
                "decision. Your job is only to produce a concise, factual, "
                "audit-friendly explanation grounded in the supplied facts "
                "and policy evidence. Never override the decision."
            ),
            input=json.dumps(prompt_data, ensure_ascii=False, indent=2),
        )

        explanation = response.output_text.strip()

        if not explanation:
            return "LLM returned an empty explanation."

        return explanation

    except Exception as error:
        return f"LLM unavailable: {error}"

from execution_record import (
    ExecutionMetadata,
    AgentDecision,
    Evidence,
    AccountabilityScore,
    ProvenanceRecordV2,
    risk_level_for,
    print_execution_records,
)


# =========================================================
# PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

GROUND_TRUTH_FILE = BASE_DIR / "ground_truth_realistic.json"
PAYSLIP_DIR = BASE_DIR / "payslips"


# =========================================================
# ACCOUNT -> PAYSLIP
# =========================================================

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


# =========================================================
# TIME
# =========================================================

VERSION = "PAYSLIP-LLM-REASONING-REJECT-BELOW-30"
def now_iso():
    return datetime.now(timezone.utc).isoformat()


# =========================================================
# LOAD APPLICANT REFERENCE DATA
# =========================================================

def load_records():
    if not GROUND_TRUTH_FILE.exists():
        raise FileNotFoundError(
            f"Reference file not found:\n{GROUND_TRUTH_FILE}"
        )

    with open(GROUND_TRUTH_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


# =========================================================
# PDF EXTRACTION
# =========================================================

def extract_pdf_text(pdf_path):
    reader = PdfReader(str(pdf_path))

    all_text = []

    for page in reader.pages:
        text = page.extract_text()

        if text:
            all_text.append(text)

    return "\n".join(all_text)


# =========================================================
# FIELD EXTRACTION
# =========================================================

def extract_field(text, label):
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    for index, line in enumerate(lines):
        if line.lower().startswith(label.lower()):

            # Format:
            # Employee Name: Udyati Seth
            if ":" in line:
                value = line.split(":", 1)[1].strip()

                if value:
                    return value

            # Format:
            # Employee Name
            # Udyati Seth
            if index + 1 < len(lines):
                return lines[index + 1].strip()

    return None


def extract_money(text, label):
    import re

    pattern = (
        re.escape(label)
        + r"\s*[:\-]?\s*"
        + r"(?:₹\s*)?"
        + r"([\d,]+(?:\.\d+)?)"
    )

    match = re.search(
        pattern,
        text,
        re.IGNORECASE
    )

    if not match:
        return None

    return float(
        match.group(1).replace(",", "")
    )


# =========================================================
# PARSE PAYSLIP
# =========================================================

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


# =========================================================
# IDENTITY VERIFICATION
# =========================================================

def verify_identity(aadhaar_record, payslip):
    aadhaar_name = (
        aadhaar_record["name"]
        .strip()
        .lower()
    )

    payslip_name = (
        payslip["employee_name"]
        .strip()
        .lower()
        if payslip["employee_name"]
        else ""
    )

    aadhaar_dob = aadhaar_record["dob"]
    payslip_dob = payslip["dob"]

    name_match = aadhaar_name == payslip_name
    dob_match = aadhaar_dob == payslip_dob

    return {
        "name_match": name_match,
        "dob_match": dob_match,
        "identity_verified": name_match and dob_match,
    }


# =========================================================
# SALARY VERIFICATION
# =========================================================

def verify_salary(payslip):
    gross = payslip["gross_salary"]
    deductions = payslip["total_deductions"]
    net = payslip["net_salary"]

    if gross is None or deductions is None or net is None:
        return {
            "salary_math_valid": False,
            "calculated_net_salary": None,
        }

    calculated_net = gross - deductions

    return {
        "salary_math_valid": abs(calculated_net - net) < 0.01,
        "calculated_net_salary": round(calculated_net, 2),
    }


# =========================================================
# LOAN / EMI POLICY
# =========================================================

MIN_EMI_PERCENT = 30.0
MAX_EMI_PERCENT = 50.0
MAX_TENURE_MONTHS = 60
ANNUAL_INTEREST_RATE = 12.0  # Demo/project assumption


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
            print("Please enter a whole number of months from 1 to 60.")


def calculate_emi(loan_amount, repayment_months, annual_interest_rate):
    monthly_rate = annual_interest_rate / 12 / 100
    if monthly_rate == 0:
        return round(loan_amount / repayment_months, 2)
    factor = (1 + monthly_rate) ** repayment_months
    return round(loan_amount * monthly_rate * factor / (factor - 1), 2)


def classify_emi(emi, net_salary):
    percent = (emi / net_salary) * 100
    if percent < MIN_EMI_PERCENT:
        return percent, "below_30_percent"
    if percent <= MAX_EMI_PERCENT:
        return percent, "within_30_to_50_percent"
    return percent, "above_50_percent"


# =========================================================
# ACCOUNT SELECTION
# =========================================================

def select_account():
    print("\nAvailable accounts:\n")

    for account_id, filename in ACCOUNT_PAYSLIP_MAP.items():
        print(
            f"  {account_id} -> {filename}"
        )

    print()

    while True:
        account_id = input(
            "Enter account ID: "
        ).strip()

        if account_id in ACCOUNT_PAYSLIP_MAP:
            return account_id

        print(
            "Invalid account ID. "
            "Use 100001 to 100010."
        )


# =========================================================
# RUN ONE PAYSLIP VERIFICATION
# =========================================================

def run_single_test(account_id):

    records = load_records()

    account_index = int(account_id) - 100001

    if account_index < 0 or account_index >= len(records):
        raise ValueError(
            "No reference record found for this account."
        )

    aadhaar_record = records[account_index]

    payslip_path = (
        PAYSLIP_DIR
        / ACCOUNT_PAYSLIP_MAP[account_id]
    )

    if not payslip_path.exists():
        raise FileNotFoundError(
            f"Payslip not found:\n{payslip_path}"
        )

    print("\n")
    print("=" * 70)
    print("SINGLE PAYSLIP VERIFICATION")
    print("=" * 70)

    print(
        f"\nAccount ID       : {account_id}"
    )

    print(
        f"Aadhaar Name     : "
        f"{aadhaar_record['name']}"
    )

    print(
        f"Payslip          : "
        f"{payslip_path.name}"
    )

    # -----------------------------------------------------
    # READ PAYSLIP
    # -----------------------------------------------------

    print("\nReading payslip...")

    payslip = parse_payslip(payslip_path)

    print("\nExtracted Payslip Data:")

    print(
        f"  Employee Name  : "
        f"{payslip['employee_name']}"
    )

    print(
        f"  DOB            : "
        f"{payslip['dob']}"
    )

    print(
        f"  Employee ID    : "
        f"{payslip['employee_id']}"
    )

    print(
        f"  Gross Salary   : "
        f"{payslip['gross_salary']}"
    )

    print(
        f"  Deductions     : "
        f"{payslip['total_deductions']}"
    )

    print(
        f"  Net Salary     : "
        f"{payslip['net_salary']}"
    )

    print(
        f"  Pay Period     : "
        f"{payslip['pay_period']}"
    )

    print(
        f"  Pay Date       : "
        f"{payslip['pay_date']}"
    )

    # -----------------------------------------------------
    # IDENTITY
    # -----------------------------------------------------

    identity = verify_identity(
        aadhaar_record,
        payslip
    )

    # -----------------------------------------------------
    # SALARY
    # -----------------------------------------------------

    salary = verify_salary(payslip)

    salary_valid = salary["salary_math_valid"]

    # -----------------------------------------------------
    # VERIFIED MONTHLY INCOME
    # -----------------------------------------------------

    verified_net_salary = payslip["net_salary"]

    if verified_net_salary is None or verified_net_salary <= 0:
        raise ValueError(
            "Net salary could not be extracted from payslip."
        )

    # -----------------------------------------------------
    # DYNAMIC LOAN AFFORDABILITY
    # -----------------------------------------------------

    print("\nLoan Affordability Details")
    print(f"  EMI affordability range : {MIN_EMI_PERCENT:.0f}% - {MAX_EMI_PERCENT:.0f}% of net salary")
    print(f"  Maximum tenure           : {MAX_TENURE_MONTHS} months (5 years)")
    print(f"  Demo interest rate       : {ANNUAL_INTEREST_RATE:.2f}% p.a.")

    loan_amount = get_positive_float("  Enter requested loan amount (₹): ")
    repayment_months = get_tenure("  Enter repayment tenure in months (1-60): ")

    estimated_monthly_repayment = calculate_emi(
        loan_amount, repayment_months, ANNUAL_INTEREST_RATE
    )

    affordability_ratio, affordability_status = classify_emi(
        estimated_monthly_repayment, verified_net_salary
    )

    max_affordable_monthly_payment = verified_net_salary * MAX_EMI_PERCENT / 100
    affordability_passed = affordability_status == "within_30_to_50_percent"

    print("\nCalculated EMI")
    print(f"  Verified Net Salary   : ₹{verified_net_salary:,.2f}")
    print(f"  Loan Amount           : ₹{loan_amount:,.2f}")
    print(f"  Tenure                : {repayment_months} months")
    print(f"  Monthly EMI           : ₹{estimated_monthly_repayment:,.2f}")
    print(f"  EMI / Salary          : {affordability_ratio:.2f}%")
    print(f"  Allowed EMI Range     : {MIN_EMI_PERCENT:.0f}% - {MAX_EMI_PERCENT:.0f}%")
    if affordability_status == "within_30_to_50_percent":
        print("  Affordability Status   : PASSED")
    elif affordability_status == "below_30_percent":
        print("  Affordability Status   : REJECTED - BELOW 30%")
    else:
        print("  Affordability Status   : FAILED - ABOVE 50%")

    # -----------------------------------------------------
    # FINAL DECISION
    # -----------------------------------------------------

    if not identity["identity_verified"]:

        decision_output = "needs_review"
        confidence = 0.90

        reasoning = (
            "The employee name or date of birth does not "
            "match the Aadhaar reference. Manual review is "
            "required before using the payslip for the loan."
        )

    elif not salary_valid:

        decision_output = "needs_review"
        confidence = 0.85

        reasoning = (
            "The salary components are not mathematically "
            "consistent because gross salary minus deductions "
            "does not match the stated net salary."
        )

    elif affordability_status == "above_50_percent":
        decision_output = "rejected"
        confidence = 0.96
        reasoning = (
            f"The identity and salary checks passed, but the calculated EMI of "
            f"₹{estimated_monthly_repayment:,.2f} is {affordability_ratio:.2f}% "
            f"of the verified net salary, which is above the maximum allowed "
            f"50% affordability limit of ₹{max_affordable_monthly_payment:,.2f}."
        )
    elif affordability_status == "below_30_percent":
        decision_output = "rejected"
        confidence = 0.95
        reasoning = (
            f"The identity and salary checks passed, but the calculated EMI of "
            f"₹{estimated_monthly_repayment:,.2f} is {affordability_ratio:.2f}% "
            f"of the verified net salary, which is below the configured "
            f"30% minimum affordability threshold. Therefore, the loan "
            f"application is rejected under the configured project policy."
        )
    else:
        decision_output = "verified"
        confidence = 0.95
        reasoning = (
            f"The employee identity matches the Aadhaar reference, the salary "
            f"calculation is internally consistent, and the calculated EMI of "
            f"₹{estimated_monthly_repayment:,.2f} is {affordability_ratio:.2f}% "
            f"of the verified net salary, which is within the configured "
            f"30%-50% affordability range."
        )

    # -----------------------------------------------------
    # IDS / TIME
    # -----------------------------------------------------

    execution_id = str(uuid.uuid4())
    decision_id = str(uuid.uuid4())
    record_id = str(uuid.uuid4())

    orchestration_id = (
        f"WF-APP-{account_id}"
    )

    start_time = now_iso()

    # -----------------------------------------------------
    # INPUT DATA
    # -----------------------------------------------------

    input_data = {

        "application_id":
            f"APP-{account_id}",

        "applicant_ref_id":
            account_id,

        "account_id":
            account_id,

        "applicant_name":
            aadhaar_record["name"],

        "loan_amount":
            loan_amount,

        "declared_monthly_income":
            verified_net_salary,

        "minimum_emi_percent": MIN_EMI_PERCENT,

        "maximum_emi_percent": MAX_EMI_PERCENT,

        "annual_interest_rate": ANNUAL_INTEREST_RATE,

        "repayment_period_months":
            repayment_months,

        "payslip_file":
            payslip_path.name,

        "extracted": {
            "name":
                payslip["employee_name"],

            "dob":
                payslip["dob"],

            "employee_id":
                payslip["employee_id"],

            "gross_salary":
                payslip["gross_salary"],

            "total_deductions":
                payslip["total_deductions"],

            "net_salary":
                payslip["net_salary"],

            "pay_period":
                payslip["pay_period"],

            "pay_date":
                payslip["pay_date"],
        },

        "validation": {

            "name_match":
                identity["name_match"],

            "dob_match":
                identity["dob_match"],

            "identity_verified":
                identity["identity_verified"],

            "salary_math_valid":
                salary_valid,

            "calculated_net_salary":
                salary["calculated_net_salary"],
        },

        "affordability_check": {

            "verified_net_monthly_salary":
                verified_net_salary,

            "requested_loan_amount":
                loan_amount,

            "repayment_period_months":
                repayment_months,

            "calculated_monthly_emi":
                round(
                    estimated_monthly_repayment,
                    2
                ),

            "minimum_emi_percent": MIN_EMI_PERCENT,

            "maximum_emi_percent": MAX_EMI_PERCENT,

            "maximum_allowed_emi":
                round(
                    max_affordable_monthly_payment,
                    2
                ),

            "emi_percent_of_salary":
                round(
                    affordability_ratio,
                    2
                ),

            "affordability_status":
                affordability_status,

            "affordability_passed":
                affordability_passed,
        },
    }

    # -----------------------------------------------------
    # OUTPUT DATA
    # -----------------------------------------------------

    output_data = {

        "decision_output":
            decision_output,

        "confidence_score":
            confidence,

        "deterministic_reasoning":
            reasoning,

        "llm_reasoning":
            llm_reasoning,

        "reasoning":
            llm_reasoning,

        "validation_results": {

            "name_match":
                identity["name_match"],

            "dob_match":
                identity["dob_match"],

            "identity_verified":
                identity["identity_verified"],

            "salary_math_valid":
                salary_valid,
        },

        "affordability_results": {

            "requested_loan_amount":
                loan_amount,

            "verified_net_monthly_salary":
                verified_net_salary,

            "repayment_period_months":
                repayment_months,

            "calculated_monthly_emi":
                round(
                    estimated_monthly_repayment,
                    2
                ),

            "minimum_emi_percent": MIN_EMI_PERCENT,

            "maximum_emi_percent": MAX_EMI_PERCENT,

            "maximum_allowed_emi":
                round(
                    max_affordable_monthly_payment,
                    2
                ),

            "emi_percent_of_salary":
                round(
                    affordability_ratio,
                    2
                ),

            "affordability_status":
                affordability_status,

            "affordability_passed":
                affordability_passed,
        },

        "risk_factors": {

            "irreversibility":
                2
                if decision_output == "verified"
                else 6,

            "impact":
                3
                if decision_output == "verified"
                else 7,

            "explainability":
                10
                if decision_output == "verified"
                else 9,
        },
    }

    # -----------------------------------------------------
    # CHROMADB POLICY EVIDENCE
    # -----------------------------------------------------

    print(
        "\nRetrieving policy evidence "
        "from ChromaDB..."
    )

    query = """
    Verify a payslip for a loan application by checking employee identity against
    Aadhaar reference data, salary consistency, and loan affordability. Calculate
    monthly EMI from the loan amount, repayment tenure up to 60 months, and the
    configured interest rate, then check EMI as a percentage of verified net salary
    against the configured 30%-50% affordability range.
    """

    chroma_results = retrieve_policy(
        query=query,
        n_results=3
    )

    # -----------------------------------------------------
    # LLM REASONING
    # -----------------------------------------------------

    llm_facts = {
        "employee_name": payslip["employee_name"],
        "payslip_dob": payslip["dob"],
        "aadhaar_name": aadhaar_record["name"],
        "aadhaar_dob": aadhaar_record["dob"],
        "name_match": identity["name_match"],
        "dob_match": identity["dob_match"],
        "identity_verified": identity["identity_verified"],
        "gross_salary": payslip["gross_salary"],
        "total_deductions": payslip["total_deductions"],
        "stated_net_salary": payslip["net_salary"],
        "calculated_net_salary": salary["calculated_net_salary"],
        "salary_math_valid": salary_valid,
        "loan_amount": loan_amount,
        "repayment_months": repayment_months,
        "annual_interest_rate": ANNUAL_INTEREST_RATE,
        "monthly_emi": estimated_monthly_repayment,
        "emi_percent_of_salary": affordability_ratio,
        "minimum_emi_percent": MIN_EMI_PERCENT,
        "maximum_emi_percent": MAX_EMI_PERCENT,
        "affordability_status": affordability_status,
        "final_decision": decision_output,
    }

    print("\nGenerating LLM reasoning...")

    llm_reasoning = generate_llm_reasoning(
        llm_facts,
        chroma_results
    )

    print("\nLLM Reasoning:")
    print(f"  {llm_reasoning}")

    evidence_records = []

    for result in chroma_results:

        distance = result["distance"]

        relevance = 1 / (1 + distance)

        evidence_records.append(
            Evidence(
                evidence_id=str(uuid.uuid4()),
                execution_id=execution_id,
                source="Payslip ChromaDB",
                document_reference=result["source"],
                retrieval_score=round(
                    relevance,
                    4
                ),
                retrieval_distance=round(
                    distance,
                    4
                ),
            )
        )

    # -----------------------------------------------------
    # EXECUTION RECORD
    # -----------------------------------------------------

    end_time = now_iso()

    execution = ExecutionMetadata(

        execution_id=execution_id,

        orchestration_id=
            orchestration_id,

        agent_id="P001",

        input_data=input_data,

        output_data=output_data,

        model_id=
            f"rule-engine+{OPENAI_MODEL}",

        rule_id=
            "payslip_policy_v1",

        start_time=start_time,

        end_time=end_time,

        status="completed",

        sequence_number=1,
    )

    # -----------------------------------------------------
    # DECISION RECORD
    # -----------------------------------------------------

    decision = AgentDecision(

        decision_id=decision_id,

        execution_id=execution_id,

        decision_output=
            decision_output,

        confidence_score=
            confidence,

        reasoning=
            llm_reasoning,
    )

    # -----------------------------------------------------
    # ACCOUNTABILITY
    # -----------------------------------------------------

    if decision_output == "verified":

        impact = 3
        irreversibility = 2
        explainability = 10

    elif decision_output == "needs_review":

        impact = 7
        irreversibility = 5
        explainability = 8

    else:

        impact = 8
        irreversibility = 7
        explainability = 9

    composite = round(
        (
            impact
            + irreversibility
            + (10 - explainability)
        ) / 3,
        2
    )

    accountability = AccountabilityScore(

        score_id=str(uuid.uuid4()),

        execution_id=execution_id,

        impact_score=impact,

        irreversibility_score=
            irreversibility,

        explainability_score=
            explainability,

        composite_risk_score=
            composite,

        risk_level=
            risk_level_for(composite),

        review_required=
            decision_output != "verified",
    )

    # -----------------------------------------------------
    # PROVENANCE
    # -----------------------------------------------------

    provenance = ProvenanceRecordV2(

        record_id=record_id,

        orchestration_id=
            orchestration_id,

        execution_id=execution_id,

        event_type="agent_execution",

        input_data=input_data,

        output_data=output_data,

        previous_record_hash=None,
    )

    # -----------------------------------------------------
    # COMPLETE TRACECHAIN OUTPUT
    # -----------------------------------------------------

    records_for_display = {

        "AGENT_EXECUTIONS":
            execution,

        "AGENT_DECISIONS":
            decision,

        "EVIDENCE":
            evidence_records,

        "ACCOUNTABILITY_SCORES":
            accountability,

        "PROVENANCE_RECORDS":
            provenance,
    }

    print_execution_records(
        records_for_display
    )

    print(
        "\n" + "=" * 70
    )

    print(
        f"FINAL RESULT: "
        f"{decision_output.upper()}"
    )

    print(
        "=" * 70
    )


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    print("[VERSION] PAYSLIP-LLM-REASONING-REJECT-BELOW-30")

    try:

        account_id = select_account()

        run_single_test(
            account_id
        )

    except Exception as error:

        print("\nERROR:")
        print(error)
