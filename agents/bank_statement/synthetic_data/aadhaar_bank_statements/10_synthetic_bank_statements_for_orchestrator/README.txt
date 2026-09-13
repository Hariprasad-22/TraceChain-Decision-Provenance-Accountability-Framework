SYNTHETIC BANK STATEMENT TEST SET
=================================

10 synthetic CSV bank statements are provided, one for each synthetic Aadhaar sample.

Period:
2026-04-01 through 2026-09-30 (6 consecutive months)

Files:
- bank_statement_001_ud...csv through bank_statement_010_...csv
- orchestrator_bank_statement_mapping.csv

Important:
- All records are synthetic and for software testing only.
- expected_test_scenario is a TEST LABEL, not a real lending decision.
- The dataset deliberately contains ACCEPT, REJECT, and MANUAL_REVIEW scenarios.
- The orchestrator mapping file tells the orchestrator which statement belongs to which applicant/Aadhaar.

Main transaction columns:
transaction_date, value_date, description, debit, credit, balance,
transaction_type, category, reference_id, account_holder_name,
aadhaar_id, applicant_id.

Useful categories:
SALARY, OTHER_INCOME, HOUSING, LOAN_EMI, EMI_RETURN, UTILITIES,
GROCERIES, TRANSPORT, DISCRETIONARY, CASH_WITHDRAWAL,
LARGE_CREDIT, LARGE_DEBIT, OVERDRAFT.
