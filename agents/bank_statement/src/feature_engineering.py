import pandas as pd
import os

# ============================================================
# FILE PATHS
# ============================================================

INPUT_FILE = "data/processed/classified_transactions.csv"
OUTPUT_FILE = "data/processed/financial_features.csv"

print("Loading classified transactions...")

# ============================================================
# LOAD DATA
# ============================================================

columns = [
    "Timestamp",
    "Amount Received",
    "Receiving Currency",
    "Amount Paid",
    "Payment Currency",
    "Payment Format",
    "Is Laundering",
    "account_id",
    "transaction_role",
    "transaction_direction",
    "transaction_type",
    "cash_flag",
    "cheque_flag",
    "transfer_flag",
    "digital_payment_flag",
    "crypto_flag",
    "reinvestment_flag",
    "laundering_flag"
]

transactions = pd.read_csv(
    INPUT_FILE,
    usecols=columns
)

print(f"Transactions loaded: {len(transactions)}")

# ============================================================
# DATE PROCESSING
# ============================================================

transactions["Timestamp"] = pd.to_datetime(
    transactions["Timestamp"],
    errors="coerce"
)

transactions["month"] = (
    transactions["Timestamp"]
    .dt.to_period("M")
    .astype(str)
)

# ============================================================
# AMOUNT
# ============================================================

# Use received amount for CREDIT records
# Use paid amount for DEBIT records

transactions["amount"] = transactions["Amount Received"]

debit_mask = (
    transactions["transaction_direction"] == "DEBIT"
)

transactions.loc[
    debit_mask,
    "amount"
] = transactions.loc[
    debit_mask,
    "Amount Paid"
]

# ============================================================
# CURRENCY
# ============================================================

# For this stage we keep currencies separate.
# No USD + EUR + INR + Bitcoin aggregation.

transactions["currency"] = transactions[
    "Receiving Currency"
]

# ============================================================
# CREDIT / DEBIT AMOUNTS
# ============================================================

transactions["credit_amount"] = 0.0
transactions["debit_amount"] = 0.0

credit_mask = (
    transactions["transaction_direction"] == "CREDIT"
)

debit_mask = (
    transactions["transaction_direction"] == "DEBIT"
)

transactions.loc[
    credit_mask,
    "credit_amount"
] = transactions.loc[
    credit_mask,
    "amount"
]

transactions.loc[
    debit_mask,
    "debit_amount"
] = transactions.loc[
    debit_mask,
    "amount"
]

# ============================================================
# GROUP BY ACCOUNT + CURRENCY
# ============================================================

group_columns = [
    "account_id",
    "currency"
]

print("Calculating financial features...")

# ============================================================
# BASIC TRANSACTION FEATURES
# ============================================================

features = (
    transactions
    .groupby(group_columns)
    .agg(
        total_transactions=(
            "amount",
            "count"
        ),

        total_credits=(
            "credit_amount",
            "sum"
        ),

        total_debits=(
            "debit_amount",
            "sum"
        ),

        average_transaction_amount=(
            "amount",
            "mean"
        ),

        maximum_transaction_amount=(
            "amount",
            "max"
        ),

        minimum_transaction_amount=(
            "amount",
            "min"
        )
    )
    .reset_index()
)

# ============================================================
# MONTHLY FEATURES
# ============================================================

monthly = (
    transactions
    .groupby(
        [
            "account_id",
            "currency",
            "month"
        ]
    )
    .agg(
        monthly_credits=(
            "credit_amount",
            "sum"
        ),

        monthly_debits=(
            "debit_amount",
            "sum"
        ),

        monthly_transactions=(
            "amount",
            "count"
        )
    )
    .reset_index()
)

monthly_summary = (
    monthly
    .groupby(
        [
            "account_id",
            "currency"
        ]
    )
    .agg(
        months_active=(
            "month",
            "nunique"
        ),

        average_monthly_credits=(
            "monthly_credits",
            "mean"
        ),

        average_monthly_debits=(
            "monthly_debits",
            "mean"
        ),

        maximum_monthly_credits=(
            "monthly_credits",
            "max"
        ),

        maximum_monthly_debits=(
            "monthly_debits",
            "max"
        )
    )
    .reset_index()
)

# ============================================================
# TRANSACTION TYPE COUNTS
# ============================================================

type_counts = (
    transactions
    .groupby(group_columns)
    .agg(
        cash_transactions=(
            "cash_flag",
            "sum"
        ),

        cheque_transactions=(
            "cheque_flag",
            "sum"
        ),

        transfer_transactions=(
            "transfer_flag",
            "sum"
        ),

        digital_payment_transactions=(
            "digital_payment_flag",
            "sum"
        ),

        crypto_transactions=(
            "crypto_flag",
            "sum"
        ),

        reinvestment_transactions=(
            "reinvestment_flag",
            "sum"
        ),

        laundering_flag_count=(
            "laundering_flag",
            "sum"
        )
    )
    .reset_index()
)

# ============================================================
# TRANSACTION TYPE AMOUNTS
# ============================================================

type_amounts = (
    transactions
    .assign(
        cash_amount=lambda x:
            x["amount"] * x["cash_flag"],

        cheque_amount=lambda x:
            x["amount"] * x["cheque_flag"],

        transfer_amount=lambda x:
            x["amount"] * x["transfer_flag"],

        digital_payment_amount=lambda x:
            x["amount"] * x["digital_payment_flag"],

        crypto_amount=lambda x:
            x["amount"] * x["crypto_flag"],

        reinvestment_amount=lambda x:
            x["amount"] * x["reinvestment_flag"]
    )
    .groupby(group_columns)
    .agg(
        total_cash_amount=(
            "cash_amount",
            "sum"
        ),

        total_cheque_amount=(
            "cheque_amount",
            "sum"
        ),

        total_transfer_amount=(
            "transfer_amount",
            "sum"
        ),

        total_digital_payment_amount=(
            "digital_payment_amount",
            "sum"
        ),

        total_crypto_amount=(
            "crypto_amount",
            "sum"
        ),

        total_reinvestment_amount=(
            "reinvestment_amount",
            "sum"
        )
    )
    .reset_index()
)

# ============================================================
# CREDIT / DEBIT TRANSACTION COUNTS
# ============================================================

direction_counts = (
    transactions
    .groupby(group_columns)
    .agg(
        credit_transaction_count=(
            "credit_amount",
            lambda x: (x > 0).sum()
        ),

        debit_transaction_count=(
            "debit_amount",
            lambda x: (x > 0).sum()
        )
    )
    .reset_index()
)

# ============================================================
# COMBINE FEATURES
# ============================================================

features = features.merge(
    monthly_summary,
    on=group_columns,
    how="left"
)

features = features.merge(
    type_counts,
    on=group_columns,
    how="left"
)

features = features.merge(
    type_amounts,
    on=group_columns,
    how="left"
)

features = features.merge(
    direction_counts,
    on=group_columns,
    how="left"
)

# ============================================================
# DERIVED FINANCIAL FEATURES
# ============================================================

# Net cash flow
features["net_cash_flow"] = (
    features["total_credits"]
    - features["total_debits"]
)

# Credit / debit ratio
features["credit_debit_ratio"] = (
    features["total_credits"]
    /
    features["total_debits"].replace(0, pd.NA)
)

# Cash transaction ratio
features["cash_transaction_ratio"] = (
    features["cash_transactions"]
    /
    features["total_transactions"].replace(0, pd.NA)
)

# Transfer transaction ratio
features["transfer_transaction_ratio"] = (
    features["transfer_transactions"]
    /
    features["total_transactions"].replace(0, pd.NA)
)

# Digital payment ratio
features["digital_payment_ratio"] = (
    features["digital_payment_transactions"]
    /
    features["total_transactions"].replace(0, pd.NA)
)

# Crypto transaction ratio
features["crypto_transaction_ratio"] = (
    features["crypto_transactions"]
    /
    features["total_transactions"].replace(0, pd.NA)
)

# Reinvestment ratio
features["reinvestment_ratio"] = (
    features["reinvestment_transactions"]
    /
    features["total_transactions"].replace(0, pd.NA)
)

# Average monthly surplus
features["average_monthly_surplus"] = (
    features["average_monthly_credits"]
    -
    features["average_monthly_debits"]
)

# ============================================================
# CLEAN NUMERIC VALUES
# ============================================================

numeric_columns = features.select_dtypes(
    include=["number"]
).columns

features[numeric_columns] = (
    features[numeric_columns]
    .replace([float("inf"), float("-inf")], pd.NA)
    .fillna(0)
)

# ============================================================
# SAVE
# ============================================================

os.makedirs(
    os.path.dirname(OUTPUT_FILE),
    exist_ok=True
)

features.to_csv(
    OUTPUT_FILE,
    index=False
)

# ============================================================
# SUMMARY
# ============================================================

print("\n================================")
print("FINANCIAL FEATURES CREATED")
print("================================")

print(
    "Input transactions:",
    len(transactions)
)

print(
    "Account-currency profiles:",
    len(features)
)

print(
    "Unique accounts:",
    features["account_id"].nunique()
)

print(
    "Unique currencies:",
    features["currency"].nunique()
)

print("\nCurrencies analyzed:")

print(
    features["currency"]
    .value_counts()
    .to_string()
)

print("\nSample financial features:")

print(
    features.head(10).to_string(index=False)
)

print("\nSaved to:")
print(OUTPUT_FILE)