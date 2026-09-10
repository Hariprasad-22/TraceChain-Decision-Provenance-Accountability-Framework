import pandas as pd
import os

INPUT_FILE = "data/processed/processed_transactions.csv"
OUTPUT_FILE = "data/processed/account_wise_transactions.csv"

print("Loading processed transactions...")

# Read only required columns
columns = [
    "Timestamp",
    "Account",
    "Account.1",
    "Amount Received",
    "Receiving Currency",
    "Amount Paid",
    "Payment Currency",
    "Payment Format",
    "Is Laundering",
    "sender_account_id",
    "receiver_account_id"
]

df = pd.read_csv(INPUT_FILE, usecols=columns)

# Convert timestamp
df["Timestamp"] = pd.to_datetime(df["Timestamp"])

# Create two views:
# 1. Sender-side transaction
sender = df.copy()
sender["account_id"] = sender["sender_account_id"]
sender["transaction_role"] = "SENDER"

# 2. Receiver-side transaction
receiver = df.copy()
receiver["account_id"] = receiver["receiver_account_id"]
receiver["transaction_role"] = "RECEIVER"

# Combine both
account_transactions = pd.concat(
    [sender, receiver],
    ignore_index=True
)

# Sort by account and timestamp
account_transactions = account_transactions.sort_values(
    ["account_id", "Timestamp"]
)

# Save
os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

account_transactions.to_csv(
    OUTPUT_FILE,
    index=False
)

print("\n================================")
print("ACCOUNT-WISE HISTORY COMPLETE")
print("================================")

print(f"Original transactions: {len(df)}")
print(f"Account-wise records: {len(account_transactions)}")
print(f"Unique accounts: {account_transactions['account_id'].nunique()}")

print("\nSaved to:")
print(OUTPUT_FILE)