from chroma_retriever import retrieve_policy


query = """
The applicant declared monthly income of ₹70,000,
but the payslip supports only ₹54,000.
"""

results = retrieve_policy(query)

print("\n===== RETRIEVED EVIDENCE =====")

for result in results:
    print("\nSource:", result["source"])
    print("Distance:", result["distance"])
    print("Policy:")
    print(result["document"][:500])

print("\n==============================")