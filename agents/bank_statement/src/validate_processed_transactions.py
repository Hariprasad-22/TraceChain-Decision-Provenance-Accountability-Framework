import pandas as pd

file_path = "data/processed/processed_transactions.csv"

print("Loading processed transactions...")

df = pd.read_csv(file_path)

print("\n================================")
print("PROCESSED DATA VALIDATION")
print("================================")

# 1. Number of rows
print(f"Total transactions: {len(df)}")

# 2. Columns
print("\nColumns:")
print(df.columns.tolist())

# 3. Missing sender IDs
print(f"\nMissing sender IDs: {df['sender_account_id'].isna().sum()}")

# 4. Missing receiver IDs
print(f"Missing receiver IDs: {df['receiver_account_id'].isna().sum()}")

# 5. Unique sender IDs
print(f"Unique sender IDs: {df['sender_account_id'].nunique()}")

# 6. Unique receiver IDs
print(f"Unique receiver IDs: {df['receiver_account_id'].nunique()}")

# 7. Duplicate rows
print(f"Duplicate transactions: {df.duplicated().sum()}")

# 8. Show sample
print("\nSample transactions:")
print(df.head(5).to_string(index=False))

print("\n================================")
print("VALIDATION COMPLETE")
print("================================")
