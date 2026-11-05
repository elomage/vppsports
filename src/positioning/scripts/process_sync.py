#!/usr/bin/env python3
"""Process the SYNC button presses of one recording: pair GNSS and XDK presses and date the XDK clock.

Usage (SD card folders ``gnss/`` and ``xdk/`` copied side by side, log number 5):
  python scripts/process_sync.py --data-dir ../../../our_data/sinhron_test_2026_11_02 --log 5 --session 20261103_231217Z_LOG00005

Or name the files one by one:
  python scripts/process_sync.py --gnss-bin LOG00005.BIN --gnss-sync SYNC00005.CSV --xdk-sync SYNC_005.CSV [--xdk-log LOG_005.CSV]

With --session the result is written to out/<session>/imu/sync_button_<xdk>.json, where fusion_compare.py
and gnss_xdk_fusion.py --sync button find it.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from session_paths import find_original_bin, output_subdir, resolve_session_dir
from sync_button import compute_button_sync, describe, sync_files_for, xdk_row_check


def main() -> int:
    parser = argparse.ArgumentParser(description="Pair GNSS and XDK SYNC button presses.")
    parser.add_argument("--data-dir", type=Path, help="Folder with gnss/ and xdk/ SD card copies")
    parser.add_argument("--log", type=int, help="Log number in --data-dir (LOG0000N.BIN / LOG_00N.CSV)")
    parser.add_argument("--gnss-bin", type=Path)
    parser.add_argument("--gnss-sync", type=Path)
    parser.add_argument("--xdk-sync", type=Path)
    parser.add_argument("--xdk-log", type=Path, help="XDK log, to cross-check the press times against the log rows")
    parser.add_argument("--session", help="out/ recording folder; its original BIN is used and the result is stored there")
    args = parser.parse_args()

    gnss_bin, gnss_sync, xdk_log, xdk_sync = args.gnss_bin, args.gnss_sync, args.xdk_log, args.xdk_sync
    if args.data_dir:
        if args.log is None:
            parser.error("--data-dir needs --log")
        b, gs, xl, xs = sync_files_for(args.data_dir / "gnss", args.data_dir / "xdk", args.log)
        gnss_bin, gnss_sync, xdk_log, xdk_sync = gnss_bin or b, gnss_sync or gs, xdk_log or xl, xdk_sync or xs
    session_dir = resolve_session_dir(args.session) if args.session else None
    if session_dir is not None:
        gnss_bin = find_original_bin(session_dir)
    if not (gnss_bin and gnss_sync and xdk_sync):
        parser.error("give --data-dir/--log or --gnss-bin, --gnss-sync and --xdk-sync")

    sync = compute_button_sync(gnss_sync, xdk_sync, gnss_bin)
    print(describe(sync))
    check = []
    if xdk_log and Path(xdk_log).is_file():
        check = xdk_row_check(xdk_sync, xdk_log)
        worst = max((abs(c["diff_ms"]) for c in check), default=0.0)
        print(f"XDK press time vs the t_ms of the logged row: worst {worst:.0f} ms over {len(check)} presses")
    if session_dir is not None:
        name = Path(xdk_log).stem if xdk_log else Path(xdk_sync).stem
        out = output_subdir(session_dir, "imu") / f"sync_button_{name}.json"
        out.write_text(json.dumps({**asdict(sync), "xdk_row_check": check}, indent=2), encoding="utf-8")
        print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
