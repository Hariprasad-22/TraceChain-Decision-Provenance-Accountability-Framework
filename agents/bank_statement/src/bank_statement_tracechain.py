import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


INPUT_FILE = Path(
    r"data\processed\bank_statement_agent_decisions.csv"
)

OUTPUT_FILE = Path(
    r"data\processed\bank_statement_tracechain_output.json"
)


# ============================================================
# HASH UTILITY
# ============================================================

def calculate_hash(payload):
    """
    Generate deterministic SHA-256 hash.
    """
    serialized = json.dumps(
        payload,
        sort_keys=True,
        default=str
    ).encode("utf-8")

    return hashlib.sha256(serialized).hexdigest()


# ============================================================
# PROVENANCE VERIFICATION
# ============================================================

def verify_provenance_record(record):
    """
    Verify that the stored hashes still match
    the original provenance contents.
    """

    input_hash = calculate_hash(
        record["input_data"]
    )

    output_hash = calculate_hash(
        record["output_data"]
    )

    if input_hash != record["input_hash"]:
        return False

    if output_hash != record["output_hash"]:
        return False

    chain_payload = {
        "record_id": record["record_id"],
        "orchestration_id": record["orchestration_id"],
        "execution_id": record["execution_id"],
        "event_type": record["event_type"],
        "timestamp": record["timestamp"],
        "input_hash": record["input_hash"],
        "output_hash": record["output_hash"],
        "previous_record_hash": record[
            "previous_record_hash"
        ],
    }

    expected_record_hash = calculate_hash(
        chain_payload
    )

    return (
        expected_record_hash
        == record["record_hash"]
    )


# ============================================================
# RISK LEVEL
# ============================================================

def risk_level_for(score):
    if score >= 7:
        return "High"

    if score >= 4:
        return "Medium"

    return "Low"


# ============================================================
# MAIN
# ============================================================

print("========== TRACECHAIN OUTPUT BUILDER ==========")


# ------------------------------------------------------------
# 1. Load Step 17 output
# ------------------------------------------------------------

df = pd.read_csv(INPUT_FILE)

# Load the rule results as the source of exact financial evidence.
RULES_FILE = Path(
    r"data\processed\bank_statement_rule_results.csv"
)

rules_df = pd.read_csv(RULES_FILE)

# Keep the exact financial features needed for evidence.
evidence_columns = [
    "account_id",
    "average_monthly_income",
    "average_monthly_expense",
    "average_monthly_surplus",
    "emi_to_income_ratio",
    "savings_ratio",
    "income_stability",
]

rules_evidence = rules_df[evidence_columns]

# Combine agent decisions with exact financial evidence.
df = df.merge(
    rules_evidence,
    on="account_id",
    how="left",
    validate="one_to_one"
)

print("Agent decisions loaded:", len(df))
print("Financial evidence joined:", len(df))


# ------------------------------------------------------------
# 2. Create orchestration metadata
# ------------------------------------------------------------

orchestration_id = (
    "ORCH_BANK_STATEMENT_STANDALONE_001"
)

agent_id = "BANK_STATEMENT_AGENT"

model_id = "bank-statement-rules-v1"
model_version = "1.0"

rule_id = "bank-affordability-rules-v1"
rule_version = "1.0"

timestamp = datetime.now(
    timezone.utc
).isoformat()


# IMPORTANT:
# In the real orchestrator, this value will come from
# the previous agent's provenance record.
#
# For standalone A3 testing it is None.

previous_record_hash = None


# ============================================================
# TRACECHAIN COLLECTIONS
# ============================================================

agent_executions = []
agent_decisions = []
evidence_records = []
accountability_scores = []
provenance_records = []


# ============================================================
# PROCESS EACH APPLICANT
# ============================================================

for sequence_number, row in enumerate(
    df.to_dict("records"),
    start=1
):

    account_id = int(
        row["account_id"]
    )

    execution_id = (
        f"EXEC_BANK_{account_id}_{sequence_number:03d}"
    )

    decision_id = (
        f"DEC_BANK_{account_id}_{sequence_number:03d}"
    )

    evidence_id = (
        f"EVID_BANK_{account_id}_{sequence_number:03d}"
    )

    score_id = (
        f"ACC_BANK_{account_id}_{sequence_number:03d}"
    )

    record_id = (
        f"PROV_BANK_{account_id}_{sequence_number:03d}"
    )


    # ========================================================
    # INPUT DATA
    # ========================================================

    input_data = {
    "account_id": account_id,
    "statement_period": "2022-01 to 2022-06",
    "source": "synthetic_bank_statement",

    "financial_features": {
        "average_monthly_income": float(
            row["average_monthly_income"]
        ),
        "average_monthly_expense": float(
            row["average_monthly_expense"]
        ),
        "average_monthly_surplus": float(
            row["average_monthly_surplus"]
        ),
        "emi_to_income_ratio": float(
            row["emi_to_income_ratio"]
        ),
        "savings_ratio": float(
            row["savings_ratio"]
        ),
        "income_stability": float(
            row["income_stability"]
        ),
    }
}


    # ========================================================
    # OUTPUT DATA
    # ========================================================

    output_data = {
    "financial_health": row[
        "financial_health"
    ],

    "financial_risk_flag_count": int(
        row["financial_risk_flag_count"]
    ),

    "agent_score": int(
        row["agent_score"]
    ),

    "decision_output": row[
        "decision_output"
    ],

    "confidence_score": float(
        row["confidence_score"]
    ),

    "reasoning": row[
        "reasoning"
    ],
}

    # ========================================================
    # INPUT / OUTPUT HASHES
    # ========================================================

    input_hash = calculate_hash(
        input_data
    )

    output_hash = calculate_hash(
        output_data
    )


    # ========================================================
    # AGENT EXECUTION
    # ========================================================

    execution = {
        "execution_id": execution_id,
        "orchestration_id": orchestration_id,
        "agent_id": agent_id,

        "parent_execution_id": None,

        "sequence_number": sequence_number,

        "input_data": input_data,
        "input_hash": input_hash,

        "model_id": model_id,
        "model_version": model_version,

        "rule_id": rule_id,
        "rule_version": rule_version,

        "output_data": output_data,
        "output_hash": output_hash,

        "start_time": timestamp,
        "end_time": timestamp,

        "status": "COMPLETED",
    }

    agent_executions.append(
        execution
    )


    # ========================================================
    # AGENT DECISION
    # ========================================================

    decision = {
        "decision_id": decision_id,

        "execution_id": execution_id,

        "decision_output": row[
            "decision_output"
        ],

        "confidence_score": float(
            row["confidence_score"]
        ),

        "reasoning": row[
            "reasoning"
        ],

        "decision_timestamp": timestamp,
    }

    agent_decisions.append(
        decision
    )


    # ========================================================
    # EVIDENCE
    # ========================================================

    evidence_data = {
        "account_id": account_id,

        "average_monthly_income": float(
            row["average_monthly_income"]
        ),

        "average_monthly_expense": float(
            row["average_monthly_expense"]
        ),

        "average_monthly_surplus": float(
            row["average_monthly_surplus"]
        ),

        "emi_to_income_ratio": float(
            row["emi_to_income_ratio"]
        ),

        "savings_ratio": float(
            row["savings_ratio"]
        ),

        "income_stability": float(
            row["income_stability"]
        ),

        "financial_risk_flag_count": int(
            row["financial_risk_flag_count"]
        ),
    }

    evidence = {
        "evidence_id": evidence_id,

        "execution_id": execution_id,

        "evidence_type": "FINANCIAL_FEATURES",

        "source": "synthetic_bank_statement",

        "data_reference": (
            f"account_{account_id}"
        ),

        "model_id": model_id,

        "rule_id": rule_id,

        "policy_id": None,

        "retrieval_score": 1.0,

        "evidence_hash": calculate_hash(
            evidence_data
        ),

        "timestamp": timestamp,

        "evidence_data": evidence_data,
    }

    evidence_records.append(
        evidence
    )


    # ========================================================
    # ACCOUNTABILITY SCORE
    # ========================================================

    financial_health = row[
        "financial_health"
    ]

    if financial_health == "HIGH_RISK":

        impact_score = 9
        irreversibility_score = 8
        explainability_score = 9

    elif financial_health == "MODERATE_RISK":

        impact_score = 8
        irreversibility_score = 7
        explainability_score = 9

    else:

        impact_score = 7
        irreversibility_score = 6
        explainability_score = 9


    composite_score = round(
        (
            impact_score
            + irreversibility_score
            + (
                10 - explainability_score
            )
        ) / 3,
        2
    )

    # For accountability risk, use a simple
    # consequence-oriented score.

    if financial_health == "HIGH_RISK":
        composite_score = 7.5

    elif financial_health == "MODERATE_RISK":
        composite_score = 5.5

    else:
        composite_score = 2.5


    accountability = {
        "score_id": score_id,

        "execution_id": execution_id,

        "irreversibility_score":
            irreversibility_score,

        "impact_score":
            impact_score,

        "explainability_score":
            explainability_score,

        "composite_risk_score":
            composite_score,

        "risk_level":
            risk_level_for(
                composite_score
            ),

        "review_required": (
            row["decision_output"]
            == "REVIEW"
            or composite_score >= 7
        ),

        "scoring_model_version":
            "tracechain-scoring-v1",

        "calculated_at": timestamp,
    }

    accountability_scores.append(
        accountability
    )


    # ========================================================
    # PROVENANCE RECORD
    # ========================================================

    chain_payload = {
        "record_id": record_id,

        "orchestration_id":
            orchestration_id,

        "execution_id":
            execution_id,

        "event_type":
            "BANK_STATEMENT_AGENT_COMPLETED",

        "timestamp":
            timestamp,

        "input_hash":
            input_hash,

        "output_hash":
            output_hash,

        "previous_record_hash":
            previous_record_hash,
    }

    record_hash = calculate_hash(
        chain_payload
    )

    provenance = {
        **chain_payload,

        "input_data":
            input_data,

        "output_data":
            output_data,

        "record_hash":
            record_hash,
    }

    provenance_records.append(
        provenance
    )

    # Chain next record to this record
    previous_record_hash = record_hash


# ============================================================
# FINAL JSON PAYLOAD
# ============================================================

tracechain_output = {

    "agent_id":
        agent_id,

    "agent_version":
        model_version,

    "schema_version":
        "TraceChain-A3-v1",

    "orchestration_id":
        orchestration_id,

    "records": {

        "AGENT_EXECUTIONS":
            agent_executions,

        "AGENT_DECISIONS":
            agent_decisions,

        "EVIDENCE":
            evidence_records,

        "ACCOUNTABILITY_SCORES":
            accountability_scores,

        "PROVENANCE_RECORDS":
            provenance_records,
    }
}


# ============================================================
# SAVE JSON
# ============================================================

OUTPUT_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)

with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8"
) as file:

    json.dump(
        tracechain_output,
        file,
        indent=2,
        ensure_ascii=False
    )


# ============================================================
# VALIDATION
# ============================================================

print("\n========== TRACECHAIN VALIDATION ==========")

print(
    "AGENT_EXECUTIONS:",
    len(agent_executions)
)

print(
    "AGENT_DECISIONS:",
    len(agent_decisions)
)

print(
    "EVIDENCE:",
    len(evidence_records)
)

print(
    "ACCOUNTABILITY_SCORES:",
    len(accountability_scores)
)

print(
    "PROVENANCE_RECORDS:",
    len(provenance_records)
)


# Verify every provenance record

verification_results = [
    verify_provenance_record(record)
    for record in provenance_records
]

print(
    "Provenance records valid:",
    all(verification_results)
)


print(
    "Decision distribution:"
)

print(
    df["decision_output"]
    .value_counts()
    .to_string()
)


print("\nJSON saved to:")

print(OUTPUT_FILE)

print(
    "\n========== TRACECHAIN OUTPUT COMPLETE =========="
)