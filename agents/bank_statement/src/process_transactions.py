import pandas as pd

TRANS_PATH = "data/raw/HI-Small_Trans.csv"
MAP_PATH = "data/processed/account_mapping.csv"
OUTPUT_PATH = "data/processed/processed_transactions.csv"


print("Loading account mapping...")

mapping = pd.read_csv(MAP_PATH)

account_lookup = dict(
    zip(
        mapping["Account Number"],
        mapping["account_id"]
    )
)


print("Reading transaction data...")

# Read the transaction file in chunks
chunks = []

for chunk in pd.read_csv(
    TRANS_PATH,
    chunksize=100000
):

    # Convert account numbers to internal IDs
    chunk["sender_account_id"] = chunk["Account"].map(
        account_lookup
    )

    chunk["receiver_account_id"] = chunk["Account.1"].map(
        account_lookup
    )

    # Convert timestamp
    chunk["Timestamp"] = pd.to_datetime(
        chunk["Timestamp"]
    )

    chunks.append(chunk)

    print(
        f"Processed {len(chunk)} transactions..."
    )


# Combine processed chunks
transactions = pd.concat(
    chunks,
    ignore_index=True
)


# Save
transactions.to_csv(
    OUTPUT_PATH,
    index=False
)


print("\n================================")
print("TRANSACTION PROCESSING COMPLETE")
print("================================")

print(
    "Total transactions:",
    len(transactions)
)

print(
    "Missing sender IDs:",
    transactions["sender_account_id"].isna().sum()
)

print(
    "Missing receiver IDs:",
    transactions["receiver_account_id"].isna().sum()
)

print("\nSaved to:")
print(OUTPUT_PATH)