#!/usr/bin/env python3
"""Local viewer server with IMU/Kalman control-panel API."""

from __future__ import annotations

import argparse
import csv
import json
import math
import mimetypes
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
VIEWER_DIR = ROOT / "viewer"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "maps"))

from assign_imu_recording import assign as assign_imu
from assign_imu_recording import gnss_duration, imu_duration
from imu_kalman import GNSS_SOURCES, load_gnss, parse_time, source_csv
from imu_processing_profile import (
    DEFAULT_PROFILE_CSV as IMU_PROCESSING_PROFILES,
    append_profile_cli_args,
    list_profiles as list_imu_processing_profiles,
    load_profile,
    profile_kalman_overrides,
)
from session_paths import OUT_DIR, output_subdir, resolve_session_dir
from recording_analysis import analyze as analyze_recording, list_sessions as analysis_sessions
from recording_analysis import get_session as analysis_session
from observation_analysis import signal_details
from imu_alignment import preview as alignment_preview, save_alignment

SOURCES = GNSS_SOURCES
IMU_BIAS_PROFILES = ROOT / "config" / "imu_bias_profiles.csv"  # legacy; prefer IMU_PROCESSING_PROFILES
IMU_PROCESSING_PROFILES_PATH = IMU_PROCESSING_PROFILES
LAYER_NAMES = (
    "receiver",
    "ppk",
    "float",
    "dgps",
    "observation",
    "kalman_bestnav",
    "kalman_fixed",
    "kalman_float",
    "kalman_dgps",
    "kalman_observation",
    "imu_dead_reckoning",
    "imu_drift_corrected",
    "matches",
    "float_matches",
    "dgps_matches",
    "observation_matches",
    "receiver_headings",
    "ppk_headings",
    "float_headings",
    "dgps_headings",
    "observation_headings",
)
SOURCE_RUN_LABELS = {
    "bestnav": "bestnav",
    "fixed_ppk": "fixed",
    "float_ppk": "float",
    "dgps": "dgps",
    "observation": "observation",
}
RUN_LABEL_TO_SOURCE = {label: source for source, label in SOURCE_RUN_LABELS.items()}


@dataclass
class Point:
    time: datetime | None
    lat: float
    lon: float


def safe_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def find_first_key(fieldnames: list[str], candidates: list[str]) -> str | None:
    lookup = {field.lower(): field for field in fieldnames}
    for candidate in candidates:
        if candidate.lower() in lookup:
            return lookup[candidate.lower()]
    return None


def read_json_body(handler: SimpleHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return {}
    raw = handler.rfile.read(length).decode("utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("JSON body must be an object.")
    return data


def write_json(handler: SimpleHTTPRequestHandler, payload: Any, status: int = 200) -> None:
    # Compact JSON: IMU recording payloads are tens of MB; pretty-print slows every map switch.
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def error_response(handler: SimpleHTTPRequestHandler, exc: BaseException, status: int = 500) -> None:
    write_json(handler, {"ok": False, "error": str(exc)}, status=status)


def list_imu_inputs() -> list[dict[str, Any]]:
    in_imu = ROOT / "in_imu"
    files = {path.resolve() for pattern in ("*.BIN", "*.bin", "*.csv") for path in in_imu.glob(pattern)}
    bin_stems = {path.stem.lower() for path in files if path.suffix.lower() == ".bin"}
    visible = [
        path for path in files
        if not (path.suffix.lower() == ".csv" and path.stem.lower() in bin_stems)
    ]
    rows = []
    for path in sorted(visible, key=lambda item: item.name.lower()):
        duration = imu_duration(path)
        rows.append({
            "name": path.name,
            "path": str(path),
            "duration_s": duration,
            "size": path.stat().st_size,
            "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        })
    return rows


def assigned_imus(session_dir: Path) -> list[dict[str, Any]]:
    imu_dir = session_dir / "imu"
    if not imu_dir.is_dir():
        return []
    rows = []
    for path in sorted(imu_dir.glob("*.csv"), key=lambda item: item.name.lower()):
        if path.name == "assignment.csv" or path.name.startswith((
            "kalman_",
            "imu_dead_reckoning_",
            "imu_drift_corrected_",
        )):
            continue
        duration = imu_duration(path)
        rows.append({
            "name": path.name,
            "path": str(path),
            "duration_s": duration,
            "size": path.stat().st_size,
            "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        })
    return rows


def kalman_outputs(session_dir: Path) -> list[dict[str, Any]]:
    imu_dir = session_dir / "imu"
    if not imu_dir.is_dir():
        return []
    rows = []
    for path in sorted(imu_dir.glob("kalman_*.csv"), key=lambda item: item.stat().st_mtime, reverse=True):
        source = ""
        parts = path.stem.split("_")
        if len(parts) >= 2:
            source = RUN_LABEL_TO_SOURCE.get(parts[1], parts[1])
        dead_name = path.name.replace("kalman_", "imu_dead_reckoning_", 1)
        dead_path = imu_dir / dead_name
        rows.append({
            "name": path.name,
            "path": str(path),
            "source": source,
            "dead_name": dead_name if dead_path.is_file() else "",
            "dead_path": str(dead_path) if dead_path.is_file() else "",
            "size": path.stat().st_size,
            "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        })
    return rows


def recording_sources(session_dir: Path) -> dict[str, dict[str, Any]]:
    sources: dict[str, dict[str, Any]] = {}
    for source in SOURCES:
        try:
            path = source_csv(session_dir, source)
            duration = gnss_duration(session_dir, source)
            available = path.is_file() and duration is not None
        except BaseException:
            path = None
            duration = None
            available = False
        sources[source] = {
            "available": available,
            "path": str(path) if path else "",
            "duration_s": duration,
        }
    return sources


def list_recordings() -> list[dict[str, Any]]:
    if not OUT_DIR.is_dir():
        return []
    rows = []
    for session_dir in sorted((path for path in OUT_DIR.iterdir() if path.is_dir()), key=lambda item: item.name.lower()):
        sources = recording_sources(session_dir)
        if not any(source["available"] for source in sources.values()) and not assigned_imus(session_dir):
            continue
        rows.append({
            "name": session_dir.name,
            "path": str(session_dir),
            "sources": sources,
            "assigned_imus": assigned_imus(session_dir),
            "kalman_outputs": kalman_outputs(session_dir),
        })
    return rows


def make_suggestions(recordings: list[dict[str, Any]], imus: list[dict[str, Any]], source: str = "bestnav") -> dict[str, list[dict[str, Any]]]:
    suggestions: dict[str, list[dict[str, Any]]] = {}
    for imu in imus:
        imu_duration_s = imu.get("duration_s")
        if imu_duration_s is None:
            continue
        scored = []
        for recording in recordings:
            gnss_duration_s = recording["sources"].get(source, {}).get("duration_s")
            if gnss_duration_s is None:
                continue
            scored.append({
                "recording": recording["name"],
                "delta_s": abs(imu_duration_s - gnss_duration_s),
                "gnss_duration_s": gnss_duration_s,
            })
        suggestions[imu["name"]] = sorted(scored, key=lambda item: item["delta_s"])[:5]
    return suggestions


def api_state() -> dict[str, Any]:
    recordings = list_recordings()
    imus = list_imu_inputs()
    return {
        "ok": True,
        "recordings": recordings,
        "imu_inputs": imus,
        "imu_processing_profiles": list_imu_processing_profiles(IMU_PROCESSING_PROFILES_PATH),
        "imu_bias_profiles": list_imu_bias_profiles(),
        "bases": list_bases(),
        "suggestions": make_suggestions(recordings, imus),
    }


def list_imu_bias_profiles() -> list[dict[str, Any]]:
    if not IMU_BIAS_PROFILES.is_file():
        return []
    rows = []
    with IMU_BIAS_PROFILES.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            profile = str(row.get("profile") or "").strip()
            if not profile:
                continue
            rows.append({
                "profile": profile,
                "created_utc": row.get("created_utc") or "",
                "source_imu": row.get("source_imu") or "",
                "sample_count": safe_float(row.get("sample_count")),
                "mean_norm_mps2": safe_float(row.get("mean_norm_mps2")),
                "rms_residual_mps2": safe_float(row.get("rms_residual_mps2")),
                "bias_ax_mps2": safe_float(row.get("bias_ax_mps2")),
                "bias_ay_mps2": safe_float(row.get("bias_ay_mps2")),
                "bias_az_mps2": safe_float(row.get("bias_az_mps2")),
            })
    return rows


def list_bases() -> list[dict[str, Any]]:
    base_root = ROOT / "base" / "rinex"
    rows = [{"name": "auto", "path": "", "modified": ""}]
    if not base_root.is_dir():
        return rows
    for path in sorted((item for item in base_root.iterdir() if item.is_dir()), key=lambda item: item.name.lower()):
        rows.append({
            "name": path.name,
            "path": str(path),
            "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        })
    return rows


def resolve_imu_for_recording(session_dir: Path, value: str) -> Path:
    path = Path(value)
    candidates = []
    if path.is_absolute():
        candidates.append(path)
    else:
        candidates.extend([
            ROOT / "in_imu" / path,
            session_dir / "imu" / path,
            ROOT / path,
        ])
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(f"IMU file not found: {value}")


def handle_assign(payload: dict[str, Any]) -> dict[str, Any]:
    recording = str(payload.get("recording") or "")
    imu = str(payload.get("imu") or "")
    if not recording or not imu:
        raise ValueError("Both recording and imu are required.")
    assign_imu(recording, imu, str(payload.get("note") or "viewer assignment"))
    session_dir = resolve_session_dir(recording)
    return {"ok": True, "recording": recording, "assigned_imus": assigned_imus(session_dir)}


def run_command(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def script_path(*parts: str) -> str:
    return str(ROOT / "scripts" / Path(*parts))


def handle_run_step(payload: dict[str, Any]) -> dict[str, Any]:
    recording = str(payload.get("recording") or "")
    action = str(payload.get("action") or "")
    if not recording or not action:
        raise ValueError("recording and action are required.")
    session_dir = resolve_session_dir(recording)
    recording_arg = str(session_dir)
    commands: list[list[str]] = []

    if action == "process_all":
        command = [sys.executable, script_path("process_recording_all.py"), recording_arg]
        base = str(payload.get("base") or "")
        if base:
            command.extend(["--base", base])
        command.extend(["--ppk-mode", str(payload.get("ppk_mode") or "all")])
        command.extend(["--rinex-obs-source", str(payload.get("rinex_obs_source") or "auto")])
        commands.append(command)
    elif action == "extract_csv":
        commands.append([sys.executable, script_path("converting", "to_csv", "unicore_n4_extract.py"), recording_arg])
    elif action == "filter_csv":
        commands.append([sys.executable, script_path("converting", "to_csv", "filter_zero_coords.py"), recording_arg])
    elif action == "rinex":
        commands.append([
            sys.executable,
            script_path("converting", "to_rinex", "rinex305_toolkit", "rinex305_toolkit", "rinex305_conversion_full.py"),
            recording_arg,
            "--obs-source",
            str(payload.get("rinex_obs_source") or "auto"),
        ])
    elif action == "observation_single":
        command = [sys.executable, script_path("ppk", "run_observation_single.py"), recording_arg]
        if bool(payload.get("force")):
            command.append("--force")
        commands.append(command)
    elif action == "ppk":
        base = str(payload.get("base") or "auto")
        mode = str(payload.get("ppk_mode") or "fixed")
        commands.append([sys.executable, script_path("ppk", "run_ppk.py"), recording_arg, "--base", base, "--mode", mode])
    elif action == "viewer_refresh":
        commands.append([sys.executable, script_path("maps", "build_recording_viewer.py")])
    else:
        raise ValueError(f"Unknown action: {action}")

    results = [run_command(command) for command in commands]
    if bool(payload.get("refresh_viewer", True)) and action != "viewer_refresh":
        results.append(run_command([sys.executable, script_path("maps", "build_recording_viewer.py")]))
    return {
        "ok": all(result["returncode"] == 0 for result in results),
        "recording": recording,
        "action": action,
        "results": results,
        "recording_state": {
            "sources": recording_sources(session_dir),
            "assigned_imus": assigned_imus(session_dir),
            "kalman_outputs": kalman_outputs(session_dir),
        },
    }


def source_run_label(source: str) -> str:
    return SOURCE_RUN_LABELS.get(source, source.replace("_ppk", ""))


def delay_run_label(delay_s: float) -> str:
    text = f"{delay_s:.3f}".rstrip("0").rstrip(".")
    return text.replace("-", "minus").replace(".", "p") or "0"


def parse_start_delays(value: object) -> list[float]:
    if isinstance(value, list):
        raw_values = value
    else:
        raw_values = str(value or "0").replace(";", ",").split(",")
    delays: list[float] = []
    for raw in raw_values:
        text = str(raw).strip()
        if not text:
            continue
        delay = float(text)
        if delay < 0:
            raise ValueError("IMU start delays must be 0 or greater.")
        delays.append(delay)
    return delays or [0.0]


def append_alignment_options(command: list[str], payload: dict[str, Any]) -> None:
    mode = str(payload.get("alignment_mode") or "offset")
    if mode == "auto":
        command.append("--auto-align")
        command.extend(["--align-step-s", str(float(payload.get("align_step_s", 0.5)))])
        command.extend(["--align-padding-s", str(float(payload.get("align_padding_s", 30.0)))])
    elif mode == "utc":
        imu_start_utc = str(payload.get("imu_start_utc") or "")
        if not imu_start_utc:
            raise ValueError("imu_start_utc is required for UTC alignment.")
        command.extend(["--imu-start-utc", imu_start_utc])
    else:
        command.extend(["--time-offset-s", str(float(payload.get("time_offset_s", 0.0)))])


def resolve_processing_profile(payload: dict[str, Any]) -> dict[str, object] | None:
    if str(payload.get("imu_mode") or "processed").strip().lower() == "raw":
        return None
    name = str(payload.get("imu_processing_profile") or payload.get("accel_bias_profile") or "").strip()
    if not name:
        return None
    try:
        return load_profile(IMU_PROCESSING_PROFILES_PATH, name)
    except SystemExit:
        return None


def append_accel_bias_options(command: list[str], payload: dict[str, Any]) -> None:
    if str(payload.get("imu_mode") or "processed").strip().lower() == "raw":
        return
    profile = resolve_processing_profile(payload)
    if profile is not None:
        append_profile_cli_args(command, profile)
        return
    name = str(payload.get("accel_bias_profile") or "").strip()
    if not name:
        return
    if not IMU_BIAS_PROFILES.is_file():
        raise FileNotFoundError(f"IMU bias/processing profile not found for: {name}")
    known = {row["profile"] for row in list_imu_bias_profiles()}
    if name not in known:
        raise ValueError(f"Unknown IMU profile: {name}")
    command.extend(["--accel-bias-profile", str(IMU_BIAS_PROFILES), "--accel-bias-name", name])


def append_drift_options(command: list[str], payload: dict[str, Any]) -> None:
    if str(payload.get("imu_mode") or "processed").strip().lower() == "raw":
        command.append("--no-drift-correct")
        return
    if resolve_processing_profile(payload) is not None:
        return
    if payload.get("drift_correct") is False:
        command.append("--no-drift-correct")
    else:
        command.append("--drift-correct")
    if payload.get("static_speed_mps") is not None:
        command.extend(["--static-speed-mps", str(float(payload["static_speed_mps"]))])
    if payload.get("accel_residual_gate_mps2") is not None:
        command.extend(["--accel-residual-gate-mps2", str(float(payload["accel_residual_gate_mps2"]))])


def kalman_numeric_args(payload: dict[str, Any]) -> dict[str, float]:
    values = {
        "position_sigma_m": float(payload.get("position_sigma_m", 0.6)),
        "accel_noise": float(payload.get("accel_noise", 2.0)),
        "gnss_update_period_s": float(payload.get("gnss_update_period_s", 0.05)),
    }
    profile = resolve_processing_profile(payload)
    if profile is not None:
        values.update(profile_kalman_overrides(profile))
    return values


def handle_calibrate_imu(payload: dict[str, Any]) -> dict[str, Any]:
    imu_value = str(payload.get("imu") or "")
    profile = str(payload.get("profile") or "").strip()
    if not imu_value or not profile:
        raise ValueError("imu and profile are required.")
    recording = str(payload.get("recording") or "").strip()
    session_dir = resolve_session_dir(recording) if recording else OUT_DIR
    imu_path = resolve_imu_for_recording(session_dir, imu_value)
    command = [
        sys.executable,
        script_path("imu_processing_profile.py"),
        str(imu_path),
        "--profile",
        profile,
        "--output",
        str(IMU_PROCESSING_PROFILES_PATH),
    ]
    if recording:
        command.extend(["--recording", recording])
    start_s = str(payload.get("start_s") or "").strip()
    end_s = str(payload.get("end_s") or "").strip()
    if start_s:
        command.extend(["--start-s", str(float(start_s))])
    if end_s:
        command.extend(["--end-s", str(float(end_s))])
    result = run_command(command)
    profiles = list_imu_processing_profiles(IMU_PROCESSING_PROFILES_PATH)
    return {
        "ok": result["returncode"] == 0,
        "command": result,
        "imu_processing_profiles": profiles,
        "imu_bias_profiles": list_imu_bias_profiles(),
        "profile": next((item for item in profiles if item["profile"] == profile), None),
    }


def handle_calculate(payload: dict[str, Any]) -> dict[str, Any]:
    recording = str(payload.get("recording") or "")
    imu_value = str(payload.get("imu") or "")
    if not recording or not imu_value:
        raise ValueError("Both recording and imu are required.")
    session_dir = resolve_session_dir(recording)
    imu_path = resolve_imu_for_recording(session_dir, imu_value)
    source_values = payload.get("sources") or []
    if source_values == "all":
        source_values = list(SOURCES)
    if not isinstance(source_values, list):
        raise ValueError("sources must be a list or 'all'.")
    sources = [source for source in source_values if source in SOURCES]
    if not sources:
        raise ValueError("Choose at least one source.")

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    imu_stem = imu_path.stem
    imu_dir = output_subdir(session_dir, "imu")
    commands = []
    outputs = []
    for source in sources:
        output = imu_dir / f"kalman_{source_run_label(source)}_{imu_stem}_{run_id}.csv"
        dead_output = imu_dir / f"imu_dead_reckoning_{source_run_label(source)}_{imu_stem}_{run_id}.csv"
        corrected_output = imu_dir / f"imu_drift_corrected_{source_run_label(source)}_{imu_stem}_{run_id}.csv"
        nums = kalman_numeric_args(payload)
        command = [
            sys.executable,
            str(ROOT / "scripts" / "imu_kalman.py"),
            str(session_dir),
            "--imu",
            str(imu_path),
            "--source",
            source,
            "--position-sigma-m",
            str(nums["position_sigma_m"]),
            "--accel-noise",
            str(nums["accel_noise"]),
            "--gnss-update-period-s",
            str(nums["gnss_update_period_s"]),
            "--output",
            str(output),
            "--dead-output",
            str(dead_output),
            "--corrected-output",
            str(corrected_output),
        ]
        append_alignment_options(command, payload)
        append_accel_bias_options(command, payload)
        append_drift_options(command, payload)
        result = run_command(command)
        commands.append(result)
        if result["returncode"] == 0:
            outputs.append({
                "source": source,
                "kalman": output.name,
                "dead": dead_output.name,
                "corrected": corrected_output.name,
            })

    viewer_result = run_command([sys.executable, str(ROOT / "scripts" / "maps" / "build_recording_viewer.py")])
    ok = all(item["returncode"] == 0 for item in commands)
    return {
        "ok": ok,
        "recording": recording,
        "outputs": outputs,
        "commands": commands,
        "viewer": viewer_result,
        "recording_state": {
            "assigned_imus": assigned_imus(session_dir),
            "kalman_outputs": kalman_outputs(session_dir),
        },
    }


def _imu_dead_only_command(
    session_dir: Path,
    imu_path: Path,
    source: str,
    delay_s: float,
    payload: dict[str, Any],
    *,
    dead_output: Path,
    corrected_output: Path,
) -> list[str]:
    nums = kalman_numeric_args(payload)
    command = [
        sys.executable,
        str(ROOT / "scripts" / "imu_kalman.py"),
        str(session_dir),
        "--imu",
        str(imu_path),
        "--source",
        source,
        "--dead-only",
        "--imu-start-delay-s",
        str(delay_s),
        "--position-sigma-m",
        str(nums["position_sigma_m"]),
        "--accel-noise",
        str(nums["accel_noise"]),
        "--gnss-update-period-s",
        str(nums["gnss_update_period_s"]),
        "--dead-output",
        str(dead_output),
        "--corrected-output",
        str(corrected_output),
    ]
    append_alignment_options(command, payload)
    append_accel_bias_options(command, payload)
    append_drift_options(command, payload)
    return command


def handle_imu_trajectory(payload: dict[str, Any]) -> dict[str, Any]:
    recording = str(payload.get("recording") or "")
    imu_value = str(payload.get("imu") or "")
    source = str(payload.get("source") or "fixed_ppk")
    if source not in SOURCES:
        raise ValueError(f"Unsupported source: {source}")
    if not recording or not imu_value:
        raise ValueError("Both recording and imu are required.")
    session_dir = resolve_session_dir(recording)
    imu_path = resolve_imu_for_recording(session_dir, imu_value)
    imu_dir = output_subdir(session_dir, "imu")
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    imu_stem = imu_path.stem
    delays = parse_start_delays(payload.get("start_delays_s"))
    commands = []
    outputs = []
    # Always produce both layers separately:
    # 1) raw diagnostic (no bias / no ZUPT)
    # 2) drift-corrected with the selected processing profile
    raw_payload = {**payload, "imu_mode": "raw"}
    processed_payload = {**payload, "imu_mode": "processed"}
    for delay_s in delays:
        dead_output = imu_dir / f"imu_dead_reckoning_{source_run_label(source)}_{imu_stem}_delay{delay_run_label(delay_s)}_{run_id}.csv"
        corrected_output = imu_dir / f"imu_drift_corrected_{source_run_label(source)}_{imu_stem}_delay{delay_run_label(delay_s)}_{run_id}.csv"
        scratch_corrected = imu_dir / f"_scratch_corrected_raw_{delay_run_label(delay_s)}_{run_id}.csv"
        scratch_dead = imu_dir / f"_scratch_dead_processed_{delay_run_label(delay_s)}_{run_id}.csv"

        raw_cmd = _imu_dead_only_command(
            session_dir,
            imu_path,
            source,
            delay_s,
            raw_payload,
            dead_output=dead_output,
            corrected_output=scratch_corrected,
        )
        proc_cmd = _imu_dead_only_command(
            session_dir,
            imu_path,
            source,
            delay_s,
            processed_payload,
            dead_output=scratch_dead,
            corrected_output=corrected_output,
        )
        raw_result = run_command(raw_cmd)
        proc_result = run_command(proc_cmd)
        commands.extend([raw_result, proc_result])
        for scratch in (scratch_corrected, scratch_dead):
            try:
                scratch.unlink(missing_ok=True)
            except OSError:
                pass
        if raw_result["returncode"] == 0 and proc_result["returncode"] == 0:
            outputs.append({
                "source": source,
                "dead": dead_output.name,
                "corrected": corrected_output.name,
                "start_delay_s": delay_s,
            })

    viewer_result = run_command([sys.executable, str(ROOT / "scripts" / "maps" / "build_recording_viewer.py")])
    ok = all(item["returncode"] == 0 for item in commands)
    return {
        "ok": ok,
        "recording": recording,
        "outputs": outputs,
        "commands": commands,
        "viewer": viewer_result,
        "recording_state": {
            "assigned_imus": assigned_imus(session_dir),
            "kalman_outputs": kalman_outputs(session_dir),
        },
    }


def load_csv_points(path: Path) -> list[Point]:
    points: list[Point] = []
    if not path.is_file():
        return points
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return points
        lat_key = find_first_key(reader.fieldnames, ["lat", "latitude", "lat_deg", "latitude_deg"])
        lon_key = find_first_key(reader.fieldnames, ["lon", "lng", "longitude", "lon_deg", "longitude_deg"])
        time_key = find_first_key(reader.fieldnames, ["time", "utc", "timestamp", "datetime", "date_time"])
        if not lat_key or not lon_key:
            return points
        for row in reader:
            lat = safe_float(row.get(lat_key))
            lon = safe_float(row.get(lon_key))
            if lat is None or lon is None or (lat == 0.0 and lon == 0.0):
                continue
            points.append(Point(parse_time(row.get(time_key)) if time_key else None, lat, lon))
    return points


def gnss_points(session_dir: Path, source: str) -> list[Point]:
    try:
        rows = load_gnss(source_csv(session_dir, source))
    except BaseException:
        return []
    return [Point(row.time, row.lat, row.lon) for row in rows]


def sample_points(points: list[Point], max_points: int = 5000) -> list[Point]:
    if len(points) <= max_points:
        return points
    step = max(1, math.ceil(len(points) / max_points))
    sampled = points[::step]
    if sampled[-1] is not points[-1]:
        sampled.append(points[-1])
    return sampled


def line_feature(points: list[Point], label: str, color: str, total_points: int) -> dict[str, Any]:
    sampled = sample_points(points)
    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [[point.lon, point.lat] for point in sampled],
        },
        "properties": {
            "label": label,
            "color": color,
            "points": total_points,
            "times": [point.time.isoformat() if point.time else "" for point in sampled],
        },
    }


def nearest_by_time(points: list[Point], target: datetime, start_index: int) -> tuple[Point, int, float] | None:
    timed = points
    if not timed:
        return None
    best = min(start_index, len(timed) - 1)
    if timed[best].time is None:
        return None
    best_delta = abs((timed[best].time - target).total_seconds())
    idx = best
    while idx + 1 < len(timed) and timed[idx + 1].time is not None:
        delta = abs((timed[idx + 1].time - target).total_seconds())
        if delta > best_delta:
            break
        idx += 1
        best = idx
        best_delta = delta
    return timed[best], best, best_delta


def meters_between(a: Point, b: Point) -> float:
    lat = math.radians((a.lat + b.lat) / 2.0)
    north = (b.lat - a.lat) * 111_320.0
    east = (b.lon - a.lon) * 111_320.0 * math.cos(lat)
    return math.hypot(east, north)


def difference_features(gnss: list[Point], kalman: list[Point], every_n: int = 80) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    gnss_timed = [point for point in gnss if point.time is not None]
    kalman_timed = [point for point in kalman if point.time is not None]
    features: list[dict[str, Any]] = []
    distances: list[float] = []
    start_index = 0
    for index, point in enumerate(kalman_timed[::max(1, every_n)]):
        match = nearest_by_time(gnss_timed, point.time, start_index)
        if match is None:
            continue
        gnss_point, start_index, delta_s = match
        if delta_s > 1.0:
            continue
        distance = meters_between(gnss_point, point)
        distances.append(distance)
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[gnss_point.lon, gnss_point.lat], [point.lon, point.lat]],
            },
            "properties": {
                "distance_m": round(distance, 3),
                "time_delta_s": round(delta_s, 3),
                "color": "#f2994a" if distance < 2.0 else "#d62728",
                "index": index + 1,
            },
        })
    stats: dict[str, Any] = {"matches": len(distances)}
    if distances:
        ordered = sorted(distances)
        stats.update({
            "median_m": round(ordered[len(ordered) // 2], 3),
            "p95_m": round(ordered[min(len(ordered) - 1, round((len(ordered) - 1) * 0.95))], 3),
            "max_m": round(max(ordered), 3),
        })
    return features, stats


def handle_result(query: dict[str, list[str]]) -> dict[str, Any]:
    recording = query.get("recording", [""])[0]
    source = query.get("source", ["bestnav"])[0]
    kalman_name = unquote(query.get("kalman", [""])[0])
    dead_name = unquote(query.get("dead", [""])[0])
    if not recording or not kalman_name:
        raise ValueError("recording and kalman are required.")
    session_dir = resolve_session_dir(recording)
    imu_dir = session_dir / "imu"
    gnss = gnss_points(session_dir, source)
    kalman = load_csv_points(imu_dir / kalman_name)
    dead = load_csv_points(imu_dir / dead_name) if dead_name else []
    diff, stats = difference_features(gnss, kalman)
    features = []
    if gnss:
        features.append(line_feature(gnss, f"{source} GNSS", "#1f77b4", len(gnss)))
    if kalman:
        features.append(line_feature(kalman, "Kalman GNSS+IMU", "#111827", len(kalman)))
    if dead:
        features.append(line_feature(dead, "IMU diagnostic", "#00a6a6", len(dead)))
    return {
        "ok": True,
        "recording": recording,
        "source": source,
        "stats": stats,
        "tracks": {"type": "FeatureCollection", "features": features},
        "differences": {"type": "FeatureCollection", "features": diff},
    }


def safe_id(value: str) -> str:
    import re

    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")
    return cleaned or "recording"


def handle_recording_data(query: dict[str, list[str]]) -> dict[str, Any]:
    recording = query.get("recording", [""])[0]
    if not recording:
        raise ValueError("recording is required.")
    session_dir = resolve_session_dir(recording)
    data_path = VIEWER_DIR / "data" / f"{safe_id(session_dir.name)}.json"
    if not data_path.is_file():
        run_command([sys.executable, script_path("maps", "build_recording_viewer.py")])
    if not data_path.is_file():
        raise FileNotFoundError(f"Viewer data not found for {session_dir.name}")
    # Do not re-parse/re-dump multi-decade-MB GeoJSON here — that blocked the server
    # for ~50s on IMU rides and made the dashboard look empty.
    return {
        "ok": True,
        "recording": session_dir.name,
        "layer_names": LAYER_NAMES,
        "data_url": f"data/{safe_id(session_dir.name)}.json",
    }


class ViewerHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(VIEWER_DIR), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.log_date_time_string(), format % args))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/observations":
            try:
                query=parse_qs(parsed.query)
                name=query.get("recording",[""])[0]
                result=analyze_recording(name,False,query.get("start_s",[None])[0],query.get("end_s",[None])[0])
                write_json(self,signal_details(analysis_session(name),result['bounds']))
            except ValueError as exc:
                error_response(self,exc,status=400)
            except Exception as exc:
                error_response(self,exc)
            return
        if parsed.path in {"/api/analysis", "/api/analysis-sessions"}:
            try:
                if parsed.path.endswith("-sessions"):
                    write_json(self, {"recordings": analysis_sessions()})
                else:
                    query = parse_qs(parsed.query)
                    write_json(self, analyze_recording(query.get("recording", [""])[0], query.get("signal", ["1"])[0] != "0",
                                                      query.get("start_s", [None])[0], query.get("end_s", [None])[0]))
            except ValueError as exc:
                error_response(self, exc, status=400)
            except Exception as exc:
                error_response(self, exc)
            return
        if parsed.path in {"", "/"}:
            self.path = "/app.html"
            return super().do_GET()
        if parsed.path == "/api/state":
            try:
                write_json(self, api_state())
            except BaseException as exc:
                error_response(self, exc)
            return
        if parsed.path == "/api/result":
            try:
                write_json(self, handle_result(parse_qs(parsed.query)))
            except BaseException as exc:
                error_response(self, exc)
            return
        if parsed.path == "/api/recording-data":
            try:
                write_json(self, handle_recording_data(parse_qs(parsed.query)))
            except BaseException as exc:
                error_response(self, exc)
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            payload = read_json_body(self)
            if parsed.path in {"/api/alignment-preview", "/api/alignment-save"}:
                session = analysis_session(str(payload.get("recording") or ""))
                imu = resolve_imu_for_recording(session, str(payload.get("imu") or ""))
                allowed = [ROOT / "in_imu", session / "imu"]
                if not any(imu.is_relative_to(folder.resolve()) for folder in allowed) or imu.suffix.lower() not in {".bin", ".csv"}:
                    raise ValueError("Izvēlies IMU failu no ierakstu saraksta.")
                source = str(payload.get("source") or "bestnav")
                if parsed.path.endswith("preview"):
                    write_json(self, alignment_preview(session, imu, source))
                else:
                    write_json(self, save_alignment(session, imu, source, float(payload["time_offset_s"])))
                return
            if parsed.path == "/api/assign":
                write_json(self, handle_assign(payload))
                return
            if parsed.path == "/api/calculate":
                write_json(self, handle_calculate(payload))
                return
            if parsed.path == "/api/imu-trajectory":
                write_json(self, handle_imu_trajectory(payload))
                return
            if parsed.path == "/api/calibrate-imu":
                write_json(self, handle_calibrate_imu(payload))
                return
            if parsed.path == "/api/run-step":
                write_json(self, handle_run_step(payload))
                return
            self.send_error(HTTPStatus.NOT_FOUND, "Unknown API endpoint")
        except ValueError as exc:
            error_response(self, exc, status=400)
        except BaseException as exc:
            error_response(self, exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the GNSS viewer and IMU/Kalman control panel.")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    mimetypes.add_type("application/javascript", ".js")
    server = ThreadingHTTPServer((args.host, args.port), ViewerHandler)
    print(f"Viewer server: http://{args.host}:{args.port}/")
    print(f"Unified GUI: http://{args.host}:{args.port}/app.html")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
        print("Stopping viewer server.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
