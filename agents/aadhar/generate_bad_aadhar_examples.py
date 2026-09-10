"""
Generates deliberately INVALID synthetic Aadhaar cards, to prove the
guardrails actually reject bad input rather than just verify good input.

Two categories, matching the hard guardrails in guardrails.py:
- bad_checksum: a 12-digit number that fails Verhoeff validation
- underage: a valid card, but the applicant is under 18
"""
import json
import os
import random
from datetime import date

from faker import Faker

from generate_synthetic_aadhar import make_card, generate_aadhaar_number

fake = Faker("en_IN")
random.seed(99)
Faker.seed(99)

OUT_DIR = "synthetic_aadhar_bad"


def make_bad_checksum_number() -> str:
    """A 12-digit number that does NOT satisfy the Verhoeff checksum -
    i.e. take a valid number and corrupt the last digit."""
    valid = generate_aadhaar_number()
    last_digit = int(valid[-1])
    bad_last_digit = (last_digit + 1) % 10  # guaranteed different, so checksum fails
    return valid[:-1] + str(bad_last_digit)


if __name__ == "__main__":
    records = []

    # --- Bad checksum examples ---
    for i in range(1, 4):
        gt = make_card(
            index=i,
            out_dir=OUT_DIR,
            aadhaar_number=make_bad_checksum_number(),
            note="SYNTHETIC SAMPLE - deliberately INVALID (bad checksum)",
        )
        gt["expected_rejection"] = "invalid_format"
        records.append(gt)

    # --- Underage examples ---
    for i in range(4, 7):
        underage_dob = date.today().replace(year=date.today().year - random.randint(10, 17))
        gt = make_card(
            index=i,
            out_dir=OUT_DIR,
            dob=underage_dob,
            note="SYNTHETIC SAMPLE - deliberately INVALID (underage)",
        )
        gt["expected_rejection"] = "underage_applicant"
        records.append(gt)

    with open(os.path.join(OUT_DIR, "ground_truth_bad.json"), "w") as f:
        json.dump(records, f, indent=2, default=str)

    print(f"Generated {len(records)} deliberately invalid Aadhaar cards in ./{OUT_DIR}/")
    print(f"Ground truth (with expected_rejection) saved to ./{OUT_DIR}/ground_truth_bad.json")
    for r in records:
        print(f"  {os.path.basename(r['file'])}: expect '{r['expected_rejection']}'")
