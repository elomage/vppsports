from __future__ import annotations
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np
from scipy.ndimage import uniform_filter1d

from segmentation import (
    Segment,
    RideSegmentation,
    detect_swing_end,
)


@dataclass
class TrackTemplate:
    name: str
    fs: float
    t: np.ndarray
    az_smooth: np.ndarray
    ay_smooth: np.ndarray
    swing_end_idx: int

    kinds: List[str] = field(default_factory=list)
    starts: List[int] = field(default_factory=list)
    ends: List[int] = field(default_factory=list)
    indices: List[int] = field(default_factory=list)

    n_source_rides: int = 0
    expected_n_curves: Optional[int] = None

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @staticmethod
    def load(path: str | Path) -> "TrackTemplate":
        with open(path, "rb") as f:
            return pickle.load(f)


def _dtw_path(x: np.ndarray, y: np.ndarray,
              band_frac: float = 0.15) -> List[Tuple[int, int]]:
    n, m = len(x), len(y)
    band = max(int(band_frac * max(n, m)), 8)
    INF = np.inf

    D = np.full((n + 1, m + 1), INF, dtype=np.float64)
    D[0, 0] = 0.0

    for i in range(1, n + 1):
        j_lo = max(1, i - band)
        j_hi = min(m, i + band)
        xi = x[i - 1]
        for j in range(j_lo, j_hi + 1):
            d = (xi - y[j - 1]) ** 2
            D[i, j] = d + min(D[i - 1, j],  # insertion
                              D[i, j - 1],  # deletion
                              D[i - 1, j - 1])  # match

    # Backtrack
    i, j = n, m
    path: List[Tuple[int, int]] = []
    while i > 0 and j > 0:
        path.append((i - 1, j - 1))
        choices = (D[i - 1, j - 1], D[i - 1, j], D[i, j - 1])
        k = int(np.argmin(choices))
        if k == 0:
            i -= 1;
            j -= 1
        elif k == 1:
            i -= 1
        else:
            j -= 1
    path.reverse()
    return path

def _normalize_for_dtw(y: np.ndarray) -> np.ndarray:
    active = y[y > 0.05]
    if len(active) < 10:
        return y.copy()
    scale = float(np.percentile(active, 90))
    return y / max(scale, 1e-3)

def _map_index_via_path(path: Sequence[Tuple[int, int]],
                        src_idx: int,
                        direction: str = "src_to_tgt") -> int:
    if direction == "src_to_tgt":
        s_col, t_col = 0, 1
    else:
        s_col, t_col = 1, 0

    matches = [pair[t_col] for pair in path if pair[s_col] == src_idx]
    if matches:
        return int(np.median(matches))
    arr = np.array([p[s_col] for p in path])
    nearest = int(np.argmin(np.abs(arr - src_idx)))
    return path[nearest][t_col]


def _prepare_signals(acc: np.ndarray, smooth_s: float = 0.4
                     ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, float, int]:
    t = acc[:, 0] - acc[0, 0]
    ax = acc[:, 1];
    ay = acc[:, 2];
    az = acc[:, 3]
    fs = 1.0 / max(float(np.median(np.diff(t))), 1e-9)
    win = max(3, int(smooth_s * fs))
    az_s = uniform_filter1d(az, size=win)
    ay_s = uniform_filter1d(ay, size=win)
    az_pos = np.maximum(az_s, 0.0)
    swing_end = detect_swing_end(ax, t)
    return t, az_pos, ay_s, fs, swing_end


def _resample_to_grid(t: np.ndarray, y: np.ndarray,
                      target_n: int) -> np.ndarray:
    t_uniform = np.linspace(t[0], t[-1], target_n)
    return np.interp(t_uniform, t, y)


def build_track_template(
        rides: Sequence[Tuple[np.ndarray, Optional[np.ndarray]]],
        track_name: str,
        expected_n_curves: int,
        grid_n: int = 2000,
        smooth_s: float = 0.4,
        dtw_band: float = 0.15,
) -> TrackTemplate:
    if len(rides) < 2:
        raise ValueError("Need at least 2 rides to build a template (3+ recommended).")

    az_stack = np.zeros((len(rides), grid_n))
    ay_stack = np.zeros((len(rides), grid_n))
    swing_ends_normalised = []
    fs_template = None

    for i, (acc, _gyro) in enumerate(rides):
        t, az_pos, ay_s, fs, swing_end = _prepare_signals(acc, smooth_s)
        az_stack[i] = _resample_to_grid(t, az_pos, grid_n)
        ay_stack[i] = _resample_to_grid(t, ay_s, grid_n)
        swing_frac = swing_end / max(len(t) - 1, 1)
        swing_ends_normalised.append(swing_frac)
        if fs_template is None or i == 0:
            fs_template = fs

    energies = az_stack.sum(axis=1)
    pivot = int(np.argmin(np.abs(energies - np.median(energies))))
    pivot_az = az_stack[pivot]

    aligned_az = np.zeros_like(az_stack)
    aligned_ay = np.zeros_like(ay_stack)
    aligned_az[pivot] = pivot_az
    aligned_ay[pivot] = ay_stack[pivot]

    for i in range(len(rides)):
        if i == pivot:
            continue
        path = _dtw_path(_normalize_for_dtw(az_stack[i]),
                         _normalize_for_dtw(pivot_az),
                         band_frac=dtw_band)
        n = grid_n
        warped_az = np.full(n, np.nan)
        warped_ay = np.full(n, np.nan)
        counts = np.zeros(n)
        sum_az = np.zeros(n)
        sum_ay = np.zeros(n)
        for src_i, tgt_j in path:
            sum_az[tgt_j] += az_stack[i, src_i]
            sum_ay[tgt_j] += ay_stack[i, src_i]
            counts[tgt_j] += 1
        mask = counts > 0
        warped_az[mask] = sum_az[mask] / counts[mask]
        warped_ay[mask] = sum_ay[mask] / counts[mask]
        if np.any(~mask):
            idx = np.arange(n)
            warped_az = np.interp(idx, idx[mask], warped_az[mask])
            warped_ay = np.interp(idx, idx[mask], warped_ay[mask])
        aligned_az[i] = warped_az
        aligned_ay[i] = warped_ay
    az_canonical = np.median(aligned_az, axis=0)
    ay_canonical = np.median(aligned_ay, axis=0)
    az_canonical = uniform_filter1d(az_canonical, size=max(3, grid_n // 200))
    ay_canonical = uniform_filter1d(ay_canonical, size=max(3, grid_n // 200))

    durations = [acc[-1, 0] - acc[0, 0] for acc, _ in rides]
    median_dur = float(np.median(durations))
    t_canonical = np.linspace(0.0, median_dur, grid_n)
    fs_canonical = (grid_n - 1) / median_dur

    swing_end_canonical = int(np.median(swing_ends_normalised) * grid_n)

    segments_final = _segment_canonical(
        az_canonical, ay_canonical, t_canonical, fs_canonical,
        swing_end_canonical, expected_n_curves)

    kinds = [s.kind for s in segments_final]
    starts = [s.start_idx for s in segments_final]
    ends = [s.end_idx for s in segments_final]
    indices_ = [s.index for s in segments_final]

    return TrackTemplate(
        name=track_name,
        fs=fs_canonical,
        t=t_canonical,
        az_smooth=az_canonical,
        ay_smooth=ay_canonical,
        swing_end_idx=swing_end_canonical,
        kinds=kinds,
        starts=starts,
        ends=ends,
        indices=indices_,
        n_source_rides=len(rides),
        expected_n_curves=expected_n_curves,
    )


def _segment_canonical(az_canonical: np.ndarray, ay_canonical: np.ndarray,
                       t_canonical: np.ndarray, fs: float,
                       swing_end: int, expected_n_curves: int,
                       min_curve_s: float = 0.4,
                       min_straight_s: float = 0.25) -> List[Segment]:
    from segmentation import _detect_curve_intervals

    n = len(az_canonical)
    az_pos = np.maximum(az_canonical, 0.0)

    def run(sensitivity: float):
        return _detect_curve_intervals(
            az_pos, None, swing_end, fs, False,
            min_curve_s, min_straight_s, 20.0, sensitivity)

    candidates = np.linspace(0.5, 1.8, 27)
    best = None
    best_score = None
    for sens in candidates:
        intervals_s, _ = run(float(sens))
        diff = abs(len(intervals_s) - expected_n_curves)
        score = (diff, abs(sens - 1.0))
        if best_score is None or score < best_score:
            best = intervals_s
            best_score = score
        if diff == 0 and abs(sens - 1.0) < 0.05:
            break
    intervals = best or []

    def curve_kind(si: int, ei: int) -> str:
        return "curve_r" if np.mean(ay_canonical[si:ei + 1]) < 0 else "curve_l"

    segments: List[Segment] = [
        Segment("start", 1, 0, swing_end, t_canonical[0],
                t_canonical[min(swing_end, n - 1)])
    ]
    valid = [(max(s, swing_end), min(e, n - 1)) for s, e in intervals
             if e > swing_end and min(e, n - 1) > max(s, swing_end)]
    c_idx = 1;
    s_idx = 1;
    prev_end = swing_end
    for si, ei in valid:
        if si > prev_end:
            segments.append(Segment("straight", s_idx, prev_end, si,
                                    t_canonical[prev_end], t_canonical[si]))
            s_idx += 1
        segments.append(Segment(curve_kind(si, ei), c_idx, si, ei,
                                t_canonical[si], t_canonical[ei]))
        c_idx += 1
        prev_end = ei
    if (n - 1) > prev_end:
        segments.append(Segment("straight", s_idx, prev_end, n - 1,
                                t_canonical[prev_end], t_canonical[n - 1]))
    return segments


def segment_ride_templated(
        acc: np.ndarray,
        gyro: Optional[np.ndarray],
        template: TrackTemplate,
        local_refine_s: float = 0.3,
        dtw_band: float = 0.15,
) -> RideSegmentation:
    t, az_pos, ay_s, fs, swing_end_local = _prepare_signals(acc)
    n = len(t)

    grid_n = len(template.az_smooth)
    az_on_grid = _resample_to_grid(t, az_pos, grid_n)

    path = _dtw_path(_normalize_for_dtw(template.az_smooth),
                     _normalize_for_dtw(az_on_grid),
                     band_frac=dtw_band)

    def template_to_ride(idx_tpl: int) -> int:
        grid_j = _map_index_via_path(path, idx_tpl, "src_to_tgt")
        frac = grid_j / max(grid_n - 1, 1)
        return int(round(frac * (n - 1)))

    mapped_starts = [template_to_ride(i) for i in template.starts]
    mapped_ends = [template_to_ride(i) for i in template.ends]

    if template.kinds and template.kinds[0] == "start":
        mapped_starts[0] = 0
        if len(mapped_starts) > 1:
            next_start = mapped_starts[1]
            if 0 < swing_end_local < next_start:
                mapped_ends[0] = swing_end_local
            else:
                mapped_ends[0] = min(mapped_ends[0], next_start - 1)
            mapped_starts[1] = mapped_ends[0]
        else:
            mapped_ends[0] = min(mapped_ends[0], n - 1)

    if local_refine_s > 0:
        walk = max(1, int(local_refine_s * fs))
        min_neigh = max(1, int(0.10 * fs))

        per_boundary_walk: List[int] = []
        for tpl_idx in template.starts:
            matches = [pair[1] for pair in path if pair[0] == tpl_idx]
            if matches:
                spread = max(matches) - min(matches)
                slack_frac = spread / max(grid_n, 1)
            else:
                slack_frac = 0.05
            adaptive = int(max(walk, slack_frac * 2.0 * fs))
            per_boundary_walk.append(min(adaptive, int(2.0 * fs)))

        mapped_starts, mapped_ends = _refine_boundaries_to_valleys(
            mapped_starts, mapped_ends, template.kinds, az_pos, walk,
            min_neighbour_samples=min_neigh,
            ay_smooth=ay_s,
            per_boundary_walk=per_boundary_walk,
            fs=fs)


    first_curve_pos = next((i for i, k in enumerate(template.kinds)
                            if k.startswith("curve")), None)
    if first_curve_pos is not None:
        first_start = mapped_starts[first_curve_pos]
        first_end = mapped_ends[first_curve_pos]
        curve_peak_idx = first_start + int(np.argmax(az_pos[first_start:first_end + 1]))
        curve_peak = float(az_pos[curve_peak_idx])
        search_back = max(1, int(6.0 * fs))
        lo = max(swing_end_local + 1, curve_peak_idx - search_back)
        hi = curve_peak_idx
        if hi > lo + 5:
            from scipy.signal import find_peaks
            search_segment = az_pos[lo:hi + 1]
            inverted = -search_segment
            valley_offsets, props = find_peaks(inverted, prominence=0.03)
            print(f"[onset] curve_peak={curve_peak:.3f} at t={t[curve_peak_idx]:.2f}s, "
                  f"search [{t[lo]:.2f}s..{t[hi]:.2f}s], "
                  f"valleys_found={len(valley_offsets)}", flush=True)
            onset_idx = None
            if len(valley_offsets) > 0:
                rise_threshold = 0.25 * curve_peak
                for vo in reversed(valley_offsets):
                    valley_v = search_segment[vo]
                    if valley_v < rise_threshold:
                        onset_idx = lo + int(vo)
                        break
                if onset_idx is None:
                    onset_idx = lo + int(valley_offsets[-1])
            else:
                onset_idx = lo + int(np.argmin(search_segment))
            print(f"[onset] picked valley at t={t[onset_idx]:.2f}s "
                  f"(az={az_pos[onset_idx]:.3f})", flush=True)
            if onset_idx is not None and onset_idx < first_start:
                mapped_starts[first_curve_pos] = onset_idx
                mapped_ends[first_curve_pos - 1] = onset_idx



    segments: List[Segment] = []
    for kind, idx, s_i, e_i in zip(template.kinds, template.indices,
                                   mapped_starts, mapped_ends):
        s_i = max(0, min(s_i, n - 1))
        e_i = max(0, min(e_i, n - 1))
        if e_i <= s_i:
            e_i = min(s_i + 1, n - 1)
        seg_kind = kind
        if kind in ("curve", "curve_r", "curve_l"):
            if gyro is not None:
                tg = gyro[:, 0] - gyro[0, 0]
                gi = int(np.searchsorted(tg, t[s_i]))
                ge = int(np.searchsorted(tg, t[e_i]))
                if ge > gi:
                    seg_kind = "curve_r" if np.mean(gyro[gi:ge, 3]) < 0 else "curve_l"
                else:
                    seg_kind = "curve_r" if np.mean(ay_s[s_i:e_i + 1]) < 0 else "curve_l"
            else:
                seg_kind = "curve_r" if np.mean(ay_s[s_i:e_i + 1]) < 0 else "curve_l"
        segments.append(Segment(seg_kind, idx, s_i, e_i,
                                t[s_i], t[e_i]))


    return RideSegmentation(
        segments=segments,
        swing_end_idx=segments[0].end_idx if segments else 0,
        t=t,
        az_smooth=az_pos,
        threshold=float(np.percentile(az_pos[swing_end_local:], 60))
        if n > swing_end_local else 0.0,
        gyro_used=gyro is not None,
        converged=True,
        sensitivity=1.0,
    )


def _refine_boundaries_to_valleys(starts: List[int], ends: List[int],
                                  kinds: List[str], az_pos: np.ndarray,
                                  max_walk: int,
                                  min_neighbour_samples: int = 0,
                                  ay_smooth: Optional[np.ndarray] = None,
                                  per_boundary_walk: Optional[List[int]] = None,
                                  fs: float = 100.0,
                                  ) -> Tuple[List[int], List[int]]:
    from scipy.signal import find_peaks

    n = len(az_pos)
    new_starts = list(starts)
    new_ends = list(ends)

    peaks: List[Optional[int]] = []
    for i, kind in enumerate(kinds):
        if kind.startswith("curve"):
            s, e = starts[i], ends[i]
            walk_i = per_boundary_walk[i] if per_boundary_walk else max_walk
            lo = max(0, s - walk_i)
            hi = min(n - 1, e + walk_i)
            if hi > lo:
                peaks.append(lo + int(np.argmax(az_pos[lo:hi + 1])))
            else:
                peaks.append(None)
        else:
            peaks.append(None)

    def find_valley(left_peak: Optional[int], right_peak: Optional[int],
                    fallback_lo: int, fallback_hi: int) -> int:
        if left_peak is not None and right_peak is not None and right_peak > left_peak + 1:
            lo = left_peak + 1
            hi = right_peak - 1
        else:
            lo = max(0, fallback_lo)
            hi = min(n - 1, fallback_hi)
        if hi <= lo:
            return (fallback_lo + fallback_hi) // 2

        inverted = -az_pos[lo:hi + 1]
        valley_offsets, props = find_peaks(inverted, prominence=0.05)
        if len(valley_offsets) == 0:
            return lo + int(np.argmin(az_pos[lo:hi + 1]))
        deepest = valley_offsets[int(np.argmax(props['prominences']))]
        return lo + int(deepest)

    for i in range(len(starts) - 1):
        if kinds[i] == "start":
            new_starts[i + 1] = new_ends[i]
            continue

        walk_b = per_boundary_walk[i] if per_boundary_walk else max_walk
        b = (new_ends[i] + new_starts[i + 1]) // 2
        fallback_lo = b - walk_b
        fallback_hi = b + walk_b

        valley = find_valley(peaks[i], peaks[i + 1], fallback_lo, fallback_hi)

        left_floor = new_starts[i] + min_neighbour_samples
        right_ceil = ends[i + 1] - min_neighbour_samples
        valley = max(left_floor, min(valley, right_ceil))

        if (ay_smooth is not None
                and kinds[i].startswith("curve")
                and kinds[i + 1].startswith("curve")):
            zc_window = max(1, int(0.2 * fs))
            lo = max(0, valley - zc_window)
            hi = min(n - 1, valley + zc_window)
            seg = ay_smooth[lo:hi + 1]
            signs = np.sign(seg)
            signs[signs == 0] = 1
            zc = np.where(np.diff(signs) != 0)[0]
            if len(zc) > 0:
                abs_idx = lo + zc
                snapped = int(abs_idx[np.argmin(np.abs(abs_idx - valley))])
                valley = max(left_floor, min(snapped, right_ceil))

        new_ends[i] = valley
        new_starts[i + 1] = valley

    return new_starts, new_ends
