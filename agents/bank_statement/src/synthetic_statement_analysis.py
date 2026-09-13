import pandas as pd
import numpy as np
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

INPUT_DIR = Path(
    r"synthetic_data\aadhaar_bank_statements"
)

OUTPUT_FILE = Path(
    r"data\processed\synthetic_statement_features.csv"
)


print("========== AADHAAR BANK STATEMENT ANALYSIS ==========")


# ============================================================
# 1. LOAD THE 10 BANK STATEMENTS
# ============================================================

statement_files = sorted(
    INPUT_DIR.glob("bank_statement_*.csv")
)
if not statement_files:
    raise FileNotFoundError(
        f"No bank statement CSV files found in: {INPUT_DIR}"
    )

print("Bank statements found:", len(statement_files))

all_transactions = []

for file in statement_files:

    print("Loading:", file.name)

    df = pd.read_csv(file)

    required_columns = [
        "statement_id",
        "bank_name",
        "account_number",
        "statement_start_date",
        "statement_end_date",
        "transaction_date",
        "description",
        "debit",
        "credit",
        "balance",
        "transaction_type",
        "category",
        "reference_id",
        "account_holder_name",
        "aadhaar_id",
        "applicant_id",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"{file.name} is missing columns: {missing_columns}"
        )

    all_transactions.append(df)


transactions = pd.concat(
    all_transactions,
    ignore_index=True
)


print("Total transactions loaded:", len(transactions))


# ============================================================
# 2. CLEAN DATA
# ============================================================

transactions["transaction_date"] = pd.to_datetime(
    transactions["transaction_date"],
    dayfirst=True,
    errors="coerce"
)

transactions["debit"] = pd.to_numeric(
    transactions["debit"],
    errors="coerce"
).fillna(0)

transactions["credit"] = pd.to_numeric(
    transactions["credit"],
    errors="coerce"
).fillna(0)

transactions["balance"] = pd.to_numeric(
    transactions["balance"],
    errors="coerce"
)

transactions["applicant_id"] = (
    transactions["applicant_id"]
    .astype(str)
    .str.strip()
)


# ============================================================
# 3. CREATE MONTH
# ============================================================

transactions["month"] = (
    transactions["transaction_date"]
    .dt.to_period("M")
    .astype(str)
)


# ============================================================
# 4. CREATE COMMON AMOUNT COLUMN
# ============================================================

transactions["amount"] = (
    transactions["debit"] +
    transactions["credit"]
)


# ============================================================
# 5. MONTHLY FINANCIAL SUMMARY
# ============================================================

monthly = (
    transactions
    .groupby(["applicant_id", "month"])
    .agg(
        monthly_income=("credit", "sum"),
        monthly_expense=("debit", "sum"),
        transaction_count=("amount", "count")
    )
    .reset_index()
)

monthly["monthly_surplus"] = (
    monthly["monthly_income"]
    - monthly["monthly_expense"]
)


# ============================================================
# 6. INCOME STABILITY
# ============================================================

income_stats = (
    monthly
    .groupby("applicant_id")
    .agg(
        average_monthly_income=("monthly_income", "mean"),
        income_std=("monthly_income", "std"),
        minimum_monthly_income=("monthly_income", "min"),
        maximum_monthly_income=("monthly_income", "max")
    )
    .reset_index()
)

income_stats["income_std"] = (
    income_stats["income_std"]
    .fillna(0)
)

income_stats["income_stability"] = np.where(
    income_stats["average_monthly_income"] > 0,

    1 - (
        income_stats["income_std"]
        /
        income_stats["average_monthly_income"]
    ),

    0
)

income_stats["income_stability"] = (
    income_stats["income_stability"]
    .clip(lower=0, upper=1)
)


# ============================================================
# 7. EXPENSE CATEGORY ANALYSIS
# ============================================================

expense_categories = [
    "HOUSING",
    "LOAN_EMI",
    "UTILITIES",
    "GROCERIES",
    "TRANSPORT",
    "DISCRETIONARY",
    "CASH_WITHDRAWAL",
    "INVESTMENT"
]


category_features = (
    transactions[
        transactions["category"].isin(expense_categories)
    ]
    .groupby(
        ["applicant_id", "category"]
    )["debit"]
    .agg(
        ["sum", "mean", "count"]
    )
    .reset_index()
)


# ============================================================
# 8. PIVOT CATEGORY TOTALS
# ============================================================

category_sum = (
    category_features
    .pivot(
        index="applicant_id",
        columns="category",
        values="sum"
    )
    .fillna(0)
)

category_mean = (
    category_features
    .pivot(
        index="applicant_id",
        columns="category",
        values="mean"
    )
    .fillna(0)
)

category_count = (
    category_features
    .pivot(
        index="applicant_id",
        columns="category",
        values="count"
    )
    .fillna(0)
)


category_sum.columns = [
    f"total_{c.lower()}"
    for c in category_sum.columns
]

category_mean.columns = [
    f"average_{c.lower()}"
    for c in category_mean.columns
]

category_count.columns = [
    f"{c.lower()}_count"
    for c in category_count.columns
]


# ============================================================
# 9. OVERALL TRANSACTION STATISTICS
# ============================================================

overall = (
    transactions
    .groupby("applicant_id")
    .agg(
        total_transactions=("amount", "count"),
        total_credits=("credit", "sum"),
        total_debits=("debit", "sum"),
        average_transaction_amount=("amount", "mean"),
        maximum_transaction_amount=("amount", "max"),
        minimum_transaction_amount=("amount", "min"),
        average_balance=("balance", "mean"),
        minimum_balance=("balance", "min"),
        maximum_balance=("balance", "max")
    )
    .reset_index()
)


# ============================================================
# 10. MERGE ALL FEATURES
# ============================================================

features = overall.merge(
    income_stats,
    on="applicant_id",
    how="left"
)

features = features.merge(
    category_sum,
    on="applicant_id",
    how="left"
)

features = features.merge(
    category_mean,
    on="applicant_id",
    how="left"
)

features = features.merge(
    category_count,
    on="applicant_id",
    how="left"
)


features = features.fillna(0)
# ============================================================
# 10A. ENSURE OPTIONAL CATEGORY COLUMNS EXIST
# ============================================================

required_category_columns = [
    "total_housing",
    "total_loan_emi",
    "total_utilities",
    "total_groceries",
    "total_transport",
    "total_discretionary",
    "total_cash_withdrawal",
    "total_investment",

    "average_housing",
    "average_loan_emi",
    "average_utilities",
    "average_groceries",
    "average_transport",
    "average_discretionary",
    "average_cash_withdrawal",
    "average_investment",

    "housing_count",
    "loan_emi_count",
    "utilities_count",
    "groceries_count",
    "transport_count",
    "discretionary_count",
    "cash_withdrawal_count",
    "investment_count"
]

for column in required_category_columns:
    if column not in features.columns:
        features[column] = 0

# ============================================================
# 11. SIX-MONTH FINANCIAL INDICATORS
# ============================================================

month_counts = (
    monthly
    .groupby("applicant_id")["month"]
    .nunique()
    .reset_index(
        name="months_analyzed"
    )
)

features = features.merge(
    month_counts,
    on="applicant_id",
    how="left"
)


features["average_monthly_expense"] = np.where(
    features["months_analyzed"] > 0,

    features["total_debits"]
    /
    features["months_analyzed"],

    0
)


features["average_monthly_surplus"] = (
    features["average_monthly_income"]
    -
    features["average_monthly_expense"]
)


# ============================================================
# 12. EMI-TO-INCOME RATIO
# ============================================================

features["emi_to_income_ratio"] = np.where(
    features["average_monthly_income"] > 0,

    features["average_loan_emi"]
    /
    features["average_monthly_income"],

    0
)


# ============================================================
# 13. SAVINGS RATIO
# ============================================================

features["savings_ratio"] = np.where(
    features["average_monthly_income"] > 0,

    features["average_monthly_surplus"]
    /
    features["average_monthly_income"],

    0
)


# ============================================================
# 14. CASH WITHDRAWAL RATIO
# ============================================================

features["cash_withdrawal_ratio"] = np.where(
    features["total_debits"] > 0,

    features["total_cash_withdrawal"]
    /
    features["total_debits"],

    0
)


# ============================================================
# 15. INVESTMENT RATIO
# ============================================================

features["investment_ratio"] = np.where(
    features["total_debits"] > 0,

    features["total_investment"]
    /
    features["total_debits"],

    0
)


# ============================================================
# 16. ADD APPLICANT IDENTITY
# ============================================================

identity = (
    transactions
    .sort_values("transaction_date")
    .groupby("applicant_id")
    .first()
    .reset_index()
)


identity = identity[
    [
        "applicant_id",
        "statement_id",
        "bank_name",
        "account_number",
        "statement_start_date",
        "statement_end_date",
        "account_holder_name",
        "aadhaar_id"
    ]
]


features = features.merge(
    identity,
    on="applicant_id",
    how="left"
)


# ============================================================
# 17. ADD EMPLOYMENT / CIBIL INFORMATION IF AVAILABLE
# ============================================================

# The new bank statements do not contain employment type
# or CIBIL score, so we do not invent those values.

features["employment_type"] = "UNKNOWN"
features["monthly_salary"] = 0
features["cibil_score"] = 0


# ============================================================
# 18. FINAL COLUMN ORDER
# ============================================================

first_columns = [
    "applicant_id",
    "statement_id",
    "bank_name",
    "account_number",
    "account_holder_name",
    "aadhaar_id",
    "statement_start_date",
    "statement_end_date",
    "months_analyzed",

    "employment_type",
    "monthly_salary",
    "cibil_score",

    "total_transactions",
    "total_credits",
    "total_debits",

    "average_monthly_income",
    "income_std",
    "income_stability",

    "average_monthly_expense",
    "average_monthly_surplus",

    "emi_to_income_ratio",
    "savings_ratio",
    "cash_withdrawal_ratio",
    "investment_ratio",

    "average_balance",
    "minimum_balance",
    "maximum_balance"
]


remaining_columns = [
    c
    for c in features.columns
    if c not in first_columns
]


features = features[
    first_columns + remaining_columns
]


# ============================================================
# 19. SAVE
# ============================================================

OUTPUT_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)

features.to_csv(
    OUTPUT_FILE,
    index=False
)


# ============================================================
# 20. VALIDATION
# ============================================================

print("\n========== VALIDATION ==========")

print(
    "Applicant profiles:",
    len(features)
)

print(
    "Unique applicants:",
    features["applicant_id"].nunique()
)

print(
    "Total transactions:",
    len(transactions)
)


print("\nApplicant financial summary:")

print(
    features[
        [
            "applicant_id",
            "account_holder_name",
            "aadhaar_id",
            "average_monthly_income",
            "average_monthly_expense",
            "average_monthly_surplus",
            "emi_to_income_ratio",
            "savings_ratio",
            "income_stability"
        ]
    ]
    .to_string(index=False)
)


print("\nOutput saved to:")
print(OUTPUT_FILE)

print(
    "\n========== AADHAAR BANK STATEMENT ANALYSIS COMPLETE =========="
)