#!/usr/bin/env python3
"""Attach an XDK log (with its SYNC button files) to an archived GNSS recording.

Usage:
  python scripts/attach_xdk.py <recording> --data-dir <folder with gnss/ and xdk/> --log 5
  python scripts/attach_xdk.py <recording> --xdk LOG_005.CSV --xdk-sync SYNC_005.CSV --gnss-sync SYNC00005.CSV
  python scripts/attach_xdk.py <recording> --list
  python scripts/attach_xdk.py <recording> --set-default LOG_004.CSV

What it does:
* copies the XDK log into  out/<recording>/imu/  and the two SYNC files into  out/<recording>/sync/
* pairs the button presses (sync_button.py) and stores the result, so the recording knows how its XDK clock
  relates to the GNSS time
* checks how much of the XDK log overlaps the GNSS recording
* registers the log in out/<recording>/imu/imu_links.json and, with --default (the default for the first
  one), marks it as the file the GUI preselects and the fusion scripts use when none is named.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import imu_links
from session_paths import find_original_bin, output_subdir, resolve_session_dir
from sync_button import compute_button_sync, sync_files_for


def gnss_log_in_sync_header(path: Path) -> str | None:
    """The SD card log named in the SYNC file header ('# log=0:/LOGS/LOG00007.BIN'), if any."""
    try:
        for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
            match = re.match(r"#\s*log=(.+)", line)
            if match:
                return match.group(1).strip()
    except OSError:
        pass
    return None


def attach(
    session_dir: Path,
    xdk: Path,
    xdk_sync: Path | None = None,
    gnss_sync: Path | None = None,
    make_default: bool | None = None,
    note: str = "",
) -> dict:
    session_dir = Path(session_dir)
    xdk = Path(xdk)
    if not xdk.is_file():
        raise SystemExit(f"XDK log not found: {xdk}")
    imu_dir = output_subdir(session_dir, "imu")
    sync_dir = output_subdir(session_dir, "sync")
    target = imu_dir / xdk.name
    if xdk.resolve() != target.resolve():
        shutil.copy2(xdk, target)
    entry: dict = {"kind": "xdk", "attached_utc": imu_links.now_utc(), "note": note, "source": str(xdk.resolve())}

    for key, source in (("xdk_sync", xdk_sync), ("gnss_sync", gnss_sync)):
        if source is None:
            continue
        source = Path(source)
        if not source.is_file():
            raise SystemExit(f"SYNC file not found: {source}")
        copy = sync_dir / source.name
        if source.resolve() != copy.resolve():
            shutil.copy2(source, copy)
        entry[key] = f"sync/{source.name}"
    if gnss_sync is not None:
        entry["gnss_sync_log_header"] = gnss_log_in_sync_header(gnss_sync)

    notes: list[str] = []
    if xdk_sync is not None and gnss_sync is not None:
        try:
            button = compute_button_sync(sync_dir / Path(gnss_sync).name, sync_dir / Path(xdk_sync).name, find_original_bin(session_dir))
            entry["sync"] = {
                "xdk_clock0_utc": button.xdk_clock0_utc,
                "xdk_clock0": button.xdk_clock0.isoformat(),
                "pairs": len(button.pairs),
                "gnss_presses": button.gnss_presses,
                "xdk_presses": button.xdk_presses,
                "spread_ms": button.spread_ms,
                "confidence": button.confidence,
                "notes": button.notes,
            }
            notes += button.notes
            if button.confidence == "low":
                notes.append("button sync confidence is low")
        except SystemExit as exc:
            entry["sync"] = {"error": str(exc)}
            notes.append(f"button sync failed: {exc}")
    else:
        notes.append("no SYNC files given: the time offset must come from the yaw-rate correlation")

    # how much of the XDK log lies inside the GNSS recording
    try:
        from gnss_curves import available_curves, load_curve
        from xdk_imu import load_xdk

        data = load_xdk(target)
        entry["duration_s"] = data.duration_s
        curves = available_curves(session_dir)
        if curves and "sync" in entry and "xdk_clock0_utc" in entry["sync"]:
            points = load_curve(session_dir, "bestnav" if "bestnav" in curves else next(iter(curves)))
            lo = entry["sync"]["xdk_clock0_utc"] + float(data.t[0])
            hi = entry["sync"]["xdk_clock0_utc"] + float(data.t[-1])
            g0, g1 = points[0].time.timestamp(), points[-1].time.timestamp()
            overlap = max(0.0, min(hi, g1) - max(lo, g0))
            entry["overlap_s"] = overlap
            if overlap < 0.5 * min(hi - lo, g1 - g0):
                notes.append(f"only {overlap:.0f} s of the XDK log overlap the GNSS recording: probably the wrong pair")
    except (SystemExit, Exception) as exc:  # noqa: BLE001 - the attachment itself succeeded
        notes.append(f"overlap not checked: {exc}")

    entry["warnings"] = notes
    first = not imu_links.xdk_links(session_dir)
    imu_links.register(session_dir, xdk.name, entry, make_default if make_default is not None else first)
    return entry


def describe(session_dir: Path) -> str:
    data = imu_links.load(session_dir)
    if not data["files"]:
        return f"{Path(session_dir).name}: no IMU files linked"
    lines = [f"{Path(session_dir).name}:"]
    for name, entry in data["files"].items():
        sync = entry.get("sync") or {}
        sync_text = (
            f"SYNC {sync['pairs']} pairs, {sync['spread_ms']:.0f} ms, {sync['confidence']}" if "pairs" in sync
            else (sync.get("error") or "no SYNC")
        )
        mark = "*" if data.get("default") == name else " "
        lines.append(f" {mark} {name:14} {entry.get('kind', '?'):5} {sync_text}" + (f"; overlap {entry['overlap_s']:.0f} s" if "overlap_s" in entry else ""))
        lines += [f"      ! {w}" for w in entry.get("warnings", [])]
    lines.append("   (* = default)")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Attach an XDK log and its SYNC files to a GNSS recording.")
    parser.add_argument("recording", help="out/ recording folder (name or path)")
    parser.add_argument("--data-dir", type=Path, help="Folder with gnss/ and xdk/ SD card copies (with --log)")
    parser.add_argument("--log", type=int, help="Log number in --data-dir")
    parser.add_argument("--xdk", type=Path, help="XDK CSV log")
    parser.add_argument("--xdk-sync", type=Path, help="XDK SYNC_nnn.CSV")
    parser.add_argument("--gnss-sync", type=Path, help="GNSS SYNCnnnnn.CSV")
    parser.add_argument("--default", dest="make_default", action=argparse.BooleanOptionalAction, default=None, help="Make it the default (default: yes for the first file)")
    parser.add_argument("--note", default="")
    parser.add_argument("--list", action="store_true", help="Show the linked files and exit")
    parser.add_argument("--set-default", metavar="NAME", help="Make an already linked file the default and exit")
    args = parser.parse_args()

    session_dir = resolve_session_dir(args.recording)
    if args.set_default:
        imu_links.set_default(session_dir, args.set_default)
    elif not args.list:
        xdk, xdk_sync, gnss_sync = args.xdk, args.xdk_sync, args.gnss_sync
        if args.data_dir:
            if args.log is None:
                parser.error("--data-dir needs --log")
            _, g_sync, x_log, x_sync = sync_files_for(args.data_dir / "gnss", args.data_dir / "xdk", args.log)
            xdk, xdk_sync, gnss_sync = xdk or x_log, xdk_sync or (x_sync if x_sync.is_file() else None), gnss_sync or (g_sync if g_sync.is_file() else None)
        if not xdk:
            parser.error("give --xdk or --data-dir with --log")
        attach(session_dir, xdk, xdk_sync, gnss_sync, args.make_default, args.note)
    print(describe(session_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
