import numpy as np
from scipy.signal import find_peaks


def count_wiggles(ax, threshold=0.07):
    ax = np.asarray(ax)

    if len(ax) < 3:
        return 0

    peaks, _ = find_peaks(ax, prominence=threshold)
    valleys, _ = find_peaks(-ax, prominence=threshold)

    all_extrema = np.sort(np.concatenate([peaks, valleys]))

    return len(all_extrema) // 2


def safe(v, default=0.0):
    if v is None:
        return default

    v = float(v)

    return v if np.isfinite(v) else default


def zero_cross_rate(x, dt):
    if len(x) < 2 or dt <= 0:
        return 0.0

    x_c = x - np.median(x)

    s = np.sign(x_c)
    s[s == 0] = 1

    flips = int(np.sum(np.abs(np.diff(s)) > 0))

    return flips / (len(x) * dt)


def jerk_rms(x, dt):
    if len(x) < 2 or dt <= 0:
        return 0.0

    return float(np.sqrt(np.mean(np.diff(x) ** 2)) / dt)


def peak_shape(x):
    if len(x) < 3:
        return 0.5, 1.0

    i = int(np.argmax(x))
    pos = i / max(len(x) - 1, 1)

    half = x[i] / 2.0
    above = x >= half

    if not above.any():
        return pos, 1.0

    width = above.sum() / len(x)

    return pos, float(width)


def percentiles(x, ps=(5, 25, 50, 75, 95)):
    if len(x) == 0:
        return {f"p{p}": 0.0 for p in ps}

    vals = np.percentile(x, ps)

    return {
        f"p{p}": float(v)
        for p, v in zip(ps, vals)
    }


def stats(series, prefix):
    import pandas as pd

    if len(series) == 0 or series.isna().all():
        return {
            f"{prefix}_{k}": np.nan
            for k in [
                "mean",
                "std",
                "cv",
                "median",
                "p90",
                "min",
                "max",
            ]
        }

    m = float(series.mean())
    sd = float(series.std())

    return {
        f"{prefix}_mean": m,
        f"{prefix}_std": sd,
        f"{prefix}_cv": sd / m if m > 1e-9 else 0.0,
        f"{prefix}_median": float(series.median()),
        f"{prefix}_p90": float(series.quantile(0.90)),
        f"{prefix}_min": float(series.min()),
        f"{prefix}_max": float(series.max()),
    }


def safe_get(seg, key):
    import pandas as pd

    if seg is None or key not in seg or pd.isna(seg[key]):
        return None

    return seg[key]