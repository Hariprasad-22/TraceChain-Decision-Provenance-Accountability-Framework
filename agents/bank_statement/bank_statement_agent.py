from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


AGENT_ID = "A003"
MODEL_ID = "bank-statement-rules"
MODEL_VERSION = "1.0"
RULE_ID = "bank-affordability-rules-v1"
SCHEMA_VERSION = "TraceChain-A3-v1"


# ============================================================
# LOAD TRANSACTIONS
# ============================================================

def _load_transactions(path: str | Path) -> pd.DataFrame:
    """
    Load one synthetic bank statement CSV and normalize
    the fields required by A003.
    """

    path = Path(path)

    df = pd.read_csv(path)

    required_columns = [
        "applicant_id",
        "transaction_date",
        "debit",
        "credit",
        "transaction_type",
    ]

    missing = [
        column for column in required_columns
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing required columns: {missing}"
        )

    # Normalize applicant ID
    df["applicant_id"] = (
        df["applicant_id"]
        .astype(str)
        .str.strip()
    )

    # Normalize date
    df["transaction_date"] = pd.to_datetime(
        df["transaction_date"],
        errors="coerce"
    )

    # Normalize numeric fields
    df["debit"] = pd.to_numeric(
        df["debit"],
        errors="coerce"
    ).fillna(0.0)

    df["credit"] = pd.to_numeric(
        df["credit"],
        errors="coerce"
    ).fillna(0.0)

    # Normalize transaction type
    df["transaction_type"] = (
        df["transaction_type"]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    # Category is required for the new synthetic statements
    if "category" in df.columns:
        df["category"] = (
            df["category"]
            .astype(str)
            .str.upper()
            .str.strip()
        )
    else:
        df["category"] = ""

    # Remove invalid dates
    df = df.dropna(
        subset=["transaction_date"]
    ).copy()

    return df


# ============================================================
# FEATURE CALCULATION
# ============================================================

def _features_for_account(
    transactions: pd.DataFrame,
) -> dict[str, Any]:
    """
    Calculate financial features for one applicant.
    """

    if transactions.empty:
        raise ValueError(
            "No transactions available."
        )

    transactions = transactions.copy()

    # --------------------------------------------------------
    # Normalize categories
    # --------------------------------------------------------

    categories = (
        transactions["category"]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    transaction_types = (
        transactions["transaction_type"]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    # --------------------------------------------------------
    # Monthly aggregation
    # --------------------------------------------------------

    transactions["month"] = (
        transactions["transaction_date"]
        .dt.to_period("M")
    )

    monthly_income = (
        transactions
        .groupby("month")["credit"]
        .sum()
    )

    monthly_expense = (
        transactions
        .groupby("month")["debit"]
        .sum()
    )

    monthly = pd.DataFrame({
        "income": monthly_income,
        "expense": monthly_expense,
    }).fillna(0.0)

    monthly["surplus"] = (
        monthly["income"]
        - monthly["expense"]
    )

    # --------------------------------------------------------
    # Average monthly income
    # --------------------------------------------------------

    average_income = float(
        monthly["income"].mean()
        if len(monthly) > 0
        else 0.0
    )

    # --------------------------------------------------------
    # Average monthly expense
    # --------------------------------------------------------

    average_expense = float(
        monthly["expense"].mean()
        if len(monthly) > 0
        else 0.0
    )

    # --------------------------------------------------------
    # Total EMI
    #
    # IMPORTANT:
    # New synthetic statements use:
    # category = LOAN_EMI
    # --------------------------------------------------------

    total_emi = float(
        transactions.loc[
            categories == "LOAN_EMI",
            "debit"
        ].sum()
    )

    # --------------------------------------------------------
    # Average monthly EMI
    # --------------------------------------------------------

    average_monthly_emi = (
        total_emi / len(monthly)
        if len(monthly) > 0
        else 0.0
    )

    # --------------------------------------------------------
    # EMI-to-income ratio
    #
    # CORRECT:
    # average monthly EMI /
    # average monthly income
    # --------------------------------------------------------

    emi_to_income_ratio = (
        average_monthly_emi / average_income
        if average_income > 0
        else 0.0
    )

    # --------------------------------------------------------
    # Cash withdrawals
    # --------------------------------------------------------

    total_cash = float(
        transactions.loc[
            categories == "CASH_WITHDRAWAL",
            "debit"
        ].sum()
    )

    average_monthly_cash = (
        total_cash / len(monthly)
        if len(monthly) > 0
        else 0.0
    )

    cash_to_income_ratio = (
        average_monthly_cash / average_income
        if average_income > 0
        else 0.0
    )

    # --------------------------------------------------------
    # Average monthly surplus
    # --------------------------------------------------------

    average_surplus = float(
        monthly["surplus"].mean()
        if len(monthly) > 0
        else 0.0
    )

    # --------------------------------------------------------
    # Savings ratio
    # --------------------------------------------------------

    savings_ratio = (
        average_surplus / average_income
        if average_income > 0
        else 0.0
    )

    # --------------------------------------------------------
    # Income stability
    #
    # Uses coefficient of variation.
    # Higher = more stable.
    # --------------------------------------------------------

    if (
        len(monthly) > 1
        and monthly["income"].mean() > 0
    ):
        income_std = float(
            monthly["income"].std(ddof=0)
        )

        income_mean = float(
            monthly["income"].mean()
        )

        income_cv = (
            income_std / income_mean
            if income_mean > 0
            else 1.0
        )

        income_stability = max(
            0.0,
            min(
                1.0,
                1.0 - income_cv
            )
        )
    else:
        income_stability = 0.0

    # --------------------------------------------------------
    # Expense-to-income ratio
    # --------------------------------------------------------

    expense_to_income_ratio = (
        average_expense / average_income
        if average_income > 0
        else 999.0
    )

    # --------------------------------------------------------
    # Balance
    # --------------------------------------------------------

    if "balance" in transactions.columns:
        balance = pd.to_numeric(
            transactions["balance"],
            errors="coerce"
        )

        ending_balance = float(
            balance.iloc[-1]
            if not balance.empty
            else 0.0
        )

        minimum_balance = float(
            balance.min()
            if not balance.empty
            else 0.0
        )
    else:
        running_balance = (
            transactions["credit"]
            - transactions["debit"]
        ).cumsum()

        ending_balance = float(
            running_balance.iloc[-1]
            if not running_balance.empty
            else 0.0
        )

        minimum_balance = float(
            running_balance.min()
            if not running_balance.empty
            else 0.0
        )

    # --------------------------------------------------------
    # Negative balance months
    # --------------------------------------------------------

    negative_months = int(
        (monthly["surplus"] < 0).sum()
    )

    # --------------------------------------------------------
    # Return features
    # --------------------------------------------------------

    return {
        "average_monthly_income": average_income,
        "average_monthly_expense": average_expense,
        "average_monthly_emi": average_monthly_emi,
        "emi_to_income_ratio": emi_to_income_ratio,
        "average_monthly_cash_withdrawal": average_monthly_cash,
        "cash_to_income_ratio": cash_to_income_ratio,
        "average_monthly_surplus": average_surplus,
        "savings_ratio": savings_ratio,
        "expense_to_income_ratio": expense_to_income_ratio,
        "income_stability": income_stability,
        "ending_balance": ending_balance,
        "minimum_balance": minimum_balance,
        "negative_months": negative_months,
        "transaction_count": int(len(transactions)),
        "statement_months": int(len(monthly)),
    }


# ============================================================
# DECISION / SCORING
# ============================================================

def _decision(
    features: dict[str, Any],
) -> dict[str, Any]:
    """
    Rule-based financial affordability assessment.
    """

    score = 100
    flags: list[str] = []

    surplus = features["average_monthly_surplus"]
    savings = features["savings_ratio"]
    emi_ratio = features["emi_to_income_ratio"]
    expense_ratio = features["expense_to_income_ratio"]
    cash_ratio = features["cash_to_income_ratio"]

    # --------------------------------------------------------
    # Negative surplus
    # --------------------------------------------------------

    if surplus < 0:
        score -= 35
        flags.append("NEGATIVE_MONTHLY_SURPLUS")

    elif surplus < 10000:
        score -= 15
        flags.append("LOW_MONTHLY_SURPLUS")

    # --------------------------------------------------------
    # Savings
    # --------------------------------------------------------

    if savings < 0:
        score -= 25
        flags.append("NEGATIVE_SAVINGS_RATIO")

    elif savings < 0.10:
        score -= 10
        flags.append("LOW_SAVINGS_RATIO")

    # --------------------------------------------------------
    # EMI
    # --------------------------------------------------------

    if emi_ratio > 0.30:
        score -= 20
        flags.append("HIGH_EMI_TO_INCOME")

    # --------------------------------------------------------
    # Expense
    # --------------------------------------------------------

    if expense_ratio > 0.80:
        score -= 20
        flags.append("HIGH_EXPENSE_TO_INCOME")

    # --------------------------------------------------------
    # Cash withdrawal
    # --------------------------------------------------------

    if cash_ratio > 0.15:
        score -= 10
        flags.append("HIGH_CASH_WITHDRAWAL")

    # --------------------------------------------------------
    # Keep score within range
    # --------------------------------------------------------

    score = max(
        0,
        min(100, score)
    )

    # --------------------------------------------------------
    # Decision
    # --------------------------------------------------------

    if score >= 80:
        decision = "ELIGIBLE"
    elif score >= 60:
        decision = "REVIEW"
    else:
        decision = "NOT_ELIGIBLE"

    # --------------------------------------------------------
    # Financial health
    # --------------------------------------------------------

    if len(flags) >= 3:
        financial_health = "HIGH_RISK"
    elif len(flags) >= 1:
        financial_health = "MODERATE_RISK"
    else:
        financial_health = "HEALTHY"

    # --------------------------------------------------------
    # Confidence
    # --------------------------------------------------------

    confidence = round(
        score / 100,
        4
    )

    return {
        "decision": decision,
        "score": score,
        "confidence": confidence,
        "financial_health": financial_health,
        "flags": flags,
    }


# ============================================================
# REASONING
# ============================================================

def _reasoning(
    features: dict[str, Any],
    decision: dict[str, Any],
) -> str:

    income = features[
        "average_monthly_income"
    ]

    expense = features[
        "average_monthly_expense"
    ]

    emi = features[
        "average_monthly_emi"
    ]

    surplus = features[
        "average_monthly_surplus"
    ]

    emi_ratio = features[
        "emi_to_income_ratio"
    ]

    savings_ratio = features[
        "savings_ratio"
    ]

    if decision["decision"] == "ELIGIBLE":
        conclusion = (
            "The applicant demonstrates "
            "sufficient monthly affordability "
            "with no major financial risk flags."
        )

    elif decision["decision"] == "REVIEW":
        conclusion = (
            "The applicant shows some financial "
            "risk indicators and should undergo "
            "manual review."
        )

    else:
        conclusion = (
            "The applicant demonstrates "
            "insufficient financial affordability "
            "based on the configured rules."
        )

    return (
        f"Average monthly income is "
        f"₹{income:,.2f}, average monthly "
        f"expense is ₹{expense:,.2f}, and "
        f"average monthly EMI is ₹{emi:,.2f}. "
        f"Average monthly surplus is "
        f"₹{surplus:,.2f}. EMI-to-income ratio "
        f"is {emi_ratio:.2%} and savings ratio "
        f"is {savings_ratio:.2%}. "
        f"{conclusion}"
    )


# ============================================================
# HASH UTILITY
# ============================================================

def _sha256(data: Any) -> str:
    """
    Generate deterministic SHA-256 hash.
    """

    if isinstance(data, str):
        payload = data.encode("utf-8")
    else:
        payload = json.dumps(
            data,
            sort_keys=True,
            default=str,
        ).encode("utf-8")

    return hashlib.sha256(
        payload
    ).hexdigest()


# ============================================================
# TRACECHAIN A003 RECORD
# ============================================================

def bank_statement_agent(
    state: dict[str, Any],
    orchestration_id: str | None = None,
    previous_record_hash: str | None = None,
) -> dict[str, Any]:
    """
    Main A003 TraceChain-compatible agent.

    Input:
        state containing statement/file information.

    Output:
        TraceChain-A3-v1 record.
    """

    file_path = (
        state.get("file_path")
        or state.get("statement_path")
    )

    if not file_path:
        raise ValueError(
            "state must contain file_path"
        )

    transactions = _load_transactions(
        file_path
    )

    applicant_id = str(
        transactions["applicant_id"]
        .iloc[0]
    )

    # --------------------------------------------------------
    # Basic applicant metadata
    # --------------------------------------------------------

    first_row = transactions.iloc[0]

    applicant_name = str(
        first_row.get(
            "account_holder_name",
            ""
        )
    )

    aadhaar_id = str(
        first_row.get(
            "aadhaar_id",
            ""
        )
    )

    bank_name = str(
        first_row.get(
            "bank_name",
            ""
        )
    )

    account_number = str(
        first_row.get(
            "account_number",
            ""
        )
    )

    statement_id = str(
        first_row.get(
            "statement_id",
            ""
        )
    )

    statement_start = str(
        first_row.get(
            "statement_start_date",
            transactions[
                "transaction_date"
            ].min().date(),
        )
    )

    statement_end = str(
        first_row.get(
            "statement_end_date",
            transactions[
                "transaction_date"
            ].max().date(),
        )
    )

    # --------------------------------------------------------
    # Calculate features
    # --------------------------------------------------------

    features = _features_for_account(
        transactions
    )

    # --------------------------------------------------------
    # Decision
    # --------------------------------------------------------

    decision = _decision(
        features
    )

    reasoning = _reasoning(
        features,
        decision
    )

    # --------------------------------------------------------
    # Evidence hash
    # --------------------------------------------------------

    evidence_payload = {
        "agent_id": AGENT_ID,
        "applicant_id": applicant_id,
        "statement_id": statement_id,
        "transaction_count": features[
            "transaction_count"
        ],
        "statement_start": statement_start,
        "statement_end": statement_end,
        "features": features,
    }

    evidence_hash = _sha256(
        evidence_payload
    )

    # --------------------------------------------------------
    # Input
    # --------------------------------------------------------

    execution_input = {
        "agent_id": AGENT_ID,
        "input_type": "bank_statement",
        "applicant_id": applicant_id,
        "applicant_name": applicant_name,
        "aadhaar_id": aadhaar_id,
        "bank_name": bank_name,
        "account_number": account_number,
        "statement_id": statement_id,
        "file_name": Path(
            file_path
        ).name,
        "transaction_count": features[
            "transaction_count"
        ],
        "statement_period": {
            "start": statement_start,
            "end": statement_end,
        },
    }

    # --------------------------------------------------------
    # Output
    # --------------------------------------------------------

    output = {
        "decision": decision["decision"],
        "confidence": decision["confidence"],
        "financial_health": decision[
            "financial_health"
        ],
        "score": decision["score"],
        "reasoning": reasoning,
        "risk_flags": decision["flags"],
        "financial_metrics": {
            "average_monthly_income":
                round(
                    features[
                        "average_monthly_income"
                    ],
                    2,
                ),

            "average_monthly_expense":
                round(
                    features[
                        "average_monthly_expense"
                    ],
                    2,
                ),

            "average_monthly_emi":
                round(
                    features[
                        "average_monthly_emi"
                    ],
                    2,
                ),

            "emi_to_income_ratio":
                round(
                    features[
                        "emi_to_income_ratio"
                    ],
                    6,
                ),

            "average_monthly_surplus":
                round(
                    features[
                        "average_monthly_surplus"
                    ],
                    2,
                ),

            "savings_ratio":
                round(
                    features[
                        "savings_ratio"
                    ],
                    6,
                ),

            "expense_to_income_ratio":
                round(
                    features[
                        "expense_to_income_ratio"
                    ],
                    6,
                ),

            "income_stability":
                round(
                    features[
                        "income_stability"
                    ],
                    6,
                ),

            "ending_balance":
                round(
                    features[
                        "ending_balance"
                    ],
                    2,
                ),

            "minimum_balance":
                round(
                    features[
                        "minimum_balance"
                    ],
                    2,
                ),

            "cash_to_income_ratio":
                round(
                    features[
                        "cash_to_income_ratio"
                    ],
                    6,
                ),
        },
        "statement_period": {
            "start": statement_start,
            "end": statement_end,
        },
    }

    # --------------------------------------------------------
    # Accountability
    # --------------------------------------------------------

    if decision["financial_health"] == "HIGH_RISK":
        composite_risk_score = 8.0
        risk_level = "High"
        review_required = True

    elif decision["financial_health"] == "MODERATE_RISK":
        composite_risk_score = 5.0
        risk_level = "Medium"
        review_required = True

    else:
        composite_risk_score = 2.5
        risk_level = "Low"
        review_required = False

    accountability = {
        "composite_risk_score":
            composite_risk_score,

        "risk_level":
            risk_level,

        "review_required":
            review_required,

        "rules_applied": [
            RULE_ID
        ],

        "risk_flag_count":
            len(decision["flags"]),
    }

    # --------------------------------------------------------
    # Provenance
    # --------------------------------------------------------

    input_hash = _sha256(
        execution_input
    )

    output_hash = _sha256(
        output
    )

    provenance_payload = {
        "input_hash": input_hash,
        "output_hash": output_hash,
        "previous_record_hash":
            previous_record_hash,
        "agent_id": AGENT_ID,
        "model_id": MODEL_ID,
        "model_version": MODEL_VERSION,
        "rule_id": RULE_ID,
    }

    record_hash = _sha256(
        provenance_payload
    )

    provenance = {
        "input_hash": input_hash,
        "output_hash": output_hash,
        "previous_record_hash":
            previous_record_hash,
        "record_hash": record_hash,
        "agent_id": AGENT_ID,
        "model_id": MODEL_ID,
        "model_version": MODEL_VERSION,
        "rule_id": RULE_ID,
    }

    # --------------------------------------------------------
    # Final TraceChain record
    # --------------------------------------------------------

    record = {
        "schema_version": SCHEMA_VERSION,

        "execution_input":
            execution_input,

        "output":
            output,

        "evidence": {
            "source_type":
                "bank_statement_csv",

            "source_file":
                Path(file_path).name,

            "evidence_hash":
                evidence_hash,

            "transaction_count":
                features[
                    "transaction_count"
                ],

            "statement_period": {
                "start": statement_start,
                "end": statement_end,
            },
        },

        "accountability":
            accountability,

        "provenance":
            provenance,
    }

    return record


# ============================================================
# RUN ONE TRANSACTION FILE
# ============================================================

def run_transactions_file(
    file_path: str | Path,
) -> dict[str, Any]:

    return bank_statement_agent(
        {
            "file_path": str(file_path)
        }
    )


# ============================================================
# RUN ALL 10 STATEMENTS
# ============================================================

def run_statement_files(
    input_dir: str | Path,
    output_path: str | Path,
) -> list[dict[str, Any]]:

    input_dir = Path(input_dir)
    output_path = Path(output_path)

    files = sorted(
        input_dir.glob(
            "bank_statement_*.csv"
        )
    )

    if len(files) != 10:
        raise ValueError(
            f"Expected exactly 10 bank statement "
            f"files, found {len(files)}"
        )

    records = []

    previous_record_hash = None

    for file_path in files:

        record = bank_statement_agent(
            {
                "file_path": str(file_path)
            },
            previous_record_hash=
                previous_record_hash,
        )

        records.append(record)

        previous_record_hash = (
            record[
                "provenance"
            ]["record_hash"]
        )

    final_output = {
        "schema_version":
            SCHEMA_VERSION,

        "agent_id":
            AGENT_ID,

        "model_id":
            MODEL_ID,

        "model_version":
            MODEL_VERSION,

        "rule_id":
            RULE_ID,

        "record_count":
            len(records),

        "records":
            records,
    }

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            final_output,
            f,
            indent=2,
            ensure_ascii=False,
        )

    return records


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    input_dir = Path(
        "synthetic_data"
        "/aadhaar_bank_statements"
    )

    output_path = Path(
        "data"
        "/processed"
        "/bank_statement_tracechain_output.json"
    )

    records = run_statement_files(
        input_dir,
        output_path,
    )

    print(
        "=========================================="
    )

    print(
        "BANK STATEMENT AGENT A003"
    )

    print(
        "=========================================="
    )

    print(
        f"Records: {len(records)}"
    )

    print(
        f"Output: {output_path}"
    )

    print(
        "=========================================="
    )

    for record in records:

        applicant_id = record[
            "execution_input"
        ]["applicant_id"]

        decision = record[
            "output"
        ]["decision"]

        score = record[
            "output"
        ]["score"]

        emi_ratio = record[
            "output"
        ]["financial_metrics"][
            "emi_to_income_ratio"
        ]

        print(
            f"Applicant {applicant_id}: "
            f"{decision} | "
            f"Score={score} | "
            f"EMI Ratio={emi_ratio:.2%}"
        )