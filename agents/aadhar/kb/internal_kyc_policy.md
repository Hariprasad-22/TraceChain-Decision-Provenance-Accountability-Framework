# Internal KYC Policy — Aadhar Verification (Personal Loan)
Team ZenX / TraceChain internal policy document. Synthetic, authored for
capstone use — not an actual bank's policy.

## Section 1: Acceptable Submission Types

1.1 For personal loan applications, Aadhaar may be submitted as: physical
Aadhaar letter (scanned), e-Aadhaar (downloaded PDF), Aadhaar PVC card
(scanned), or Aadhaar Paperless Offline e-KYC (signed XML).

1.2 Signed XML submissions are preferred and receive the highest
automated-verification confidence tier, since authenticity can be
cryptographically confirmed per UIDAI guidelines Section 2.1.

1.3 Image/PDF submissions (non-XML) are accepted but are routed through
additional corroborating checks before being marked verified (see
Section 3).

## Section 2: Identity vs Address Proof

2.1 A full (unmasked) Aadhaar may be used for both identity proof and
address proof.

2.2 A masked Aadhaar (per UIDAI guidelines Section 1.2) may be used for
identity proof only. It is NOT accepted as standalone address proof for
loan applications above INR 200,000 — a supplementary address document
(utility bill, rent agreement) is required in that case.

2.3 For loans at or below INR 200,000, masked Aadhaar alone may serve as
both identity and address proof, given the lower financial exposure.

## Section 3: Corroborating Checks (Non-XML Submissions)

3.1 Name on Aadhaar must match name on the loan application (fuzzy match
threshold: 90% similarity, accounting for minor spelling/transliteration
variance).

3.2 Date of birth on Aadhaar must match date of birth on the loan
application exactly.

3.3 Applicant must be 18 years or older as of the application date.

3.4 Aadhaar number must be exactly 12 digits and pass the Verhoeff
checksum validation.

3.5 If any of 3.1–3.4 fail, the submission is rejected at the guardrail
(tool validation) stage before any LLM reasoning is applied.

## Section 4: Validity & Freshness

4.1 A submitted e-Aadhaar or XML file should reflect current demographic
details; if the applicant has an open UIDAI update request against their
Aadhaar number, the agent should flag the submission for human review
rather than auto-verify.

4.2 There is no fixed "expiry" for Aadhaar itself, but downloaded e-Aadhaar
PDFs older than 12 months from the application date should be flagged as
lower-confidence and re-verification requested.

## Section 5: Risk Factor Guidance for This Agent

5.1 Irreversibility: identity verification itself is low-irreversibility
(can be re-checked), but an incorrect verification that lets a fraudulent
application proceed downstream carries higher effective irreversibility -
score irreversibility based on submission type: XML=2, image/PDF
non-XML=4.

5.2 Impact: scale with loan amount tier per Section 2.2/2.3 - higher loan
amounts needing address-proof escalation should score impact higher.

5.3 Explainability: score higher (more explainable) when the agent's
decision cites a specific retrieved clause from this document or the
UIDAI guidelines; score lower when the agent's reasoning does not
reference any retrieved policy text.
