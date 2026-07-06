#!/usr/bin/env python3
"""Generate a rover-only RTKLIB single solution from a recording's RINEX files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from gnss_track_utils import ensure_observation_single_solution, resolve_rnx2rtkp
from session_paths import output_subdir, resolve_session_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a rover-only observation single-position solution.")
    parser.add_argument("recording", help="Recording output directory, e.g. 20260510_181210Z_LOG00006")
    parser.add_argument("--rnx2rtkp", type=Path, help="Path to rnx2rtkp.exe. Default: RTKLIB_RNX2RTKP_EXE from .env.")
    parser.add_argument("--single-pos", type=Path, help="Default: out/<recording>/ppk/observation_single.pos")
    parser.add_argument("--single-csv", type=Path, help="Default: out/<recording>/ppk/observation_single.csv")
    parser.add_argument("--force", action="store_true", help="Regenerate even if observation_single.csv already exists.")
    args = parser.parse_args()

    session_dir = resolve_session_dir(args.recording)
    ppk_dir = output_subdir(session_dir, "ppk")
    single_pos = args.single_pos or ppk_dir / "observation_single.pos"
    single_csv = args.single_csv or ppk_dir / "observation_single.csv"

    ensure_observation_single_solution(
        session_dir=session_dir,
        rnx2rtkp=resolve_rnx2rtkp(args.rnx2rtkp),
        single_pos=single_pos,
        single_csv=single_csv,
        force=args.force,
    )

    print(f"Observation single POS: {single_pos}")
    print(f"Observation single CSV: {single_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
