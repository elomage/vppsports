"""GNSS ieraksta darba vieta: viss, kas pieder vienam ierakstam, atrodas tā mapē out/<ieraksts>/.

    original/   BIN (vienīgais obligātais)        csv/ rinex/ ppk/   apstrādes rezultāti
    imu/        XDK/IMU žurnāli (neobligāti)      sync/              POGU SPIEDIENU faili, gan GNSS, gan XDK (neobligāti)
    video/      video faili (neobligāti)          trips/ fusion/     braucieni un Kalman rezultāti

Starp ierakstiem kopīgas ir tikai IMU/akselerometra konfigurācijas (config/imu_*_profiles.csv).
"""
from __future__ import annotations

import csv
import hashlib
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from . import store
from .paths import OUT_DIR, ROOT, session_dir

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mts"}
NAME_OK = re.compile(r"[^\w.\- ()]")
RANK = {"high": 2, "medium": 1, "low": 0}


def clean_name(name: str) -> str:
    base = Path(str(name).replace("\\", "/")).name.strip().strip(".")
    base = NAME_OK.sub("_", base)
    if not base:
        raise ValueError("Nederīgs faila nosaukums.")
    return base


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- jauns ieraksts no BIN
def create_recording(tmp: Path, original_name: str) -> dict:
    """Augšupielādēts BIN -> out/<laiks>_<nosaukums>/original/. Dublikātu (tas pats saturs) neveido."""
    from archive_in_recordings import first_packet_timestamp, timestamp_label
    name = clean_name(original_name)
    if Path(name).suffix.lower() != ".bin":
        raise ValueError("Jauns ieraksts jāaugšupielādē kā .BIN fails.")
    digest, size = sha256(tmp), tmp.stat().st_size
    for d in OUT_DIR.glob("*/original/*"):
        if d.suffix.lower() == ".bin" and d.stat().st_size == size and sha256(d) == digest:
            return {"id": d.parents[1].name, "duplicate": True}
    when = first_packet_timestamp(tmp)
    stem = Path(name).stem
    base = f"{timestamp_label(when)}_{stem}"
    sdir, n = OUT_DIR / base, 2
    while sdir.exists():
        sdir = OUT_DIR / f"{base}_{n:02d}"
        n += 1
    for sub in ("original", "csv", "rinex", "ppk", "other", "imu", "sync", "video"):
        (sdir / sub).mkdir(parents=True)
    shutil.move(str(tmp), str(sdir / "original" / name))
    return {"id": sdir.name, "duplicate": False, "time_known": when is not None}


# ---------------------------------------------------------------- faila veida noteikšana
def sniff(path: Path) -> dict:
    """Nosaka, kas ir augšupielādētais fails: xdk | sync (gnss/xdk) | video | bin."""
    ext = path.suffix.lower()
    if ext in VIDEO_EXT:
        return {"kind": "video"}
    if ext == ".bin":
        return {"kind": "bin"}
    head = path.read_text(encoding="utf-8", errors="replace")[:4000] if path.stat().st_size else ""
    lines = [l for l in head.splitlines() if l.strip()]
    if lines and lines[0].lower().startswith("t_ms"):
        return {"kind": "xdk"}
    if any(l.startswith("SYNC,") for l in lines) or any(l.startswith("# log=") for l in lines):
        gnss = any(l.startswith("# log=") for l in lines) or not re.match(r"SYNC_\d", path.name, re.I)
        return {"kind": "sync", "side": "gnss" if gnss else "xdk"}
    return {"kind": "unknown"}


def sync_info(path: Path) -> dict:
    import sync_button
    g = sniff(path).get("side") or "gnss"
    reader = sync_button.read_gnss_sync if g == "gnss" else sync_button.read_xdk_sync
    presses = reader(path)
    log = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"#\s*log=(.+)", line)
        if m:
            log = m.group(1).strip()
            break
    return {"name": path.name, "side": g, "presses": len(presses), "log": log, "bytes": path.stat().st_size}


def store_file(rec: str, tmp: Path, name: str, kind: str = "auto") -> dict:
    sdir = session_dir(rec)
    name = clean_name(name)
    found = sniff(tmp) if Path(name).suffix.lower() != ".bin" or kind != "auto" else {"kind": "bin"}
    if kind in ("", "auto"):
        kind = found["kind"]
    if kind == "bin":
        raise ValueError("BIN nevar pievienot esošam ierakstam; augšupielādē to kā jaunu ierakstu.")
    if kind == "unknown":
        raise ValueError("Neatpazīts fails: gaidīju XDK žurnālu (t_ms galvene), SYNC failu vai video.")
    if kind == "xdk":
        if found["kind"] != "xdk":
            raise ValueError("Tas nav XDK žurnāls (pirmajā rindā jābūt t_ms,…).")
        dest = sdir / "imu" / name
    elif kind == "sync":
        if found["kind"] != "sync":
            raise ValueError("Tas nav SYNC fails (rindas SYNC,<laiks>,<nr>,<marķieris>).")
        dest = sdir / "sync" / name
    elif kind == "video":
        if Path(name).suffix.lower() not in VIDEO_EXT:
            raise ValueError("Neatbalstīts video formāts.")
        dest = sdir / "video" / name
    else:
        raise ValueError(f"Nezināms veids: {kind}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    replaced = dest.exists()
    shutil.move(str(tmp), str(dest))
    out = {"kind": kind, "name": dest.name, "replaced": replaced}
    if kind == "sync":
        out.update(sync_info(dest))
    return out


def remove_file(rec: str, kind: str, name: str) -> None:
    sub = {"xdk": "imu", "sync": "sync", "video": "video"}.get(kind)
    if not sub:
        raise ValueError("Dzēšama tikai XDK, SYNC vai video pievienošana.")
    p = session_dir(rec) / sub / clean_name(name)
    if not p.is_file():
        raise ValueError("Fails nav atrasts.")
    p.unlink()
    if kind == "xdk":  # noņem arī saiti
        import imu_links
        d = imu_links.load(session_dir(rec))
        d["files"].pop(p.name, None)
        if d.get("default") == p.name:
            d["default"] = next(iter(d["files"]), None)
        imu_links.save(session_dir(rec), d)


# ---------------------------------------------------------------- pārskats
def _recording_bin(sdir: Path) -> Path | None:
    bins = list((sdir / "original").glob("*.[Bb][Ii][Nn]")) if (sdir / "original").is_dir() else []
    return bins[0] if len(bins) == 1 else None


def inventory(rec: str) -> dict:
    import imu_links
    sdir = session_dir(rec)
    b = _recording_bin(sdir)
    ppk = {k: (sdir / "ppk" / f).is_file() for k, f in (("single", "observation_single.csv"), ("fixed", "solution.csv"),
                                                          ("float", "solution_float.csv"), ("dgps", "solution_dgps.csv"))}
    rinex = sorted(p.name for p in (sdir / "rinex").glob("*")) if (sdir / "rinex").is_dir() else []
    links = imu_links.load(sdir)
    xdk = []
    for p in sorted((sdir / "imu").glob("*.[Cc][Ss][Vv]")) if (sdir / "imu").is_dir() else []:
        if sniff(p).get("kind") != "xdk":
            continue
        e = links["files"].get(p.name, {})
        xdk.append({"name": p.name, "bytes": p.stat().st_size, "default": links.get("default") == p.name,
                    "linked": bool(e), "sync": e.get("sync"), "overlap_s": e.get("overlap_s"),
                    "warnings": e.get("warnings", []), "xdk_sync": e.get("xdk_sync"), "gnss_sync": e.get("gnss_sync")})
    syncs = [sync_info(p) for p in sorted((sdir / "sync").glob("*")) if p.is_file()] if (sdir / "sync").is_dir() else []
    videos = [{"name": p.name, "bytes": p.stat().st_size} for p in sorted((sdir / "video").glob("*")) if p.is_file() and p.suffix.lower() in VIDEO_EXT] \
        if (sdir / "video").is_dir() else []
    tf = sdir / "trips" / "trips.json"
    return {"id": rec, "bin": b.name if b else None, "bin_bytes": b.stat().st_size if b else 0,
            "is_trip": (sdir / "trip.json").is_file(),
            "gnss": {"csv": (sdir / "csv" / "bestnavxyz.csv").is_file(), "rinex": rinex, "ppk": ppk},
            "xdk": xdk, "sync": syncs, "video": videos,
            "trips": store.list_trips(rec) if tf.is_file() else []}


def _num(name: str) -> int | None:
    m = re.search(r"(\d+)", Path(name).stem)
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------- automātiska savienošana
def auto_link(rec: str, xdk: str | None = None, xdk_sync: str | None = None, gnss_sync: str | None = None,
              make_default: bool = True, note: str = "") -> dict:
    """Piesaista XDK žurnālu ierakstam. Ja SYNC faili nav norādīti, izmēģina visus augšupielādētos pārus un
    ņem to, kas dod labāko pogu spiedienu sasaisti."""
    import attach_xdk
    import sync_button
    from session_paths import find_original_bin
    sdir = session_dir(rec)
    inv = inventory(rec)
    logs = [x["name"] for x in inv["xdk"]]
    if not logs:
        raise ValueError("Ierakstam nav XDK žurnāla: vispirms augšupielādē to.")
    xdk = clean_name(xdk) if xdk else (logs[0] if len(logs) == 1 else None)
    if xdk is None or xdk not in logs:
        raise ValueError(f"Norādi XDK žurnālu: {', '.join(logs)}")
    log_path = sdir / "imu" / xdk
    gs = [clean_name(gnss_sync)] if gnss_sync else [s["name"] for s in inv["sync"] if s["side"] == "gnss"]
    xs = [clean_name(xdk_sync)] if xdk_sync else [s["name"] for s in inv["sync"] if s["side"] == "xdk"]
    best, tried = None, []
    bin_path = find_original_bin(sdir)
    for g in gs:
        for x in xs:
            try:
                bs = sync_button.compute_button_sync(sdir / "sync" / g, sdir / "sync" / x, bin_path)
            except SystemExit as exc:
                tried.append({"gnss_sync": g, "xdk_sync": x, "error": str(exc)})
                continue
            check = sync_button.xdk_row_check(sdir / "sync" / x, log_path)
            fits_log = bool(check) and all(abs(c["diff_ms"]) < 100 for c in check)
            same_no = int(_num(g) == _num(bin_path.name)) + int(_num(x) == _num(xdk))  # LOG00005 ↔ SYNC00005, LOG_005 ↔ SYNC_005
            score = (fits_log, same_no, RANK[bs.confidence], len(bs.pairs), -bs.spread_ms)
            tried.append({"gnss_sync": g, "xdk_sync": x, "confidence": bs.confidence, "pairs": len(bs.pairs),
                          "spread_ms": bs.spread_ms, "fits_log": fits_log})
            if len(bs.pairs) >= 1 and (best is None or score > best[0]):
                best = (score, g, x)
    if best:
        entry = attach_xdk.attach(sdir, log_path, sdir / "sync" / best[2], sdir / "sync" / best[1], make_default, note)
    else:
        entry = attach_xdk.attach(sdir, log_path, None, None, make_default, note)
    return {"entry": entry, "used": {"gnss_sync": best[1], "xdk_sync": best[2]} if best else None, "tried": tried,
            "button_sync": bool(best)}


# ---------------------------------------------------------------- globālā IMU konfigurācija
def imu_config() -> dict:
    """Vienīgais, kas ir kopīgs visiem ierakstiem: akselerometra nobīžu un apstrādes profili + filtru noklusējumi."""
    cfg = ROOT / "config"

    def rows(name: str) -> list[dict]:
        p = cfg / name
        if not p.is_file():
            return []
        with p.open(newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))

    return {"dir": str(cfg), "bias_profiles": rows("imu_bias_profiles.csv"),
            "processing_profiles": rows("imu_processing_profiles.csv"),
            "defaults": {"accelerometer": "fusion_defaults.json", "xdk": "xdk_fusion_defaults.json"}}


# ---------------------------------------------------------------- pogas spiedieni kā laika momenti (kartei/video sinhronizācijai)
def presses(name: str) -> dict:
    """GNSS un XDK pogas spiedienu laiki (UTC epoch s). Brauciena sesijai ņem vecāka ierakstu (rx_bytes attiecas uz pilno BIN)."""
    import imu_links
    import sync_button
    from session_paths import find_original_bin
    sdir = session_dir(name)
    parent = store.parent_of(name) if (sdir / "trip.json").is_file() else name
    pd = session_dir(parent)
    binp = find_original_bin(pd)
    link = imu_links.resolve_xdk(pd)
    gsync = link.gnss_sync if link else None
    xsync = link.xdk_sync if link else None
    if gsync is None:  # nav piesaistes: meklē GNSS SYNC ar to pašu numuru kā BIN
        want = _num(binp.name)
        cands = [pd / "sync" / s["name"] for s in inventory(parent)["sync"] if s["side"] == "gnss" and _num(s["name"]) == want]
        gsync = cands[0] if len(cands) == 1 else None
    out: dict = {"recording": parent, "gnss": [], "xdk": [], "pairs": 0, "confidence": None, "notes": []}
    bs = None
    if gsync and xsync:
        try:
            bs = sync_button.compute_button_sync(gsync, xsync, binp)
        except SystemExit as exc:
            out["notes"].append(str(exc))
    if bs:
        out["pairs"], out["confidence"] = len(bs.pairs), bs.confidence
        out["gnss"] = [{"seq": g["seq"], "utc": g["utc"], "paired": bool(g["paired"]), "partner": g.get("xdk_seq")} for g in bs.gnss_press_list]
        out["xdk"] = [{"seq": x["seq"], "utc": x["utc"], "paired": bool(x["paired"]), "partner": x.get("gnss_seq")} for x in bs.xdk_press_list]
    else:
        if gsync:
            clock = sync_button.ByteClock(binp)
            for p in sync_button.read_gnss_sync(gsync):
                u = clock.utc_at(p.marker)
                if u is not None:
                    out["gnss"].append({"seq": p.seq, "utc": u, "paired": False, "partner": None})
        c0 = ((link.entry.get("sync") or {}).get("xdk_clock0_utc")) if link else None
        if xsync and c0 is not None:
            out["xdk"] = [{"seq": p.seq, "utc": c0 + p.t_s, "paired": False, "partner": None} for p in sync_button.read_xdk_sync(xsync)]
        if not out["gnss"] and not out["xdk"]:
            out["notes"].append("Nav pogu spiedienu failu: augšupielādē SYNC failus lapā Ieraksti un spied 'Savienot automātiski'.")
    return out
