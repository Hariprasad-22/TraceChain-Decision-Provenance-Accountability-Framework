import pandas as pd


INPUT_FILE = r"data\processed\bank_statement_rule_results.csv"
OUTPUT_FILE = r"data\processed\bank_statement_agent_decisions.csv"


print("========== BANK STATEMENT AGENT ==========")


# --------------------------------------------------
# 1. Load rule results
# --------------------------------------------------

df = pd.read_csv(INPUT_FILE)

print("Profiles loaded:", len(df))


# --------------------------------------------------
# 2. Calculate agent score
# --------------------------------------------------

def calculate_score(row):
    score = 100

    # Surplus
    if row["negative_surplus_flag"] == 1:
        score -= 35
    elif row["low_surplus_flag"] == 1:
        score -= 15

    # Savings
    if row["negative_savings_flag"] == 1:
        score -= 25
    elif row["low_savings_flag"] == 1:
        score -= 10

    # EMI burden
    if row["high_emi_flag"] == 1:
        score -= 20

    # Expense burden
    if row["excessive_expense_flag"] == 1:
        score -= 20

    # Cash withdrawal
    if row["high_cash_withdrawal_flag"] == 1:
        score -= 10

    return max(0, score)


df["agent_score"] = df.apply(
    calculate_score,
    axis=1
)


# --------------------------------------------------
# 3. Determine decision
# --------------------------------------------------

def determine_decision(row):

    score = row["agent_score"]

    if score >= 80:
        return "ELIGIBLE"

    elif score >= 60:
        return "REVIEW"

    return "NOT_ELIGIBLE"


df["decision_output"] = df.apply(
    determine_decision,
    axis=1
)


# --------------------------------------------------
# 4. Confidence
# --------------------------------------------------

df["confidence_score"] = (
    df["agent_score"] / 100
).round(2)


# --------------------------------------------------
# 5. Generate reasoning
# --------------------------------------------------

def generate_reasoning(row):

    reasons = []

    income = row["average_monthly_income"]
    expense = row["average_monthly_expense"]
    surplus = row["average_monthly_surplus"]
    emi_ratio = row["emi_to_income_ratio"]
    savings_ratio = row["savings_ratio"]
    stability = row["income_stability"]

    reasons.append(
        f"Six-month bank statement analysis shows "
        f"average monthly income of INR {income:.2f} "
        f"and average monthly expenses of INR {expense:.2f}."
    )

    reasons.append(
        f"Average monthly surplus is INR {surplus:.2f}."
    )

    reasons.append(
        f"EMI-to-income ratio is {emi_ratio * 100:.2f}% "
        f"and savings ratio is {savings_ratio * 100:.2f}%."
    )

    reasons.append(
        f"Income stability score is {stability:.2f}."
    )

    if row["negative_surplus_flag"] == 1:
        reasons.append(
            "The applicant has a negative monthly surplus, "
            "indicating that expenses exceed income."
        )

    elif row["low_surplus_flag"] == 1:
        reasons.append(
            "The applicant has a low monthly surplus, "
            "providing a limited repayment buffer."
        )

    if row["negative_savings_flag"] == 1:
        reasons.append(
            "The savings ratio is negative or zero."
        )

    elif row["low_savings_flag"] == 1:
        reasons.append(
            "The savings ratio is below the defined threshold."
        )

    if row["high_emi_flag"] == 1:
        reasons.append(
            "The EMI burden is above the defined risk threshold."
        )

    if row["excessive_expense_flag"] == 1:
        reasons.append(
            "Monthly expenses exceed monthly income."
        )

    if row["high_cash_withdrawal_flag"] == 1:
        reasons.append(
            "Cash withdrawal activity is relatively high."
        )

    decision = row["decision_output"]

    if decision == "ELIGIBLE":
        reasons.append(
            "Overall bank statement indicators support "
            "repayment affordability."
        )

    elif decision == "REVIEW":
        reasons.append(
            "The applicant shows some financial concerns "
            "and should undergo further review."
        )

    else:
        reasons.append(
            "The observed financial position does not "
            "support sufficient repayment affordability."
        )

    return " ".join(reasons)


df["reasoning"] = df.apply(
    generate_reasoning,
    axis=1
)


# --------------------------------------------------
# 6. Evidence summary
# --------------------------------------------------

def generate_evidence(row):

    evidence = [
        f"Average monthly income: INR "
        f"{row['average_monthly_income']:.2f}",

        f"Average monthly expense: INR "
        f"{row['average_monthly_expense']:.2f}",

        f"Average monthly surplus: INR "
        f"{row['average_monthly_surplus']:.2f}",

        f"EMI-to-income ratio: "
        f"{row['emi_to_income_ratio'] * 100:.2f}%",

        f"Savings ratio: "
        f"{row['savings_ratio'] * 100:.2f}%",

        f"Income stability: "
        f"{row['income_stability']:.2f}",

        f"Financial risk flags: "
        f"{int(row['financial_risk_flag_count'])}"
    ]

    return " | ".join(evidence)


df["evidence_summary"] = df.apply(
    generate_evidence,
    axis=1
)


# --------------------------------------------------
# 7. Select final agent output
# --------------------------------------------------

output_columns = [
    "account_id",
    "employment_type",
    "monthly_salary",
    "cibil_score",
    "financial_health",
    "financial_risk_flag_count",
    "agent_score",
    "decision_output",
    "confidence_score",
    "reasoning",
    "evidence_summary"
]

result = df[output_columns]


# --------------------------------------------------
# 8. Save
# --------------------------------------------------

result.to_csv(
    OUTPUT_FILE,
    index=False
)


# --------------------------------------------------
# 9. Validation
# --------------------------------------------------

print("\n========== AGENT DECISION VALIDATION ==========")

print("\nDecision distribution:")
print(
    result["decision_output"]
    .value_counts()
    .to_string()
)

print("\nApplicant decisions:")

print(
    result[
        [
            "account_id",
            "financial_health",
            "agent_score",
            "decision_output",
            "confidence_score"
        ]
    ].to_string(index=False)
)

print("\n========== SAMPLE REASONING ==========")

sample = result[result["account_id"] == 100008]

if not sample.empty:
    print(sample["reasoning"].iloc[0])

print("\n========== SAMPLE EVIDENCE ==========")

if not sample.empty:
    print(sample["evidence_summary"].iloc[0])

print("\nOutput saved to:")
print(OUTPUT_FILE)

print("\n========== BANK STATEMENT AGENT COMPLETE ==========")