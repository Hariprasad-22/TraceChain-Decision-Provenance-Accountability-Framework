"""Tests for execution_record.py - the schema-shaped records and the
tamper-evident hash chain."""
from execution_record import (
    ExecutionMetadata, ProvenanceRecordV2, verify_provenance_record, risk_level_for,
)


# --- ExecutionMetadata.input_hash ---

def test_input_hash_is_deterministic():
    data = {"name": "Hemal Sen", "loan_amount": 150000}
    e1 = ExecutionMetadata(execution_id="e1", orchestration_id="o1", agent_id="A001",
                            input_data=data, output_data={}, model_id="m", rule_id="r",
                            start_time="t0", end_time="t1", status="completed")
    e2 = ExecutionMetadata(execution_id="e2", orchestration_id="o1", agent_id="A001",
                            input_data=data, output_data={}, model_id="m", rule_id="r",
                            start_time="t0", end_time="t1", status="completed")
    assert e1.input_hash == e2.input_hash


def test_input_hash_changes_when_input_changes():
    e1 = ExecutionMetadata(execution_id="e1", orchestration_id="o1", agent_id="A001",
                            input_data={"name": "Hemal Sen"}, output_data={}, model_id="m",
                            rule_id="r", start_time="t0", end_time="t1", status="completed")
    e2 = ExecutionMetadata(execution_id="e1", orchestration_id="o1", agent_id="A001",
                            input_data={"name": "Someone Else"}, output_data={}, model_id="m",
                            rule_id="r", start_time="t0", end_time="t1", status="completed")
    assert e1.input_hash != e2.input_hash


# --- ProvenanceRecordV2 / verify_provenance_record: the tamper-evidence contract ---

def _make_record(prev_hash=None):
    return ProvenanceRecordV2(
        record_id="r1", orchestration_id="100001", execution_id="e1",
        event_type="agent_decision",
        input_data={"applicant_name": "Hemal Sen"},
        output_data={"decision_output": "verified"},
        previous_record_hash=prev_hash,
    )


def test_fresh_record_verifies_true():
    record = _make_record()
    assert verify_provenance_record(record) is True


def test_tampering_with_output_data_is_detected():
    record = _make_record()
    record.output_data["decision_output"] = "rejected"  # tamper after the fact
    assert verify_provenance_record(record) is False


def test_tampering_with_input_data_is_detected():
    record = _make_record()
    record.input_data["applicant_name"] = "A Different Person"
    assert verify_provenance_record(record) is False


def test_chained_record_references_previous_hash():
    first = _make_record()
    second = _make_record(prev_hash=first.record_hash)
    assert second.previous_record_hash == first.record_hash
    assert verify_provenance_record(second) is True


def test_breaking_the_chain_is_detected():
    first = _make_record()
    second = _make_record(prev_hash=first.record_hash)
    # Simulate the earlier record being altered after second was written -
    # second's stored previous_record_hash no longer matches reality.
    second.previous_record_hash = "a-different-hash-entirely"
    assert verify_provenance_record(second) is False


# --- risk_level_for thresholds ---

def test_low_risk_below_four():
    assert risk_level_for(3.9) == "Low"


def test_medium_risk_boundary_at_four():
    assert risk_level_for(4.0) == "Medium"
    assert risk_level_for(6.9) == "Medium"


def test_high_risk_boundary_at_seven():
    assert risk_level_for(7.0) == "High"
    assert risk_level_for(10.0) == "High"
