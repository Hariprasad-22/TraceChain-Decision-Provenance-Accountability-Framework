"""
Test Payslip Execution Record with real ChromaDB retrieval.

This file:
    1. Creates a payslip verification execution
    2. Retrieves relevant policies from ChromaDB
    3. Creates AGENT_EXECUTIONS
    4. Creates AGENT_DECISIONS
    5. Creates EVIDENCE
    6. Creates ACCOUNTABILITY_SCORES
    7. Creates PROVENANCE_RECORDS
    8. Verifies the provenance hash

ChromaDB is used only for policy/evidence retrieval.
The execution-record classes remain in execution_record.py.
"""

import uuid
from datetime import datetime, timezone

from execution_record import (
    ExecutionMetadata,
    AgentDecision,
    Evidence,
    AccountabilityScore,
    ProvenanceRecordV2,
    risk_level_for,
    print_execution_records,
)

from chroma_retriever import retrieve_policy


# =========================================================
# UTILITY
# =========================================================

def now_iso():
    """Return current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


# =========================================================
# POLICY QUERIES FOR CHROMADB
# =========================================================

POLICY_QUERIES = {

    "everything_correct": """
    The payslip contains the required employee information,
    including employee name, employer name, pay period,
    salary information and deductions. The employee identity
    matches the applicant and the declared income is supported
    by the payslip.
    """,

    "income_overstated": """
    The applicant declared a monthly income higher than the
    income supported by the submitted payslip. The declared
    income does not match the verified income shown on the payslip.
    """,

    "missing_payslip": """
    The required payslip document is missing, therefore income
    verification cannot be completed.
    """,

    "name_mismatch": """
    The applicant name does not match the employee name shown
    on the submitted payslip. Identity verification should fail
    or require manual review.
    """,

    "payslip_too_old": """
    The submitted payslip is older than the permitted verification
    period. An outdated payslip should be flagged or rejected.
    """,
}


# =========================================================
# DECISION LOGIC
# =========================================================

def make_decision(scenario):
    """
    Create the decision for a payslip scenario.

    This keeps the current rule-based demo logic.
    ChromaDB provides the supporting policy evidence.
    """

    if scenario == "everything_correct":

        return {
            "decision_output": "verified",
            "confidence_score": 0.95,
            "reasoning": (
                "Employee information is consistent and the "
                "declared income is supported by the payslip."
            ),
        }

    elif scenario == "income_overstated":

        return {
            "decision_output": "rejected",
            "confidence_score": 0.97,
            "reasoning": (
                "Declared income is higher than the income "
                "supported by the payslip."
            ),
        }

    elif scenario == "missing_payslip":

        return {
            "decision_output": "rejected",
            "confidence_score": 0.98,
            "reasoning": (
                "The required payslip document is missing, "
                "so income verification cannot be completed."
            ),
        }

    elif scenario == "name_mismatch":

        return {
            "decision_output": "rejected",
            "confidence_score": 0.99,
            "reasoning": (
                "The applicant name does not match the employee "
                "name shown on the payslip."
            ),
        }

    elif scenario == "payslip_too_old":

        return {
            "decision_output": "rejected",
            "confidence_score": 0.96,
            "reasoning": (
                "The submitted payslip is older than the permitted "
                "verification period."
            ),
        }

    else:

        return {
            "decision_output": "manual_review",
            "confidence_score": 0.50,
            "reasoning": (
                "The scenario is not recognized and requires "
                "manual review."
            ),
        }


# =========================================================
# ACCOUNTABILITY SCORE
# =========================================================

def calculate_accountability(scenario, decision):
    """
    Calculate accountability/risk information.

    Scores are kept as simple demo values.
    """

    if scenario == "income_overstated":

        impact_score = 8
        irreversibility_score = 7
        explainability_score = 9

    elif scenario == "missing_payslip":

        impact_score = 7
        irreversibility_score = 6
        explainability_score = 9

    elif scenario == "name_mismatch":

        impact_score = 8
        irreversibility_score = 7
        explainability_score = 9

    elif scenario == "payslip_too_old":

        impact_score = 6
        irreversibility_score = 5
        explainability_score = 9

    else:

        impact_score = 2
        irreversibility_score = 2
        explainability_score = 9

    # Convert to 0-10 composite risk.
    #
    # Higher impact + higher irreversibility
    # increase risk.
    #
    # Higher explainability reduces risk.

    composite_score = (
        impact_score
        + irreversibility_score
        + (10 - explainability_score)
    ) / 3

    composite_score = round(composite_score, 2)

    risk_level = risk_level_for(composite_score)

    review_required = (
        decision["decision_output"]
        in ["rejected", "manual_review"]
    )

    return AccountabilityScore(
        score_id=str(uuid.uuid4()),
        execution_id="",
        impact_score=impact_score,
        irreversibility_score=irreversibility_score,
        explainability_score=explainability_score,
        composite_risk_score=composite_score,
        risk_level=risk_level,
        review_required=review_required,
    )


# =========================================================
# CREATE ONE PAYSLIP EXECUTION
# =========================================================

def create_payslip_execution(
    scenario,
    employee_name,
    declared_income,
    payslip_income,
):
    """
    Create complete TraceChain records for one payslip case.
    """

    # -----------------------------------------------------
    # IDs
    # -----------------------------------------------------

    execution_id = str(uuid.uuid4())
    orchestration_id = str(uuid.uuid4())

    decision_id = str(uuid.uuid4())
    record_id = str(uuid.uuid4())

    # -----------------------------------------------------
    # TIME
    # -----------------------------------------------------

    start_time = now_iso()

    # -----------------------------------------------------
    # INPUT DATA
    # -----------------------------------------------------

    input_data = {

        "employee_name": employee_name,

        "declared_monthly_income": declared_income,

        "payslip_monthly_income": payslip_income,

        "scenario": scenario,
    }

    # -----------------------------------------------------
    # DECISION
    # -----------------------------------------------------

    decision_data = make_decision(scenario)

    # -----------------------------------------------------
    # OUTPUT DATA
    # -----------------------------------------------------

    output_data = {

        "decision": decision_data["decision_output"],

        "confidence": decision_data["confidence_score"],

        "reasoning": decision_data["reasoning"],
    }

    # -----------------------------------------------------
    # CHROMADB RETRIEVAL
    # -----------------------------------------------------

    query = POLICY_QUERIES.get(
        scenario,

        """
        Verify the submitted payslip using the payslip,
        income verification and identity verification policies.
        """
    )

    retrieved_policies = retrieve_policy(
        query=query,
        n_results=2,
    )

    # -----------------------------------------------------
    # EVIDENCE RECORDS
    # -----------------------------------------------------

    evidence_records = []

    for policy in retrieved_policies:

        distance = policy["distance"]

        # This is a simple normalized relevance indicator.
        #
        # It is NOT an official ChromaDB similarity score.
        relevance_score = 1 / (1 + distance)

        evidence = Evidence(
            evidence_id=str(uuid.uuid4()),

            execution_id=execution_id,

            source="ChromaDB",

            document_reference=policy["source"],

            retrieval_score=round(
                relevance_score,
                4
            ),

            retrieval_distance=round(
                distance,
                4
            ),
        )

        evidence_records.append(evidence)

    # -----------------------------------------------------
    # EXECUTION METADATA
    # -----------------------------------------------------

    end_time = now_iso()

    execution = ExecutionMetadata(

        execution_id=execution_id,

        orchestration_id=orchestration_id,

        agent_id="payslip-income-verification-agent",

        input_data=input_data,

        output_data=output_data,

        model_id="rule-based-demo",

        rule_id="payslip-verification-v1",

        start_time=start_time,

        end_time=end_time,

        status="completed",

        sequence_number=1,
    )

    # -----------------------------------------------------
    # AGENT DECISION
    # -----------------------------------------------------

    decision = AgentDecision(

        decision_id=decision_id,

        execution_id=execution_id,

        decision_output=decision_data[
            "decision_output"
        ],

        confidence_score=decision_data[
            "confidence_score"
        ],

        reasoning=decision_data[
            "reasoning"
        ],
    )

    # -----------------------------------------------------
    # ACCOUNTABILITY SCORE
    # -----------------------------------------------------

    accountability = calculate_accountability(
        scenario,
        decision_data,
    )

    accountability.execution_id = execution_id

    # -----------------------------------------------------
    # PROVENANCE RECORD
    # -----------------------------------------------------

    provenance = ProvenanceRecordV2(

        record_id=record_id,

        orchestration_id=orchestration_id,

        execution_id=execution_id,

        event_type="PAYSLIP_VERIFICATION",

        input_data=input_data,

        output_data=output_data,

        previous_record_hash=None,
    )

    # -----------------------------------------------------
    # RETURN ALL RECORDS
    # -----------------------------------------------------

    return {

        "AGENT_EXECUTIONS": execution,

        "AGENT_DECISIONS": decision,

        "EVIDENCE": evidence_records,

        "ACCOUNTABILITY_SCORES": accountability,

        "PROVENANCE_RECORDS": provenance,
    }


# =========================================================
# TEST CASES
# =========================================================

TEST_CASES = [

    {
        "scenario": "everything_correct",
        "employee_name": "Rahul Sharma",
        "declared_income": 54000,
        "payslip_income": 54000,
    },

    {
        "scenario": "income_overstated",
        "employee_name": "Priya Reddy",
        "declared_income": 70000,
        "payslip_income": 54000,
    },

    {
        "scenario": "missing_payslip",
        "employee_name": "Arjun Kumar",
        "declared_income": 60000,
        "payslip_income": None,
    },

    {
        "scenario": "name_mismatch",
        "employee_name": "Nikhila Palla",
        "declared_income": 55000,
        "payslip_income": 55000,
    },

    {
        "scenario": "payslip_too_old",
        "employee_name": "Sneha Patel",
        "declared_income": 50000,
        "payslip_income": 50000,
    },

    {
        "scenario": "everything_correct",
        "employee_name": "Kiran Rao",
        "declared_income": 65000,
        "payslip_income": 65000,
    },

    {
        "scenario": "income_overstated",
        "employee_name": "Vikram Singh",
        "declared_income": 90000,
        "payslip_income": 70000,
    },

    {
        "scenario": "missing_payslip",
        "employee_name": "Anjali Mehta",
        "declared_income": 45000,
        "payslip_income": None,
    },

    {
        "scenario": "name_mismatch",
        "employee_name": "Rohit Verma",
        "declared_income": 58000,
        "payslip_income": 58000,
    },

    {
        "scenario": "payslip_too_old",
        "employee_name": "Divya Reddy",
        "declared_income": 62000,
        "payslip_income": 62000,
    },
]


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    print(
        "\n"
        "===================================================="
    )

    print(
        "       TRACECHAIN PAYSLIP VERIFICATION"
    )

    print(
        "       REAL CHROMADB POLICY RETRIEVAL"
    )

    print(
        "===================================================="
    )

    print(
        f"\nTotal test cases: {len(TEST_CASES)}"
    )

    for index, case in enumerate(
        TEST_CASES,
        start=1
    ):

        print(
            "\n\n"
            "####################################################"
        )

        print(
            f"                TEST CASE {index}"
        )

        print(
            "####################################################"
        )

        print(
            f"\nScenario: {case['scenario']}"
        )

        print(
            f"Employee: {case['employee_name']}"
        )

        print(
            f"Declared Income: "
            f"{case['declared_income']}"
        )

        print(
            f"Payslip Income: "
            f"{case['payslip_income']}"
        )

        # ---------------------------------------------
        # CREATE EXECUTION
        # ---------------------------------------------

        records = create_payslip_execution(

            scenario=case["scenario"],

            employee_name=case["employee_name"],

            declared_income=case["declared_income"],

            payslip_income=case["payslip_income"],
        )

        # ---------------------------------------------
        # PRINT RECORDS
        # ---------------------------------------------

        print_execution_records(records)

    print(
        "\n\n"
        "===================================================="
    )

    print(
        "              ALL TEST CASES COMPLETED"
    )

    print(
        "===================================================="
    )