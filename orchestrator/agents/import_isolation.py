"""
agents/import_isolation.py
--------------------------
Each agent package ships top-level modules with the same names
(especially ``execution_record``).  Python caches the first import in
``sys.modules``, so later agents would silently bind the wrong class
(e.g. Payslip passing ``retrieval_distance`` into Aadhaar's Evidence).

The Aadhaar tree also ships a top-level ``chain.py``, which shadows the
orchestrator's ``chain/`` *package* whenever that agent directory sits
ahead of the orchestrator on ``sys.path`` (e.g. after a uvicorn --reload).

Call ``prepare_agent_import(agent_dir)`` immediately before importing
an agent entrypoint so that agent's directory wins and shared module
names are reloaded from that directory.  Call
``restore_orchestrator_path(orch_dir)`` afterwards so orchestrator
packages (``chain``, ``scoring``, …) keep resolving correctly.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Modules that exist (with different contents) in more than one agent tree.
# Keep this list narrow: we do NOT touch the orchestrator package name
# ``agents`` itself, because deleting that package from sys.modules while the
# orchestrator is still importing submodules causes partial-import KeyError
# failures.
_COLLIDING_MODULES = (
    "execution_record",
    "scoring",
    "chain",
    "db",
    "final_decision",
)

# Names that belong to the orchestrator package tree and must not stay bound
# to an agent-side impostor module (e.g. aadhaar's chain.py).
_ORCHESTRATOR_PACKAGES = (
    "chain",
    "scoring",
    "db",
    "agents",
    "final_decision",
)


def prepare_agent_import(agent_dir: Path | str) -> None:
    """Put *agent_dir* first on ``sys.path`` and drop colliding cached modules."""
    agent_dir = str(Path(agent_dir).resolve())

    # Ensure this agent is searched first.
    while agent_dir in sys.path:
        sys.path.remove(agent_dir)
    sys.path.insert(0, agent_dir)

    for name in _COLLIDING_MODULES:
        for key in list(sys.modules):
            if key == name or key.startswith(name + "."):
                del sys.modules[key]


def _is_under(path: Path | str | None, root: Path) -> bool:
    if not path:
        return False
    try:
        return Path(path).resolve().is_relative_to(root)
    except (OSError, ValueError):
        return False


def restore_orchestrator_path(orch_dir: Path | str) -> None:
    """
    Keep agent dirs importable, but put the orchestrator directory first and
    drop any cached modules that shadowed orchestrator packages (notably
    ``chain`` from aadhaar's ``chain.py``).
    """
    orch_root = Path(orch_dir).resolve()
    orch_dir_s = str(orch_root)

    while orch_dir_s in sys.path:
        sys.path.remove(orch_dir_s)
    sys.path.insert(0, orch_dir_s)

    for name in _ORCHESTRATOR_PACKAGES:
        for key in list(sys.modules):
            if key != name and not key.startswith(name + "."):
                continue
            mod = sys.modules.get(key)
            origin = getattr(mod, "__file__", None)
            paths = getattr(mod, "__path__", None)
            if _is_under(origin, orch_root):
                continue
            if paths and any(_is_under(p, orch_root) for p in paths):
                continue
            # Impostor (e.g. aadhaar chain.py) or unknown — drop so the real
            # orchestrator package can be imported again.
            if origin or paths:
                del sys.modules[key]
