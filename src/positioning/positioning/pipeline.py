"""Brauciena apstrāde: CSV -> RINEX -> single/PPK (esošie skripti kā apakšprocesi)."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from . import store
from .paths import OUT_DIR, PYTHON, SCRIPTS_DIR, script

RINEX_SCRIPT = ("converting", "to_rinex", "rinex305_toolkit", "rinex305_toolkit", "rinex305_conversion_full.py")
STEPS = ("csv", "rinex", "observation_single", "ppk")
Log = Callable[[str], None]


def _run(cmd: list[str], log: Log | None) -> dict:
    if log:
        log("$ " + " ".join(cmd))
    r = subprocess.run(cmd, cwd=SCRIPTS_DIR.parent, capture_output=True, text=True)
    if log:
        for line in (r.stdout + r.stderr).splitlines()[-40:]:
            log(line)
    return {"command": cmd, "returncode": r.returncode, "stdout": r.stdout[-4000:], "stderr": r.stderr[-4000:]}


def commands_for(step: str, session: Path, base: str = "auto", ppk_mode: str = "all", obs_source: str = "auto") -> list[list[str]]:
    s = str(session)
    if step == "csv":
        return [[PYTHON, script("converting", "to_csv", "unicore_n4_extract.py"), s],
                [PYTHON, script("converting", "to_csv", "filter_zero_coords.py"), s]]
    if step == "rinex":
        return [[PYTHON, script(*RINEX_SCRIPT), s, "--obs-source", obs_source]]
    if step == "observation_single":
        return [[PYTHON, script("ppk", "run_observation_single.py"), s]]
    if step == "ppk":
        modes = ["fixed", "float", "dgps"] if ppk_mode == "all" else [ppk_mode]
        return [[PYTHON, script("ppk", "run_ppk.py"), s, "--base", base, "--mode", m] for m in modes]
    raise ValueError(f"Nezināms solis: {step}")


def process(trip_id: str, steps: list[str] | None = None, base: str = "auto", ppk_mode: str = "all",
            obs_source: str = "auto", log: Log | None = None) -> dict:
    """Izpilda izvēlētos soļus; apstājas pie pirmās kļūdas (PPK kļūda neaptur, jo bāze var nebūt pieejama)."""
    trip = store.get_trip(trip_id)
    session = OUT_DIR / trip["session"]
    steps = steps or ["csv", "rinex", "observation_single"]
    for s in steps:
        if s not in STEPS:
            raise ValueError(f"Nezināms solis: {s}")
    results, ok = [], True
    for step in steps:
        step_ok = True
        for cmd in commands_for(step, session, base, ppk_mode, obs_source):
            res = _run(cmd, log)
            res["step"] = step
            results.append(res)
            step_ok = step_ok and res["returncode"] == 0
        if step_ok:
            store.update_trip(trip_id, status={step: store.now()})
        elif step != "ppk":
            ok = False
            break
        else:
            ok = False
    return {"ok": ok, "trip": trip_id, "results": results}


def rinex_files(trip_id: str) -> list[Path]:
    d = OUT_DIR / store.get_trip(trip_id)["session"] / "rinex"
    return sorted(p for p in d.glob("*") if p.is_file()) if d.is_dir() else []
