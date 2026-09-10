import pandas as pd
import numpy as np


INPUT_FILE = r"synthetic_data\bank_transactions.csv"
APPLICANT_FILE = r"synthetic_data\applications.csv"
OUTPUT_FILE = r"data\processed\synthetic_statement_features.csv"


print("========== SYNTHETIC STATEMENT ANALYSIS ==========")

# --------------------------------------------------
# 1. Load data
# --------------------------------------------------

transactions = pd.read_csv(INPUT_FILE)
applicants = pd.read_csv(APPLICANT_FILE)

transactions["date"] = pd.to_datetime(transactions["date"])

print("Transactions loaded:", len(transactions))
print("Applicants loaded:", len(applicants))


# --------------------------------------------------
# 2. Create month column
# --------------------------------------------------

transactions["month"] = transactions["date"].dt.to_period("M").astype(str)


# --------------------------------------------------
# 3. Separate credits and debits
# --------------------------------------------------

transactions["credit_amount"] = np.where(
    transactions["transaction_direction"] == "CREDIT",
    transactions["amount"],
    0
)

transactions["debit_amount"] = np.where(
    transactions["transaction_direction"] == "DEBIT",
    transactions["amount"],
    0
)


# --------------------------------------------------
# 4. Monthly financial summary
# --------------------------------------------------

monthly = (
    transactions
    .groupby(["account_id", "month"])
    .agg(
        monthly_income=("credit_amount", "sum"),
        monthly_expense=("debit_amount", "sum"),
        transaction_count=("amount", "count")
    )
    .reset_index()
)

monthly["monthly_surplus"] = (
    monthly["monthly_income"] - monthly["monthly_expense"]
)


# --------------------------------------------------
# 5. Income stability
# --------------------------------------------------

income_stats = (
    monthly
    .groupby("account_id")
    .agg(
        average_monthly_income=("monthly_income", "mean"),
        income_std=("monthly_income", "std"),
        minimum_monthly_income=("monthly_income", "min"),
        maximum_monthly_income=("monthly_income", "max")
    )
    .reset_index()
)

# Six-month salary is regular, therefore std can be NaN
# when only one observation exists.
income_stats["income_std"] = income_stats["income_std"].fillna(0)

income_stats["income_stability"] = np.where(
    income_stats["average_monthly_income"] > 0,
    1 - (
        income_stats["income_std"]
        / income_stats["average_monthly_income"]
    ),
    0
)

income_stats["income_stability"] = (
    income_stats["income_stability"]
    .clip(lower=0, upper=1)
)


# --------------------------------------------------
# 6. Expense category analysis
# --------------------------------------------------

expense_types = [
    "RENT",
    "EMI",
    "GROCERY",
    "UTILITY",
    "SHOPPING",
    "FOOD",
    "TRANSFER",
    "CASH_WITHDRAWAL",
    "INVESTMENT"
]

category_features = (
    transactions[
        transactions["transaction_type"].isin(expense_types)
    ]
    .groupby(["account_id", "transaction_type"])["amount"]
    .agg(["sum", "mean", "count"])
    .reset_index()
)


# --------------------------------------------------
# 7. Convert categories into columns
# --------------------------------------------------

category_sum = (
    category_features
    .pivot(
        index="account_id",
        columns="transaction_type",
        values="sum"
    )
    .fillna(0)
)

category_mean = (
    category_features
    .pivot(
        index="account_id",
        columns="transaction_type",
        values="mean"
    )
    .fillna(0)
)

category_count = (
    category_features
    .pivot(
        index="account_id",
        columns="transaction_type",
        values="count"
    )
    .fillna(0)
)


# Rename columns

category_sum.columns = [
    f"total_{c.lower()}" for c in category_sum.columns
]

category_mean.columns = [
    f"average_{c.lower()}" for c in category_mean.columns
]

category_count.columns = [
    f"{c.lower()}_count" for c in category_count.columns
]


# --------------------------------------------------
# 8. Overall transaction statistics
# --------------------------------------------------

overall = (
    transactions
    .groupby("account_id")
    .agg(
        total_transactions=("amount", "count"),
        total_credits=("credit_amount", "sum"),
        total_debits=("debit_amount", "sum")
    )
    .reset_index()
)

overall["average_transaction_amount"] = (
    transactions
    .groupby("account_id")["amount"]
    .mean()
    .values
)

overall["maximum_transaction_amount"] = (
    transactions
    .groupby("account_id")["amount"]
    .max()
    .values
)

overall["minimum_transaction_amount"] = (
    transactions
    .groupby("account_id")["amount"]
    .min()
    .values
)


# --------------------------------------------------
# 9. Merge all financial features
# --------------------------------------------------

features = overall.merge(
    income_stats,
    on="account_id",
    how="left"
)

features = features.merge(
    category_sum,
    on="account_id",
    how="left"
)

features = features.merge(
    category_mean,
    on="account_id",
    how="left"
)

features = features.merge(
    category_count,
    on="account_id",
    how="left"
)

# Replace missing category values with zero
features = features.fillna(0)


# --------------------------------------------------
# 10. Derived financial indicators
# --------------------------------------------------

features["average_monthly_expense"] = (
    features["total_debits"] / 6
)

features["average_monthly_surplus"] = (
    features["average_monthly_income"]
    - features["average_monthly_expense"]
)

features["emi_to_income_ratio"] = np.where(
    features["average_monthly_income"] > 0,
    features["average_emi"]
    / features["average_monthly_income"],
    0
)

features["savings_ratio"] = np.where(
    features["average_monthly_income"] > 0,
    features["average_monthly_surplus"]
    / features["average_monthly_income"],
    0
)

features["cash_withdrawal_ratio"] = np.where(
    features["total_debits"] > 0,
    features["total_cash_withdrawal"]
    / features["total_debits"],
    0
)

features["investment_ratio"] = np.where(
    features["total_debits"] > 0,
    features["total_investment"]
    / features["total_debits"],
    0
)


# --------------------------------------------------
# 11. Add applicant information
# --------------------------------------------------

features = features.merge(
    applicants,
    on="account_id",
    how="left"
)


# --------------------------------------------------
# 12. Final column ordering
# --------------------------------------------------

first_columns = [
    "account_id",
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
    "investment_ratio"
]

remaining_columns = [
    c for c in features.columns
    if c not in first_columns
]

features = features[
    first_columns + remaining_columns
]


# --------------------------------------------------
# 13. Save output
# --------------------------------------------------

features.to_csv(
    OUTPUT_FILE,
    index=False
)


# --------------------------------------------------
# 14. Validation
# --------------------------------------------------

print("\n========== VALIDATION ==========")

print("Account profiles:", len(features))
print("Unique accounts:", features["account_id"].nunique())

print(
    "Income stability range:",
    round(features["income_stability"].min(), 4),
    "to",
    round(features["income_stability"].max(), 4)
)

print("\nSample features:")
print(
    features[
        [
            "account_id",
            "average_monthly_income",
            "average_monthly_expense",
            "average_monthly_surplus",
            "emi_to_income_ratio",
            "savings_ratio",
            "income_stability"
        ]
    ].head(10).to_string(index=False)
)

print("\nOutput saved to:")
print(OUTPUT_FILE)

print("\n========== ANALYSIS COMPLETE ==========")