"""
Aadhar Verification Agent.

Flow: extract fields from the image (Gemini vision) -> hard guardrails
(format/checksum, age) reject immediately with no LLM call, per Internal
KYC Policy 3.5 -> soft checks (name/DOB match, loan-amount tier) build a
query -> retrieve relevant policy clauses from ChromaDB (Gemini
embeddings) -> LLM reasons over extracted data + retrieved clauses ->
validate the LLM's own output.

Output shape matches TraceChain_Schema_Design.pdf exactly: a dict with
"execution", "decision", "evidence", "accountability", and "provenance"
keys, mapping 1:1 to AGENT_EXECUTIONS, AGENT_DECISIONS, EVIDENCE,
ACCOUNTABILITY_SCORES, and PROVENANCE_RECORDS - so the orchestrator can
write each section straight into its table with no translation.
"""
from datetime import datetime, timezone

from aadhar_extraction import extract_aadhaar_fields
from guardrails import (
    validate_aadhaar_format, validate_age, name_similarity, dob_matches,
    validate_llm_output, scope_for_aadhar_agent, ValidationError,
)
from retrieval import AadharRetriever
from llm_client import call_agent_llm, MODEL as GEMINI_MODEL
from execution_record import (
    ExecutionMetadata, AgentDecision, Evidence, AccountabilityScore,
    ProvenanceRecordV2, risk_level_for,
)
from schema import new_id
from pii_masking import mask_extracted_fields, scrub_text

REQUIRED_FIELDS = ["decision_output", "confidence_score", "reasoning", "risk_factors"]
NAME_MATCH_THRESHOLD = 0.90
HIGH_VALUE_LOAN_THRESHOLD = 200_000
AGENT_ID = "A001"  # per AGENTS table: A001 = Aadhaar Verification Agent

_retriever = AadharRetriever()


def _assemble(orchestration_id: str, execution_id: str, agent_input: dict, agent_output: dict,
              model_id: str, rule_id: str, start_time: str, status: str,
              evidence_items: list, risk_factors: dict) -> dict:
    """Builds all five schema-shaped sections from raw agent results."""
    end_time = datetime.now(timezone.utc).isoformat()

    execution = ExecutionMetadata(
        execution_id=execution_id, orchestration_id=orchestration_id, agent_id=AGENT_ID,
        input_data=agent_input, output_data=agent_output, model_id=model_id, rule_id=rule_id,
        start_time=start_time, end_time=end_time, status=status,
    )

    decision = AgentDecision(
        decision_id=new_id(), execution_id=execution_id,
        decision_output=agent_output["decision_output"],
        confidence_score=agent_output["confidence_score"],
        reasoning=agent_output["reasoning"],
    )

    evidence = [
        Evidence(
            evidence_id=new_id(), execution_id=execution_id,
            source="Aadhar ChromaDB", document_reference=item["id"],
            retrieval_score=item.get("retrieval_score", 0.0),
        )
        for item in evidence_items
    ]

    composite_0_10 = round(
        (risk_factors["irreversibility"] * 0.40 +
         risk_factors["impact"] * 0.35 +
         (10 - risk_factors["explainability"]) * 0.25), 2
    )
    accountability = AccountabilityScore(
        score_id=new_id(), execution_id=execution_id,
        impact_score=risk_factors["impact"],
        irreversibility_score=risk_factors["irreversibility"],
        explainability_score=risk_factors["explainability"],
        composite_risk_score=composite_0_10,
        risk_level=risk_level_for(composite_0_10),
        review_required=composite_0_10 >= 6.0,
    )

    # Aadhaar always runs first in the orchestration sequence
    # (Aadhaar -> Payslip -> Bank -> CIBIL), so it has no prior record to
    # chain from - previous_record_hash is None by design, not an oversight.
    provenance = ProvenanceRecordV2(
        record_id=new_id(), orchestration_id=orchestration_id, execution_id=execution_id,
        event_type="agent_decision", input_data=agent_input, output_data=agent_output,
        previous_record_hash=None,
    )

    return {
        "execution": execution.__dict__,
        "decision": decision.__dict__,
        "evidence": [e.__dict__ for e in evidence],
        "accountability": accountability.__dict__,
        "provenance": provenance.__dict__,
    }


def aadhar_verification_agent(state: dict, orchestration_id: str = None) -> dict:
    orchestration_id = orchestration_id or state.get("application_id", new_id())
    execution_id = new_id()
    start_time = datetime.now(timezone.utc).isoformat()

    scoped = scope_for_aadhar_agent(state)
    extracted = extract_aadhaar_fields(scoped["aadhar_image_path"])
    # agent_input is what gets permanently STORED (AGENT_EXECUTIONS,
    # PROVENANCE_RECORDS) - it holds the MASKED extraction, never the raw
    # values. All verification logic below still uses the raw `extracted`
    # dict directly, since checking a checksum against a masked number
    # would be meaningless.
    agent_input = {"applicant_name": scoped["applicant_name"], "loan_amount": scoped["loan_amount"],
                   "extracted": mask_extracted_fields(extracted)}

    # --- Hard guardrails: reject before any LLM call (Internal KYC Policy 3.5) ---
    try:
        validate_aadhaar_format(extracted.get("aadhaar_number"))
    except ValidationError as e:
        output = {
            "decision_output": "invalid_format", "confidence_score": 1.0,
            "reasoning": scrub_text(f"Rejected at guardrail: {e}", extracted),
        }
        return _assemble(orchestration_id, execution_id, agent_input, output,
                          model_id="rule-engine", rule_id="validate_aadhaar_format",
                          start_time=start_time, status="rejected", evidence_items=[],
                          risk_factors={"irreversibility": 2, "impact": 5, "explainability": 10})

    try:
        validate_age(extracted.get("dob"))
    except ValidationError as e:
        output = {
            "decision_output": "underage_applicant", "confidence_score": 1.0,
            "reasoning": scrub_text(f"Rejected at guardrail: {e}", extracted),
        }
        return _assemble(orchestration_id, execution_id, agent_input, output,
                          model_id="rule-engine", rule_id="validate_age",
                          start_time=start_time, status="rejected", evidence_items=[],
                          risk_factors={"irreversibility": 2, "impact": 5, "explainability": 10})

    # --- Soft checks: build a query describing what's uncertain, not a hard fail ---
    concerns = []
    sim = name_similarity(extracted.get("name"), scoped["applicant_name"])
    if sim < NAME_MATCH_THRESHOLD:
        concerns.append(f"name similarity only {sim:.2f} between Aadhaar ('{extracted.get('name')}') "
                        f"and application ('{scoped['applicant_name']}')")

    if scoped.get("applicant_dob") and not dob_matches(extracted.get("dob"), scoped["applicant_dob"]):
        concerns.append(f"DOB mismatch: Aadhaar shows {extracted.get('dob')}, "
                        f"application shows {scoped['applicant_dob']}")

    if scoped["loan_amount"] > HIGH_VALUE_LOAN_THRESHOLD:
        concerns.append(f"loan amount {scoped['loan_amount']} exceeds high-value threshold "
                        f"of {HIGH_VALUE_LOAN_THRESHOLD} - address-proof rules apply")

    query = "; ".join(concerns) if concerns else "routine Aadhaar verification, no discrepancies found"
    retrieved = _retriever.retrieve(query, k=3)
    retrieved_text = "\n\n".join(f"[{r['id']}] {r['text']}" for r in retrieved)

    # --- LLM reasoning, grounded in retrieved policy clauses ---
    system = ("You are an Aadhaar verification agent for a personal loan pipeline. "
              "Decide 'verified', 'needs_review', or 'rejected' based on the extracted data, "
              "any flagged concerns, and the retrieved policy clauses. Cite the specific clause "
              "ID(s) you relied on in your reasoning.")
    user = (
        f"Extracted Aadhaar data: {extracted}\n"
        f"Application name: {scoped['applicant_name']}\n"
        f"Loan amount: {scoped['loan_amount']}\n"
        f"Concerns flagged: {concerns or 'none'}\n\n"
        f"Retrieved policy clauses:\n{retrieved_text}"
    )
    llm_result = call_agent_llm(system, user)
    validate_llm_output(llm_result, REQUIRED_FIELDS)
    llm_result["reasoning"] = scrub_text(llm_result["reasoning"], extracted)

    # rule_id should reflect what the reasoning actually relied on, not
    # just what was retrieved and available - an audit trail that lists
    # unused evidence as "the rule applied" overstates its own grounding.
    cited = [r["id"] for r in retrieved if r["id"] in llm_result["reasoning"]]
    rule_id = ", ".join(cited) if cited else "llm-reasoning-only"
    return _assemble(
        orchestration_id, execution_id, agent_input,
        {"decision_output": llm_result["decision_output"], "confidence_score": llm_result["confidence_score"],
         "reasoning": llm_result["reasoning"]},
        model_id=GEMINI_MODEL, rule_id=rule_id, start_time=start_time, status="completed",
        evidence_items=retrieved, risk_factors=llm_result["risk_factors"],
    )
