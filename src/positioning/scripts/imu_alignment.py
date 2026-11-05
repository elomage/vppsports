"""Read-only signal preview and explicit, per-pair alignment persistence."""
import json
import math
import struct
from datetime import timedelta, datetime, timezone
from pathlib import Path

from imu_kalman import ImuSample, load_gnss, load_imu, source_csv, GNSS_SOURCES
import imu_links
from gnss_imu_fusion import scan_alignment


def is_xdk(path):
    """A Bosch XDK SD card log: CSV whose header starts with t_ms (accelerometer AND gyroscope)."""
    if path.suffix.lower() != '.csv' or not path.is_file():
        return False
    with path.open('r', encoding='utf-8-sig', errors='replace') as stream:
        return stream.readline().strip().lower().startswith('t_ms')


def load_xdk_data(path):
    from xdk_imu import load_xdk
    return load_xdk(path)


def button_offset(session, imu, points):
    """Offset from the SYNC button presses stored with the linked XDK log (seconds after the first GNSS point)."""
    link = next((item for item in imu_links.xdk_links(session) if item.xdk.resolve() == imu.resolve()), None)
    clock0 = ((link.entry.get('sync') or {}).get('xdk_clock0_utc') if link else None)
    if clock0 is None:
        return None
    return float(clock0) - points[0].time.timestamp()


def button_sync_for_plot(session, imu, points):
    """The SYNC button presses of the linked XDK log, on the plots' axes (GNSS seconds from the first point / XDK clock)."""
    link = next((item for item in imu_links.xdk_links(session) if item.xdk.resolve() == imu.resolve()), None)
    if link is None or link.gnss_sync is None or link.xdk_sync is None:
        return None
    from session_paths import find_original_bin
    from sync_button import compute_button_sync
    try:
        button = compute_button_sync(link.gnss_sync, link.xdk_sync, find_original_bin(session))
    except SystemExit as exc:
        return dict(error=str(exc))
    t0 = points[0].time.timestamp()
    return dict(
        clock0_utc=button.xdk_clock0_utc, offset_s=button.xdk_clock0_utc - t0, first_gnss_utc=t0,
        spread_ms=button.spread_ms, clock_check_ms=button.clock_check_ms, confidence=button.confidence,
        pico_to_utc=button.pico_to_utc, notes=button.notes,
        pairs=[dict(gnss_seq=p.gnss_seq, xdk_seq=p.xdk_seq, interval_error_ms=p.interval_error_ms, xdk_t_s=p.xdk_t_s,
                    gnss_utc=p.gnss_utc_refined, clock0_utc=p.xdk_clock0_utc) for p in button.pairs],
        gnss=[dict(seq=g['seq'], t=g['utc'] - t0, pico_t_s=g['pico_t_s'], rx_bytes=g['rx_bytes'], paired=g['paired'], xdk_seq=g['xdk_seq']) for g in button.gnss_press_list],
        xdk=[dict(seq=x['seq'], t_xdk=x['t_s'], rows=x['rows'], paired=x['paired'], gnss_seq=x['gnss_seq']) for x in button.xdk_press_list],
    )


def read_samples(path):
    if is_xdk(path):
        data = load_xdk_data(path)
        return [ImuSample(float(t), float(a[0]), float(a[1]), float(a[2])) for t, a in zip(data.t, data.acc)]
    if path.suffix.lower() != '.bin':
        return load_imu(path)
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
    xdk = is_xdk(imu)
    if xdk and saved is None:  # the SYNC button gives the offset without any search
        offset = button_offset(session, imu, points)
        if offset is not None:
            saved = dict(recording=session.name, imu=str(imu), source='button', time_offset_s=offset,
                         imu_start_utc=(points[0].time + timedelta(seconds=offset)).isoformat())
    step = max(1, len(points) // 8000)  # plain GNSS path for the comparison map (east/north from the first fix)
    track = dict(origin=[points[0].lat, points[0].lon], pts=[[p.east, p.north, 'used'] for p in points[::step]])
    sync = button_sync_for_plot(session, imu, points) if xdk else None
    return dict(start_utc=start.isoformat(), imu_kind='xdk' if xdk else 'accelerometer', sync=sync,
                imu=[[s.seconds, s.ax_mps2, s.ay_mps2, s.az_mps2] for s in samples],
                gnss=gnss, track=track, saved=saved)


def scan(session, imu, source):
    """Score every candidate IMU time offset (how well the IMU explains GNSS acceleration)."""
    if source not in GNSS_SOURCES:
        raise ValueError('Nezināms GNSS avots.')
    points = load_gnss(source_csv(session, source))
    if is_xdk(imu):
        return scan_xdk(session, imu, points)
    result = scan_alignment(points, read_samples(imu))
    result['start_utc'] = points[0].time.isoformat()
    return result


def scan_xdk(session, imu, points):
    """XDK: the gyroscope yaw rate against the GNSS heading change (and the SYNC button offset, if there is one)."""
    from xdk_imu import correlation_at, find_offset, offset_curve
    xdk = load_xdk_data(imu)
    curve = offset_curve(xdk, points)
    if not curve:
        raise ValueError('IMU un GNSS pārklājas par īsu laiku, lai meklētu nobīdi.')
    peaks = []
    try:
        found = find_offset(xdk, points)
        peaks.append(dict(offset_s=round(found.offset_s, 3), score=round(found.correlation, 4), r2=round(found.correlation, 4),
                          axis=[], overlap_s=round(found.overlap_s, 1), label='Grozīšanās ātrums (žiroskops)'))
        confidence = found.confidence
    except ValueError:
        confidence = 'low'
    for off, corr, overlap in sorted(curve, key=lambda row: -row[1]):
        if len(peaks) >= 3:
            break
        if all(abs(off - p['offset_s']) >= 5.0 for p in peaks):
            peaks.append(dict(offset_s=round(off, 3), score=round(corr, 4), r2=round(corr, 4), axis=[], overlap_s=round(overlap, 1)))
    button = button_offset(session, imu, points)
    if button is not None:
        corr, overlap = correlation_at(xdk, points, button)
        peaks.insert(0, dict(offset_s=round(button, 3), score=round(max(corr, 0.0), 4), r2=round(corr, 4), axis=[],
                             overlap_s=round(overlap, 1), label='SYNC poga'))
        link = next((item for item in imu_links.xdk_links(session) if item.xdk.resolve() == imu.resolve()), None)
        if ((link.entry.get('sync') or {}).get('confidence') if link else None) == 'high':
            confidence = 'high'
    if not peaks:
        raise ValueError('Nobīdi atrast neizdevās.')
    step = 4
    return dict(curve=[[round(o, 3), round(max(c, 0.0), 4)] for o, c, _ in curve[::step]], peaks=peaks[:4], confidence=confidence,
                has_doppler=bool(any(getattr(p, 've_mps', None) is not None for p in points[:50])),
                start_utc=points[0].time.isoformat(), imu_kind='xdk')


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
