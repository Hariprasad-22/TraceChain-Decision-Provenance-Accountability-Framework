import json
import uuid
import hashlib
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
    verify_provenance_record,
    print_execution_records,
)


# =========================================================
# PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

GROUND_TRUTH_FILE = BASE_DIR / "ground_truth_realistic.json"
PAYSLIP_DIR = BASE_DIR / "payslips"


# =========================================================
# ACCOUNT MAPPING
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

def now_iso():
    return datetime.now(timezone.utc).isoformat()


# =========================================================
# HASH
# =========================================================

def make_hash(data):
    text = json.dumps(
        data,
        sort_keys=True,
        default=str
    )

    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


# =========================================================
# LOAD AADHAAR DATA
# =========================================================

def load_records():

    if not GROUND_TRUTH_FILE.exists():
        raise FileNotFoundError(
            f"File not found:\n{GROUND_TRUTH_FILE}"
        )

    with open(
        GROUND_TRUTH_FILE,
        "r",
        encoding="utf-8"
    ) as f:
        return json.load(f)


# =========================================================
# EXTRACT PDF TEXT
# =========================================================

def extract_pdf_text(pdf_path):

    reader = PdfReader(
        str(pdf_path)
    )

    all_text = []

    for page in reader.pages:
        text = page.extract_text()

        if text:
            all_text.append(text)

    return "\n".join(all_text)


# =========================================================
# EXTRACT FIELD
# =========================================================

def extract_field(
    text,
    label
):
    """
    Simple line-based field extraction.
    """

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    for i, line in enumerate(lines):

        if line.lower().startswith(
            label.lower()
        ):

            # Format:
            # Employee Name: Udyati Seth

            if ":" in line:

                value = line.split(
                    ":",
                    1
                )[1].strip()

                if value:
                    return value

            # Format:
            # Employee Name
            # Udyati Seth

            if i + 1 < len(lines):
                return lines[i + 1].strip()

    return None


# =========================================================
# EXTRACT MONEY
# =========================================================

def extract_money(
    text,
    label
):
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
        match.group(1).replace(
            ",",
            ""
        )
    )


# =========================================================
# PARSE PAYSLIP
# =========================================================

def parse_payslip(
    pdf_path
):

    text = extract_pdf_text(
        pdf_path
    )

    employee_name = extract_field(
        text,
        "Employee Name"
    )

    dob = extract_field(
        text,
        "Date of Birth"
    )

    employee_id = extract_field(
        text,
        "Employee ID"
    )

    gross_salary = extract_money(
        text,
        "Gross Salary"
    )

    total_deductions = extract_money(
        text,
        "Total Deductions"
    )

    net_salary = extract_money(
        text,
        "NET SALARY PAYABLE"
    )

    return {
        "employee_name": employee_name,
        "dob": dob,
        "employee_id": employee_id,
        "gross_salary": gross_salary,
        "total_deductions": total_deductions,
        "net_salary": net_salary,
        "raw_text": text,
    }


# =========================================================
# VERIFY IDENTITY
# =========================================================

def verify_identity(
    aadhaar_record,
    payslip
):

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

    aadhaar_dob = (
        aadhaar_record["dob"]
    )

    payslip_dob = (
        payslip["dob"]
    )

    name_match = (
        aadhaar_name
        == payslip_name
    )

    dob_match = (
        aadhaar_dob
        == payslip_dob
    )

    return {
        "name_match": name_match,
        "dob_match": dob_match,
        "identity_verified": (
            name_match
            and dob_match
        ),
    }


# =========================================================
# VERIFY SALARY
# =========================================================

def verify_salary(
    payslip
):

    gross = payslip[
        "gross_salary"
    ]

    deductions = payslip[
        "total_deductions"
    ]

    net = payslip[
        "net_salary"
    ]

    if (
        gross is None
        or deductions is None
        or net is None
    ):
        return False

    calculated_net = (
        gross - deductions
    )

    return abs(
        calculated_net - net
    ) < 0.01


# =========================================================
# GET ACCOUNT ID
# =========================================================

def select_account():

    print("\nAvailable accounts:\n")

    for account_id, filename in (
        ACCOUNT_PAYSLIP_MAP.items()
    ):
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
# SINGLE EXECUTION
# =========================================================

def run_single_test(
    account_id
):

    records = load_records()

    account_index = (
        int(account_id) - 100001
    )

    aadhaar_record = records[
        account_index
    ]

    payslip_path = (
        PAYSLIP_DIR
        / ACCOUNT_PAYSLIP_MAP[
            account_id
        ]
    )

    if not payslip_path.exists():
        raise FileNotFoundError(
            f"Payslip not found:\n"
            f"{payslip_path}"
        )

    print("\n")
    print("=" * 70)
    print(
        "SINGLE PAYSLIP VERIFICATION"
    )
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
    # Parse PDF
    # -----------------------------------------------------

    print(
        "\nReading payslip..."
    )

    payslip = parse_payslip(
        payslip_path
    )

    print(
        "\nExtracted Payslip Data:"
    )

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

    # -----------------------------------------------------
    # Identity verification
    # -----------------------------------------------------

    identity = verify_identity(
        aadhaar_record,
        payslip
    )

    # -----------------------------------------------------
    # Salary verification
    # -----------------------------------------------------

    salary_valid = verify_salary(
        payslip
    )

    # -----------------------------------------------------
    # Income
    # -----------------------------------------------------

    declared_income = (
        payslip["net_salary"]
    )

    # -----------------------------------------------------
    # Decision
    # -----------------------------------------------------

    if (
        identity["identity_verified"]
        and salary_valid
    ):

        decision_output = "verified"
        confidence = 0.95

        reasoning = (
            "The employee identity matches the Aadhaar "
            "reference, the date of birth matches, and "
            "the payslip salary calculation is internally "
            "consistent."
        )

    elif not identity["identity_verified"]:

        decision_output = "rejected"
        confidence = 0.99

        reasoning = (
            "The payslip identity does not match the "
            "Aadhaar reference."
        )

    else:

        decision_output = "needs_review"
        confidence = 0.70

        reasoning = (
            "The payslip salary components are not "
            "mathematically consistent."
        )

    # -----------------------------------------------------
    # IDs
    # -----------------------------------------------------

    execution_id = str(
        uuid.uuid4()
    )

    orchestration_id = (
        f"APP-{account_id}"
    )

    start_time = now_iso()

    # -----------------------------------------------------
    # Input data
    # -----------------------------------------------------

    input_data = {

        "applicant_name":
            aadhaar_record["name"],

        "loan_amount":
            150000.0,

        "account_id":
            account_id,

        "payslip_file":
            payslip_path.name,

        "extracted":
            {
                "name":
                    payslip[
                        "employee_name"
                    ],

                "dob":
                    payslip["dob"],

                "employee_id":
                    payslip[
                        "employee_id"
                    ],

                "gross_salary":
                    payslip[
                        "gross_salary"
                    ],

                "total_deductions":
                    payslip[
                        "total_deductions"
                    ],

                "net_salary":
                    payslip[
                        "net_salary"
                    ],
            },

        "identity_check":
            identity,

        "salary_check":
            salary_valid,
    }

    output_data = {

        "decision_output":
            decision_output,

        "confidence_score":
            confidence,

        "reasoning":
            reasoning,
    }

    # -----------------------------------------------------
    # ChromaDB
    # -----------------------------------------------------

    print(
        "\nRetrieving policy evidence "
        "from ChromaDB..."
    )

    query = """
    Verify a payslip by checking employee identity,
    date of birth, required payslip information and
    mathematical salary consistency.
    """

    chroma_results = retrieve_policy(
        query=query,
        n_results=3
    )

    evidence_records = []

    for result in chroma_results:

        distance = result[
            "distance"
        ]

        relevance = (
            1 / (1 + distance)
        )

        evidence_records.append(

            Evidence(

                evidence_id=str(
                    uuid.uuid4()
                ),

                execution_id=(
                    execution_id
                ),

                source=(
                    "Payslip ChromaDB"
                ),

                document_reference=(
                    result["source"]
                ),

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
    # Execution
    # -----------------------------------------------------

    end_time = now_iso()

    execution = ExecutionMetadata(

        execution_id=execution_id,

        orchestration_id=(
            orchestration_id
        ),

        agent_id="P001",

        input_data=input_data,

        output_data=output_data,

        model_id=(
            "rule-based-payslip-agent"
        ),

        rule_id=(
            "payslip-verification-v2"
        ),

        start_time=start_time,

        end_time=end_time,

        status="completed",

        sequence_number=1,
    )

    # -----------------------------------------------------
    # Decision
    # -----------------------------------------------------

    decision = AgentDecision(

        decision_id=str(
            uuid.uuid4()
        ),

        execution_id=execution_id,

        decision_output=(
            decision_output
        ),

        confidence_score=confidence,

        reasoning=reasoning,
    )

    # -----------------------------------------------------
    # Accountability
    # -----------------------------------------------------

    if decision_output == "verified":

        impact = 3
        irreversibility = 2
        explainability = 9

    else:

        impact = 8
        irreversibility = 7
        explainability = 8

    composite = round(
        (
            impact
            + irreversibility
            + (10 - explainability)
        ) / 3,
        2
    )

    accountability = (
        AccountabilityScore(

            score_id=str(
                uuid.uuid4()
            ),

            execution_id=execution_id,

            impact_score=impact,

            irreversibility_score=(
                irreversibility
            ),

            explainability_score=(
                explainability
            ),

            composite_risk_score=(
                composite
            ),

            risk_level=risk_level_for(
                composite
            ),

            review_required=(
                decision_output
                != "verified"
            ),
        )
    )

    # -----------------------------------------------------
    # Provenance
    # -----------------------------------------------------

    provenance = ProvenanceRecordV2(

        record_id=str(
            uuid.uuid4()
        ),

        orchestration_id=(
            orchestration_id
        ),

        execution_id=execution_id,

        event_type="agent_decision",

        input_data=input_data,

        output_data=output_data,

        previous_record_hash=None,
    )

    # -----------------------------------------------------
    # BUILD COMPLETE EXECUTION RECORD
    # -----------------------------------------------------

    records = {
        "AGENT_EXECUTIONS": execution,
        "AGENT_DECISIONS": decision,
        "EVIDENCE": evidence_records,
        "ACCOUNTABILITY_SCORES": accountability,
        "PROVENANCE_RECORDS": provenance,
    }

    # Use the SAME formatter as test_execution_record.py.
    # This prints all execution-record fields instead of
    # only the short verification summary.
    print_execution_records(records)

    # Verify and display the provenance tamper check.
    tamper_check = verify_provenance_record(provenance)

    print(
        "\n[tamper-check] recomputed hash chain matches "
        f"stored record: {tamper_check}"
    )

    print("\n" + "=" * 70)
    print(
        f"FINAL RESULT: {decision_output.upper()}"
    )
    print("=" * 70)


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    try:

        account_id = select_account()

        run_single_test(
            account_id
        )

    except Exception as error:

        print(
            "\nERROR:"
        )

        print(
            error
        )
