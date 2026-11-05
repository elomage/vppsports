"""Fona darbu rinda ilgstošiem darbiem (RINEX/PPK/fūzija) ar statusu un žurnālu."""
from __future__ import annotations

import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from .store import now

_POOL = ThreadPoolExecutor(max_workers=2)
_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()
MAX_LOG = 500


def submit(kind: str, fn: Callable[..., Any], **meta) -> dict:
    """fn(log) -> JSON-saderīgs rezultāts. Atgriež darba aprakstu ar id."""
    job = {"id": uuid.uuid4().hex[:12], "kind": kind, "status": "queued", "created": now(), "log": [], **meta}
    with _LOCK:
        _JOBS[job["id"]] = job

    def log(line: str) -> None:
        job["log"].append(line)
        del job["log"][:-MAX_LOG]

    def run() -> None:
        job["status"] = "running"
        try:
            job["result"] = fn(log)
            job["status"] = "done"
        except BaseException as exc:  # SystemExit no esošajiem skriptiem arī
            job["status"] = "error"
            job["error"] = str(exc) or type(exc).__name__
            log(traceback.format_exc()[-1500:])
        job["finished"] = now()

    _POOL.submit(run)
    return job


def get(job_id: str) -> dict:
    with _LOCK:
        if job_id not in _JOBS:
            raise ValueError(f"Darbs nav atrasts: {job_id}")
        return _JOBS[job_id]


def listing() -> list[dict]:
    with _LOCK:
        return [{k: v for k, v in j.items() if k != "log"} for j in _JOBS.values()]
