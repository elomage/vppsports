#!/usr/bin/env python3
"""
Run every available conversion for one or more archived GNSS recordings.

Usage:
  python scripts/process_recording_all.py 20260421_213418Z_LOG00003
  python scripts/process_recording_all.py 20260421_213418Z_LOG00003 20260421_213500Z_LOG00004
  python scripts/process_recording_all.py all --base auto

This expects:
  out/<recording>/original/<recording>.BIN

It writes generated files into:
  out/<recording>/csv/
  out/<recording>/rinex/
  out/<recording>/ppk/
  out/<recording>/other/
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from session_paths import OUT_DIR, find_original_bin, output_subdir, resolve_session_dir

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class StepResult:
    name: str
    command: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def script_path(*parts: str) -> Path:
    return ROOT / "scripts" / Path(*parts)


def run_step(name: str, command: list[str]) -> StepResult:
    print()
    print(f"== {name} ==")
    print(" ".join(command))
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if completed.stdout:
        print(completed.stdout.rstrip())
    if completed.stderr:
        print(completed.stderr.rstrip(), file=sys.stderr)
    print(f"Exit code: {completed.returncode}")
    return StepResult(
        name=name,
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )


def write_report(session_dir: Path, results: list[StepResult]) -> Path:
    other_dir = output_subdir(session_dir, "other")
    report_path = other_dir / "process_all_report.txt"
    lines = [
        f"Run time: {datetime.now().isoformat(timespec='seconds')}",
        f"Recording: {session_dir}",
        "",
    ]
    for result in results:
        status = "OK" if result.ok else "FAILED"
        lines.append(f"[{status}] {result.name}")
        lines.append("Command: " + " ".join(result.command))
        if result.stdout.strip():
            lines.append("STDOUT:")
            lines.append(result.stdout.rstrip())
        if result.stderr.strip():
            lines.append("STDERR:")
            lines.append(result.stderr.rstrip())
        lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def existing_outputs(session_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for subdir_name in ("csv", "rinex", "ppk", "other"):
        subdir = session_dir / subdir_name
        if subdir.is_dir():
            paths.extend(sorted(path for path in subdir.iterdir() if path.is_file()))
    return paths


def print_outputs(paths: Iterable[Path]) -> None:
    print()
    print("Generated/available files:")
    for path in paths:
        print(f"  {path}")


def discover_all_recordings() -> list[Path]:
    if not OUT_DIR.is_dir():
        raise SystemExit(f"Output directory not found: {OUT_DIR}")

    recordings: list[Path] = []
    skipped: list[str] = []
    for session_dir in sorted((path for path in OUT_DIR.iterdir() if path.is_dir()), key=lambda item: item.name.lower()):
        try:
            find_original_bin(session_dir)
        except SystemExit as exc:
            skipped.append(f"{session_dir.name}: {exc}")
            continue
        recordings.append(session_dir.resolve())

    if skipped:
        print("Skipping out/ directories without exactly one original .BIN:")
        for item in skipped:
            print(f"  - {item}")

    if not recordings:
        raise SystemExit(f"No processable recordings found in {OUT_DIR}")
    return recordings


def resolve_recording_args(values: list[str]) -> list[Path]:
    if any(value.lower() == "all" for value in values):
        if len(values) > 1:
            raise SystemExit("Use either 'all' or explicit recording names, not both.")
        return discover_all_recordings()
    return [resolve_session_dir(value) for value in values]


def update_viewer(py: str, output_dir: Path) -> StepResult:
    return run_step(
        "Update all-recordings viewer data",
        [
            py,
            str(script_path("maps", "build_recording_viewer.py")),
            "--output-dir",
            str(output_dir),
        ],
    )


def process_recording(args: argparse.Namespace, session_dir: Path) -> int:
    original_bin = find_original_bin(session_dir)
    for name in ("csv", "rinex", "ppk", "other"):
        output_subdir(session_dir, name)

    print()
    print("=" * 80)
    print(f"Recording directory: {session_dir}")
    print(f"Original file: {original_bin}")

    py = args.python
    recording_arg = str(session_dir)
    results: list[StepResult] = []

    results.append(run_step(
        "Extract Unicore N4 CSV files",
        [py, str(script_path("converting", "to_csv", "unicore_n4_extract.py")), recording_arg],
    ))

    results.append(run_step(
        "Filter zero-coordinate CSV rows",
        [py, str(script_path("converting", "to_csv", "filter_zero_coords.py")), recording_arg],
    ))

    results.append(run_step(
        "Generate full RINEX 3.05 OBS and NAV files",
        [
            py,
            str(script_path("converting", "to_rinex", "rinex305_toolkit", "rinex305_toolkit", "rinex305_conversion_full.py")),
            recording_arg,
            "--obs-source",
            args.rinex_obs_source,
        ],
    ))

    if not args.skip_observation_single:
        observation_command = [
            py,
            str(script_path("ppk", "run_observation_single.py")),
            recording_arg,
        ]
        if args.rnx2rtkp:
            observation_command.extend(["--rnx2rtkp", str(args.rnx2rtkp)])
        if args.force_observation_single:
            observation_command.append("--force")
        results.append(run_step("Run rover-only observation single solution", observation_command))

    if args.base:
        ppk_command = [
            py,
            str(script_path("ppk", "run_ppk.py")),
            recording_arg,
            "--base",
            args.base,
            "--mode",
            args.ppk_mode,
        ]
        if args.rnx2rtkp:
            ppk_command.extend(["--rnx2rtkp", str(args.rnx2rtkp)])
        results.append(run_step(
            "Run RTKLIB PPK",
            ppk_command,
        ))

    report_path = write_report(session_dir, results)
    print_outputs(existing_outputs(session_dir))
    print()
    print(f"Report: {report_path}")

    failures = [result for result in results if not result.ok and not result.name.startswith("Create ")]
    if failures:
        print("Some steps failed for this recording. See the report above for details.")
        return 1
    optional_failures = [result for result in results if not result.ok]
    if optional_failures:
        print("Some optional steps failed for this recording. See the report above for details.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all available processing for archived GNSS recordings.")
    parser.add_argument(
        "recording",
        nargs="+",
        help="One or more recording output directories, or 'all' to process every recording in out/.",
    )
    parser.add_argument("--python", default=sys.executable, help="Python executable to use for subprocesses.")
    parser.add_argument(
        "--skip-viewer-update",
        action="store_true",
        help="Skip refreshing the local all-recordings viewer data.",
    )
    parser.add_argument(
        "--viewer-output-dir",
        type=Path,
        default=ROOT / "viewer",
        help="Output directory for the local all-recordings viewer.",
    )
    parser.add_argument(
        "--base",
        help=(
            "Optional base name under base/rinex/<base>; use auto or auto:STATION/auto|STATION "
            "to select the base by overlapping RINEX observation time."
        ),
    )
    parser.add_argument(
        "--ppk-mode",
        choices=["all", "both", "fixed", "float", "dgps", "configured"],
        default="all",
        help=(
            "RTKLIB PPK mode passed to run_ppk.py. Default all runs fixed kinematic PPK, "
            "float kinematic PPK, and the less precise DGPS fallback."
        ),
    )
    parser.add_argument(
        "--skip-observation-single",
        action="store_true",
        help="Skip rover-only observation single-position solution generation.",
    )
    parser.add_argument(
        "--force-observation-single",
        action="store_true",
        help="Regenerate observation_single.pos/csv even if they already exist.",
    )
    parser.add_argument("--rnx2rtkp", type=Path, help="Path to rnx2rtkp.exe for rover-only and PPK steps.")
    parser.add_argument(
        "--rinex-obs-source",
        default="auto",
        choices=["auto", "rangeb", "rangecmpb", "obsvmb", "obsvmcmpb", "obsvhb", "obsvhcmpb"],
        help="Raw observation log used for RINEX. auto prefers master antenna logs; obsvh* uses the slave antenna.",
    )
    args = parser.parse_args()

    session_dirs = resolve_recording_args(args.recording)
    print(f"Recordings to process: {len(session_dirs)}")
    for session_dir in session_dirs:
        print(f"  - {session_dir}")

    statuses: list[tuple[Path, int]] = []
    for session_dir in session_dirs:
        try:
            status = process_recording(args, session_dir)
        except SystemExit as exc:
            print(f"Failed before processing {session_dir}: {exc}", file=sys.stderr)
            status = 1
        statuses.append((session_dir, status))

    viewer_status = 0
    if not args.skip_viewer_update:
        viewer_result = update_viewer(args.python, args.viewer_output_dir)
        if not viewer_result.ok:
            viewer_status = 1

    print()
    print("Batch summary:")
    for session_dir, status in statuses:
        label = "OK" if status == 0 else "FAILED"
        print(f"  [{label}] {session_dir.name}")
    if not args.skip_viewer_update:
        label = "OK" if viewer_status == 0 else "FAILED"
        print(f"  [{label}] viewer update")

    if any(status != 0 for _, status in statuses) or viewer_status != 0:
        print("Some recordings failed. See each recording's process_all_report.txt for details.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
