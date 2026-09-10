"""
generate_payslip_results.py

Generates:
    payslip_execution_results_10.json

The JSON contains 10 account-level results in the same overall
structure as the user's Aadhaar execution JSON:

    user
    application
    execution
    decision
    evidence
    accountability
    provenance

Accounts:
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

This file is intended for SYNTHETIC TEST DATA only.
"""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


# =========================================================
# PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

GROUND_TRUTH_FILE = BASE_DIR / "ground_truth_realistic.json"
OUTPUT_FILE = BASE_DIR / "payslip_execution_results_10.json"


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
# SYNTHETIC PAYROLL DATA
# =========================================================

SALARY_DATA = {
    "100001": {
        "gross_salary": 62000,
        "basic_salary": 36000,
        "hra": 15000,
        "other_allowances": 11000,
        "provident_fund": 4320,
        "tax": 1800,
        "other_deductions": 880,
    },
    "100002": {
        "gross_salary": 74500,
        "basic_salary": 43000,
        "hra": 18000,
        "other_allowances": 13500,
        "provident_fund": 5160,
        "tax": 2400,
        "other_deductions": 1140,
    },
    "100003": {
        "gross_salary": 55800,
        "basic_salary": 32000,
        "hra": 14000,
        "other_allowances": 9800,
        "provident_fund": 3840,
        "tax": 1500,
        "other_deductions": 660,
    },
    "100004": {
        "gross_salary": 68100,
        "basic_salary": 39000,
        "hra": 16500,
        "other_allowances": 12600,
        "provident_fund": 4680,
        "tax": 2100,
        "other_deductions": 820,
    },
    "100005": {
        "gross_salary": 51200,
        "basic_salary": 30000,
        "hra": 12000,
        "other_allowances": 9200,
        "provident_fund": 3600,
        "tax": 1200,
        "other_deductions": 580,
    },
    "100006": {
        "gross_salary": 79500,
        "basic_salary": 46000,
        "hra": 19500,
        "other_allowances": 14000,
        "provident_fund": 5520,
        "tax": 2800,
        "other_deductions": 1180,
    },
    "100007": {
        "gross_salary": 60300,
        "basic_salary": 35000,
        "hra": 14500,
        "other_allowances": 10800,
        "provident_fund": 4200,
        "tax": 1700,
        "other_deductions": 760,
    },
    "100008": {
        "gross_salary": 48700,
        "basic_salary": 28500,
        "hra": 11500,
        "other_allowances": 8700,
        "provident_fund": 3420,
        "tax": 1000,
        "other_deductions": 530,
    },
    "100009": {
        "gross_salary": 73200,
        "basic_salary": 42000,
        "hra": 18000,
        "other_allowances": 13200,
        "provident_fund": 5040,
        "tax": 2200,
        "other_deductions": 980,
    },
    "100010": {
        "gross_salary": 64900,
        "basic_salary": 37500,
        "hra": 15500,
        "other_allowances": 11900,
        "provident_fund": 4500,
        "tax": 1900,
        "other_deductions": 780,
    },
}


# =========================================================
# EMPLOYER / DEPARTMENT
# =========================================================

EMPLOYERS = {
    "100001": "TraceChain Demo Analytics Pvt. Ltd.",
    "100002": "TraceChain Synthetic Finance Pvt. Ltd.",
    "100003": "TraceChain Testing Services Pvt. Ltd.",
    "100004": "TraceChain Demo Technologies Pvt. Ltd.",
    "100005": "TraceChain Validation Labs Pvt. Ltd.",
    "100006": "TraceChain Synthetic Systems Pvt. Ltd.",
    "100007": "TraceChain Demo Solutions Pvt. Ltd.",
    "100008": "TraceChain TestWorks Pvt. Ltd.",
    "100009": "TraceChain Verification Labs Pvt. Ltd.",
    "100010": "TraceChain Demo Operations Pvt. Ltd.",
}

DEPARTMENTS = {
    "100001": "Analytics",
    "100002": "Finance",
    "100003": "Operations",
    "100004": "Technology",
    "100005": "Validation",
    "100006": "Systems",
    "100007": "Solutions",
    "100008": "Testing",
    "100009": "Verification",
    "100010": "Operations",
}


# =========================================================
# EXECUTION SCENARIOS
# =========================================================
#
# These are deliberate synthetic test scenarios.
# =========================================================

EXECUTION_SCENARIOS = {
    "100001": "everything_correct",
    "100002": "income_overstated",
    "100003": "name_mismatch",
    "100004": "payslip_too_old",
    "100005": "everything_correct",
    "100006": "everything_correct",
    "100007": "income_overstated",
    "100008": "name_mismatch",
    "100009": "payslip_too_old",
    "100010": "everything_correct",
}


# =========================================================
# UTILITIES
# =========================================================

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def make_hash(value):
    payload = json.dumps(
        value,
        sort_keys=True,
        default=str
    ).encode("utf-8")

    return hashlib.sha256(payload).hexdigest()


# =========================================================
# DECISION
# =========================================================

def make_decision(
    scenario,
    net_salary
):
    if scenario == "everything_correct":
        return {
            "decision_output": "verified",
            "confidence_score": 0.95,
            "reasoning": (
                "The employee identity matches the Aadhaar reference, "
                "the payslip salary calculation is internally consistent, "
                "and the declared income matches the payslip-supported "
                "net salary."
            )
        }

    if scenario == "income_overstated":
        return {
            "decision_output": "rejected",
            "confidence_score": 0.97,
            "reasoning": (
                "The declared monthly income is higher than the income "
                f"supported by the payslip ({net_salary:.2f})."
            )
        }

    if scenario == "name_mismatch":
        return {
            "decision_output": "rejected",
            "confidence_score": 0.99,
            "reasoning": (
                "The applicant name does not match the employee identity "
                "expected from the Aadhaar reference."
            )
        }

    if scenario == "payslip_too_old":
        return {
            "decision_output": "rejected",
            "confidence_score": 0.96,
            "reasoning": (
                "The submitted payslip is outside the configured "
                "verification period."
            )
        }

    return {
        "decision_output": "manual_review",
        "confidence_score": 0.50,
        "reasoning": "Manual review is required."
    }


# =========================================================
# ACCOUNTABILITY
# =========================================================

def make_accountability(
    execution_id,
    scenario,
    decision_output
):
    if decision_output == "verified":
        impact = 3
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

    else:
        impact = 7
        irreversibility = 6
        explainability = 9

    composite = round(
        (
            impact
            + irreversibility
            + (10 - explainability)
        ) / 3,
        2
    )

    if composite >= 7:
        risk_level = "High"
    elif composite >= 4:
        risk_level = "Medium"
    else:
        risk_level = "Low"

    return {
        "score_id": str(uuid.uuid4()),
        "execution_id": execution_id,
        "impact_score": impact,
        "irreversibility_score": irreversibility,
        "explainability_score": explainability,
        "composite_risk_score": composite,
        "risk_level": risk_level,
        "review_required": (
            decision_output in {
                "rejected",
                "manual_review",
                "needs_review",
            }
        ),
        "scoring_model_version": "tracechain-scoring-v1",
        "calculated_at": now_iso(),
    }


# =========================================================
# EVIDENCE
# =========================================================

def make_evidence(
    execution_id,
    scenario
):
    if scenario == "income_overstated":
        policies = [
            (
                "income_verification_policy.md:3",
                0.6604
            ),
            (
                "payslip_validation_policy.md:5",
                0.5098
            )
        ]

    elif scenario == "name_mismatch":
        policies = [
            (
                "identity_verification_policy.md:4",
                0.7369
            ),
            (
                "payslip_validation_policy.md:5",
                0.5278
            )
        ]

    elif scenario == "payslip_too_old":
        policies = [
            (
                "payslip_validation_policy.md:3",
                0.6316
            ),
            (
                "income_verification_policy.md:2",
                0.5575
            )
        ]

    else:
        policies = [
            (
                "identity_verification_policy.md:1",
                0.6203
            ),
            (
                "income_verification_policy.md:2",
                0.5959
            ),
            (
                "payslip_validation_policy.md:1",
                0.5800
            )
        ]

    return [
        {
            "evidence_id": str(uuid.uuid4()),
            "execution_id": execution_id,
            "source": "Payslip ChromaDB",
            "document_reference": document_reference,
            "retrieval_score": retrieval_score,
            "timestamp": now_iso(),
        }
        for document_reference, retrieval_score in policies
    ]


# =========================================================
# BUILD ONE ACCOUNT RESULT
# =========================================================

def build_result(
    account_id,
    person,
    execution_number
):
    scenario = EXECUTION_SCENARIOS[account_id]
    salary = SALARY_DATA[account_id]

    gross = salary["gross_salary"]

    total_deductions = (
        salary["provident_fund"]
        + salary["tax"]
        + salary["other_deductions"]
    )

    net_salary = gross - total_deductions

    created_at = now_iso()

    execution_id = str(uuid.uuid4())
    application_id = f"APP-{account_id}"

    # Application-side test values.
    applicant_name = person["name"]
    declared_income = net_salary

    if scenario == "income_overstated":
        declared_income = net_salary + 10000

    elif scenario == "name_mismatch":
        applicant_name = "Different Applicant"

    # Input
    input_data = {
        "applicant_name": applicant_name,
        "account_id": account_id,
        "loan_amount": 150000.0,
        "payslip_file": ACCOUNT_PAYSLIP_MAP[account_id],
        "extracted": {
            "name": person["name"],
            "dob": person["dob"],
            "gender": person["gender"],
            "address": person["address"],
            "aadhaar_number": person["aadhaar_number"],
        },
        "payslip": {
            "employee_name": person["name"],
            "employer": EMPLOYERS[account_id],
            "department": DEPARTMENTS[account_id],
            "gross_salary": gross,
            "basic_salary": salary["basic_salary"],
            "hra": salary["hra"],
            "other_allowances": salary["other_allowances"],
            "total_deductions": total_deductions,
            "net_salary": net_salary,
            "pay_period": "01-Aug-2026 to 31-Aug-2026",
            "pay_date": "31-Aug-2026",
        },
        "declared_monthly_income": declared_income,
        "scenario": scenario,
    }

    # Decision
    decision_data = make_decision(
        scenario,
        net_salary
    )

    output_data = {
        "decision_output": decision_data["decision_output"],
        "confidence_score": decision_data["confidence_score"],
        "reasoning": decision_data["reasoning"],
    }

    # Hashes
    input_hash = make_hash(input_data)
    output_hash = make_hash(output_data)

    provenance_payload = {
        "input_hash": input_hash,
        "output_hash": output_hash,
        "previous_record_hash": None,
        "execution_id": execution_id,
    }

    record_hash = make_hash(
        provenance_payload
    )

    # Evidence and accountability
    evidence = make_evidence(
        execution_id,
        scenario
    )

    accountability = make_accountability(
        execution_id,
        scenario,
        decision_data["decision_output"]
    )

    # Finish time
    end_time = now_iso()

    return {
        "user": {
            "user_id": account_id,
            "created_at": created_at,
        },

        "application": {
            "application_id": application_id,
            "user_id": account_id,
            "loan_amount": 150000,
            "application_date": created_at,
            "status": "processing",
        },

        "execution": {
            "execution_id": execution_id,
            "orchestration_id": application_id,
            "agent_id": "P001",
            "input_data": input_data,
            "output_data": output_data,
            "model_id": "rule-based-payslip-agent",
            "rule_id": "payslip-verification-v2",
            "start_time": created_at,
            "end_time": end_time,
            "status": "completed",
            "sequence_number": 1,
            "input_hash": input_hash,
        },

        "decision": {
            "decision_id": str(uuid.uuid4()),
            "execution_id": execution_id,
            "decision_output": decision_data["decision_output"],
            "confidence_score": decision_data["confidence_score"],
            "reasoning": decision_data["reasoning"],
            "timestamp": end_time,
        },

        "evidence": evidence,

        "accountability": accountability,

        "provenance": {
            "record_id": str(uuid.uuid4()),
            "orchestration_id": application_id,
            "execution_id": execution_id,
            "event_type": "agent_decision",
            "input_data": input_data,
            "output_data": output_data,
            "previous_record_hash": None,
            "timestamp": end_time,
            "input_hash": input_hash,
            "output_hash": output_hash,
            "record_hash": record_hash,
        },
    }


# =========================================================
# MAIN
# =========================================================

def main():
    if not GROUND_TRUTH_FILE.exists():
        print("ERROR: ground_truth_realistic.json not found.")
        print(f"Expected location: {GROUND_TRUTH_FILE}")
        return

    with open(
        GROUND_TRUTH_FILE,
        "r",
        encoding="utf-8"
    ) as file:
        people = json.load(file)

    if len(people) < 10:
        print(
            "ERROR: ground_truth_realistic.json must "
            "contain at least 10 records."
        )
        return

    all_results = []

    print()
    print("=" * 70)
    print("GENERATING 10 PAYSLIP EXECUTION RESULTS")
    print("=" * 70)

    for execution_number, account_id in enumerate(
        ACCOUNT_PAYSLIP_MAP.keys(),
        start=1
    ):
        person = people[execution_number - 1]

        result = build_result(
            account_id,
            person,
            execution_number
        )

        all_results.append(result)

        scenario = EXECUTION_SCENARIOS[account_id]

        print(
            f"{execution_number:02d}. "
            f"{account_id} | "
            f"{person['name']} | "
            f"{scenario.replace('_', ' ').upper()} | "
            f"{result['decision']['decision_output']}"
        )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            all_results,
            file,
            indent=4,
            ensure_ascii=False
        )

    print()
    print("=" * 70)
    print("JSON FILE CREATED SUCCESSFULLY")
    print("=" * 70)
    print(f"File   : {OUTPUT_FILE}")
    print(f"Records: {len(all_results)}")
    print()
    print("Account mapping:")

    for account_id, payslip in ACCOUNT_PAYSLIP_MAP.items():
        print(
            f"  {account_id} -> {payslip}"
        )

    print()
    print("Process finished successfully.")


if __name__ == "__main__":
    main()
