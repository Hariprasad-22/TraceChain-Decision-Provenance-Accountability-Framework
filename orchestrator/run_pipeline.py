"""
run_pipeline.py
---------------
CLI test runner for the TraceChain Orchestrator.

Usage:
    cd orchestrator
    python run_pipeline.py

Uses account 100001 (Udyati Seth) as the default test case,
matching the synthetic data already in the database.

You can edit the STATE dict below to test different applicants.
"""

import json
import sys
import io
from pathlib import Path

# Windows cmd/PowerShell may default to cp1252 which can't encode ₹ or emoji.
# Reconfigure stdout and stderr to UTF-8 so the output renders correctly.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure orchestrator package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from orchestrator import run_pipeline

# ─── Test Application State ───────────────────────────────────────────────────
# Edit these fields to test different scenarios.

BASE_DIR  = Path(__file__).resolve().parent.parent / "agents"
AADHAAR_IMG = BASE_DIR / "aadhaar" / "Deloitte_capstone" / "synthetic_aadhar_realistic" / "aadhar_realistic_001.png"
PAYSLIP_PDF = BASE_DIR / "payslip" / "PythonProject1" / "Payslips" / "payslip_02_Dev_Bhargava.pdf"

STATE = {
    # Identity
    "user_id":         "100002",
    "application_id":  "APP-100004",
    "applicant_name":  "Dev Bhargava",
    "applicant_dob":   "1963-01-27",

    # Loan
    "loan_amount": 170_000.0,

    # Income
    "declared_monthly_income": 65_800.0,

    # CIBIL
    "cibil_score":             650,
    "credit_utilization_pct":  45.0,
    "dpd_history":             [0,0,30],      # empty = no overdue accounts

    # Document paths + metadata
    "applicant_data": {
        "aadhar_image_path": str(AADHAAR_IMG),
        "payslip_file_path": str(PAYSLIP_PDF),
        "scenario":          "everything_correct",  # payslip scenario
        "gender":            "Male",
        "address":           "Hayre,Durg-017468",
    },
}


if __name__ == "__main__":
    print("\n" + "=" * 65)
    print("  TraceChain Orchestrator — Test Run")
    print("=" * 65)
    print(f"  Applicant  : {STATE['applicant_name']}")
    print(f"  Application: {STATE['application_id']}")
    print(f"  Loan Amount: ₹{STATE['loan_amount']:,.0f}")
    print(f"  CIBIL Score: {STATE['cibil_score']}")
    print("=" * 65 + "\n")

    result = run_pipeline(STATE)

    print("\n" + "=" * 65)
    print("  PIPELINE RESULT")
    print("=" * 65)

    if "error" in result:
        print(f"\n❌ ERROR: {result['error']}")
        sys.exit(1)

    print(f"\n🏦 Loan Decision      : {result['loan_decision']}")
    print(f"📊 Overall Risk Score : {result['overall_accountability']['composite_score']:.2f}/10"
          f"  ({result['overall_accountability']['risk_level']})")
    print(f"🔗 Chain Verified     : {'✅' if result['chain_verified'] else '❌'} {result['chain_verified']}")
    print(f"🆔 Orchestration ID   : {result['orchestration_id']}")
    print(f"🤖 Responsible Agent  : {result['responsible_agent']}")

    print("\n── Agent Breakdown ──────────────────────────────────────")
    for agent in result["agent_breakdown"]:
        symbol = "✅" if agent["decision_output"] == "verified" else \
                 "❌" if agent["decision_output"] in ("rejected", "high_risk") else "⚠️"
        print(f"  {symbol} [{agent['agent_id']}] {agent['agent_name']}")
        print(f"       Decision  : {agent['decision_output']}")
        print(f"       Confidence: {agent['confidence_score']:.0%}")
        print(f"       Risk Score: {agent['composite_risk_score']:.1f}/10")
        print(f"       Reasoning : {agent['reasoning'][:120]}...")
        print()

    print("── Full Reasoning ───────────────────────────────────────")
    print(result["reasoning"])
    print("\n" + "=" * 65)

    # Dump full result as JSON
    output_path = Path(__file__).resolve().parent / "last_pipeline_result.json"
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\n📄 Full result saved to: {output_path}")
