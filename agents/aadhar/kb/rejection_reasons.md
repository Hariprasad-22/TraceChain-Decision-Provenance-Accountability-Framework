# Common Rejection Reasons — Aadhar Verification
Reference text for the Aadhar Verification Agent to match against and
cite when flagging or rejecting a submission.

## R1: Invalid Aadhaar Number Format
The submitted number is not exactly 12 digits, or fails the Verhoeff
checksum validation. This indicates either a data-entry error or a
non-genuine number. Reject at guardrail stage; do not escalate to LLM
reasoning (see Internal KYC Policy Section 3.5).

## R2: Name Mismatch
The name on the Aadhaar does not sufficiently match (below 90%
similarity) the name on the loan application. Common legitimate causes
include maiden-name changes, transliteration differences, or middle-name
omission — these should be flagged for human review rather than
auto-rejected outright, since they may be false positives.

## R3: Date of Birth Mismatch
DOB on Aadhaar does not match DOB on the application. Unlike name
mismatches, DOB mismatches rarely have an innocent explanation and
should be treated as higher-confidence rejections.

## R4: Underage Applicant
Applicant is under 18 years of age as of the application date. Hard
reject — no escalation path, per lending regulation.

## R5: Masked Aadhaar Used as Sole Address Proof (High-Value Loan)
Loan amount exceeds INR 200,000 and only a masked Aadhaar was submitted
with no supplementary address document, violating Internal KYC Policy
Section 2.2. Flag for additional-document request, not outright
rejection.

## R6: Unverifiable Submission Format
A plain scanned image or photograph of an Aadhaar card was submitted
with no accompanying corroborating documents, and automated verification
cannot confirm authenticity per UIDAI Guidelines Section 4.2. Route to
corroborating checks; if those also fail or are inconclusive, escalate
to human review rather than auto-reject, since the underlying Aadhaar
may still be genuine.

## R7: Open Update Request on Record
UIDAI records indicate a pending demographic update request against this
Aadhaar number. Current submitted details may not reflect the applicant's
true current status. Always escalate to human review — never auto-verify
or auto-reject.

## R8: Stale e-Aadhaar Document
Downloaded e-Aadhaar PDF is more than 12 months old as of the application
date. Not an automatic rejection, but confidence score should be reduced
and a fresh download requested if feasible.

## R9: Duplicate Submission Detected
The same Aadhaar number has already been used in a separate, still-open
loan application within the system. Flag for human review to rule out
identity fraud or an accidental duplicate submission by the same
applicant.
