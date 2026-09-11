import sys
from pathlib import Path
import json
from datetime import datetime, timezone

# Ensure orchestrator package is importable from workspace root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import runpy

# Load hasher and writer modules by path to avoid importing the 'orchestrator' package
hasher_mod = runpy.run_path(str(ROOT / "orchestrator" / "chain" / "hasher.py"))
recompute_provenance_chain = hasher_mod["recompute_provenance_chain"]
compute_input_hash = hasher_mod["compute_input_hash"]
compute_output_hash = hasher_mod["compute_output_hash"]
compute_record_hash = hasher_mod["compute_record_hash"]
verify_chain = hasher_mod["verify_chain"]

writer_mod = runpy.run_path(str(ROOT / "orchestrator" / "db" / "writer.py"))

# Prepare sample tracechain JSON in the active bank_statement agent path
BANK_SRC = ROOT / "agents" / "bank_statement" / "src"
OUTPUT_DIR = BANK_SRC.parent / "data" / "processed"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_FILE = OUTPUT_DIR / "bank_statement_tracechain_output.json"

now = datetime.now(timezone.utc).isoformat()

# Minimal sample record
execution_id = "EXEC_BANK_TEST_001"
record_id = "PROV_BANK_TEST_001"

tracechain = {
    "agent_id": "BANK_STATEMENT_AGENT",
    "agent_version": "1.0",
    "schema_version": "TraceChain-A3-v1",
    "orchestration_id": "ORCH_BANK_TEST_001",
    "records": {
        "AGENT_EXECUTIONS": [
            {
                "execution_id": execution_id,
                "orchestration_id": "ORCH_BANK_TEST_001",
                "agent_id": "BANK_STATEMENT_AGENT",
                "parent_execution_id": None,
                "sequence_number": 1,
                "input_data": {"account_id": 100001, "statement_period": "2022-01 to 2022-06"},
                "model_id": "bank-statement-rules-v1",
                "model_version": "1.0",
                "rule_id": "bank-affordability-rules-v1",
                "rule_version": "1.0",
                "output_data": {"decision_output": "ELIGIBLE", "confidence_score": 0.95, "agent_score": 85},
                "start_time": now,
                "end_time": now,
                "status": "COMPLETED",
            }
        ],
        "AGENT_DECISIONS": [
            {
                "decision_id": "DEC_BANK_TEST_001",
                "execution_id": execution_id,
                "decision_output": "ELIGIBLE",
                "confidence_score": 0.95,
                "reasoning": "All indicators support affordability.",
                "decision_timestamp": now,
            }
        ],
        "EVIDENCE": [
            {
                "evidence_id": "EVID_BANK_TEST_001",
                "execution_id": execution_id,
                "evidence_type": "FINANCIAL_FEATURES",
                "source": "synthetic_bank_statement",
                "data_reference": "account_100001",
                "model_id": "bank-statement-rules-v1",
                "rule_id": "bank-affordability-rules-v1",
                "policy_id": None,
                "retrieval_score": 1.0,
                "evidence_hash": "",
                "timestamp": now,
                "evidence_data": {"average_monthly_income": 50000.0}
            }
        ],
        "ACCOUNTABILITY_SCORES": [
            {
                "score_id": "ACC_BANK_TEST_001",
                "execution_id": execution_id,
                "irreversibility_score": 6,
                "impact_score": 7,
                "explainability_score": 9,
                "composite_risk_score": 2.5,
                "risk_level": "Low",
                "review_required": False,
                "scoring_model_version": "tracechain-scoring-v1",
                "calculated_at": now,
            }
        ],
        "PROVENANCE_RECORDS": [
            {
                "record_id": record_id,
                "orchestration_id": "ORCH_BANK_TEST_001",
                "execution_id": execution_id,
                "event_type": "BANK_STATEMENT_AGENT_COMPLETED",
                "timestamp": now,
                "input_hash": "",
                "output_hash": "",
                "previous_record_hash": None,
                "record_hash": "",
            }
        ]
    }
}

# Save sample tracechain
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(tracechain, f, indent=2)
print("Wrote sample tracechain to:", OUTPUT_FILE)

# --- Build two previous provenance records (Aadhaar, Payslip) and compute their record_hashes
def make_prev_record(execution_id, input_data, output_data, previous_record_hash=None):
    inp_h = compute_input_hash(input_data)
    out_h = compute_output_hash(output_data)
    rh = compute_record_hash(inp_h, out_h, execution_id, previous_record_hash)
    return {
        "execution_id": execution_id,
        "input_hash": inp_h,
        "output_hash": out_h,
        "previous_record_hash": previous_record_hash,
        "record_hash": rh,
    }

# Aadhaar (first)
aadhaar = make_prev_record("EXEC_AADHAAR_001", {"a":"b"}, {"result":"ok"}, None)
# Payslip (second)
payslip = make_prev_record("EXEC_PAYSLIP_001", {"p":"q"}, {"income":65000}, aadhaar["record_hash"])

print("Previous record hashes:", aadhaar["record_hash"], payslip["record_hash"])

# Normalise tracechain (pick first bank record) to orchestrator shape
records = tracechain.get("records", {})
execs = records.get("AGENT_EXECUTIONS", [])
decs = records.get("AGENT_DECISIONS", [])
evs = records.get("EVIDENCE", [])
accs = records.get("ACCOUNTABILITY_SCORES", [])
provs = records.get("PROVENANCE_RECORDS", [])

execution = dict(execs[0])
decision = dict(decs[0]) if decs else {}
evidence = [dict(e) for e in evs]
accountability = dict(accs[0]) if accs else {}
provenance = dict(provs[0]) if provs else {}

# Enforce orchestrator metadata
execution["agent_id"] = "A003"
execution["orchestration_id"] = "ORC-TEST-001"
execution["sequence_number"] = 3
provenance["orchestration_id"] = "ORC-TEST-001"

res = {
    "execution": execution,
    "decision": decision,
    "evidence": evidence,
    "accountability": accountability,
    "provenance": provenance,
}
print("Normalised adapter result keys:", list(res.keys()))
state = {"application_id": "APP-TEST", "user_id": "100001", "applicant_name": "Test User", "loan_amount": 100000.0, "applicant_data": {}}
orc_id = "ORC-TEST-001"

# Recompute provenance using the payslip previous_record_hash
prev = payslip["record_hash"]
prov = recompute_provenance_chain(agent_result=res, previous_record_hash=prev, execution_id=res["execution"]["execution_id"])
print("Recomputed provenance record_hash:", prov.get("record_hash"))

# Verify full chain (aadhaar -> payslip -> bank)
full_chain = [
    {
        "input_hash": aadhaar["input_hash"],
        "output_hash": aadhaar["output_hash"],
        "previous_record_hash": aadhaar["previous_record_hash"],
        "record_hash": aadhaar["record_hash"],
        "execution_id": aadhaar["execution_id"],
    },
    {
        "input_hash": payslip["input_hash"],
        "output_hash": payslip["output_hash"],
        "previous_record_hash": payslip["previous_record_hash"],
        "record_hash": payslip["record_hash"],
        "execution_id": payslip["execution_id"],
    },
    prov,
]

ok = verify_chain(full_chain)
print("Full chain verification result:", ok)

# Monkeypatch writer._exec in the loaded writer module to print SQL instead of executing
orig_exec = writer_mod.get("_exec")

def _print_exec(sql, params):
    first = sql.strip().splitlines()[0]
    print("DB EXECUTE:", first)
    # Print a small sample of params for readability
    try:
        print("  PARAMS:", params[:6])
    except Exception:
        print("  PARAMS: (could not slice)")

writer_mod["_exec"] = _print_exec

# Call writer functions directly to simulate DB writes
try:
    exec_meta = res["execution"]
    decision_data = res["decision"]
    evidence_list = res["evidence"]
    acc = res["accountability"]

    # write_agent_execution
    writer_mod["write_agent_execution"](
        execution_id=exec_meta["execution_id"],
        orchestration_id=orc_id,
        agent_id=exec_meta.get("agent_id", "A003"),
        sequence_number=exec_meta.get("sequence_number", 3),
        input_data=exec_meta.get("input_data", {}),
        output_data=exec_meta.get("output_data", {}),
        model_id=exec_meta.get("model_id", "bank-statement-rules-v1"),
        rule_id=exec_meta.get("rule_id", None),
        start_time=exec_meta.get("start_time"),
        end_time=exec_meta.get("end_time"),
        status=exec_meta.get("status", "COMPLETED"),
    )

    # write_agent_decision
    writer_mod["write_agent_decision"](
        decision_id=decision_data.get("decision_id", ""),
        execution_id=exec_meta["execution_id"],
        decision_output=decision_data.get("decision_output", ""),
        confidence_score=float(decision_data.get("confidence_score", 0.0)),
        reasoning=decision_data.get("reasoning", ""),
        decision_timestamp=decision_data.get("decision_timestamp", decision_data.get("timestamp", now)),
    )

    # Transform evidence to the DB shape expected by writer.write_evidence_items
    transformed_evidence = []
    for e in evidence_list:
        transformed_evidence.append({
            "evidence_id": e.get("evidence_id"),
            "execution_id": e.get("execution_id", exec_meta["execution_id"]),
            "source": e.get("source"),
            "document_reference": e.get("data_reference", e.get("document_reference")),
            "retrieval_score": e.get("retrieval_score", 0.0),
            "timestamp": e.get("timestamp", now),
        })

    writer_mod["write_evidence_items"](transformed_evidence)

    # write_accountability_score
    writer_mod["write_accountability_score"](
        score_id=acc.get("score_id", ""),
        execution_id=exec_meta["execution_id"],
        impact_score=int(acc.get("impact_score", acc.get("impact", 0))),
        irreversibility_score=int(acc.get("irreversibility_score", acc.get("irreversibility", 0))),
        explainability_score=int(acc.get("explainability_score", 10)),
        composite_risk_score=float(acc.get("composite_risk_score", 0.0)),
        risk_level=acc.get("risk_level", "Low"),
        review_required=bool(acc.get("review_required", False)),
        scoring_model_version=acc.get("scoring_model_version", "tracechain-scoring-v1"),
        calculated_at=acc.get("calculated_at", now),
    )

    # write_provenance_record
    writer_mod["write_provenance_record"](
        record_id=prov.get("record_id", prov.get("record_id", "")),
        orchestration_id=orc_id,
        execution_id=exec_meta["execution_id"],
        event_type=prov.get("event_type", "agent_decision"),
        timestamp=prov.get("timestamp", now),
        input_hash=prov.get("input_hash", prov.get("input_hash", "")),
        output_hash=prov.get("output_hash", prov.get("output_hash", "")),
        previous_record_hash=prov.get("previous_record_hash"),
        record_hash=prov.get("record_hash"),
    )

    print("Simulated DB writes completed (printed above).")
except Exception as e:
    print("Simulated DB writes failed:", e)
finally:
    writer_mod["_exec"] = orig_exec
