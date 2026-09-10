"""
ProvenanceChain: appends ProvenanceRecords with automatic hash-chaining,
and verifies chain integrity so tampering after the fact is detectable.
"""
import hashlib
import json
from typing import List, Optional

from schema import ProvenanceRecord


class ProvenanceChain:
    def __init__(self, chain_id: str):
        self.chain_id = chain_id
        self.records: List[ProvenanceRecord] = []

    def append(self, record: ProvenanceRecord) -> ProvenanceRecord:
        prev_hash = self.records[-1].record_hash if self.records else None
        record.finalize(prev_hash)
        self.records.append(record)
        return record

    def verify(self) -> bool:
        """Recompute every hash from scratch. Returns False if any record
        was altered after being written, or if the chain order was tampered with."""
        prev_hash = None
        for r in self.records:
            if r.prev_record_hash != prev_hash:
                return False
            payload = json.dumps(r._canonical_payload(), sort_keys=True).encode()
            recomputed = hashlib.sha256(payload).hexdigest()
            if recomputed != r.record_hash:
                return False
            prev_hash = r.record_hash
        return True

    def to_json(self) -> str:
        return json.dumps([r.to_dict() for r in self.records], indent=2)

    def save(self, path: str):
        with open(path, "w") as f:
            f.write(self.to_json())
