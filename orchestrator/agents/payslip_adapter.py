"""
agents/payslip_adapter.py
--------------------------
Adapter for the Payslip Income Verification Agent (A002).

Key differences from the Aadhaar agent that this adapter fixes:

1. OUTPUT KEY NAMES — Payslip uses uppercase table-style keys:
       AGENT_EXECUTIONS, AGENT_DECISIONS, EVIDENCE,
       ACCOUNTABILITY_SCORES, PROVENANCE_RECORDS
   We normalise these to the orchestrator's canonical lowercase keys:
       execution, decision, evidence, accountability, provenance

2. AGENT ID — Payslip hardcodes "P001"; the TraceChain AGENTS table
   expects "A002". We override it here.

3. ORCHESTRATION_ID — The payslip agent generates its own orchestration_id
   internally. We replace it with the orchestrator's real ID everywhere.

4. SEQUENCE NUMBER — Fixed to 2 (Payslip runs second).

5. OBJECT vs DICT — Payslip build_execution() returns dataclass instances,
   not plain dicts. We call __dict__ to convert them.

6. INPUT SCOPING — Payslip needs: applicant_name, declared_monthly_income,
   payslip_file_path (as Path), and an aadhaar_reference dict.

The payslip agent's build_execution() function is called directly
(not main()) so the orchestrator controls which account/scenario runs.
"""

import sys
import uuid
import importlib.util
import logging
from pathlib import Path
from dataclasses import asdict

logger = logging.getLogger(__name__)

try:
    from .import_isolation import prepare_agent_import, restore_orchestrator_path
except ImportError:  # pragma: no cover - script-style execution from orchestrator/
    from agents.import_isolation import prepare_agent_import, restore_orchestrator_path

try:
    from ..name_match import annotate_name_mismatch
except ImportError:  # pragma: no cover
    from name_match import annotate_name_mismatch

_ORCH_DIR = Path(__file__).resolve().parent.parent
_PAYSLIP_DIR = _ORCH_DIR.parent / "agents" / "payslip"
_PAYSLIP_FILE = _PAYSLIP_DIR / "main.py"

AGENT_ID        = "A002"
SEQUENCE_NUMBER = 2


def _load_payslip_build_execution():
    """Reload payslip main.py so reasoning changes apply without stale imports."""
    prepare_agent_import(_PAYSLIP_DIR)
    try:
        if not _PAYSLIP_FILE.exists():
            raise FileNotFoundError(f"Payslip agent file not found at {_PAYSLIP_FILE}")
        for key in list(sys.modules):
            if key in {"tracechain_payslip_agent"} or key.startswith("tracechain_payslip"):
                del sys.modules[key]
        _spec = importlib.util.spec_from_file_location("tracechain_payslip_agent", _PAYSLIP_FILE)
        if _spec is None or _spec.loader is None:
            raise ImportError(f"Could not create import spec for {_PAYSLIP_FILE}")
        _payslip_module = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_payslip_module)
        return _payslip_module.build_execution
    finally:
        restore_orchestrator_path(_ORCH_DIR)


def _scope(state: dict) -> dict:
    """
    Return only the fields the Payslip agent is permitted to read.
    """
    return {
        "applicant_name":        state["applicant_name"],
        "declared_monthly_income": state.get("declared_monthly_income"),
        "loan_amount":           state.get("loan_amount"),
        "repayment_period_months": state.get("repayment_period_months"),
        "payslip_file_path":     Path(state["applicant_data"]["payslip_file_path"]),
        "aadhaar_reference": {
            "name":    state["applicant_name"],
            "dob":     state.get("applicant_dob", ""),
            "gender":  state.get("applicant_data", {}).get("gender", ""),
            "address": state.get("applicant_data", {}).get("address", ""),
        },
    }


def _to_dict(obj):
    """Convert dataclass or plain object to dict."""
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return obj


def _normalise(raw: dict, orchestration_id: str) -> dict:
    """
    Convert payslip agent's uppercase-keyed output to canonical shape
    and fix all orchestration_id / agent_id references.
    """
    execution      = _to_dict(raw["AGENT_EXECUTIONS"])
    decision       = _to_dict(raw["AGENT_DECISIONS"])
    evidence_objs  = raw["EVIDENCE"]                          # list of dataclass/objects
    accountability = _to_dict(raw["ACCOUNTABILITY_SCORES"])
    provenance     = _to_dict(raw["PROVENANCE_RECORDS"])

    evidence = [_to_dict(e) for e in evidence_objs]

    # Fix agent_id (P001 → A002)
    execution["agent_id"]        = AGENT_ID
    execution["orchestration_id"] = orchestration_id
    execution["sequence_number"]  = SEQUENCE_NUMBER
    provenance["orchestration_id"] = orchestration_id

    return {
        "execution":      execution,
        "decision":       decision,
        "evidence":       evidence,
        "accountability": accountability,
        "provenance":     provenance,
    }


def run(state: dict, orchestration_id: str) -> dict:
    """
    Execute the Payslip agent and return a normalised result dict.

    Parameters
    ----------
    state : dict
        Full application state. Must include:
          - applicant_name
          - applicant_dob (optional but recommended)
          - declared_monthly_income (float)
          - applicant_data.payslip_file_path  (str path to PDF)
          - loan_amount (optional, used for EMI affordability)
          - repayment_period_months (optional, used for EMI affordability)
          - applicant_data.gender (optional)
          - applicant_data.address (optional)
          - applicant_data.scenario (optional, defaults to 'everything_correct')
    orchestration_id : str

    Returns
    -------
    dict with keys: execution, decision, evidence, accountability, provenance
    """
    scoped = _scope(state)
    account_id = state.get("user_id", state.get("application_id", str(uuid.uuid4())))
    scenario   = state.get("applicant_data", {}).get("scenario", "everything_correct")

    # Build an aadhaar-style record dict for the payslip agent's identity check
    aadhaar_record = {
        "name":    scoped["aadhaar_reference"]["name"],
        "dob":     scoped["aadhaar_reference"]["dob"],
        "gender":  scoped["aadhaar_reference"]["gender"],
        "address": scoped["aadhaar_reference"]["address"],
    }

    logger.info(
        "[A002] Running Payslip agent for account_id=%s scenario=%s "
        "loan_amount=%s tenure_months=%s",
        account_id,
        scenario,
        scoped.get("loan_amount"),
        scoped.get("repayment_period_months"),
    )

    _payslip_build_execution = _load_payslip_build_execution()
    raw = _payslip_build_execution(
        account_id=account_id,
        aadhaar_record=aadhaar_record,
        payslip_path=scoped["payslip_file_path"],
        scenario=scenario,
        loan_amount=scoped.get("loan_amount"),
        repayment_period_months=scoped.get("repayment_period_months"),
    )

    result = _normalise(raw, orchestration_id)

    # Annotate only — do not override Payslip's own decision_output.
    payslip = ((result.get("execution") or {}).get("input_data") or {}).get("extracted_payslip") or {}
    doc_name = (payslip.get("employee_name") or "").strip() or None
    if annotate_name_mismatch(
        result,
        agent_label="Payslip",
        applicant_name=str(state.get("applicant_name", "")),
        document_name=doc_name,
    ):
        logger.warning("[A002] Name mismatch annotated (decision left as agent returned)")

    logger.info(
        "[A002] Done — decision=%s confidence=%.2f reasoning=%s",
        result["decision"]["decision_output"],
        result["decision"]["confidence_score"],
        (result["decision"].get("reasoning") or "")[:160],
    )
    return result
