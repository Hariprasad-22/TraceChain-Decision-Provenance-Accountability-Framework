import pandas as pd

TRANS_PATH = "data/raw/HI-Small_Trans.csv"
ACCOUNT_PATH = "data/raw/HI-Small_accounts.csv"


# Read only 10,000 transactions
trans = pd.read_csv(
    TRANS_PATH,
    nrows=10000
)

# Read accounts file
accounts = pd.read_csv(
    ACCOUNT_PATH,
    usecols=["Account Number", "Bank ID"]
)


# Create sets
transaction_accounts = set(trans["Account"])
transaction_receiver_accounts = set(trans["Account.1"])
account_numbers = set(accounts["Account Number"])


# Check matches
sender_matches = transaction_accounts.intersection(account_numbers)
receiver_matches = transaction_receiver_accounts.intersection(account_numbers)


print("========== ACCOUNT MATCHING ==========")

print("Unique sender accounts in sample:",
      len(transaction_accounts))

print("Sender accounts found in accounts file:",
      len(sender_matches))

print("Unique receiver accounts in sample:",
      len(transaction_receiver_accounts))

print("Receiver accounts found in accounts file:",
      len(receiver_matches))


print("\n========== MATCH PERCENTAGE ==========")

sender_percentage = (
    len(sender_matches) / len(transaction_accounts)
) * 100

receiver_percentage = (
    len(receiver_matches) / len(transaction_receiver_accounts)
) * 100

print(f"Sender match: {sender_percentage:.2f}%")
print(f"Receiver match: {receiver_percentage:.2f}%")


print("\n========== SAMPLE MATCHES ==========")

print(list(sender_matches)[:20])