"""
Runs the CIBIL Score Agent against all 10 mock CIBIL accounts, using
account/user IDs 100001 through 100010 - matching the same 10 applicants
used by the Aadhaar agent (same account_id, same applicant_ref_id linkage).

Also builds the USERS and APPLICATIONS records (tables 1 & 2 in the
orchestrator's schema) explicitly, matching the Aadhaar teammate's script
exactly, so account_id maps unambiguously across all four agents.

Output is saved as JSON in the exact schema shape (users / applications /
execution / decision / evidence / accountability / provenance) so the
orchestrator teammate can use it directly as sample data for their tables.
"""
import json
from datetime import datetime, timezone

from cibil_agent import cibil_verification_agent

ACCOUNT_ID_START = 100001
DEFAULT_LOAN_AMOUNT = 150_000

# The 10 real CIBIL test accounts, matching applicant_ref_id hashes already
# linked to the same 10 Aadhaar cards used by the Aadhaar agent.
CIBIL_ACCOUNTS = [
    {"applicant_ref_id": "hash_0fb7266073b4", "cibil_score": 812, "credit_utilization_pct": 18, "dpd_history": [0, 0, 0]},
    {"applicant_ref_id": "hash_5e7bae7a5caf", "cibil_score": 760, "credit_utilization_pct": 30, "dpd_history": [0, 0]},
    {"applicant_ref_id": "hash_53a219a3f2b1", "cibil_score": 735, "credit_utilization_pct": 25, "dpd_history": [0, 0]},
    {"applicant_ref_id": "hash_d1f57939753a", "cibil_score": 712, "credit_utilization_pct": 82, "dpd_history": [0, 0, 15, 0]},
    {"applicant_ref_id": "hash_642c9278cf13", "cibil_score": 668, "credit_utilization_pct": 71, "dpd_history": [0, 20, 0]},
    {"applicant_ref_id": "hash_a1b84cc266af", "cibil_score": 620, "credit_utilization_pct": 55, "dpd_history": [0, 0]},
    {"applicant_ref_id": "hash_c8f644e852e9", "cibil_score": 590, "credit_utilization_pct": 95, "dpd_history": [0, 92, 45, 0]},
    {"applicant_ref_id": "hash_c952bd5411e8", "cibil_score": 540, "credit_utilization_pct": 98, "dpd_history": [120, 0, 30]},
    {"applicant_ref_id": "hash_3fa599330808", "cibil_score": 950, "credit_utilization_pct": 20, "dpd_history": [0, 0]},
    {"applicant_ref_id": "hash_5c0ac2cce6c3", "cibil_score": 250, "credit_utilization_pct": 60, "dpd_history": [0, 0]},
]

if __name__ == "__main__":
    all_results = []

    for i, acc in enumerate(CIBIL_ACCOUNTS):
        account_id = str(ACCOUNT_ID_START + i)  # doubles as user_id, by team agreement
        application_id = f"APP-{account_id}"
        print(f"\n=== Account {account_id}: CIBIL score {acc['cibil_score']} ===")

        # --- Table 1: USERS ---
        user_record = {
            "user_id": account_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # --- Table 2: APPLICATIONS ---
        application_record = {
            "application_id": application_id,
            "user_id": account_id,
            "loan_amount": DEFAULT_LOAN_AMOUNT,
            "application_date": datetime.now(timezone.utc).isoformat(),
            "status": "processing",
        }

        state = {
            "application_id": application_id,
            "applicant_ref_id": acc["applicant_ref_id"],
            "cibil_score": acc["cibil_score"],
            "credit_utilization_pct": acc["credit_utilization_pct"],
            "dpd_history": acc["dpd_history"],
        }

        agent_result = cibil_verification_agent(state, orchestration_id=application_id)

        all_results.append({
            "user": user_record,
            "application": application_record,
            **agent_result,
        })

        print(f"  user_id: {account_id}  application_id: {application_id}")
        print(f"  decision: {agent_result['decision']['decision_output']}  "
              f"(confidence: {agent_result['decision']['confidence_score']})")
        print(f"  risk_level: {agent_result['accountability']['risk_level']}  "
              f"composite: {agent_result['accountability']['composite_risk_score']}  "
              f"review_required: {agent_result['accountability']['review_required']}")
        print(f"  provenance.record_hash: {agent_result['provenance']['record_hash'][:20]}...")

    with open("account_100001_to_100010_cibil_results.json", "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\nSaved all {len(all_results)} full schema-shaped results "
          f"(users, applications, and agent output) to "
          f"account_100001_to_100010_cibil_results.json")
