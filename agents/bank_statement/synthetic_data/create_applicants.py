import pandas as pd
import os

OUTPUT_FILE = "synthetic_data/applications.csv"

# Create synthetic personal-loan applicants
applicants = [
    {
        "account_id": 100001,
        "employment_type": "Private Salaried Employee",
        "monthly_salary": 60000,
        "cibil_score": 760
    },
    {
        "account_id": 100002,
        "employment_type": "Govt Job",
        "monthly_salary": 70000,
        "cibil_score": 790
    },
    {
        "account_id": 100003,
        "employment_type": "Private Salaried Employee",
        "monthly_salary": 45000,
        "cibil_score": 680
    },
    {
        "account_id": 100004,
        "employment_type": "Govt Job",
        "monthly_salary": 85000,
        "cibil_score": 820
    },
    {
        "account_id": 100005,
        "employment_type": "Private Salaried Employee",
        "monthly_salary": 55000,
        "cibil_score": 720
    },
    {
        "account_id": 100006,
        "employment_type": "Govt Job",
        "monthly_salary": 50000,
        "cibil_score": 740
    },
    {
        "account_id": 100007,
        "employment_type": "Private Salaried Employee",
        "monthly_salary": 90000,
        "cibil_score": 810
    },
    {
        "account_id": 100008,
        "employment_type": "Private Salaried Employee",
        "monthly_salary": 40000,
        "cibil_score": 650
    },
    {
        "account_id": 100009,
        "employment_type": "Govt Job",
        "monthly_salary": 65000,
        "cibil_score": 770
    },
    {
        "account_id": 100010,
        "employment_type": "Private Salaried Employee",
        "monthly_salary": 75000,
        "cibil_score": 730
    }
]

df = pd.DataFrame(applicants)

os.makedirs("synthetic_data", exist_ok=True)

df.to_csv(OUTPUT_FILE, index=False)

print("================================")
print("APPLICANT DATA CREATED")
print("================================")

print(f"Total applicants: {len(df)}")

print("\nApplicant data:")
print(df.to_string(index=False))

print(f"\nSaved to:")
print(OUTPUT_FILE)