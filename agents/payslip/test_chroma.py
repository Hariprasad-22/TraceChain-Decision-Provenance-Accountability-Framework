import chromadb

# Connect to the existing ChromaDB
client = chromadb.PersistentClient(
    path="./chroma_db"
)

# Get the policy collection
collection = client.get_collection(
    name="payslip_policies"
)

# Test query
query = """
The applicant declared a monthly income of ₹70,000,
but the payslip supports only ₹54,000.
"""

results = collection.query(
    query_texts=[query],
    n_results=2
)

print("\n===== CHROMADB SEARCH RESULT =====")

for i, document in enumerate(results["documents"][0]):

    print(f"\nResult {i + 1}")
    print("-------------------------")

    print("Source:")
    print(results["metadatas"][0][i]["source"])

    print("\nPolicy:")
    print(document)

    print("\nDistance:")
    print(results["distances"][0][i])

print("\n==============================")