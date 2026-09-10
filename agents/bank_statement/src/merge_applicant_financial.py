import pandas as pd

# File paths
applicant_file = r"data\processed\applicant_master.csv"
financial_file = r"data\processed\financial_features.csv"

# Read both files
applicants = pd.read_csv(applicant_file)
financial = pd.read_csv(financial_file)

# Merge using account_id
merged = pd.merge(
    applicants,
    financial,
    on="account_id",
    how="inner"
)

# Save the merged file
output_file = r"data\processed\applicant_financial_profile.csv"
merged.to_csv(output_file, index=False)

# Display result
print("========== MERGE RESULT ==========")
print("Applicants:", len(applicants))
print("Financial records:", len(financial))
print("Merged records:", len(merged))

print("\nMerged data:")
print(merged.to_string(index=False))

print("\nSaved to:")
print(output_file)