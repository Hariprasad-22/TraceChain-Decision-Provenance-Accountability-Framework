"""
Streamlit UI for the Aadhar Verification Agent.

Run once with: streamlit run aadhar_agent_app.py
It opens a browser tab and stays running - you can upload a new Aadhaar
image and get a result as many times as you want without touching the
terminal again.
"""
import os
import tempfile

import streamlit as st

from aadhar_agent import aadhar_verification_agent
from execution_record import verify_provenance_record, ProvenanceRecordV2

st.set_page_config(page_title="Aadhar Verification Agent", page_icon="🪪")

st.title("🪪 Aadhar Verification Agent")
st.caption("TraceChain — upload an Aadhaar card image and see the agent's decision, reasoning, and risk score.")

with st.form("verification_form"):
    uploaded_file = st.file_uploader("Aadhaar card image", type=["png", "jpg", "jpeg"])
    applicant_name = st.text_input("Applicant name (as on the loan application)")
    applicant_dob = st.text_input("Applicant DOB on the application (YYYY-MM-DD)", placeholder="1991-11-19")
    loan_amount = st.number_input("Loan amount (INR)", min_value=1000.0, value=150_000.0, step=10_000.0)
    account_id = st.text_input("Account / application ID", value="100001")
    submitted = st.form_submit_button("Run Verification")

if submitted:
    if not uploaded_file or not applicant_name:
        st.error("Please upload an image and enter the applicant name.")
    else:
        st.image(uploaded_file, caption="Uploaded Aadhaar card", width=400)

        suffix = os.path.splitext(uploaded_file.name)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded_file.getbuffer())
            tmp_path = tmp.name

        state = {
            "application_id": account_id,
            "loan_amount": loan_amount,
            "applicant_name": applicant_name,
            "applicant_dob": applicant_dob or None,
            "applicant_data": {"aadhar_image_path": tmp_path},
        }

        with st.spinner("Extracting fields, running guardrails, retrieving policy, reasoning..."):
            try:
                result = aadhar_verification_agent(state, orchestration_id=account_id)
            except Exception as e:
                st.error(f"Agent error: {e}")
                result = None
            finally:
                os.unlink(tmp_path)

        if result:
            decision = result["decision"]
            accountability = result["accountability"]
            evidence = result["evidence"]
            provenance = result["provenance"]

            color = {"verified": "green", "needs_review": "orange"}.get(decision["decision_output"], "red")
            st.markdown(f"### Decision: :{color}[{decision['decision_output']}]")

            col1, col2 = st.columns(2)
            col1.metric("Confidence", f"{decision['confidence_score']:.2f}")
            col1.metric("Composite risk score", f"{accountability['composite_risk_score']}/10 ({accountability['risk_level']})")

            col2.write(f"**Irreversibility:** {accountability['irreversibility_score']}/10")
            col2.write(f"**Impact:** {accountability['impact_score']}/10")
            col2.write(f"**Explainability:** {accountability['explainability_score']}/10")

            if accountability["review_required"]:
                st.warning("⚠️ Flagged for human review (composite risk score ≥ 6.0)")

            st.markdown("**Reasoning:**")
            st.info(decision["reasoning"])

            if evidence:
                st.markdown("**Evidence retrieved (policy clauses cited):**")
                for e in evidence:
                    st.write(f"`{e['document_reference']}` — retrieval score: {e['retrieval_score']}")
            else:
                st.markdown("*No policy clauses were retrieved for this decision.*")

            st.markdown("**Provenance record (tamper-evident, PROVENANCE_RECORDS table):**")
            record = ProvenanceRecordV2(
                record_id=provenance["record_id"], orchestration_id=provenance["orchestration_id"],
                execution_id=provenance["execution_id"], event_type=provenance["event_type"],
                input_data=provenance["input_data"], output_data=provenance["output_data"],
                previous_record_hash=provenance["previous_record_hash"],
            )
            pcol1, pcol2 = st.columns(2)
            pcol1.code(provenance["record_hash"][:24] + "...", language=None)
            pcol2.write(f"Chain integrity verified: {'✅' if verify_provenance_record(record) else '❌'}")

            with st.expander("Full raw result — execution / decision / evidence / accountability / provenance (JSON)"):
                st.json(result)
