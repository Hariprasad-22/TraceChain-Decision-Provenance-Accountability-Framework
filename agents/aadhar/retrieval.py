"""
Loads the three Aadhaar policy documents (kb_aadhar/), splits them into
citable clause-level chunks, embeds them with Gemini, and retrieves the
most relevant clauses for a given query via ChromaDB.
"""
import os
import re
import glob

import chromadb

from llm_client import embed_text

KB_DIR = os.path.join(os.path.dirname(__file__), "kb_aadhar")
_CLAUSE_RE = re.compile(r"^(\d+\.\d+|R\d+):?\s")


def load_clauses() -> list:
    """Splits each markdown doc into individually citable clauses
    (e.g. '2.2 A masked Aadhaar...' or 'R6: Unverifiable Submission...')."""
    clauses = []
    for path in sorted(glob.glob(os.path.join(KB_DIR, "*.md"))):
        source = os.path.basename(path)
        with open(path) as f:
            paragraphs = f.read().split("\n\n")
        for para in paragraphs:
            para = para.strip()
            if not para or para.startswith("#"):
                continue
            first_line = para.split("\n")[0]
            match = _CLAUSE_RE.match(first_line)
            clause_id = first_line.split(" ")[0].rstrip(":") if match else None
            if clause_id:
                clauses.append({"id": f"{source}:{clause_id}", "source": source, "text": para})
    return clauses


class AadharRetriever:
    def __init__(self):
        self.clauses = load_clauses()
        self._client = chromadb.PersistentClient(path=os.path.join(os.path.dirname(__file__), "chroma_db"))
        self._collection = self._client.get_or_create_collection("aadhar_kb")

        existing = set(self._collection.get()["ids"]) if self._collection.count() else set()
        new = [c for c in self.clauses if c["id"] not in existing]
        if new:
            self._collection.add(
                ids=[c["id"] for c in new],
                embeddings=[embed_text(c["text"]) for c in new],
                documents=[c["text"] for c in new],
                metadatas=[{"source": c["source"]} for c in new],
            )

    def retrieve(self, query: str, k: int = 3) -> list:
        results = self._collection.query(
            query_embeddings=[embed_text(query)], n_results=k,
            include=["documents", "distances"],
        )
        # Chroma returns a distance (lower = more similar); convert to a
        # 0-1 similarity-style score for EVIDENCE.retrieval_score, which
        # reads more naturally as "higher is better".
        return [
            {"id": rid, "text": doc, "retrieval_score": round(max(0.0, 1 - dist), 4)}
            for rid, doc, dist in zip(results["ids"][0], results["documents"][0], results["distances"][0])
        ]
