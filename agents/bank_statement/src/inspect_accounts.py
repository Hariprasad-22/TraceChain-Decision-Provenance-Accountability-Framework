import pandas as pd

TRANS_PATH = "data/raw/HI-Small_Trans.csv"
ACCOUNT_PATH = "data/raw/HI-Small_accounts.csv"


# Read only a small portion first
trans = pd.read_csv(
    TRANS_PATH,
    nrows=10000
)

accounts = pd.read_csv(
    ACCOUNT_PATH
)


print("========== TRANSACTIONS ==========")

print("Number of sample transactions:", len(trans))

print("Unique sender accounts:",
      trans["Account"].nunique())

print("Unique receiver accounts:",
      trans["Account.1"].nunique())


print("\n========== ACCOUNTS FILE ==========")

print("Number of accounts:", len(accounts))

print("Unique Account Numbers:",
      accounts["Account Number"].nunique())


print("\n========== SAMPLE ACCOUNT NUMBERS ==========")

print(accounts["Account Number"].head(10).tolist())


print("\n========== SAMPLE TRANSACTION ACCOUNTS ==========")

print(trans["Account"].head(10).tolist())