"""Ceļi un sys.path sagatavošana (scripts/ ir tajā pašā projektā)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
ROOT = PACKAGE_DIR.parent  # src/positioning
SCRIPTS_DIR = ROOT / "scripts"
OUT_DIR = Path(os.environ.get("POSITIONING_OUT", ROOT / "out")).resolve()

for _p in (SCRIPTS_DIR, SCRIPTS_DIR / "converting" / "to_csv"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

PYTHON = os.environ.get("POSITIONING_PYTHON", sys.executable)


def script(*parts: str) -> str:
    return str(SCRIPTS_DIR.joinpath(*parts))


def session_dir(name: str) -> Path:
    """Sesijas mape zem OUT_DIR; noraida ceļu izkļūšanu no OUT_DIR."""
    if not name or "/" in name or "\\" in name or name in (".", "..") or ".." in name:
        raise ValueError(f"Nederīgs ieraksta nosaukums: {name!r}")
    path = OUT_DIR / name
    if not path.is_dir():
        raise ValueError(f"Ieraksts nav atrasts: {name}")
    return path
