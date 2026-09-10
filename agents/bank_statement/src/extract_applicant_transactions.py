import pandas as pd

# ==============================
# FILE PATHS
# ==============================

applicant_file = r"data\processed\applicant_financial_profile.csv"
mapping_file = r"data\processed\account_mapping.csv"
transaction_file = r"data\raw\HI-Small_Trans.csv"

output_file = r"data\processed\applicant_transactions.csv"


# ==============================
# LOAD DATA
# ==============================

applicants = pd.read_csv(applicant_file)

mapping = pd.read_csv(
    mapping_file,
    usecols=["account_id", "Account Number"]
)

transactions = pd.read_csv(transaction_file)


# ==============================
# PREPARE ACCOUNT MAPPING
# ==============================

mapping["Account Number"] = mapping["Account Number"].astype(str)

# Keep only our 10 applicant accounts
mapping = mapping[
    mapping["account_id"].between(100001, 100010)
].copy()


# ==============================
# CONNECT APPLICANT + ACCOUNT
# ==============================

applicant_accounts = pd.merge(
    applicants,
    mapping,
    on="account_id",
    how="inner"
)


# ==============================
# PREPARE TRANSACTION ACCOUNTS
# ==============================

transactions["Account"] = transactions["Account"].astype(str)
transactions["Account.1"] = transactions["Account.1"].astype(str)


# ==============================
# FIND SENDER TRANSACTIONS
# ==============================

sender_transactions = transactions.merge(
    applicant_accounts[
        ["applicant_id", "name", "account_id", "Account Number"]
    ],
    left_on="Account",
    right_on="Account Number",
    how="inner"
)

sender_transactions["account_role"] = "sender"


# ==============================
# FIND RECEIVER TRANSACTIONS
# ==============================

receiver_transactions = transactions.merge(
    applicant_accounts[
        ["applicant_id", "name", "account_id", "Account Number"]
    ],
    left_on="Account.1",
    right_on="Account Number",
    how="inner"
)

receiver_transactions["account_role"] = "receiver"


# ==============================
# COMBINE RESULTS
# ==============================

applicant_transactions = pd.concat(
    [
        sender_transactions,
        receiver_transactions
    ],
    ignore_index=True
)


# ==============================
# REMOVE DUPLICATES
# ==============================

applicant_transactions = applicant_transactions.drop_duplicates()


# ==============================
# SAVE
# ==============================

applicant_transactions.to_csv(
    output_file,
    index=False
)


# ==============================
# RESULTS
# ==============================

print("========== APPLICANT TRANSACTION EXTRACTION ==========")

print("Applicants:", len(applicants))

print(
    "Applicant accounts mapped:",
    len(mapping)
)

print(
    "Transactions linked to applicants:",
    len(applicant_transactions)
)

print(
    "Unique applicants:",
    applicant_transactions["applicant_id"].nunique()
)

print(
    "Unique accounts:",
    applicant_transactions["account_id"].nunique()
)

print("\nTransactions by applicant:")

print(
    applicant_transactions
    .groupby(["applicant_id", "name"])
    .size()
    .to_string()
)

print("\nSaved to:")

print(output_file)