import os
import pandas as pd
import chromadb


INPUT_FILE = r"data\processed\synthetic_statement_features.csv"
CHROMA_PATH = r"data\chroma_db"
COLLECTION_NAME = "bank_statement_evidence"


print("========== BANK STATEMENT RAG ==========")


# --------------------------------------------------
# 1. Load financial features
# --------------------------------------------------

df = pd.read_csv(INPUT_FILE)

print("Financial profiles loaded:", len(df))


# --------------------------------------------------
# 2. Create ChromaDB client
# --------------------------------------------------

os.makedirs(CHROMA_PATH, exist_ok=True)

client = chromadb.PersistentClient(
    path=CHROMA_PATH
)


# --------------------------------------------------
# 3. Create / reset collection
# --------------------------------------------------

try:
    client.delete_collection(COLLECTION_NAME)
except Exception:
    pass

collection = client.create_collection(
    name=COLLECTION_NAME,
    metadata={
        "description": "Bank statement financial evidence",
        "source": "synthetic six-month bank statements"
    }
)


# --------------------------------------------------
# 4. Create evidence documents
# --------------------------------------------------

documents = []
metadatas = []
ids = []


for _, row in df.iterrows():

    account_id = int(row["account_id"])

    document = f"""
Bank Statement Financial Profile

Account ID: {account_id}
Employment Type: {row["employment_type"]}
Monthly Salary: INR {row["monthly_salary"]:.2f}
CIBIL Score: {row["cibil_score"]:.0f}

Six-Month Transaction Summary:
Total Transactions: {row["total_transactions"]:.0f}
Total Credits: INR {row["total_credits"]:.2f}
Total Debits: INR {row["total_debits"]:.2f}

Income:
Average Monthly Income: INR {row["average_monthly_income"]:.2f}
Income Standard Deviation: INR {row["income_std"]:.2f}
Income Stability: {row["income_stability"]:.4f}

Expenses:
Average Monthly Expense: INR {row["average_monthly_expense"]:.2f}
Average Monthly Surplus: INR {row["average_monthly_surplus"]:.2f}

Debt:
Average Monthly EMI: INR {row["average_emi"]:.2f}
EMI-to-Income Ratio: {row["emi_to_income_ratio"]:.4f}

Savings:
Savings Ratio: {row["savings_ratio"]:.4f}

Spending Behaviour:
Average Rent: INR {row["average_rent"]:.2f}
Average Grocery: INR {row["average_grocery"]:.2f}
Average Utility: INR {row["average_utility"]:.2f}
Average Shopping: INR {row["average_shopping"]:.2f}
Average Food: INR {row["average_food"]:.2f}
Average Transfer: INR {row["average_transfer"]:.2f}
Average Cash Withdrawal: INR {row["average_cash_withdrawal"]:.2f}
Average Investment: INR {row["average_investment"]:.2f}
""".strip()

    documents.append(document)

    metadatas.append({
        "account_id": str(account_id),
        "employment_type": str(row["employment_type"]),
        "source": "synthetic_bank_statement",
        "period": "2022-01 to 2022-06"
    })

    ids.append(f"account_{account_id}")


# --------------------------------------------------
# 5. Store evidence in ChromaDB
# --------------------------------------------------

collection.add(
    ids=ids,
    documents=documents,
    metadatas=metadatas
)


# --------------------------------------------------
# 6. Validate collection
# --------------------------------------------------

print("Collection:", COLLECTION_NAME)
print("Documents stored:", collection.count())


# --------------------------------------------------
# 7. Test retrieval
# --------------------------------------------------

test_query = (
    "Which applicant has negative monthly surplus "
    "and financial difficulty?"
)

results = collection.query(
    query_texts=[test_query],
    n_results=3
)


print("\n========== RETRIEVAL TEST ==========")
print("Query:", test_query)

for i, document in enumerate(results["documents"][0], start=1):

    print(f"\n--- Result {i} ---")
    print(document)


print("\n========== RAG BUILD COMPLETE ==========")
print("ChromaDB location:", CHROMA_PATH)