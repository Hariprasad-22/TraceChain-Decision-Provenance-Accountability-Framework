"""
TRACECHAIN PAYSLIP VERIFICATION AGENT

10 synthetic accounts are mapped to 10 synthetic payslips.

Account mapping:
    100001 -> Udyati Seth
    100002 -> Dev Bhargava
    100003 -> Aachal Murty
    100004 -> Oni Bora
    100005 -> Raghav Sem
    100006 -> Brijesh Dhingra
    100007 -> Joshua Sule
    100008 -> Ikbal Barad
    100009 -> Simon Jani
    100010 -> Ganga Vig

The Aadhaar JSON file is used as the identity reference.
The payslip PDF is used as the payroll document.
ChromaDB supplies policy evidence.
TraceChain creates execution, decision, evidence,
accountability and provenance records.
"""

import json
import re
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
    verify_provenance_record,
)


# =========================================================
# PROJECT PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

AADHAAR_JSON = (
    BASE_DIR / "ground_truth_realistic.json"
)

PAYSLIP_DIR = (
    BASE_DIR / "payslips"
)


# =========================================================
# ACCOUNT -> PAYSLIP MAPPING
# =========================================================

ACCOUNT_PAYSLIP_MAP = {

    "100001":
        "payslip_01_Udyati_Seth.pdf",

    "100002":
        "payslip_02_Dev_Bhargava.pdf",

    "100003":
        "payslip_03_Aachal_Murty.pdf",

    "100004":
        "payslip_04_Oni_Bora.pdf",

    "100005":
        "payslip_05_Raghav_Sem.pdf",

    "100006":
        "payslip_06_Brijesh_Dhingra.pdf",

    "100007":
        "payslip_07_Joshua_Sule.pdf",

    "100008":
        "payslip_08_Ikbal_Barad.pdf",

    "100009":
        "payslip_09_Simon_Jani.pdf",

    "100010":
        "payslip_10_Ganga_Vig.pdf",
}


# =========================================================
# 10 EXECUTION SCENARIOS
# =========================================================
#
# These are TEST scenarios.
#
# The underlying PDFs remain synthetic and valid.
# The scenario determines what the verification agent
# should test for that execution.
#
# Execution 1 is intentionally "everything correct".
# =========================================================

EXECUTION_SCENARIOS = [

    "everything_correct",

    "income_overstated",

    "name_mismatch",

    "payslip_too_old",

    "everything_correct",

    "everything_correct",

    "income_overstated",

    "name_mismatch",

    "payslip_too_old",

    "everything_correct",
]


# =========================================================
# POLICY QUERIES
# =========================================================

POLICY_QUERIES = {

    "everything_correct": """
    The employee identity on the payslip matches the applicant
    identity, the payslip contains required employee information,
    the payslip is within the permitted verification period,
    and the declared monthly income matches the verified payslip
    income.
    """,

    "income_overstated": """
    The applicant declared a monthly income higher than the
    income supported by the submitted payslip. The declared
    income does not match the verified income shown on the payslip.
    """,

    "name_mismatch": """
    The applicant name does not match the employee name shown
    on the payslip. Identity verification should fail or require
    manual review.
    """,

    "payslip_too_old": """
    The submitted payslip is older than the permitted verification
    period. An outdated payslip should be flagged or rejected.
    """,

    "missing_payslip": """
    The required payslip document is missing and income verification
    cannot be completed.
    """,
}


# =========================================================
# TIMESTAMP
# =========================================================

def now_iso():

    return datetime.now(
        timezone.utc
    ).isoformat()


# =========================================================
# LOAD AADHAAR REFERENCE DATA
# =========================================================

def load_aadhaar_records():

    if not AADHAAR_JSON.exists():

        raise FileNotFoundError(
            f"Aadhaar JSON file not found:\n"
            f"{AADHAAR_JSON}"
        )

    with open(
        AADHAAR_JSON,
        "r",
        encoding="utf-8"
    ) as file:

        records = json.load(file)

    return records


# =========================================================
# CREATE ACCOUNT LOOKUP
# =========================================================

def build_account_lookup():

    records = load_aadhaar_records()

    lookup = {}

    for index, record in enumerate(
        records,
        start=1
    ):

        account_id = f"{100000 + index}"

        lookup[account_id] = record

    return lookup


# =========================================================
# READ PDF TEXT
# =========================================================

def extract_pdf_text(pdf_path):

    reader = PdfReader(
        str(pdf_path)
    )

    pages = []

    for page in reader.pages:

        text = page.extract_text()

        if text:
            pages.append(text)

    return "\n".join(pages)


# =========================================================
# EXTRACT FIELD FROM PDF
# =========================================================

def extract_field(
    text,
    label,
    next_labels
):
    """
    Extract a text value after a label.

    Example:

        Employee Name
        Udyati Seth
    """

    escaped_label = re.escape(label)

    next_part = "|".join(
        re.escape(item)
        for item in next_labels
    )

    pattern = (
        escaped_label
        + r"\s*[:\-]?\s*"
        + r"(.+?)(?=\s*(?:"
        + next_part
        + r")\s*[:\-]?|\n|$)"
    )

    match = re.search(
        pattern,
        text,
        flags=re.IGNORECASE
    )

    if match:

        value = match.group(1).strip()

        value = re.sub(
            r"\s+",
            " ",
            value
        )

        return value

    return None


# =========================================================
# EXTRACT MONETARY VALUE
# =========================================================

def extract_money(
    text,
    label
):

    pattern = (
        re.escape(label)
        + r"\s*[:\-]?\s*"
        + r"(?:₹\s*)?"
        + r"([\d,]+(?:\.\d+)?)"
    )

    match = re.search(
        pattern,
        text,
        flags=re.IGNORECASE
    )

    if not match:
        return None

    value = match.group(1)

    value = value.replace(
        ",",
        ""
    )

    return float(value)


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
        "Employee Name",
        [
            "Gender",
            "Date of Birth",
            "Aadhaar Ref."
        ]
    )

    gender = extract_field(
        text,
        "Gender",
        [
            "Date of Birth",
            "Aadhaar Ref.",
            "Employee ID"
        ]
    )

    dob = extract_field(
        text,
        "Date of Birth",
        [
            "Aadhaar Ref.",
            "Employee ID"
        ]
    )

    employee_id = extract_field(
        text,
        "Employee ID",
        [
            "Department"
        ]
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

        "employee_name":
            employee_name,

        "gender":
            gender,

        "dob":
            dob,

        "employee_id":
            employee_id,

        "gross_salary":
            gross_salary,

        "total_deductions":
            total_deductions,

        "net_salary":
            net_salary,

        "raw_text":
            text,
    }


# =========================================================
# NUMERIC COMPARISON
# =========================================================

def same_money(
    first,
    second
):

    if first is None or second is None:
        return False

    return abs(
        float(first)
        - float(second)
    ) < 0.01


# =========================================================
# PAYSLIP ↔ AADHAAR IDENTITY CHECK
# =========================================================

def verify_identity(
    aadhaar_record,
    payslip_data
):

    aadhaar_name = (
        aadhaar_record["name"]
    )

    payslip_name = (
        payslip_data["employee_name"]
    )

    aadhaar_dob = (
        aadhaar_record["dob"]
    )

    payslip_dob = (
        payslip_data["dob"]
    )

    name_match = (
        aadhaar_name.strip().lower()
        ==
        payslip_name.strip().lower()
        if payslip_name
        else False
    )

    dob_match = (
        aadhaar_dob
        ==
        payslip_dob
        if payslip_dob
        else False
    )

    return {

        "name_match":
            name_match,

        "dob_match":
            dob_match,

        "identity_verified":
            name_match and dob_match,
    }


# =========================================================
# SALARY MATHEMATICAL CHECK
# =========================================================

def verify_salary_math(
    payslip_data
):

    gross = payslip_data[
        "gross_salary"
    ]

    deductions = payslip_data[
        "total_deductions"
    ]

    net = payslip_data[
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
# GET SCENARIO DECISION
# =========================================================

def create_decision(
    scenario,
    aadhaar_record,
    payslip_data,
    declared_income,
):
    """
    Generate the decision.

    The scenarios intentionally demonstrate the
    expected TraceChain outputs.
    """

    identity = verify_identity(
        aadhaar_record,
        payslip_data
    )

    salary_math_valid = (
        verify_salary_math(
            payslip_data
        )
    )

    payslip_income = (
        payslip_data["net_salary"]
    )

    # -----------------------------------------------------
    # EVERYTHING CORRECT
    # -----------------------------------------------------

    if scenario == "everything_correct":

        income_valid = same_money(
            declared_income,
            payslip_income
        )

        if (
            identity["identity_verified"]
            and salary_math_valid
            and income_valid
        ):

            return {

                "decision":
                    "verified",

                "confidence":
                    0.95,

                "reasoning":
                    (
                        "The Aadhaar reference matches the "
                        "employee identity on the payslip, "
                        "the salary calculation is consistent, "
                        "and the declared income matches the "
                        "payslip-supported net income."
                    ),
            }

        return {

            "decision":
                "manual_review",

            "confidence":
                0.70,

            "reasoning":
                (
                    "One or more verification fields "
                    "could not be confirmed automatically."
                ),
        }

    # -----------------------------------------------------
    # INCOME OVERSTATED
    # -----------------------------------------------------

    if scenario == "income_overstated":

        return {

            "decision":
                "rejected",

            "confidence":
                0.97,

            "reasoning":
                (
                    f"Declared income of "
                    f"₹{declared_income:,.2f} is higher "
                    f"than the payslip-supported income "
                    f"of ₹{payslip_income:,.2f}."
                ),
        }

    # -----------------------------------------------------
    # NAME MISMATCH
    # -----------------------------------------------------

    if scenario == "name_mismatch":

        return {

            "decision":
                "rejected",

            "confidence":
                0.99,

            "reasoning":
                (
                    "The applicant identity does not match "
                    "the employee identity expected from "
                    "the Aadhaar reference."
                ),
        }

    # -----------------------------------------------------
    # OLD PAYSLIP
    # -----------------------------------------------------

    if scenario == "payslip_too_old":

        return {

            "decision":
                "rejected",

            "confidence":
                0.96,

            "reasoning":
                (
                    "The payslip is marked for an "
                    "outdated verification-period test."
                ),
        }

    # -----------------------------------------------------
    # MISSING PAYSLIP
    # -----------------------------------------------------

    if scenario == "missing_payslip":

        return {

            "decision":
                "rejected",

            "confidence":
                0.98,

            "reasoning":
                (
                    "The required payslip document "
                    "is missing."
                ),
        }

    # -----------------------------------------------------
    # FALLBACK
    # -----------------------------------------------------

    return {

        "decision":
            "manual_review",

        "confidence":
            0.50,

        "reasoning":
            "Manual review is required.",
    }


# =========================================================
# ACCOUNTABILITY
# =========================================================

def calculate_accountability(
    execution_id,
    scenario,
    decision
):

    if decision == "verified":

        impact = 2
        irreversibility = 2
        explainability = 9

    elif scenario == "income_overstated":

        impact = 8
        irreversibility = 7
        explainability = 9

    elif scenario == "name_mismatch":

        impact = 8
        irreversibility = 7
        explainability = 9

    elif scenario == "payslip_too_old":

        impact = 6
        irreversibility = 5
        explainability = 9

    elif scenario == "missing_payslip":

        impact = 7
        irreversibility = 6
        explainability = 9

    else:

        impact = 5
        irreversibility = 4
        explainability = 8

    composite = (
        impact
        + irreversibility
        + (10 - explainability)
    ) / 3

    composite = round(
        composite,
        2
    )

    return AccountabilityScore(

        score_id=str(
            uuid.uuid4()
        ),

        execution_id=execution_id,

        impact_score=impact,

        irreversibility_score=irreversibility,

        explainability_score=explainability,

        composite_risk_score=composite,

        risk_level=risk_level_for(
            composite
        ),

        review_required=(
            decision
            in [
                "rejected",
                "manual_review"
            ]
        ),
    )


# =========================================================
# CHROMADB EVIDENCE
# =========================================================

def retrieve_evidence(
    scenario,
    execution_id
):

    query = POLICY_QUERIES[
        scenario
    ]

    results = retrieve_policy(
        query=query,
        n_results=3
    )

    evidence_records = []

    for result in results:

        distance = result[
            "distance"
        ]

        # Lower ChromaDB distance means
        # a closer semantic match.

        relevance_score = (
            1 / (1 + distance)
        )

        evidence = Evidence(

            evidence_id=str(
                uuid.uuid4()
            ),

            execution_id=(
                execution_id
            ),

            source="Payslip ChromaDB",

            document_reference=(
                result["source"]
            ),

            retrieval_score=round(
                relevance_score,
                4
            ),

            retrieval_distance=round(
                distance,
                4
            ),
        )

        evidence_records.append(
            evidence
        )

    return evidence_records


# =========================================================
# BUILD TRACECHAIN RECORDS
# =========================================================

def build_execution(
    account_id,
    aadhaar_record,
    payslip_path,
    scenario,
):
    """
    Run one complete execution.
    """

    execution_id = str(
        uuid.uuid4()
    )

    orchestration_id = str(
        uuid.uuid4()
    )

    start_time = now_iso()

    # -----------------------------------------------------
    # Parse payslip
    # -----------------------------------------------------

    payslip_data = parse_payslip(
        payslip_path
    )

    # -----------------------------------------------------
    # Determine declared income
    # -----------------------------------------------------
    #
    # For the first/everything-correct case,
    # declared income equals payslip net salary.
    #
    # For test scenarios we intentionally modify the
    # declared application value.
    # -----------------------------------------------------

    payslip_net = (
        payslip_data[
            "net_salary"
        ]
    )

    if scenario == "income_overstated":

        declared_income = (
            payslip_net + 10000
            if payslip_net is not None
            else 0
        )

    else:

        declared_income = payslip_net

    # -----------------------------------------------------
    # Name used by application
    # -----------------------------------------------------

    applicant_name = (
        aadhaar_record["name"]
    )

    if scenario == "name_mismatch":

        applicant_name = (
            "Different Applicant"
        )

    # -----------------------------------------------------
    # Identity reference
    # -----------------------------------------------------

    identity_result = verify_identity(
        aadhaar_record,
        payslip_data
    )

    # -----------------------------------------------------
    # Decision
    # -----------------------------------------------------

    decision_data = create_decision(

        scenario=scenario,

        aadhaar_record=aadhaar_record,

        payslip_data=payslip_data,

        declared_income=declared_income,
    )

    # -----------------------------------------------------
    # Input data
    # -----------------------------------------------------

    input_data = {

        "account_id":
            account_id,

        "applicant_name":
            applicant_name,

        "declared_monthly_income":
            declared_income,

        "aadhaar_reference":
            {
                "name":
                    aadhaar_record["name"],

                "dob":
                    aadhaar_record["dob"],

                "gender":
                    aadhaar_record["gender"],

                "address":
                    aadhaar_record["address"],
            },

        "payslip_file":
            payslip_path.name,

        "extracted_payslip":
            {
                "employee_name":
                    payslip_data[
                        "employee_name"
                    ],

                "dob":
                    payslip_data["dob"],

                "gross_salary":
                    payslip_data[
                        "gross_salary"
                    ],

                "total_deductions":
                    payslip_data[
                        "total_deductions"
                    ],

                "net_salary":
                    payslip_data[
                        "net_salary"
                    ],

                "employee_id":
                    payslip_data[
                        "employee_id"
                    ],
            },

        "identity_check":
            identity_result,

        "scenario":
            scenario,
    }

    # -----------------------------------------------------
    # Output data
    # -----------------------------------------------------

    output_data = {

        "decision_output":
            decision_data["decision"],

        "confidence_score":
            decision_data["confidence"],

        "reasoning":
            decision_data["reasoning"],
    }

    # -----------------------------------------------------
    # ChromaDB
    # -----------------------------------------------------

    evidence_records = retrieve_evidence(

        scenario=scenario,

        execution_id=execution_id,
    )

    # -----------------------------------------------------
    # Execution metadata
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

        model_id="rule-based-payslip-agent",

        rule_id="payslip-verification-v2",

        start_time=start_time,

        end_time=end_time,

        status="completed",

        sequence_number=1,
    )

    # -----------------------------------------------------
    # Agent decision
    # -----------------------------------------------------

    decision = AgentDecision(

        decision_id=str(
            uuid.uuid4()
        ),

        execution_id=execution_id,

        decision_output=(
            decision_data["decision"]
        ),

        confidence_score=(
            decision_data["confidence"]
        ),

        reasoning=(
            decision_data["reasoning"]
        ),
    )

    # -----------------------------------------------------
    # Accountability
    # -----------------------------------------------------

    accountability = (
        calculate_accountability(

            execution_id=execution_id,

            scenario=scenario,

            decision=(
                decision_data["decision"]
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

        execution_id=(
            execution_id
        ),

        event_type="agent_decision",

        input_data=input_data,

        output_data=output_data,

        previous_record_hash=None,
    )

    return {

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


# =========================================================
# PRINT EXECUTION
# =========================================================

def print_execution(
    execution_number,
    scenario,
    account_id,
    aadhaar_record,
    payslip_path,
    records,
):
    """
    Print output in the requested format.
    """

    execution = records[
        "AGENT_EXECUTIONS"
    ]

    decision = records[
        "AGENT_DECISIONS"
    ]

    evidence = records[
        "EVIDENCE"
    ]

    accountability = records[
        "ACCOUNTABILITY_SCORES"
    ]

    provenance = records[
        "PROVENANCE_RECORDS"
    ]

    title = scenario.replace(
        "_",
        " "
    ).upper()

    print("\n")
    print("=" * 70)

    print(
        f"EXECUTION {execution_number} - {title}"
    )

    print("=" * 70)

    print(
        f"\nAccount ID          : {account_id}"
    )

    print(
        f"Aadhaar Name       : "
        f"{aadhaar_record['name']}"
    )

    print(
        f"Payslip File       : "
        f"{payslip_path.name}"
    )

    print(
        "\n=== AGENT_EXECUTIONS ==="
    )

    for key, value in execution.__dict__.items():

        print(
            f"  {key}: {value}"
        )

    print(
        "\n=== AGENT_DECISIONS ==="
    )

    for key, value in decision.__dict__.items():

        print(
            f"  {key}: {value}"
        )

    print(
        "\n=== EVIDENCE ==="
    )

    for item in evidence:

        print(
            " ",
            item.__dict__
        )

    print(
        "\n=== ACCOUNTABILITY_SCORES ==="
    )

    for key, value in accountability.__dict__.items():

        print(
            f"  {key}: {value}"
        )

    print(
        "\n=== PROVENANCE_RECORDS ==="
    )

    for key, value in provenance.__dict__.items():

        print(
            f"  {key}: {value}"
        )

    verified = (
        verify_provenance_record(
            provenance
        )
    )

    print(
        "\n[tamper-check] "
        "recomputed hash chain matches "
        f"stored record: {verified}"
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "\n"
        "============================================================"
    )

    print(
        "          TRACECHAIN PAYSLIP VERIFICATION AGENT"
    )

    print(
        "          10 ACCOUNTS + 10 SYNTHETIC PAYSLIPS"
    )

    print(
        "============================================================"
    )

    # -----------------------------------------------------
    # Validate folders/files
    # -----------------------------------------------------

    if not PAYSLIP_DIR.exists():

        print(
            f"\nERROR: Payslip folder not found:\n"
            f"{PAYSLIP_DIR}"
        )

        return

    try:

        account_lookup = (
            build_account_lookup()
        )

    except Exception as error:

        print(
            "\nERROR loading Aadhaar JSON:"
        )

        print(error)

        return

    # -----------------------------------------------------
    # Run all 10 executions
    # -----------------------------------------------------

    for index, account_id in enumerate(
        ACCOUNT_PAYSLIP_MAP.keys(),
        start=1
    ):

        scenario = (
            EXECUTION_SCENARIOS[
                index - 1
            ]
        )

        payslip_filename = (
            ACCOUNT_PAYSLIP_MAP[
                account_id
            ]
        )

        payslip_path = (
            PAYSLIP_DIR
            / payslip_filename
        )

        aadhaar_record = (
            account_lookup.get(
                account_id
            )
        )

        if aadhaar_record is None:

            print(
                f"\nERROR: No Aadhaar record "
                f"for account {account_id}"
            )

            continue

        if not payslip_path.exists():

            print(
                f"\nERROR: Payslip not found:\n"
                f"{payslip_path}"
            )

            continue

        print(
            f"\nRunning execution "
            f"{index} on {payslip_filename} "
            f"(account: {account_id}) ..."
        )

        try:

            records = build_execution(

                account_id=account_id,

                aadhaar_record=aadhaar_record,

                payslip_path=payslip_path,

                scenario=scenario,
            )

            print_execution(

                execution_number=index,

                scenario=scenario,

                account_id=account_id,

                aadhaar_record=aadhaar_record,

                payslip_path=payslip_path,

                records=records,
            )

        except Exception as error:

            print(
                f"\nERROR in execution {index}:"
            )

            print(
                error
            )

    # -----------------------------------------------------
    # Finished
    # -----------------------------------------------------

    print(
        "\n\n"
        "============================================================"
    )

    print(
        "                 ALL 10 EXECUTIONS COMPLETED"
    )

    print(
        "============================================================"
    )


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":
    main()