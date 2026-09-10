import pandas as pd


TRANS_PATH = "data/raw/HI-Small_Trans.csv"
MAP_PATH = "data/processed/account_mapping.csv"


# Read sample transactions
trans = pd.read_csv(
    TRANS_PATH,
    nrows=10000
)


# Read mapping
mapping = pd.read_csv(
    MAP_PATH
)


# Create lookup dictionary
account_lookup = dict(
    zip(
        mapping["Account Number"],
        mapping["account_id"]
    )
)


# Map sender and receiver
trans["sender_account_id"] = trans["Account"].map(
    account_lookup
)

trans["receiver_account_id"] = trans["Account.1"].map(
    account_lookup
)


print("========== MAPPING TEST ==========")

print("Transactions:", len(trans))

print(
    "Sender IDs missing:",
    trans["sender_account_id"].isna().sum()
)

print(
    "Receiver IDs missing:",
    trans["receiver_account_id"].isna().sum()
)


print("\n========== SAMPLE ==========")

print(
    trans[
        [
            "Account",
            "sender_account_id",
            "Account.1",
            "receiver_account_id"
        ]
    ].head(10).to_string(index=False)
)