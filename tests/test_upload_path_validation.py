import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from orchestrator.orchestrator import validate_state


def test_validate_state_rejects_missing_uploaded_files(tmp_path):
    missing_path = tmp_path / "missing_aadhaar.png"
    state = {
        "user_id": "100001",
        "application_id": "APP-100001",
        "loan_amount": 150000,
        "applicant_name": "Test User",
        "cibil_score": 720,
        "applicant_data": {
            "aadhar_image_path": str(missing_path),
            "payslip_file_path": str(tmp_path / "missing_payslip.pdf"),
            "bank_statement_file_path": str(tmp_path / "missing_bank.csv"),
        },
    }

    with pytest.raises(ValueError, match="does not exist|Missing uploaded file"):
        validate_state(state)
