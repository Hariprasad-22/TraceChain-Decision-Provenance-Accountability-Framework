import pandas as pd
import random
import os
from datetime import datetime
from dateutil.relativedelta import relativedelta

INPUT_FILE = "synthetic_data/applications.csv"
OUTPUT_FILE = "synthetic_data/bank_transactions.csv"

random.seed(42)

applicants = pd.read_csv(INPUT_FILE)

transactions = []

start_date = datetime(2022, 1, 1)

for _, applicant in applicants.iterrows():

    account_id = int(applicant["account_id"])
    salary = int(applicant["monthly_salary"])

    # Generate 6 months
    for month in range(6):

        current_month = start_date + relativedelta(months=month)

        # -------------------------
        # SALARY
        # -------------------------
        salary_date = current_month.replace(day=1)

        transactions.append({
            "account_id": account_id,
            "date": salary_date.strftime("%Y-%m-%d"),
            "transaction_type": "SALARY",
            "description": "Monthly Salary",
            "amount": salary,
            "transaction_direction": "CREDIT"
        })

        # -------------------------
        # RENT
        # -------------------------
        rent = random.randint(10000, 18000)

        transactions.append({
            "account_id": account_id,
            "date": current_month.replace(day=5).strftime("%Y-%m-%d"),
            "transaction_type": "RENT",
            "description": "Monthly House Rent",
            "amount": rent,
            "transaction_direction": "DEBIT"
        })

        # -------------------------
        # EXISTING EMI
        # -------------------------
        emi = random.randint(5000, 12000)

        transactions.append({
            "account_id": account_id,
            "date": current_month.replace(day=7).strftime("%Y-%m-%d"),
            "transaction_type": "EMI",
            "description": "Existing Loan EMI",
            "amount": emi,
            "transaction_direction": "DEBIT"
        })

        # -------------------------
        # GROCERY
        # -------------------------
        grocery = random.randint(3000, 6000)

        transactions.append({
            "account_id": account_id,
            "date": current_month.replace(day=10).strftime("%Y-%m-%d"),
            "transaction_type": "GROCERY",
            "description": "Grocery Purchase",
            "amount": grocery,
            "transaction_direction": "DEBIT"
        })

        # -------------------------
        # UTILITIES
        # -------------------------
        utility = random.randint(1500, 3500)

        transactions.append({
            "account_id": account_id,
            "date": current_month.replace(day=12).strftime("%Y-%m-%d"),
            "transaction_type": "UTILITY",
            "description": "Electricity / Internet / Bills",
            "amount": utility,
            "transaction_direction": "DEBIT"
        })

        # -------------------------
        # SHOPPING
        # -------------------------
        shopping = random.randint(1000, 5000)

        transactions.append({
            "account_id": account_id,
            "date": current_month.replace(day=15).strftime("%Y-%m-%d"),
            "transaction_type": "SHOPPING",
            "description": "Shopping",
            "amount": shopping,
            "transaction_direction": "DEBIT"
        })

        # -------------------------
        # FOOD
        # -------------------------
        food = random.randint(2000, 5000)

        transactions.append({
            "account_id": account_id,
            "date": current_month.replace(day=18).strftime("%Y-%m-%d"),
            "transaction_type": "FOOD",
            "description": "Food / Dining",
            "amount": food,
            "transaction_direction": "DEBIT"
        })

        # -------------------------
        # TRANSFER
        # -------------------------
        transfer = random.randint(1000, 5000)

        transactions.append({
            "account_id": account_id,
            "date": current_month.replace(day=20).strftime("%Y-%m-%d"),
            "transaction_type": "TRANSFER",
            "description": "Personal Transfer",
            "amount": transfer,
            "transaction_direction": "DEBIT"
        })

        # -------------------------
        # CASH WITHDRAWAL
        # -------------------------
        cash = random.randint(1000, 4000)

        transactions.append({
            "account_id": account_id,
            "date": current_month.replace(day=22).strftime("%Y-%m-%d"),
            "transaction_type": "CASH_WITHDRAWAL",
            "description": "ATM Cash Withdrawal",
            "amount": cash,
            "transaction_direction": "DEBIT"
        })

        # -------------------------
        # INVESTMENT
        # -------------------------
        investment = random.randint(1000, 5000)

        transactions.append({
            "account_id": account_id,
            "date": current_month.replace(day=25).strftime("%Y-%m-%d"),
            "transaction_type": "INVESTMENT",
            "description": "Monthly Investment",
            "amount": investment,
            "transaction_direction": "DEBIT"
        })


# Convert to DataFrame
df = pd.DataFrame(transactions)

# Sort
df = df.sort_values(["account_id", "date"])

# Create directory
os.makedirs("synthetic_data", exist_ok=True)

# Save
df.to_csv(OUTPUT_FILE, index=False)

print("================================")
print("BANK STATEMENTS GENERATED")
print("================================")

print(f"Applicants: {applicants['account_id'].nunique()}")
print(f"Months per applicant: 6")
print(f"Total transactions: {len(df)}")

print("\nTransaction types:")
print(df["transaction_type"].value_counts().to_string())

print("\nSaved to:")
print(OUTPUT_FILE)