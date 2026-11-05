#!/usr/bin/env python3
"""Align a Bosch XDK log with a GNSS recording from the SYNC button presses.

Both loggers have a button wired to them and the operator presses both together:

* the Pico GNSS logger writes ``SYNC,<time_us>,<seq>,<rx_bytes>`` to ``SYNCnnnnn.CSV``; ``time_us`` is the
  Pico's own clock and ``rx_bytes`` is the byte offset in ``LOGnnnnn.BIN`` at the press;
* the XDK writes ``SYNC,<t_ms>,<seq>,<rows>`` to ``SYNC_nnn.CSV`` on the XDK clock of its ``LOG_nnn.CSV``.

The GNSS press is dated by looking up the receiver time at ``rx_bytes`` in the BIN. Presses of the two
files are paired by their spacing (a press may exist on one side only, or bounce), and every pair gives
the UTC time at which the XDK clock read 0.
"""

from __future__ import annotations

import argparse
import bisect
import json
import statistics
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "converting" / "to_csv"))

PAIR_TOLERANCE_S = 0.2  # spacing of two presses must agree this well to be the same press
MIN_VALID_YEAR = 2020  # a receiver without time reports 1980


@dataclass
class Press:
    seq: int
    t_s: float  # Pico clock (GNSS side) or XDK clock (XDK side), seconds
    marker: int  # rx_bytes (GNSS) or log row (XDK)


@dataclass
class PressPair:
    gnss_seq: int
    xdk_seq: int
    interval_error_ms: float
    gnss_utc: float  # epoch seconds, from the byte offset
    gnss_utc_refined: float  # epoch seconds, byte-offset UTC averaged over all presses and put on the Pico clock
    xdk_t_s: float
    xdk_clock0_utc: float  # epoch seconds when the XDK clock read 0


@dataclass
class ButtonSync:
    xdk_clock0_utc: float  # best estimate, epoch seconds
    pairs: list[PressPair]
    gnss_presses: int
    xdk_presses: int
    spread_ms: float  # spread of the per-pair XDK clock-0 estimates
    clock_check_ms: float  # spread of (UTC from bytes - Pico clock): how well rx_bytes dates a press
    confidence: str
    notes: list[str] = field(default_factory=list)
    pico_to_utc: float = 0.0  # UTC (epoch s) at Pico clock 0, from all presses
    gnss_press_list: list[dict] = field(default_factory=list)  # every GNSS press: seq, pico_t_s, rx_bytes, utc_bytes, utc, paired, xdk_seq
    xdk_press_list: list[dict] = field(default_factory=list)  # every XDK press: seq, t_s, rows, utc, paired, gnss_seq

    @property
    def xdk_clock0(self) -> datetime:
        return datetime.fromtimestamp(self.xdk_clock0_utc, timezone.utc)

    def offset_s(self, first_gnss_time: datetime) -> float:
        """Seconds after `first_gnss_time` at which the XDK clock reads 0 (the offset gnss_xdk_fusion uses)."""
        return self.xdk_clock0_utc - first_gnss_time.timestamp()


def read_sync_file(path: Path, time_scale: float) -> list[Press]:
    presses: list[Press] = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("SYNC,"):
            continue
        parts = line.strip().split(",")
        try:
            presses.append(Press(int(parts[2]), float(parts[1]) * time_scale, int(parts[3])))
        except (IndexError, ValueError):
            continue
    return presses


def read_gnss_sync(path: Path) -> list[Press]:
    return read_sync_file(path, 1e-6)


def read_xdk_sync(path: Path) -> list[Press]:
    return read_sync_file(path, 1e-3)


class ByteClock:
    """Receiver UTC (epoch seconds) as a function of the byte offset in a Unicore BIN."""

    def __init__(self, bin_path: Path):
        import unicore_n4_extract as n4

        blob = Path(bin_path).read_bytes()
        self.size = len(blob)
        offsets: list[int] = []
        seconds: list[float] = []
        last = -1.0
        for frame in n4.iter_n4_frames(blob):
            utc = frame["utc"]
            if utc.year < MIN_VALID_YEAR:
                continue
            stamp = utc.timestamp()
            if last > 0 and not 0.0 <= stamp - last <= 10.0:  # a stray frame with a wrong time (monotonic, no jumps)
                continue
            last = stamp
            offsets.append(frame["file_offset"])
            seconds.append(stamp)
        if len(offsets) < 2:
            raise SystemExit(f"No messages with a valid receiver time in {bin_path}")
        self.offsets, self.seconds = offsets, seconds

    def utc_at(self, rx_bytes: int) -> float | None:
        i = bisect.bisect_right(self.offsets, rx_bytes) - 1
        if i < 0 or i >= len(self.offsets) - 1:
            return None
        span = max(1, self.offsets[i + 1] - self.offsets[i])
        return self.seconds[i] + (self.seconds[i + 1] - self.seconds[i]) * (rx_bytes - self.offsets[i]) / span


def pair_presses(gnss: list[Press], xdk: list[Press], tolerance_s: float = PAIR_TOLERANCE_S) -> list[tuple[Press, Press, float]]:
    """Pair presses by spacing. Returns (gnss press, xdk press, spacing error s); tries every anchor pair."""
    best: tuple[tuple[int, float], list[tuple[Press, Press, float]]] | None = None
    for ga in gnss:
        for xa in xdk:
            used: set[int] = set()
            pairs: list[tuple[Press, Press, float]] = []
            for x in xdk:
                dx = x.t_s - xa.t_s
                j = min(range(len(gnss)), key=lambda k: abs((gnss[k].t_s - ga.t_s) - dx))
                err = (gnss[j].t_s - ga.t_s) - dx
                if abs(err) <= tolerance_s and j not in used:
                    used.add(j)
                    pairs.append((gnss[j], x, err))
            score = (len(pairs), -sum(abs(p[2]) for p in pairs))
            if best is None or score > best[0]:
                best = (score, pairs)
    return best[1] if best else []


def compute_button_sync(
    gnss_sync: Path,
    xdk_sync: Path,
    gnss_bin: Path,
    tolerance_s: float = PAIR_TOLERANCE_S,
) -> ButtonSync:
    gnss = read_gnss_sync(gnss_sync)
    xdk = read_xdk_sync(xdk_sync)
    if not gnss:
        raise SystemExit(f"No SYNC presses in the GNSS sync file {gnss_sync} (the Pico did not see the button).")
    if not xdk:
        raise SystemExit(f"No SYNC presses in the XDK sync file {xdk_sync}.")
    clock = ByteClock(gnss_bin)
    notes: list[str] = []
    for press in gnss:
        if press.marker > clock.size:
            notes.append(
                f"GNSS press #{press.seq}: rx_bytes {press.marker} is past the end of {Path(gnss_bin).name} "
                f"({clock.size} bytes); the SYNC file does not belong to this BIN"
            )
    matched = pair_presses(gnss, xdk, tolerance_s)
    if not matched:
        raise SystemExit("No GNSS press matches an XDK press by spacing; check that the two files are from the same session.")

    utc_by_press = {g.seq: clock.utc_at(g.marker) for g, _, _ in matched}
    usable = [(g, x, e) for g, x, e in matched if utc_by_press[g.seq] is not None]
    if not usable:
        raise SystemExit("The receiver time at the GNSS presses is unknown (no valid time in the BIN there).")

    # The Pico clock is exact between presses; the byte offset only dates a press to the message spacing.
    # Date the Pico clock once from all presses instead of trusting each byte lookup separately.
    clock_residuals = [utc_by_press[g.seq] - g.t_s for g, _, _ in usable]
    pico_to_utc = statistics.median(clock_residuals)
    pairs: list[PressPair] = []
    for g, x, err in usable:
        refined = g.t_s + pico_to_utc
        pairs.append(PressPair(
            gnss_seq=g.seq, xdk_seq=x.seq, interval_error_ms=err * 1000.0,
            gnss_utc=utc_by_press[g.seq], gnss_utc_refined=refined,
            xdk_t_s=x.t_s, xdk_clock0_utc=refined - x.t_s,
        ))
    estimates = [p.xdk_clock0_utc for p in pairs]
    best = statistics.median(estimates)
    spread = (max(estimates) - min(estimates)) * 1000.0
    clock_check = (max(clock_residuals) - min(clock_residuals)) * 1000.0
    unpaired_g = len(gnss) - len(pairs)
    if unpaired_g:
        notes.append(f"{unpaired_g} GNSS press(es) have no XDK partner (extra or bounced presses are ignored)")
    if len(xdk) - len(pairs):
        notes.append(f"{len(xdk) - len(pairs)} XDK press(es) have no GNSS partner")
    if len(pairs) >= 3 and spread <= 60.0:
        confidence = "high"
    elif len(pairs) >= 2 and spread <= 150.0:
        confidence = "medium"
    else:
        confidence = "low"
        if len(pairs) < 2:
            notes.append("only one press pair: the offset cannot be cross-checked")
    partner_of_gnss = {p.gnss_seq: p.xdk_seq for p in pairs}
    partner_of_xdk = {p.xdk_seq: p.gnss_seq for p in pairs}
    gnss_list = [
        {"seq": g.seq, "pico_t_s": g.t_s, "rx_bytes": g.marker, "utc_bytes": clock.utc_at(g.marker), "utc": g.t_s + pico_to_utc,
         "paired": g.seq in partner_of_gnss, "xdk_seq": partner_of_gnss.get(g.seq)}
        for g in gnss
    ]
    xdk_list = [
        {"seq": x.seq, "t_s": x.t_s, "rows": x.marker, "utc": best + x.t_s, "paired": x.seq in partner_of_xdk, "gnss_seq": partner_of_xdk.get(x.seq)}
        for x in xdk
    ]
    return ButtonSync(best, pairs, len(gnss), len(xdk), spread, clock_check, confidence, notes, pico_to_utc, gnss_list, xdk_list)


def xdk_row_check(xdk_sync: Path, xdk_log: Path) -> list[dict[str, float]]:
    """The XDK sync file names the log row of each press; its t_ms must match the t_ms of that row."""
    rows: list[list[str]] = []
    with Path(xdk_log).open("r", encoding="utf-8-sig") as f:
        next(f, None)
        rows = [line.split(",", 1) for line in f]
    out = []
    for press in read_xdk_sync(xdk_sync):
        idx = press.marker - 1
        if 0 <= idx < len(rows):
            try:
                log_t = float(rows[idx][0]) / 1000.0
            except ValueError:
                continue
            out.append({"seq": press.seq, "sync_t_s": press.t_s, "log_row_t_s": log_t, "diff_ms": (press.t_s - log_t) * 1000.0})
    return out


def sync_files_for(gnss_dir: Path, xdk_dir: Path, log_number: int) -> tuple[Path, Path, Path, Path]:
    """(gnss BIN, gnss SYNC, xdk LOG, xdk SYNC) for the same log number in the two SD card folders."""
    return (
        Path(gnss_dir) / f"LOG{log_number:05d}.BIN",
        Path(gnss_dir) / f"SYNC{log_number:05d}.CSV",
        Path(xdk_dir) / f"LOG_{log_number:03d}.CSV",
        Path(xdk_dir) / f"SYNC_{log_number:03d}.CSV",
    )


def describe(sync: ButtonSync) -> str:
    lines = [
        f"XDK clock 0 = {sync.xdk_clock0.isoformat()}  (confidence {sync.confidence})",
        f"presses: GNSS {sync.gnss_presses}, XDK {sync.xdk_presses}, paired {len(sync.pairs)}",
        f"spread of the pair estimates: {sync.spread_ms:.0f} ms; byte-offset dating vs Pico clock: {sync.clock_check_ms:.0f} ms",
    ]
    for p in sync.pairs:
        lines.append(
            f"  GNSS #{p.gnss_seq} <-> XDK #{p.xdk_seq}: spacing error {p.interval_error_ms:+.0f} ms, "
            f"XDK t={p.xdk_t_s:.3f}s, clock 0 at {datetime.fromtimestamp(p.xdk_clock0_utc, timezone.utc).strftime('%H:%M:%S.%f')[:-3]}"
        )
    lines += [f"note: {n}" for n in sync.notes]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Pair SYNC button presses of a GNSS BIN and an XDK log.")
    parser.add_argument("--gnss-bin", required=True, type=Path)
    parser.add_argument("--gnss-sync", required=True, type=Path)
    parser.add_argument("--xdk-sync", required=True, type=Path)
    parser.add_argument("--json", type=Path, help="Write the result as JSON")
    args = parser.parse_args()
    sync = compute_button_sync(args.gnss_sync, args.xdk_sync, args.gnss_bin)
    print(describe(sync))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(asdict(sync), indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
