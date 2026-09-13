import pandas as pd
import numpy as np


INPUT_FILE = r"data\processed\synthetic_statement_features.csv"
OUTPUT_FILE = r"data\processed\bank_statement_rule_results.csv"


print("========== BANK STATEMENT RULE ENGINE ==========")


# --------------------------------------------------
# 1. Load features
# --------------------------------------------------

df = pd.read_csv(INPUT_FILE)

print("Profiles loaded:", len(df))


# --------------------------------------------------
# 2. Rule evaluation functions
# --------------------------------------------------

def evaluate_income_stability(value):
    if value >= 0.80:
        return "STRONG"
    elif value >= 0.60:
        return "MODERATE"
    else:
        return "WEAK"


def evaluate_surplus(value):
    if value > 30000:
        return "STRONG"
    elif value > 10000:
        return "MODERATE"
    elif value > 0:
        return "LOW"
    else:
        return "DEFICIT"


def evaluate_emi_ratio(value):
    if value <= 0.20:
        return "LOW"
    elif value <= 0.30:
        return "MODERATE"
    elif value <= 0.40:
        return "HIGH"
    else:
        return "VERY_HIGH"


def evaluate_savings_ratio(value):
    if value >= 0.30:
        return "STRONG"
    elif value >= 0.20:
        return "MODERATE"
    elif value > 0:
        return "LOW"
    else:
        return "NEGATIVE"


def evaluate_expense_burden(income, expense):
    if income <= 0:
        return "UNKNOWN"

    ratio = expense / income

    if ratio <= 0.60:
        return "LOW"
    elif ratio <= 0.75:
        return "MODERATE"
    elif ratio <= 1.00:
        return "HIGH"
    else:
        return "EXCESSIVE"


def evaluate_cash_withdrawal(value):
    if value <= 0.05:
        return "LOW"
    elif value <= 0.15:
        return "MODERATE"
    else:
        return "HIGH"


# --------------------------------------------------
# 3. Apply rules
# --------------------------------------------------

df["income_stability_status"] = (
    df["income_stability"]
    .apply(evaluate_income_stability)
)

df["surplus_status"] = (
    df["average_monthly_surplus"]
    .apply(evaluate_surplus)
)

df["emi_status"] = (
    df["emi_to_income_ratio"]
    .apply(evaluate_emi_ratio)
)

df["savings_status"] = (
    df["savings_ratio"]
    .apply(evaluate_savings_ratio)
)

df["expense_burden_status"] = df.apply(
    lambda row: evaluate_expense_burden(
        row["average_monthly_income"],
        row["average_monthly_expense"]
    ),
    axis=1
)

df["cash_withdrawal_status"] = (
    df["cash_withdrawal_ratio"]
    .apply(evaluate_cash_withdrawal)
)


# --------------------------------------------------
# 4. Financial warning flags
# --------------------------------------------------

df["negative_surplus_flag"] = (
    df["average_monthly_surplus"] < 0
).astype(int)

df["low_surplus_flag"] = (
    (df["average_monthly_surplus"] >= 0)
    & (df["average_monthly_surplus"] <= 10000)
).astype(int)

df["high_emi_flag"] = (
    df["emi_to_income_ratio"] > 0.30
).astype(int)

df["negative_savings_flag"] = (
    df["savings_ratio"] <= 0
).astype(int)

df["low_savings_flag"] = (
    (df["savings_ratio"] > 0)
    & (df["savings_ratio"] < 0.10)
).astype(int)

df["excessive_expense_flag"] = (
    df["average_monthly_expense"]
    > df["average_monthly_income"]
).astype(int)

df["high_cash_withdrawal_flag"] = (
    df["cash_withdrawal_ratio"] > 0.15
).astype(int)


# --------------------------------------------------
# 5. Count financial risk indicators
# --------------------------------------------------

risk_flags = [
    "negative_surplus_flag",
    "low_surplus_flag",
    "high_emi_flag",
    "negative_savings_flag",
    "low_savings_flag",
    "excessive_expense_flag",
    "high_cash_withdrawal_flag"
]

df["financial_risk_flag_count"] = (
    df[risk_flags].sum(axis=1)
)


# --------------------------------------------------
# 6. Overall financial health
# --------------------------------------------------

def determine_financial_health(row):

    risks = row["financial_risk_flag_count"]

    if risks >= 3:
        return "HIGH_RISK"

    if risks >= 1:
        return "MODERATE_RISK"

    return "HEALTHY"


df["financial_health"] = (
    df.apply(determine_financial_health, axis=1)
)


# --------------------------------------------------
# 7. Rule evidence text
# --------------------------------------------------

def build_evidence(row):

    evidence = []

    evidence.append(
        f"Average monthly income is "
        f"INR {row['average_monthly_income']:.2f}."
    )

    evidence.append(
        f"Average monthly expense is "
        f"INR {row['average_monthly_expense']:.2f}."
    )

    evidence.append(
        f"Average monthly surplus is "
        f"INR {row['average_monthly_surplus']:.2f}."
    )

    evidence.append(
        f"EMI-to-income ratio is "
        f"{row['emi_to_income_ratio'] * 100:.2f}%."
    )

    evidence.append(
        f"Savings ratio is "
        f"{row['savings_ratio'] * 100:.2f}%."
    )

    evidence.append(
        f"Income stability is "
        f"{row['income_stability']:.2f}."
    )

    if row["negative_surplus_flag"] == 1:
        evidence.append(
            "Monthly expenses exceed monthly income."
        )

    if row["negative_savings_flag"] == 1:
        evidence.append(
            "Savings ratio is negative or zero."
        )

    if row["high_emi_flag"] == 1:
        evidence.append(
            "EMI burden exceeds the defined 30% threshold."
        )
    if row["low_surplus_flag"] == 1:
        evidence.append(
            "Monthly surplus is low and provides limited repayment buffer."
    )

    if row["low_savings_flag"] == 1:
        evidence.append(
            "Savings ratio is below the defined 10% threshold."
    )

    return " ".join(evidence)

df["evidence_summary"] = df.apply(
    build_evidence,
    axis=1
)


# --------------------------------------------------
# 8. Save results
# --------------------------------------------------

df.to_csv(
    OUTPUT_FILE,
    index=False
)


# --------------------------------------------------
# 9. Validation
# --------------------------------------------------

print("\n========== RULE VALIDATION ==========")

print("\nFinancial health:")
print(
    df["financial_health"]
    .value_counts()
    .to_string()
)

print("\nRisk flag count:")
print(
    df["financial_risk_flag_count"]
    .value_counts()
    .sort_index()
    .to_string()
)

print("\nApplicant results:")

print(
    df[
        [
            "applicant_id",
            "average_monthly_income",
            "average_monthly_expense",
            "average_monthly_surplus",
            "emi_to_income_ratio",
            "savings_ratio",
            "financial_risk_flag_count",
            "financial_health"
        ]
    ].to_string(index=False)
)

print("\nOutput saved to:")
print(OUTPUT_FILE)

print("\n========== RULE ENGINE COMPLETE ==========")