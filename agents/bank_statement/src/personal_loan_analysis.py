import pandas as pd
import os

# ============================================================
# FILE PATHS
# ============================================================

INPUT_FILE = "data/processed/applicant_financial_profile.csv"
OUTPUT_FILE = "data/processed/personal_loan_analysis.csv"

print("Loading applicant financial profiles...")

df = pd.read_csv(INPUT_FILE)

print(f"Applicants loaded: {len(df)}")


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def cibil_score(cibil):
    if cibil >= 750:
        return 100
    elif cibil >= 700:
        return 80
    elif cibil >= 650:
        return 60
    elif cibil >= 600:
        return 40
    else:
        return 20


def emi_score(ratio):
    if ratio <= 0.20:
        return 100
    elif ratio <= 0.30:
        return 80
    elif ratio <= 0.40:
        return 60
    elif ratio <= 0.50:
        return 40
    else:
        return 20


def surplus_score(surplus):
    if surplus > 30000:
        return 100
    elif surplus > 20000:
        return 80
    elif surplus > 10000:
        return 60
    elif surplus > 0:
        return 40
    else:
        return 20


def savings_score(ratio):
    if ratio >= 0.30:
        return 100
    elif ratio >= 0.20:
        return 80
    elif ratio >= 0.10:
        return 60
    elif ratio > 0:
        return 40
    else:
        return 20


def stability_score(stability):
    if stability >= 0.80:
        return 100
    elif stability >= 0.60:
        return 80
    elif stability >= 0.40:
        return 60
    elif stability > 0:
        return 40
    else:
        return 20


# ============================================================
# INDIVIDUAL SCORES
# ============================================================

df["cibil_component"] = df["cibil_score"].apply(
    cibil_score
)

df["emi_component"] = df["emi_to_income_ratio"].apply(
    emi_score
)

df["surplus_component"] = df["monthly_surplus"].apply(
    surplus_score
)

df["savings_component"] = df["savings_ratio"].apply(
    savings_score
)

df["stability_component"] = df["income_stability"].apply(
    stability_score
)


# ============================================================
# PERSONAL LOAN AFFORDABILITY SCORE
# ============================================================

df["loan_affordability_score"] = (
    df["cibil_component"] * 0.30
    + df["emi_component"] * 0.25
    + df["surplus_component"] * 0.20
    + df["savings_component"] * 0.15
    + df["stability_component"] * 0.10
)


# ============================================================
# AFFORDABILITY LEVEL
# ============================================================

def affordability_level(score):
    if score >= 80:
        return "HIGH"
    elif score >= 60:
        return "MEDIUM"
    else:
        return "LOW"


df["affordability_level"] = (
    df["loan_affordability_score"]
    .apply(affordability_level)
)


# ============================================================
# LOAN RECOMMENDATION
# ============================================================

def loan_recommendation(row):

    if (
        row["loan_affordability_score"] >= 80
        and row["monthly_surplus"] > 0
    ):
        return "ELIGIBLE"

    elif (
        row["loan_affordability_score"] >= 60
        and row["monthly_surplus"] > 0
    ):
        return "REVIEW"

    else:
        return "NOT_ELIGIBLE"


df["loan_recommendation"] = df.apply(
    loan_recommendation,
    axis=1
)


# ============================================================
# REASONING
# ============================================================

def generate_reasoning(row):

    reasons = []

    if row["cibil_score"] >= 750:
        reasons.append("strong CIBIL score")
    elif row["cibil_score"] < 650:
        reasons.append("low CIBIL score")

    if row["emi_to_income_ratio"] <= 0.20:
        reasons.append("low existing EMI burden")
    elif row["emi_to_income_ratio"] > 0.40:
        reasons.append("high existing EMI burden")

    if row["monthly_surplus"] > 0:
        reasons.append("positive monthly surplus")
    else:
        reasons.append("negative monthly surplus")

    if row["savings_ratio"] >= 0.20:
        reasons.append("healthy savings ratio")
    elif row["savings_ratio"] <= 0:
        reasons.append("negative savings ratio")

    if row["income_stability"] >= 0.80:
        reasons.append("stable income")

    return "; ".join(reasons)


df["reasoning"] = df.apply(
    generate_reasoning,
    axis=1
)


# ============================================================
# CONFIDENCE SCORE
# ============================================================

df["confidence_score"] = (
    df["loan_affordability_score"] / 100
)


# ============================================================
# SAVE USEFUL COLUMNS
# ============================================================

output_columns = [
    "applicant_id",
    "name",
    "account_id",
    "employment_type",
    "monthly_salary",
    "cibil_score",
    "average_monthly_income",
    "average_monthly_expense",
    "average_existing_emi",
    "monthly_surplus",
    "emi_to_income_ratio",
    "savings_ratio",
    "income_stability",
    "loan_affordability_score",
    "affordability_level",
    "loan_recommendation",
    "confidence_score",
    "reasoning"
]

result = df[output_columns].copy()


# ============================================================
# SAVE
# ============================================================

os.makedirs(
    os.path.dirname(OUTPUT_FILE),
    exist_ok=True
)

result.to_csv(
    OUTPUT_FILE,
    index=False
)


# ============================================================
# DISPLAY RESULTS
# ============================================================

print("\n================================")
print("PERSONAL LOAN ANALYSIS COMPLETE")
print("================================")

print(
    "Applicants analyzed:",
    len(result)
)

print("\nRecommendations:")

print(
    result["loan_recommendation"]
    .value_counts()
    .to_string()
)

print("\nApplicant results:")

print(
    result.to_string(index=False)
)

print("\nSaved to:")
print(OUTPUT_FILE)