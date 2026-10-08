"""SQLite store for GNSS+IMU fusion runs (settings, results and file names), so many runs of the same
GNSS recording can be listed, compared and reproduced without keeping everything in JSON files."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any

from session_paths import OUT_DIR

DB_PATH = OUT_DIR / "fusion_runs.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS fusion_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    TEXT NOT NULL,
    recording     TEXT NOT NULL,
    source        TEXT NOT NULL,
    imu_path      TEXT NOT NULL,
    imu_name      TEXT NOT NULL,
    name          TEXT NOT NULL DEFAULT '',
    notes         TEXT NOT NULL DEFAULT '',
    imu_start_utc TEXT NOT NULL DEFAULT '',
    profile       TEXT NOT NULL DEFAULT '',
    settings_json TEXT NOT NULL DEFAULT '{}',
    outages_json  TEXT NOT NULL DEFAULT '[]',
    metrics_json  TEXT NOT NULL DEFAULT '{}',
    kalman_file   TEXT NOT NULL,
    dead_file     TEXT NOT NULL DEFAULT '',
    corrected_file TEXT NOT NULL DEFAULT '',
    gnss_log_file TEXT NOT NULL DEFAULT '',
    report_file   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS fusion_runs_recording ON fusion_runs (recording, source, imu_name);
"""

JSON_COLUMNS = ("settings_json", "outages_json", "metrics_json")
EDITABLE = ("name", "notes")


def _connect(path: Path | None = None) -> sqlite3.Connection:
    db = path or DB_PATH
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _row(row: sqlite3.Row) -> dict[str, Any]:
    out = dict(row)
    for column in JSON_COLUMNS:
        out[column[:-5]] = json.loads(out.pop(column) or "null")
    return out


def add_run(values: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    record = {
        "created_at": datetime.now().isoformat(timespec="seconds"),  # local time, like file times
        "name": "", "notes": "", "imu_start_utc": "", "profile": "",
        "dead_file": "", "corrected_file": "", "gnss_log_file": "", "report_file": "",
        **values,
    }
    for column in JSON_COLUMNS:
        key = column[:-5]
        record[column] = json.dumps(record.pop(key, {} if key != "outages" else []), ensure_ascii=False)
    columns = ", ".join(record)
    marks = ", ".join("?" for _ in record)
    with closing(_connect(path)) as conn, conn:
        cursor = conn.execute(f"INSERT INTO fusion_runs ({columns}) VALUES ({marks})", list(record.values()))
        return _row(conn.execute("SELECT * FROM fusion_runs WHERE id = ?", (cursor.lastrowid,)).fetchone())


def list_runs(recording: str | None = None, path: Path | None = None) -> list[dict[str, Any]]:
    query, args = "SELECT * FROM fusion_runs", []
    if recording:
        query += " WHERE recording = ?"
        args.append(recording)
    with closing(_connect(path)) as conn:
        return [_row(r) for r in conn.execute(query + " ORDER BY id DESC", args)]


def get_run(run_id: int, path: Path | None = None) -> dict[str, Any] | None:
    with closing(_connect(path)) as conn:
        row = conn.execute("SELECT * FROM fusion_runs WHERE id = ?", (run_id,)).fetchone()
        return _row(row) if row else None


def update_run(run_id: int, changes: dict[str, Any], path: Path | None = None) -> dict[str, Any] | None:
    fields = {k: str(v) for k, v in changes.items() if k in EDITABLE}
    if fields:
        assignments = ", ".join(f"{k} = ?" for k in fields)
        with closing(_connect(path)) as conn, conn:
            conn.execute(f"UPDATE fusion_runs SET {assignments} WHERE id = ?", [*fields.values(), run_id])
    return get_run(run_id, path)


def delete_run(run_id: int, path: Path | None = None) -> bool:
    with closing(_connect(path)) as conn, conn:
        return conn.execute("DELETE FROM fusion_runs WHERE id = ?", (run_id,)).rowcount > 0
