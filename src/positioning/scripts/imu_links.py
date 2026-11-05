#!/usr/bin/env python3
"""Which IMU/XDK files belong to a GNSS recording, which one is the default, and where their SYNC files are.

Every recording folder gets ``imu/imu_links.json``:

    {
      "default": "LOG_005.CSV",
      "files": {
        "LOG_005.CSV": {
          "kind": "xdk",
          "xdk_sync": "sync/SYNC_005.CSV",      # paths relative to the recording folder
          "gnss_sync": "sync/SYNC00005.CSV",
          "attached_utc": "...", "note": "...",
          "sync": {"xdk_clock0_utc": ..., "pairs": 4, "spread_ms": 30.0, "confidence": "high"}
        }
      }
    }

The default is what the GUI preselects and the fusion scripts use when no file is named; any other file of
the recording (or any other file at all) can still be chosen explicitly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_NAME = "imu_links.json"


@dataclass
class XdkLink:
    name: str
    xdk: Path
    xdk_sync: Path | None
    gnss_sync: Path | None
    is_default: bool
    entry: dict


def manifest_path(session_dir: Path) -> Path:
    return Path(session_dir) / "imu" / MANIFEST_NAME


def load(session_dir: Path) -> dict:
    path = manifest_path(session_dir)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data.setdefault("default", None)
            data.setdefault("files", {})
            return data
        except (OSError, ValueError):
            pass
    return {"default": None, "files": {}}


def save(session_dir: Path, data: dict) -> Path:
    path = manifest_path(session_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_name(session_dir: Path) -> str | None:
    data = load(session_dir)
    name = data.get("default")
    return name if name in data["files"] else None


def set_default(session_dir: Path, name: str) -> None:
    data = load(session_dir)
    if name not in data["files"] and not (Path(session_dir) / "imu" / name).is_file():
        raise ValueError(f"{name} is not in {Path(session_dir).name}/imu/")
    data["default"] = name
    save(session_dir, data)


def register(session_dir: Path, name: str, entry: dict, make_default: bool) -> None:
    data = load(session_dir)
    data["files"][name] = entry
    if make_default or not data.get("default"):
        data["default"] = name
    save(session_dir, data)


def _path(session_dir: Path, relative: str | None) -> Path | None:
    if not relative:
        return None
    path = Path(session_dir) / relative
    return path if path.is_file() else None


def xdk_links(session_dir: Path) -> list[XdkLink]:
    data = load(session_dir)
    links = []
    for name, entry in data["files"].items():
        if entry.get("kind") != "xdk":
            continue
        xdk = Path(session_dir) / "imu" / name
        if not xdk.is_file():
            continue
        links.append(XdkLink(name, xdk, _path(session_dir, entry.get("xdk_sync")), _path(session_dir, entry.get("gnss_sync")),
                             data.get("default") == name, entry))
    # default first
    return sorted(links, key=lambda link: (not link.is_default, link.name.lower()))


def resolve_xdk(session_dir: Path, name: str | None = None) -> XdkLink | None:
    """The linked XDK log called `name`, or the default one (the first XDK log if none is marked)."""
    links = xdk_links(session_dir)
    if name:
        return next((link for link in links if link.name.lower() == Path(name).name.lower()), None)
    return links[0] if links else None
