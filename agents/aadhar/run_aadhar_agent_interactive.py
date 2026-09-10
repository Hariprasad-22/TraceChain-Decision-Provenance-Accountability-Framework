"""
Interactive runner: lists every available synthetic Aadhaar card across
all three sets - valid (synthetic_aadhar/), deliberately invalid
(synthetic_aadhar_bad/), and visually realistic (synthetic_aadhar_realistic/)
- lets you pick one, and runs it through the real Aadhar Verification
Agent.

Account/application IDs are assigned automatically, never typed:
- The 10 realistic cards always get their fixed account ID (100001-100010),
  the exact same mapping run_aadhar_batch_accounts.py uses - so a given
  card always maps to the same account, everywhere, with no chance of a
  manual mismatch.
- Every other card (good/bad) gets a fresh, unique ID auto-generated on
  the spot, since those aren't part of the fixed 10-account set.
"""
import json
import os

from aadhar_agent import aadhar_verification_agent
from schema import new_id

GOOD_DIR = "synthetic_aadhar"
BAD_DIR = "synthetic_aadhar_bad"
REALISTIC_DIR = "synthetic_aadhar_realistic"
REALISTIC_ACCOUNT_ID_START = 100001  # must match run_aadhar_batch_accounts.py


def load_records():
    records = []
    good_gt = os.path.join(GOOD_DIR, "ground_truth.json")
    if os.path.exists(good_gt):
        with open(good_gt) as f:
            for r in json.load(f):
                r["_category"] = "good"
                records.append(r)

    bad_gt = os.path.join(BAD_DIR, "ground_truth_bad.json")
    if os.path.exists(bad_gt):
        with open(bad_gt) as f:
            for r in json.load(f):
                r["_category"] = "bad"
                records.append(r)

    realistic_gt = os.path.join(REALISTIC_DIR, "ground_truth_realistic.json")
    if os.path.exists(realistic_gt):
        with open(realistic_gt) as f:
            for realistic_index, r in enumerate(json.load(f)):
                r["_category"] = "realistic"
                r["_account_id"] = str(REALISTIC_ACCOUNT_ID_START + realistic_index)
                records.append(r)

    return records


def main():
    records = load_records()
    if not records:
        print("No cards found. Run generate_synthetic_aadhar.py, "
              "generate_bad_aadhar_examples.py, and/or "
              "generate_realistic_aadhar.py first.")
        return

    print("Available Aadhaar cards:\n")
    for i, r in enumerate(records, 1):
        if r["_category"] == "bad":
            tag = f"[expect: {r['expected_rejection']}]"
        elif r["_category"] == "realistic":
            tag = f"[valid, realistic style, account {r['_account_id']}]"
        else:
            tag = "[valid]"
        print(f"  {i}. {os.path.basename(r['file']):24} {r['name']:20} {tag}")

    choice = input("\nPick a card number to run: ").strip()
    try:
        record = records[int(choice) - 1]
    except (ValueError, IndexError):
        print("Invalid choice.")
        return

    loan_amount_input = input("Loan amount (default 150000): ").strip()
    loan_amount = float(loan_amount_input) if loan_amount_input else 150_000

    name_input = input(f"Applicant name on application (default '{record['name']}', "
                       f"type a different name to test a mismatch): ").strip()
    applicant_name = name_input or record["name"]

    # Account ID is never typed - it's fixed for the 10 realistic cards
    # (matching the batch script), auto-generated for everything else.
    account_id = record.get("_account_id") or new_id()

    application_state = {
        "application_id": account_id,
        "loan_amount": loan_amount,
        "applicant_name": applicant_name,
        "applicant_dob": record["dob"],
        "applicant_data": {"aadhar_image_path": record["file"]},
    }

    print(f"\nRunning agent on {record['file']} (account: {account_id}) ...\n")
    result = aadhar_verification_agent(application_state, orchestration_id=account_id)

    print("=== AGENT_EXECUTIONS ===")
    for k, v in result["execution"].items():
        print(f"  {k}: {v}")
    print("\n=== AGENT_DECISIONS ===")
    for k, v in result["decision"].items():
        print(f"  {k}: {v}")
    print("\n=== EVIDENCE ===")
    for e in result["evidence"]:
        print(f"  {e}")
    print("\n=== ACCOUNTABILITY_SCORES ===")
    for k, v in result["accountability"].items():
        print(f"  {k}: {v}")
    print("\n=== PROVENANCE_RECORDS ===")
    for k, v in result["provenance"].items():
        print(f"  {k}: {v}")

    if record["_category"] == "bad":
        expected = record["expected_rejection"]
        got = result["decision"]["decision_output"]
        status = "PASS" if got == expected else "MISMATCH"
        print(f"\n[{status}] expected rejection: '{expected}', got: '{got}'")


if __name__ == "__main__":
    main()
