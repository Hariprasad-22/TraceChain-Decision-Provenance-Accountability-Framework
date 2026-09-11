"""
chain/hasher.py
---------------
Orchestrator-side hash-chain management for TraceChain.

KEY DESIGN (per user requirement):
  - Each agent computes its own record_hash internally, but with
    previous_record_hash=None (because agents run standalone).
  - The ORCHESTRATOR is solely responsible for the real chain:
      1. Take the agent's raw output.
      2. Discard the agent's record_hash (it used None as previous).
      3. Recompute input_hash and output_hash from the actual data.
      4. Set previous_record_hash = previous agent's record_hash.
      5. Compute a fresh record_hash that includes the previous link.
      6. Store this corrected provenance in the DB.

The resulting chain:
    Aadhaar   → previous=None          → record_hash=AAA
    Payslip   → previous=AAA           → record_hash=BBB
    Bank      → previous=BBB           → record_hash=CCC  (stub slot)
    CIBIL     → previous=CCC           → record_hash=DDD

Tampering with any record breaks every record_hash after it.
"""

import hashlib
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ─── core hashing ─────────────────────────────────────────────────────────────

def _sha256(payload: dict | str) -> str:
    """
    Deterministic SHA-256 hex digest.
    Accepts a dict (JSON-serialised with sorted keys) or a plain string.
    """
    if isinstance(payload, dict):
        raw = json.dumps(payload, sort_keys=True, default=str).encode()
    else:
        raw = str(payload).encode()
    return hashlib.sha256(raw).hexdigest()


def compute_input_hash(input_data: dict) -> str:
    return _sha256(input_data)


def compute_output_hash(output_data: dict) -> str:
    return _sha256(output_data)


def compute_record_hash(
    input_hash: str,
    output_hash: str,
    execution_id: str,
    previous_record_hash: Optional[str],
) -> str:
    """
    Build the tamper-evident record_hash exactly as the agents do,
    but with the *real* previous_record_hash supplied by the orchestrator.

    chain_payload mirrors ProvenanceRecordV2.__post_init__ in execution_record.py
    so verification logic works identically whether run by an agent or the orchestrator.
    """
    chain_payload = {
        "input_hash":           input_hash,
        "output_hash":          output_hash,
        "previous_record_hash": previous_record_hash,
        "execution_id":         execution_id,
    }
    return _sha256(chain_payload)


# ─── main orchestrator entry-point ────────────────────────────────────────────

def recompute_provenance_chain(
    agent_result: dict,
    previous_record_hash: Optional[str],
    execution_id: str,
) -> dict:
    """
    Given a normalised agent result dict and the previous agent's record_hash,
    recompute the provenance hashes with the correct chain link and return
    an updated provenance dict ready to be written to PROVENANCE_RECORDS.

    Parameters
    ----------
    agent_result : dict
        Normalised agent output with keys: execution, decision, evidence,
        accountability, provenance.
    previous_record_hash : str | None
        record_hash from the previous agent's provenance.
        None for Aadhaar (first in chain).
    execution_id : str
        The execution_id assigned by the orchestrator (matches AGENT_EXECUTIONS).

    Returns
    -------
    dict
        Updated provenance sub-dict with corrected hashes.
        Also returns the new record_hash so the orchestrator can pass it
        to the next agent as previous_record_hash.
    """
    prov = agent_result["provenance"]
    exec_meta = agent_result["execution"]

    # Re-hash input and output from the actual data (ignore agent's version)
    input_hash  = compute_input_hash(exec_meta.get("input_data", {}))
    output_hash = compute_output_hash(exec_meta.get("output_data", {}))

    # Build the chain link with the REAL previous hash
    record_hash = compute_record_hash(
        input_hash=input_hash,
        output_hash=output_hash,
        execution_id=execution_id,
        previous_record_hash=previous_record_hash,
    )

    updated_provenance = {
        "record_id":            prov["record_id"],
        "orchestration_id":     prov["orchestration_id"],
        "execution_id":         execution_id,
        "event_type":           prov.get("event_type", "agent_decision"),
        "timestamp":            prov.get("timestamp"),
        "input_hash":           input_hash,
        "output_hash":          output_hash,
        "previous_record_hash": previous_record_hash,
        "record_hash":          record_hash,
    }

    logger.info(
        "hasher: execution_id=%s  prev=%s  new_hash=%s",
        execution_id,
        (previous_record_hash or "GENESIS")[:16],
        record_hash[:16],
    )

    return updated_provenance


def verify_chain(records: list[dict]) -> bool:
    """
    Verify an ordered list of provenance dicts form a valid chain.
    Returns True if every record_hash checks out.

    Parameters
    ----------
    records : list[dict]
        Ordered list of provenance dicts (Aadhaar → Payslip → Bank → CIBIL).
        Each dict must have: input_hash, output_hash, previous_record_hash,
        record_hash, execution_id.
    """
    for i, rec in enumerate(records):
        expected_prev = records[i - 1]["record_hash"] if i > 0 else None
        if rec["previous_record_hash"] != expected_prev:
            logger.error(
                "chain broken at index %d: expected prev=%s got=%s",
                i, expected_prev, rec["previous_record_hash"]
            )
            return False

        expected_hash = compute_record_hash(
            input_hash=rec["input_hash"],
            output_hash=rec["output_hash"],
            execution_id=rec["execution_id"],
            previous_record_hash=rec["previous_record_hash"],
        )
        if expected_hash != rec["record_hash"]:
            logger.error(
                "tamper detected at index %d: expected=%s stored=%s",
                i, expected_hash[:16], rec["record_hash"][:16]
            )
            return False

    logger.info("chain verification passed for %d records", len(records))
    return True
