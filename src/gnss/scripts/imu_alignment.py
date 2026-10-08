"""Read-only signal preview and explicit, per-pair alignment persistence."""
import json
import math
import struct
from datetime import timedelta, datetime, timezone
from pathlib import Path

from imu_kalman import load_gnss, load_imu, source_csv, GNSS_SOURCES
from gnss_imu_fusion import scan_alignment


def read_samples(path):
    if path.suffix.lower() != '.bin':
        return load_imu(path)
    from imu_kalman import ImuSample
    rows = []
    with path.open('rb') as stream:
        while chunk := stream.read(16):
            if len(chunk) != 16:
                raise ValueError('Nepilnīgs IMU BIN ieraksts.')
            t, x, y, z = struct.unpack('<Iiii', chunk)
            rows.append(ImuSample(t / 1e6, x * 19.5e-6 * 9.80665,
                                  y * 19.5e-6 * 9.80665, z * 19.5e-6 * 9.80665))
    return rows


def alignment_path(session, imu, source):
    return session / 'imu' / f'alignment_{source}_{imu.stem}.json'


def preview(session, imu, source):
    if source not in GNSS_SOURCES:
        raise ValueError('Nezināms GNSS avots.')
    points = load_gnss(source_csv(session, source))
    samples = read_samples(imu)
    if not samples:
        raise ValueError('IMU ieraksts ir tukšs.')
    if any(not all(math.isfinite(v) for v in (s.seconds, s.ax_mps2, s.ay_mps2, s.az_mps2)) for s in samples):
        raise ValueError('IMU satur nederīgas vērtības.')
    if any(b.seconds <= a.seconds for a, b in zip(samples, samples[1:])):
        raise ValueError('IMU laiks nav stingri augošs; jāpārbauda taimera atiestate.')
    start = points[0].time
    gnss = []
    for i, p in enumerate(points):
        a, b = points[max(0, i-1)], points[min(len(points)-1, i+1)]
        dt = (b.time-a.time).total_seconds()
        gnss.append([(p.time-start).total_seconds(), math.hypot(p.east, p.north),
                     p.speed_mps, (b.speed_mps-a.speed_mps)/dt if dt > 0 else None])
    saved_path = alignment_path(session, imu, source)
    saved = json.loads(saved_path.read_text(encoding='utf-8')) if saved_path.exists() else None
    return dict(start_utc=start.isoformat(),
                imu=[[s.seconds, s.ax_mps2, s.ay_mps2, s.az_mps2] for s in samples],
                gnss=gnss, saved=saved)


def scan(session, imu, source):
    """Score every candidate IMU time offset (how well the IMU explains GNSS acceleration)."""
    if source not in GNSS_SOURCES:
        raise ValueError('Nezināms GNSS avots.')
    points = load_gnss(source_csv(session, source))
    result = scan_alignment(points, read_samples(imu))
    result['start_utc'] = points[0].time.isoformat()
    return result


def save_alignment(session, imu, source, offset):
    if source not in GNSS_SOURCES or not math.isfinite(offset):
        raise ValueError('Nederīgs avots vai laika nobīde.')
    points = load_gnss(source_csv(session, source))
    samples = read_samples(imu)
    if not samples or samples[-1].seconds + offset < 0 or samples[0].seconds + offset > (points[-1].time-points[0].time).total_seconds():
        raise ValueError('IMU un GNSS laiki nepārklājas.')
    row = dict(recording=session.name, imu=str(imu), source=source, time_offset_s=offset,
               imu_start_utc=(points[0].time+timedelta(seconds=offset)).isoformat(),
               saved_utc=datetime.now(timezone.utc).isoformat())
    path = alignment_path(session, imu, source)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(row, indent=2), encoding='utf-8')
    temporary.replace(path)
    return dict(ok=True, path=str(path), **row)
