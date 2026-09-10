import chromadb

client = chromadb.PersistentClient(path="./tracechain_cibil_db")
collection = client.get_or_create_collection("cibil_decisions")


def store_decision(application_id, score, decision_output):
    summary = f"Applicant with CIBIL score {score}. Decision: {decision_output}."
    collection.add(
        documents=[summary],
        metadatas=[{"application_id": application_id, "cibil_score": score, "decision_output": decision_output}],
        ids=[application_id]
    )


def find_similar(score, decision_output, n_results=2):
    query_text = f"Applicant with CIBIL score {score}. Decision: {decision_output}."
    results = collection.query(query_texts=[query_text], n_results=n_results)
    return results