import pandas as pd

ACCOUNT_PATH = "data/raw/HI-Small_accounts.csv"
OUTPUT_PATH = "data/processed/account_mapping.csv"


# Read accounts
accounts = pd.read_csv(
    ACCOUNT_PATH,
    usecols=[
        "Bank Name",
        "Bank ID",
        "Account Number",
        "Entity ID",
        "Entity Name"
    ]
)


# Remove duplicate account numbers
accounts = accounts.drop_duplicates(
    subset=["Account Number"]
).reset_index(drop=True)


# Create internal account IDs
accounts["account_id"] = range(
    100001,
    100001 + len(accounts)
)


# Put account_id first
accounts = accounts[
    [
        "account_id",
        "Account Number",
        "Bank Name",
        "Bank ID",
        "Entity ID",
        "Entity Name"
    ]
]


# Save mapping
accounts.to_csv(
    OUTPUT_PATH,
    index=False
)


print("Account mapping created successfully!")

print("Total unique accounts:",
      len(accounts))

print("\nFirst 10 mappings:")
print(accounts.head(10).to_string(index=False))

print("\nSaved to:")
print(OUTPUT_PATH)