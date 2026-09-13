import chromadb
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

client = chromadb.PersistentClient(
    path=str(BASE_DIR / "chroma_db")
)

try:
    collection = client.get_collection(name="payslip_policies")
except Exception:
    collection = client.get_or_create_collection(name="payslip_policies")


def _populate_if_empty():
    if collection.count() > 0:
        return

    policy_dir = BASE_DIR / "policies"
    if not policy_dir.exists():
        return

    for policy_file in sorted(policy_dir.glob("*.md")):
        text = policy_file.read_text(encoding="utf-8")
        collection.upsert(
            documents=[text],
            ids=[policy_file.stem],
            metadatas=[{"source": policy_file.name}],
        )


_populate_if_empty()


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