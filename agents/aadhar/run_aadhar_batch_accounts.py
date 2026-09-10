"""
Runs the Aadhar Verification Agent against all 10 realistic synthetic
cards (synthetic_aadhar_realistic/), assigning account/user IDs 100001
through 100010 - one per applicant, as agreed with the team.

Also builds the USERS and APPLICATIONS records (tables 1 & 2 in the
orchestrator's schema) explicitly, so account_id maps unambiguously to a
user, and that user's application - rather than reusing one ID across
every table's meaning.

Output is saved as JSON in the exact schema shape (users / applications /
execution / decision / evidence / accountability / provenance) so the
orchestrator teammate can use it directly as sample data for their tables.
"""
import json
from datetime import datetime, timezone

from aadhar_agent import aadhar_verification_agent

CARDS_DIR = "synthetic_aadhar_realistic"
ACCOUNT_ID_START = 100001
DEFAULT_LOAN_AMOUNT = 150_000

with open(f"{CARDS_DIR}/ground_truth_realistic.json") as f:
    cards = json.load(f)

if __name__ == "__main__":
    all_results = []

    for i, card in enumerate(cards[:10]):
        account_id = str(ACCOUNT_ID_START + i)  # doubles as user_id here, by team agreement
        application_id = f"APP-{account_id}"
        print(f"\n=== Account {account_id}: {card['name']} ===")

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
            "loan_amount": DEFAULT_LOAN_AMOUNT,
            "applicant_name": card["name"],
            "applicant_dob": card["dob"],
            "applicant_data": {"aadhar_image_path": card["file"]},
        }

        agent_result = aadhar_verification_agent(state, orchestration_id=application_id)

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

    with open("account_100001_to_100010_results.json", "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\nSaved all {len(all_results)} full schema-shaped results "
          f"(users, applications, and agent output) to "
          f"account_100001_to_100010_results.json")
