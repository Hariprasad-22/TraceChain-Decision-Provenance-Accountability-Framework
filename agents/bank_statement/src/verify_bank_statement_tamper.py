import json
import hashlib
from pathlib import Path


INPUT_FILE = Path(
    r"data\processed\bank_statement_tracechain_output_tampered.json"
)


def calculate_hash(payload):
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_record(record):
    stored_input_hash = record["input_hash"]
    stored_output_hash = record["output_hash"]
    stored_record_hash = record["record_hash"]

    # Recalculate input hash
    recalculated_input_hash = calculate_hash(record["input_data"])

    # Recalculate output hash
    recalculated_output_hash = calculate_hash(record["output_data"])

    # Recalculate complete provenance record hash
    record_payload = {
        "record_id": record["record_id"],
        "orchestration_id": record["orchestration_id"],
        "execution_id": record["execution_id"],
        "event_type": record["event_type"],
        "timestamp": record["timestamp"],
        "input_hash": stored_input_hash,
        "output_hash": stored_output_hash,
        "previous_record_hash": record["previous_record_hash"],
    }

    recalculated_record_hash = calculate_hash(record_payload)

    input_valid = (
        recalculated_input_hash == stored_input_hash
    )

    output_valid = (
        recalculated_output_hash == stored_output_hash
    )

    record_valid = (
        recalculated_record_hash == stored_record_hash
    )

    return input_valid and output_valid and record_valid


def main():
    print("========== TAMPER VERIFICATION ==========")

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    records = data["records"]["PROVENANCE_RECORDS"]

    results = []

    for record in records:
        valid = verify_record(record)
        results.append(valid)

        print(
            f"{record['record_id']} -> "
            f"{'VALID' if valid else 'TAMPERED'}"
        )

    all_valid = all(results)

    print("\n========== RESULT ==========")

    if all_valid:
        print("Tamper detected: FALSE")
        print("All provenance records are valid.")
    else:
        print("Tamper detected: TRUE")
        print("One or more provenance records have been modified.")


if __name__ == "__main__":
    main()