import chromadb
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

client = chromadb.PersistentClient(
    path=str(BASE_DIR / "chroma_db")
)

collection = client.get_collection(
    name="payslip_policies"
)


def retrieve_policy(query, n_results=2):
    results = collection.query(
        query_texts=[query],
        n_results=n_results
    )

    policies = []

    for i, document in enumerate(results["documents"][0]):

        policies.append({
            "source": results["metadatas"][0][i]["source"],
            "document": document,
            "distance": results["distances"][0][i]
        })

    return policies