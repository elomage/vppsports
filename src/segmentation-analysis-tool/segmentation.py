from __future__ import annotations
import numpy as np
from dataclasses import dataclass, replace
from typing import List, Optional, Tuple
from scipy.ndimage import uniform_filter1d


@dataclass
class Segment:
    kind: str
    index: int
    start_idx: int
    end_idx: int
    t_start: float
    t_end: float

    @property
    def duration(self) -> float:
        return self.t_end - self.t_start

    @property
    def label(self) -> str:
        if self.kind == "start": return "Start"
        if self.kind == "curve": return f"Curve {self.index}"
        if self.kind == "curve_r": return f"Right {self.index}"
        if self.kind == "curve_l": return f"Left {self.index}"
        return f"Straight {self.index}"

    @property
    def color(self) -> str:
        if self.kind == "start": return "#f0913d"
        if self.kind == "curve": return "#9b59b6"
        if self.kind == "curve_r": return "#2ecc71"
        if self.kind == "curve_l": return "#e74c3c"
        return "#3d8ef0"

    def normalized(self) -> "Segment":
        if self.kind in ("curve_r", "curve_l"):
            return replace(self, kind="curve")
        return self


@dataclass
class RideSegmentation:
    segments: List[Segment]
    swing_end_idx: int
    t: np.ndarray
    az_smooth: np.ndarray
    threshold: float
    gyro_used: bool = False
    converged: bool = True
    sensitivity: float = 1.0

    @property
    def curves(self) -> List[Segment]:
        return [s for s in self.segments if s.kind in ("curve", "curve_r", "curve_l")]

    @property
    def straights(self) -> List[Segment]:
        return [s for s in self.segments if s.kind == "straight"]

    @property
    def start(self) -> Optional[Segment]:
        res = [s for s in self.segments if s.kind == "start"]
        return res[0] if res else None

    def normalized_segments(self) -> List[Segment]:
        return [s.normalized() for s in self.segments]

def detect_swing_end(ax, t, max_time_sec=7.0, threshold=0.18,
                     neighbor_window=3, neighbor_soft_ratio=0.5,
                     end_ratio=0.2, tail_ratio=0.05, noise_multiplier=2.0):
    ax = np.asarray(ax, dtype=float)
    t = np.asarray(t, dtype=float)
    if len(t) < 2 or len(ax) < 2:
        return 0

    mask = t <= max_time_sec
    ax_w = ax[mask]
    t_w = t[mask]
    n = len(ax_w)
    if n < 10:
        return len(ax) - 1

    sig = ax_w - np.median(ax_w)

    s = np.sign(sig)
    s[s == 0] = 1
    zc = np.where(np.diff(s) != 0)[0]
    if len(zc) < 3:
        return n - 1

    starts = zc[:-1]
    ends = zc[1:]

    amps = np.array([
        np.max(np.abs(sig[starts[i]:ends[i] + 1]))
        for i in range(len(starts))
    ])

    soft_threshold = threshold * neighbor_soft_ratio
    strict_real = amps > threshold
    soft_real = amps > soft_threshold

    last_real = -1
    for i in range(len(strict_real) - 1, -1, -1):
        if strict_real[i]:
            lo = max(0, i - neighbor_window)
            hi = min(len(strict_real), i + neighbor_window + 1)
            if np.sum(soft_real[lo:hi]) > 1:
                last_real = i
                break

    if last_real < 0:
        real_idx = np.where(strict_real)[0]
        if len(real_idx) > 0:
            last_real = int(real_idx[-1])

    if last_real < 0:
        return 0

    last_start = starts[last_real]
    last_end = ends[last_real]
    seg = sig[last_start:last_end + 1]
    peak_offset = int(np.argmax(np.abs(seg)))
    peak_idx = last_start + peak_offset
    peak_value = abs(sig[peak_idx])

    settle_threshold = peak_value * end_ratio
    cutoff_idx = last_end
    for j in range(peak_idx, last_end + 1):
        if abs(sig[j]) < settle_threshold:
            cutoff_idx = j
            break

    global_peak = float(np.max(np.abs(sig)))
    tail_start = int(0.85 * n)
    noise_level = float(np.median(np.abs(sig[tail_start:]))) if tail_start < n else 0.0
    tail_floor = max(global_peak * tail_ratio, noise_level * noise_multiplier)
    smooth_w = max(5, n // 40)
    kernel = np.ones(smooth_w) / smooth_w
    smoothed = np.convolve(np.abs(sig), kernel, mode='same')

    quiet_run_needed = max(smooth_w * 2, n // 25)
    extended = cutoff_idx
    quiet_count = 0
    for j in range(cutoff_idx + 1, n):
        if smoothed[j] > tail_floor:
            extended = j
            quiet_count = 0
        else:
            quiet_count += 1
            if quiet_count >= quiet_run_needed:
                break
    cutoff_idx = extended

    return int(cutoff_idx)

def _runs_in_mask(mask: np.ndarray, search_start: int) -> List[Tuple[int, int]]:
    intervals: List[Tuple[int, int]] = []
    n = len(mask)
    i = search_start
    while i < n:
        if not mask[i]:
            i += 1
            continue
        j = i
        while j < n and mask[j]:
            j += 1
        intervals.append((i, j - 1))
        i = j + 1
    return intervals


def _refine_boundaries(intervals: List[Tuple[int, int]],
                       az_pos: np.ndarray,
                       az_quiet: float,
                       az_thresh: float,
                       swing_end: int,
                       fs: float,
                       min_gap_samples: int = 0,
                       adjacent_to_prev: Optional[List[bool]] = None
                       ) -> List[Tuple[int, int]]:
    if not intervals:
        return intervals
    if adjacent_to_prev is None:
        adjacent_to_prev = [False] * len(intervals)

    n = len(az_pos)
    boundary = az_quiet + 0.35 * (az_thresh - az_quiet)
    max_walk = max(1, int(0.4 * fs))

    refined: List[Tuple[int, int]] = []
    for k, (s, e) in enumerate(intervals):
        prev_end = refined[-1][1] if refined else swing_end - 1
        gap_left = 0 if adjacent_to_prev[k] else min_gap_samples
        prev_floor = prev_end + 1 + gap_left
        new_s = s
        walk_limit = max(prev_floor, s - max_walk)
        while new_s > walk_limit and az_pos[new_s - 1] > boundary:
            new_s -= 1

        gap_right = (0 if (k + 1 < len(adjacent_to_prev)
                           and adjacent_to_prev[k + 1])
                     else min_gap_samples)
        next_start = intervals[k + 1][0] if k + 1 < len(intervals) else n
        next_ceiling = next_start - 1 - gap_right
        new_e = e
        walk_limit_e = min(next_ceiling, e + max_walk)
        while new_e < walk_limit_e and az_pos[new_e + 1] > boundary:
            new_e += 1

        if new_s > new_e:
            new_s, new_e = s, e
        refined.append((new_s, new_e))
    return refined


def _bridge_runs(intervals: List[Tuple[int, int]],
                 az_pos: np.ndarray,
                 az_quiet: float,
                 az_thresh: float,
                 short_gap_samples: int, long_gap_samples: int,
                 dip_ratio: float = 0.40
                 ) -> List[Tuple[int, int]]:
    if len(intervals) < 2:
        return list(intervals)

    bridged: List[Tuple[int, int]] = [intervals[0]]
    for s, e in intervals[1:]:
        ps, pe = bridged[-1]
        gap = s - pe - 1
        do_bridge = False

        if 0 < gap <= short_gap_samples:
            az_prev_peak = float(np.max(az_pos[ps:pe + 1]))
            az_curr_peak = float(np.max(az_pos[s:e + 1]))
            az_local_peak = min(az_prev_peak, az_curr_peak)
            az_dip_min = float(np.min(az_pos[pe:s + 1]))
            az_ratio = az_dip_min / az_local_peak if az_local_peak > 0 else 0.0
            do_bridge = az_ratio >= dip_ratio

        elif short_gap_samples < gap <= long_gap_samples:
            az_gap = az_pos[pe:s + 1]
            az_soft_floor = az_quiet + (az_thresh - az_quiet) * 0.30
            az_active_frac = float(np.mean(az_gap > az_soft_floor))
            do_bridge = az_active_frac >= 0.70

        if do_bridge:
            bridged[-1] = (ps, e)
        else:
            bridged.append((s, e))
    return bridged


def _filter_weak(intervals: List[Tuple[int, int]],
                 az_pos: np.ndarray,
                 min_samples: int,
                 az_min_peak: float,
                 az_min_ever: float,
                 g_mag: Optional[np.ndarray] = None,
                 gy_min_peak: float = 0.0) -> List[Tuple[int, int]]:
    out: List[Tuple[int, int]] = []
    for s, e in intervals:
        n_samples = e - s + 1
        az_peak = float(np.max(az_pos[s:e + 1]))
        gy_peak = float(np.max(g_mag[s:e + 1])) if g_mag is not None else 0.0

        too_short = n_samples < min_samples
        no_az = az_peak < az_min_ever
        az_strong = az_peak >= az_min_peak
        az_borderline_with_gyro = (
                g_mag is not None
                and az_peak >= az_min_ever
                and gy_peak >= gy_min_peak
        )
        too_weak = not (az_strong or az_borderline_with_gyro)

        if too_short or too_weak or no_az:
            continue
        out.append((s, e))
    return out


def _split_at_valleys(intervals: List[Tuple[int, int]],
                      az_pos: np.ndarray,
                      az_thresh: float,
                      az_quiet: float,
                      min_samples: int,
                      straight_min_samples: int = 0,
                      g_mag: Optional[np.ndarray] = None
                      ) -> Tuple[List[Tuple[int, int]], List[bool]]:
    from scipy.signal import find_peaks

    out: List[Tuple[int, int]] = []
    adjacent_to_prev: List[bool] = []

    for s, e in intervals:
        seg = az_pos[s:e + 1]
        if len(seg) < 2 * min_samples:
            out.append((s, e))
            adjacent_to_prev.append(False)
            continue

        peak_floor = az_quiet + 0.20 * (az_thresh - az_quiet)
        prominence = max(0.10, 0.30 * (az_thresh - az_quiet))
        peaks_arr, _ = find_peaks(seg, prominence=prominence,
                                  height=peak_floor,
                                  distance=max(2, min_samples // 2))
        merged_peaks = list(peaks_arr)

        if len(merged_peaks) < 2:
            out.append((s, e))
            adjacent_to_prev.append(False)
            continue

        gy_seg = g_mag[s:e + 1] if g_mag is not None else None

        split_points = []
        for a, b in zip(merged_peaks, merged_peaks[1:]):
            valley_idx = a + int(np.argmin(seg[a:b + 1]))
            valley_v = seg[valley_idx]
            peak_v = min(seg[a], seg[b])
            depth_ratio = valley_v / peak_v if peak_v > 0 else 1.0

            condition_a = depth_ratio <= 0.50 and valley_v < az_thresh
            condition_d = depth_ratio <= 0.70 and valley_v < az_thresh * 1.25
            both_peaks_strong = seg[a] > az_thresh * 1.5 and seg[b] > az_thresh * 1.5
            condition_e = depth_ratio <= 0.55 and both_peaks_strong
            condition_f = valley_v < az_quiet + 0.30 * (az_thresh - az_quiet)

            max_peak = max(seg[a], seg[b])
            peak_similarity = peak_v / max_peak if max_peak > 0 else 0.0
            condition_g = (peak_similarity >= 0.60
                           and depth_ratio <= 0.75
                           and max_peak >= az_thresh)

            condition_b = False
            condition_c = False
            if gy_seg is not None:
                gy_peak_local = min(
                    float(np.max(gy_seg[max(0, a - min_samples):a + 1])),
                    float(np.max(gy_seg[b:min(len(gy_seg), b + min_samples) + 1]))
                )
                gy_valley_min = float(np.min(gy_seg[a:b + 1]))
                gy_dip_ok = (gy_peak_local > 0
                             and (gy_valley_min / gy_peak_local) <= 0.55)
                condition_b = depth_ratio <= 0.65 and gy_dip_ok
                condition_c = depth_ratio <= 0.75 and gy_dip_ok and valley_v < az_thresh * 1.5

            if (condition_a or condition_b or condition_c or condition_d
                    or condition_e or condition_f or condition_g):
                split_points.append(valley_idx)

        if not split_points:
            out.append((s, e))
            adjacent_to_prev.append(False)
            continue

        sub_intervals = []
        prev_end_off = -1
        for vi in split_points:
            sub_start = prev_end_off + 1
            sub_end = vi
            if sub_end - sub_start + 1 >= min_samples:
                sub_intervals.append((s + sub_start, s + sub_end))
            prev_end_off = vi - 1
        sub_start = prev_end_off + 1
        sub_end = len(seg) - 1
        if sub_end - sub_start + 1 >= min_samples:
            sub_intervals.append((s + sub_start, s + sub_end))

        if len(sub_intervals) >= 2:
            out.extend(sub_intervals)
            adjacent_to_prev.append(False)
            for _ in range(len(sub_intervals) - 1):
                adjacent_to_prev.append(True)
        else:
            out.append((s, e))
            adjacent_to_prev.append(False)
    return out, adjacent_to_prev


def _detect_curve_intervals(
        az_pos: np.ndarray,
        g_mag_smooth: Optional[np.ndarray],
        swing_end: int,
        fs: float,
        gyro_used: bool,
        min_curve_s: float,
        min_straight_s: float,
        min_gyro_deg: float,
        sensitivity: float,
) -> Tuple[List[Tuple[int, int]], dict]:
    n = len(az_pos)
    az_post = az_pos[swing_end:] if n > swing_end else az_pos
    az_quiet = float(np.percentile(az_post, 25)) if len(az_post) else 0.0

    base_thresh = max(az_quiet + 0.12, 0.18)
    az_thresh = max(az_quiet + 0.05, base_thresh * sensitivity)

    if gyro_used:
        base_min_peak = max(az_quiet + 0.30, 0.40)
    else:
        base_min_peak = max(az_quiet + 0.15, 0.22)
    az_min_peak = max(az_quiet + 0.08, base_min_peak * sensitivity)
    az_min_ever = max(az_quiet + 0.05, 0.10)

    if gyro_used and g_mag_smooth is not None:
        gy_post = g_mag_smooth[swing_end:]
        gy_quiet = float(np.percentile(gy_post, 25))
        gy_min_peak = max(gy_quiet * 1.5, gy_quiet + 20.0, min_gyro_deg * 1.5) * sensitivity
    else:
        gy_quiet = 0.0
        gy_min_peak = 0.0

    min_samples = max(2, int(min_curve_s * fs * 0.5))
    bridge_samples = max(1, int(0.6 * fs))
    straight_min_samples = max(1, int(min_straight_s * fs))

    active = az_pos > az_thresh
    active[:swing_end] = False

    raw = _runs_in_mask(active, swing_end)
    bridged = _bridge_runs(raw, az_pos, az_quiet, az_thresh,
                           short_gap_samples=bridge_samples,
                           long_gap_samples=max(bridge_samples, int(1.5 * fs)),
                           dip_ratio=0.20)
    split, adj_flags = _split_at_valleys(bridged, az_pos, az_thresh, az_quiet,
                                         min_samples,
                                         straight_min_samples=straight_min_samples,
                                         g_mag=g_mag_smooth)

    filtered = []
    filtered_adj = []
    for iv, adj in zip(split, adj_flags):
        s, e = iv
        n_samples = e - s + 1
        az_peak = float(np.max(az_pos[s:e + 1]))
        gy_peak = float(np.max(g_mag_smooth[s:e + 1])) if g_mag_smooth is not None else 0.0
        too_short = n_samples < min_samples
        no_az = az_peak < az_min_ever
        az_strong = az_peak >= az_min_peak
        az_borderline_with_gyro = (
                g_mag_smooth is not None
                and az_peak >= az_min_ever
                and gy_peak >= gy_min_peak
        )
        too_weak = not (az_strong or az_borderline_with_gyro)
        if too_short or too_weak or no_az:
            continue
        filtered.append(iv)
        filtered_adj.append(adj)

    refined = _refine_boundaries(filtered, az_pos, az_quiet, az_thresh,
                                 swing_end, fs,
                                 min_gap_samples=straight_min_samples,
                                 adjacent_to_prev=filtered_adj)

    info = dict(az_quiet=az_quiet, az_thresh=az_thresh, az_min_peak=az_min_peak,
                az_min_ever=az_min_ever, gy_min_peak=gy_min_peak,
                min_samples=min_samples, bridge_samples=bridge_samples,
                straight_min_samples=straight_min_samples)
    return refined, info

def _filter_relative(intervals: List[Tuple[int, int]],
                     az_pos: np.ndarray,
                     rel_ratio: float = 0.30) -> List[Tuple[int, int]]:
    if len(intervals) < 2:
        return list(intervals)
    peaks = np.array([float(np.max(az_pos[s:e + 1])) for s, e in intervals])
    reference = float(np.percentile(peaks, 75))
    floor = reference * rel_ratio
    return [iv for iv, p in zip(intervals, peaks) if p >= floor]

def segment_ride(
        acc: np.ndarray,
        gyro: Optional[np.ndarray] = None,
        threshold: Optional[float] = None,
        smooth_s: float = 0.4,
        min_curve_s: float = 0.4,
        min_gyro_deg: float = 20.0,
        min_straight_s: float = 0.25,
        expected_n_curves: Optional[int] = None,
        debug: bool = False,
) -> RideSegmentation:
    t = acc[:, 0]
    ax, ay, az = acc[:, 1], acc[:, 2], acc[:, 3]
    fs = 1.0 / max(float(np.median(np.diff(t))), 1e-9)
    n = len(t)

    swing_end = detect_swing_end(ax, t)
    win = max(3, int(smooth_s * fs))
    az_smooth = uniform_filter1d(az, size=win)
    ay_smooth = uniform_filter1d(ay, size=win)
    az_rel = az_smooth
    az_pos = np.maximum(az_rel, 0.0)

    gyro_used = gyro is not None
    if gyro_used:
        tg = gyro[:, 0]
        g_mag_raw = np.sqrt(np.sum(gyro[:, 1:] ** 2, axis=1))
        g_mag_interp = np.interp(t, tg, g_mag_raw)
        wide_win = max(win, int(0.4 * fs))
        g_mag_smooth = uniform_filter1d(g_mag_interp, size=wide_win)
    else:
        g_mag_smooth = None

    def run(sensitivity: float):
        return _detect_curve_intervals(
            az_pos, g_mag_smooth, swing_end, fs, gyro_used,
            min_curve_s, min_straight_s, min_gyro_deg, sensitivity)

    converged = True
    sensitivity = 1.0

    if threshold is not None:
        intervals, info = run(1.0)
        info["az_thresh"] = threshold
    elif expected_n_curves is None:
        intervals, info = run(1.0)
    else:
        candidates = np.linspace(0.7, 1.6, 19)
        best = None
        best_score = None
        for sens in candidates:
            intervals_s, info_s = run(float(sens))
            n_s = len(intervals_s)
            diff = abs(n_s - expected_n_curves)
            score = (diff, abs(sens - 1.0))
            if best_score is None or score < best_score:
                best = (intervals_s, info_s, float(sens))
                best_score = score
            if diff == 0 and abs(sens - 1.0) < 0.05:
                break
        intervals, info, sensitivity = best
        converged = (best_score[0] == 0)

    def curve_kind(si: int, ei: int) -> str:
        if gyro is not None:
            tg = gyro[:, 0]
            gi = int(np.searchsorted(tg, t[si]))
            ge = int(np.searchsorted(tg, t[ei]))
            if ge > gi:
                return "curve_r" if np.mean(gyro[gi:ge, 3]) < 0 else "curve_l"
        return "curve_r" if np.mean(ay_smooth[si:ei + 1]) < 0 else "curve_l"

    segments: List[Segment] = [
        Segment("start", 1, 0, swing_end, t[0], t[min(swing_end, n - 1)])
    ]

    valid_curves = []
    for s, e in intervals:
        if e <= swing_end:
            continue
        si = max(s, swing_end)
        ei = min(e, n - 1)
        if ei > si:
            valid_curves.append((si, ei))

    c_idx, s_idx = 1, 1
    prev_end = swing_end

    for si, ei in valid_curves:
        if si > prev_end:
            segments.append(Segment("straight", s_idx, prev_end, si,
                                    t[prev_end], t[si]))
            s_idx += 1
        segments.append(Segment(curve_kind(si, ei), c_idx, si, ei,
                                t[si], t[ei]))
        c_idx += 1
        prev_end = ei

    if (n - 1) > prev_end:
        segments.append(Segment("straight", s_idx, prev_end, n - 1,
                                t[prev_end], t[n - 1]))

    if debug:
        n_curves = sum(1 for s in segments if s.kind in ("curve", "curve_r", "curve_l"))
        n_straights = sum(1 for s in segments if s.kind == "straight")
        print(f"Final segments: {len(segments)} → {n_curves} curves, {n_straights} straights")
        for seg in segments:
            print(f"  {seg.label:>12s}: t={seg.t_start:.2f}-{seg.t_end:.2f}s ({seg.duration:.2f}s)")

    return RideSegmentation(segments, swing_end, t, az_smooth,
                            info.get("az_thresh", 0.18), gyro_used,
                            converged=converged, sensitivity=sensitivity)