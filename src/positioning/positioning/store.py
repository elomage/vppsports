"""Braucienu metadati: out/<ieraksts>/trips/trips.json (atomisks raksts, bloķēšana)."""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from .paths import OUT_DIR, session_dir

_LOCK = threading.RLock()
TRIP_SUFFIX = re.compile(r"^(?P<parent>.+)__t(?P<n>\d+)$")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_utc(value) -> float:
    """ISO-8601 (ar/bez Z) vai epoch sekundes -> epoch sekundes (UTC)."""
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    try:
        return float(text)
    except ValueError:
        pass
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    d = datetime.fromisoformat(text)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp()


def iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def trips_file(parent: str) -> Path:
    return session_dir(parent) / "trips" / "trips.json"


def _read(parent: str) -> dict:
    p = trips_file(parent)
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"parent": parent, "trips": []}


def _write(parent: str, data: dict) -> None:
    p = trips_file(parent)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def parent_of(trip_id: str) -> str:
    m = TRIP_SUFFIX.match(trip_id)
    if not m:
        raise ValueError(f"Nederīgs brauciena id: {trip_id}")
    return m.group("parent")


def list_trips(parent: str) -> list[dict]:
    with _LOCK:
        return _read(parent)["trips"]


def get_trip(trip_id: str) -> dict:
    with _LOCK:
        for t in _read(parent_of(trip_id))["trips"]:
            if t["id"] == trip_id:
                return t
    raise ValueError(f"Brauciens nav atrasts: {trip_id}")


def next_id(parent: str, trips: list[dict]) -> str:
    used = {t["id"] for t in trips}
    n = 1
    while f"{parent}__t{n:02d}" in used or (OUT_DIR / f"{parent}__t{n:02d}").exists():
        n += 1
    return f"{parent}__t{n:02d}"


def add_trip(parent: str, trip: dict) -> dict:
    with _LOCK:
        data = _read(parent)
        data["trips"].append(trip)
        _write(parent, data)
    return trip


def update_trip(trip_id: str, **changes) -> dict:
    with _LOCK:
        parent = parent_of(trip_id)
        data = _read(parent)
        for t in data["trips"]:
            if t["id"] == trip_id:
                for k, v in changes.items():
                    if k == "status":
                        t.setdefault("status", {}).update(v)
                    else:
                        t[k] = v
                _write(parent, data)
                return t
    raise ValueError(f"Brauciens nav atrasts: {trip_id}")


def remove_trip(trip_id: str) -> None:
    with _LOCK:
        parent = parent_of(trip_id)
        data = _read(parent)
        data["trips"] = [t for t in data["trips"] if t["id"] != trip_id]
        _write(parent, data)
