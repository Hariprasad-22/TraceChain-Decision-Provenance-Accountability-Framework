import pandas as pd
import os

INPUT_FILE = "data/processed/account_wise_transactions.csv"
OUTPUT_FILE = "data/processed/classified_transactions.csv"

print("Loading account-wise transactions...")

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
    "receiver_account_id",
    "account_id",
    "transaction_role"
]

df = pd.read_csv(
    INPUT_FILE,
    usecols=columns
)

print(f"Loaded records: {len(df)}")


# ============================================================
# 1. TRANSACTION DIRECTION
# ============================================================

df["transaction_direction"] = df["transaction_role"].map({
    "SENDER": "DEBIT",
    "RECEIVER": "CREDIT"
})


# ============================================================
# 2. TRANSACTION TYPE
# ============================================================

df["transaction_type"] = df["Payment Format"].map({
    "Cash": "CASH",
    "Cheque": "CHEQUE",
    "ACH": "ACH_TRANSFER",
    "Wire": "WIRE_TRANSFER",
    "Credit Card": "CREDIT_CARD",
    "Bitcoin": "CRYPTO",
    "Reinvestment": "REINVESTMENT"
})

df["transaction_type"] = df["transaction_type"].fillna("OTHER")


# ============================================================
# 3. TRANSACTION FLAGS
# ============================================================

df["cash_flag"] = (
    df["Payment Format"] == "Cash"
).astype(int)

df["cheque_flag"] = (
    df["Payment Format"] == "Cheque"
).astype(int)

df["transfer_flag"] = (
    df["Payment Format"].isin(["ACH", "Wire"])
).astype(int)

df["digital_payment_flag"] = (
    df["Payment Format"].isin(
        ["Credit Card", "ACH", "Wire"]
    )
).astype(int)

df["crypto_flag"] = (
    df["Payment Format"] == "Bitcoin"
).astype(int)

df["reinvestment_flag"] = (
    df["Payment Format"] == "Reinvestment"
).astype(int)


# ============================================================
# 4. LAUNDERING FLAG
# ============================================================

df["laundering_flag"] = (
    df["Is Laundering"].astype(int)
)


# ============================================================
# 5. VALIDATION
# ============================================================

print("\n================================")
print("TRANSACTION CLASSIFICATION")
print("================================")

print("\nTransaction direction:")
print(
    df["transaction_direction"]
    .value_counts(dropna=False)
    .to_string()
)

print("\nTransaction type:")
print(
    df["transaction_type"]
    .value_counts(dropna=False)
    .to_string()
)

print("\nMissing classifications:")

print(
    "Direction:",
    df["transaction_direction"].isna().sum()
)

print(
    "Type:",
    df["transaction_type"].isna().sum()
)


# ============================================================
# 6. SAVE
# ============================================================

os.makedirs(
    os.path.dirname(OUTPUT_FILE),
    exist_ok=True
)

df.to_csv(
    OUTPUT_FILE,
    index=False
)


print("\n================================")
print("TRANSACTION CLASSIFICATION COMPLETE")
print("================================")

print(
    "Total classified records:",
    len(df)
)

print("\nSaved to:")
print(OUTPUT_FILE)