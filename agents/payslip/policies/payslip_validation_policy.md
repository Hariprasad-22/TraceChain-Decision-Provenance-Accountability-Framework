# Payslip Validation Policy

## 1. Required Information

A payslip should contain relevant information such as:

- Employee name
- Employer name
- Pay period
- Employee ID, when available
- Salary information
- Deductions
- Net salary

## 2. Document Availability

If the required payslip is missing, income verification cannot be completed.

## 3. Document Age

The system should verify that the payslip falls within the permitted verification period.

An outdated payslip should be flagged or rejected according to the configured verification policy.

## 4. Mathematical Consistency

The salary components should be internally consistent.

## 5. Suspicious Documents

The system should flag documents when there are:

- Missing required fields
- Inconsistent salary calculations
- Identity mismatches
- Unusual or inconsistent information
- Possible document manipulation

## 6. Verification Decision

The system may produce:

- VERIFIED
- SUSPICIOUS
- REJECTED
- MANUAL_REVIEW

The final decision should include the reason and supporting evidence.