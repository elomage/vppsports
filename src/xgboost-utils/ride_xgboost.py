from __future__ import annotations
import warnings
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import xgboost as xgb
import shap
import seaborn as sns
from scipy.stats import spearmanr
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import LeaveOneOut

from ANALYSIS_TOOL.segmentation import segment_ride
from XGBOOST.features.segment_features import build_segment_dataset
from XGBOOST.features.ride_features import build_ride_dataset

warnings.filterwarnings("ignore", category=UserWarning)
plt.rcParams["figure.dpi"] = 120


NON_FEATURE_COLS = {
    "ride_id", "source_ride_id", "rider_id", "track_id", "is_augmented",
    "target_time", "target_residual", "target_z", "track_mean", "track_std",
    "_perm_target", "perf_class", "perf_binary",
    "seg_idx", "kind", "duration", "delta_duration",
    "n_segments", "n_curves", "n_lefts", "n_rights", "n_straights",
    "time_since_start", "frac_ride_elapsed", "total_time", "ride_duration",
    "index", "Unnamed: 0", "timestamp", "count",
}

LEAK_SUBSTRINGS = ["duration", "elapsed", "total_time", "ride_time"]

XGB_PARAMS = dict(
    n_estimators=30,
    max_depth=2,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.9,
    reg_alpha=0.3,
    reg_lambda=1.5,
    min_child_weight=2,
    gamma=0.1,
    objective="reg:squarederror",
)

TARGET_CORR_THRESHOLD = 0.99
INTER_CORR_THRESHOLD = 0.80
TARGET_N_FEATURES = 5
N_PERMUTATIONS = 1

MIN_RIDES_PER_TRACK = 3
INCLUDE_TRACKS = {"cortina", "whistler", "sigulda", "undef"}


def _autoscale_total_time(raw_diff):
    if raw_diff <= 0:
        return 0.0
    for divisor in [1.0, 1e3, 1e6, 1e9]:
        scaled = raw_diff / divisor
        if 10.0 <= scaled <= 300.0:
            return scaled
    return raw_diff


def _load_txt(path):
    try:
        data = np.loadtxt(path, delimiter=",", skiprows=1)
        if data.size == 0:
            return None
        return data.reshape(-1, 4) if data.ndim == 1 else data
    except Exception:
        try:
            return np.loadtxt(path, delimiter=",")
        except Exception:
            return None


def discover_rides(track_root, track_id):
    track_root = Path(track_root)
    accel_dir = track_root / "accel"
    if not accel_dir.is_dir():
        return []
    rides = []
    for ap in sorted(accel_dir.glob("*.txt")):
        acc = _load_txt(ap)
        if acc is None:
            continue
        gp = track_root / "gyro" / ap.name
        gyro = _load_txt(gp) if gp.is_file() else None
        raw_diff = float(acc[-1, 0] - acc[0, 0])
        rides.append({
            "ride_id": f"{track_id}__{ap.stem}",
            "rider_id": ap.stem.split("_")[0],
            "track_id": track_id,
            "acc": acc,
            "gyro": gyro,
            "total_time": _autoscale_total_time(raw_diff),
            "target_time": _autoscale_total_time(raw_diff),
        })
    return rides


def build_full_dataset(seg_df, per_ride_inputs, include_tracks):
    frames = []
    for r in per_ride_inputs:
        if r["track_id"] not in include_tracks:
            continue
        sdf = seg_df[seg_df["ride_id"] == r["ride_id"]] if seg_df is not None else None
        rdf = build_ride_dataset(
            sdf, r["total_time"], r["ride_id"],
            acc=r.get("acc"), gyro=r.get("gyro")
        )
        if rdf.empty:
            continue
        rdf["track_id"] = r["track_id"]
        rdf["rider_id"] = r["rider_id"]
        rdf["target_time"] = r["target_time"]
        frames.append(rdf)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def drop_correlated_features(X, threshold=INTER_CORR_THRESHOLD):
    corr = X.corr().abs()
    upper = corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool))
    to_drop = set()
    for col in upper.columns:
        if col in to_drop:
            continue
        for c in upper.index:
            if c == col or c in to_drop:
                continue
            if upper.loc[c, col] > threshold:
                if X[col].std() >= X[c].std():
                    to_drop.add(c)
                else:
                    to_drop.add(col)
                    break
    return [c for c in X.columns if c not in to_drop]


def _center_features_by_track(ride_df, feature_cols):
    centered = ride_df[feature_cols].copy()
    for t, g in ride_df.groupby("track_id"):
        means = ride_df.loc[g.index, feature_cols].mean()
        centered.loc[g.index] = ride_df.loc[g.index, feature_cols] - means
    return centered


def _compute_track_stats(df, target_col="target_time"):
    stats = {}
    for t, g in df.groupby("track_id"):
        mu = float(g[target_col].mean())
        sd = float(g[target_col].std())
        if pd.isna(sd) or sd < 1e-9:
            sd = 1.0
        stats[t] = (mu, sd)
    return stats


def select_features(ride_df, target_col="target_z"):
    if target_col not in ride_df.columns:
        return []
    target_std = ride_df[target_col].std()
    if pd.isna(target_std) or target_std < 1e-9:
        return []

    candidate_cols = [
        c for c in ride_df.columns
        if c not in NON_FEATURE_COLS
           and not any(sub in c.lower() for sub in LEAK_SUBSTRINGS)
           and pd.api.types.is_numeric_dtype(ride_df[c])
    ]

    centered = _center_features_by_track(ride_df, candidate_cols)
    centered = centered.fillna(centered.median())

    target_filtered = []
    y = ride_df[target_col]
    for c in candidate_cols:
        col_std = centered[c].std()
        if pd.isna(col_std) or col_std < 1e-9:
            continue
        correlation = abs(centered[c].corr(y, method="spearman"))
        if pd.isna(correlation) or correlation >= TARGET_CORR_THRESHOLD:
            continue
        target_filtered.append(c)

    if not target_filtered:
        return []

    X = centered[target_filtered].loc[:, centered[target_filtered].std() > 1e-9]
    kept = drop_correlated_features(X, threshold=INTER_CORR_THRESHOLD)

    if len(kept) > TARGET_N_FEATURES:
        corrs = X[kept].apply(lambda col: abs(col.corr(y, method="spearman")))
        kept = corrs.sort_values(ascending=False).head(TARGET_N_FEATURES).index.tolist()

    return kept


def make_xgb():
    return xgb.XGBRegressor(**XGB_PARAMS)


def loo_predict_z(ride_df):
    pred_z, actual_z = [], []
    pred_ms, actual_ms = [], []
    loo = LeaveOneOut()
    indices = np.arange(len(ride_df))

    for tr_idx, te_idx in loo.split(indices):
        train_df = ride_df.iloc[tr_idx].reset_index(drop=True)
        test_df = ride_df.iloc[te_idx].reset_index(drop=True)
        test_track = test_df["track_id"].iloc[0]
        test_time = float(test_df["target_time"].iloc[0])

        train_stats = _compute_track_stats(train_df, "target_time")
        train_df["target_z"] = train_df.apply(
            lambda r: (r["target_time"] - train_stats[r["track_id"]][0])
                      / train_stats[r["track_id"]][1],
            axis=1
        )

        if test_track in train_stats:
            test_mu, test_sd = train_stats[test_track]
        else:
            test_mu = float(train_df["target_time"].mean())
            test_sd = float(train_df["target_time"].std()) or 1.0
        actual_z_val = (test_time - test_mu) / test_sd

        feats = select_features(train_df, target_col="target_z")
        if not feats:
            pred_z_val = 0.0
        else:
            train_centered = _center_features_by_track(train_df, feats)
            test_track_feat_means = train_df[train_df["track_id"] == test_track][feats].mean()
            test_centered = test_df[feats].fillna(test_track_feat_means) - test_track_feat_means

            train_medians = train_centered.median()
            train_means = train_centered.mean()
            train_stds = train_centered.std().replace(0, 1)
            X_tr = (train_centered.fillna(train_medians) - train_means) / train_stds
            X_te = (test_centered - train_means) / train_stds
            y_tr = train_df["target_z"]

            model = make_xgb().fit(X_tr, y_tr)
            pred_z_val = float(model.predict(X_te)[0])

        pred_time = test_mu + pred_z_val * test_sd

        pred_z.append(pred_z_val)
        actual_z.append(actual_z_val)
        pred_ms.append(pred_time)
        actual_ms.append(test_time)

    return (np.array(pred_z), np.array(actual_z),
            np.array(pred_ms), np.array(actual_ms))

def get_bilingual_labels(feature_names):
    from XGBOOST.features.features_naming import bilingual_label
    return [bilingual_label(name) for name in feature_names]


def permutation_test_z(ride_df, observed_mae_z, observed_rho, n_perms=N_PERMUTATIONS):
    perm_maes, perm_rhos = [], []
    for seed in range(n_perms):
        rng = np.random.RandomState(seed)
        permuted = ride_df.copy()
        for t, g in ride_df.groupby("track_id"):
            permuted.loc[g.index, "target_time"] = rng.permutation(g["target_time"].values)
        try:
            pz, az, _, _ = loo_predict_z(permuted)
            perm_maes.append(mean_absolute_error(az, pz))
            rho, _ = spearmanr(pz, az)
            perm_rhos.append(float(rho) if not np.isnan(rho) else 0.0)
        except Exception:
            continue
    perm_maes = np.array(perm_maes)
    perm_rhos = np.array(perm_rhos)
    p_mae = float(np.mean(perm_maes <= observed_mae_z))
    p_rho = float(np.mean(perm_rhos >= observed_rho))
    return perm_maes, perm_rhos, p_mae, p_rho

def plot_shap_interaction(model, X, out_path, title, title_lv=None, max_features=5):
    model.get_booster().feature_names = list(X.columns)
    explainer = shap.TreeExplainer(model)
    interaction_values = explainer.shap_interaction_values(X)

    mean_interactions = np.abs(interaction_values).mean(axis=0)
    np.fill_diagonal(mean_interactions, 0)

    importance = mean_interactions.sum(axis=0)
    top_idx = np.argsort(importance)[-max_features:][::-1]

    sub_matrix = mean_interactions[np.ix_(top_idx, top_idx)]
    sub_labels_en = [X.columns[i] for i in top_idx]
    sub_labels_bilingual = get_bilingual_labels(sub_labels_en)

    fig, ax = plt.subplots(figsize=(12, 10))
    sns.heatmap(
        sub_matrix,
        xticklabels=sub_labels_bilingual,
        yticklabels=sub_labels_bilingual,
        cmap="viridis",
        annot=True,
        fmt=".3f",
        cbar_kws={"label": "Vidējā |SHAP mijiedarbība|"},
        ax=ax,
    )

    full_title = f"{title}"
    if title_lv:
        full_title = f"{title} / {title_lv}"
    ax.set_title(full_title)
    plt.xticks(rotation=45, ha="right")
    plt.yticks(rotation=0)
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight", dpi=120)
    plt.close()
    return mean_interactions


def run_shap_bar(model, X, out_path, title, title_lv=None, color="#FF1493"):
    model.get_booster().feature_names = list(X.columns)
    sv = shap.TreeExplainer(model).shap_values(X)
    mean_abs_shap = np.abs(sv).mean(axis=0)

    order = np.argsort(mean_abs_shap)
    sorted_labels_en = [X.columns[i] for i in order]
    sorted_labels_bilingual = get_bilingual_labels(sorted_labels_en)
    sorted_values = mean_abs_shap[order]

    fig_height = max(8, 0.55 * len(X.columns))
    plt.figure(figsize=(16, fig_height))
    bars = plt.barh(sorted_labels_bilingual, sorted_values, color=color)

    for bar, val in zip(bars, sorted_values):
        plt.text(
            val + max(sorted_values) * 0.005,
            bar.get_y() + bar.get_height() / 2,
            f"{val:.2f}",
            va="center", fontsize=9,
            )

    full_title = f"{title}"
    if title_lv:
        full_title = f"{title} / {title_lv}"

    plt.xlabel("Vidējā SHAP vērtība")
    plt.ylabel("Metrika")
    plt.title(full_title)
    plt.grid(axis="x", linestyle="--", alpha=0.4)
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight", dpi=150)
    plt.close()


def run_shap_summary(model, X, out_path, title, title_lv=None):
    model.get_booster().feature_names = list(X.columns)
    sv = shap.TreeExplainer(model).shap_values(X)

    X_renamed = X.copy()
    X_renamed.columns = get_bilingual_labels(list(X.columns))

    shap.summary_plot(
        sv, X_renamed,
        show=False,
        plot_size=(10, max(5, 0.7 * len(X.columns))),
    )

    fig = plt.gcf()
    ax = plt.gca()

    ax.tick_params(axis="both", labelsize=13)
    ax.set_xlabel("SHAP vērtība (ietekme uz modeļa prognozi)", fontsize=15)

    for cbar_ax in fig.axes:
        ylabel = cbar_ax.get_ylabel()
        if ylabel == "Feature value":
            cbar_ax.set_ylabel("Metrikas ietekme", fontsize=14)

        yticklabels = [t.get_text() for t in cbar_ax.get_yticklabels()]
        if "High" in yticklabels or "Low" in yticklabels:
            new_labels = []
            for lbl in yticklabels:
                if lbl == "High":
                    new_labels.append("Augsta")
                elif lbl == "Low":
                    new_labels.append("Zema")
                else:
                    new_labels.append(lbl)
            cbar_ax.set_yticklabels(new_labels, fontsize=13)

    full_title = f"{title}"
    if title_lv:
        full_title = f"{title} / {title_lv}"
    plt.title(full_title, fontsize=16)
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight", dpi=200)
    plt.close()
    return sv


def plot_correlation_matrix(X, out_path, title, title_lv=None, method="spearman", figsize=(12, 10)):
    corr = X.corr(method=method)

    bilingual_labels = get_bilingual_labels(list(X.columns))

    fig, ax = plt.subplots(figsize=figsize)
    sns.heatmap(
        corr,
        cmap="RdBu_r",
        center=0,
        vmin=-1, vmax=1,
        square=True,
        linewidths=0.3,
        xticklabels=bilingual_labels,
        yticklabels=bilingual_labels,
        cbar_kws={"shrink": 0.7, "label": f"{method.title()} korelācija"},
        ax=ax,
    )

    full_title = f"{title}"
    if title_lv:
        full_title = f"{title} / {title_lv}"
    ax.set_title(full_title)
    plt.xticks(rotation=45, ha="right")
    plt.yticks(rotation=0)
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight", dpi=120)
    plt.close()
    return corr


def report_high_correlations(corr_matrix, threshold=0.85, top_n=30):
    pairs = []
    cols = corr_matrix.columns.tolist()
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            r = corr_matrix.iloc[i, j]
            if abs(r) >= threshold:
                pairs.append((cols[i], cols[j], r))
    pairs.sort(key=lambda x: abs(x[2]), reverse=True)
    df = pd.DataFrame(pairs[:top_n], columns=["feature_1", "feature_2", "correlation"])
    return df


def feature_target_correlation(X, y, method="spearman"):
    results = []
    for col in X.columns:
        s = X[col].dropna()
        y_aligned = y.loc[s.index]
        if len(s) < 5 or s.std() < 1e-9:
            continue
        if method == "spearman":
            r = s.corr(y_aligned, method="spearman")
        else:
            r = s.corr(y_aligned, method="pearson")
        results.append({"feature": col, "correlation": r})
    df = pd.DataFrame(results).sort_values("correlation", key=abs, ascending=False)
    return df


def plot_pred_vs_actual_z(pred_z, actual_z, tracks, per_track_stats, out_path):
    plt.figure(figsize=(10, 10))
    palette = sns.color_palette("husl", len(set(tracks)))
    track_to_color = dict(zip(sorted(set(tracks)), palette))

    track_names_lv = {
        "cortina": "Kortīna",
        "whistler": "Vistlera",
        "sigulda": "Sigulda",
        "undef": "Nedefinēta",
    }

    for t in sorted(set(tracks)):
        mask = np.array(tracks) == t
        stats = per_track_stats.get(t, {})
        t_lv = track_names_lv.get(t, t)
        label = (f"{t}/{t_lv} (n={mask.sum()}, ρ={stats.get('rho', float('nan')):+.2f}, "
                 f"MAE={stats.get('mae_ms', 0):.0f}ms)")
        plt.scatter(actual_z[mask], pred_z[mask],
                    s=80, alpha=0.8,
                    color=track_to_color[t], edgecolor="black", label=label)

    all_vals = np.concatenate([actual_z, pred_z])
    lo, hi = all_vals.min() - 0.3, all_vals.max() + 0.3
    plt.plot([lo, hi], [lo, hi], "k--", alpha=0.4, label="y=x")
    plt.axhline(0, color="gray", alpha=0.3, linestyle=":")
    plt.axvline(0, color="gray", alpha=0.3, linestyle=":")

    plt.xlabel("Actual time (z-score) / Faktiskais laiks (z-rādītājs)")
    plt.ylabel("Predicted time (z-score) / Prognozētais laiks (z-rādītājs)")
    plt.title("Within-track LOO predictions / Trases ietvaros LOO prognozes")
    plt.legend(loc="best", fontsize=9)
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight", dpi=150)
    plt.close()



def train_ride_models(seg_df, per_ride_inputs, output_dir="ride_outputs"):
    out_dir = Path(output_dir)
    out_dir.mkdir(exist_ok=True, parents=True)

    ride_df = build_full_dataset(seg_df, per_ride_inputs, INCLUDE_TRACKS)
    if ride_df.empty:
        print("No rides retained.")
        return None

    track_counts = ride_df.groupby("track_id").size()
    underpowered = track_counts[track_counts < MIN_RIDES_PER_TRACK].index.tolist()
    if underpowered:
        print(f"Dropping underpowered tracks (n < {MIN_RIDES_PER_TRACK}): {underpowered}")
        ride_df = ride_df[~ride_df["track_id"].isin(underpowered)].reset_index(drop=True)

    if ride_df.empty:
        print("No tracks have enough rides.")
        return None

    n = len(ride_df)
    print(f"\nRides retained: {n}   Tracks: {sorted(ride_df['track_id'].unique())}")
    print("Per-track:")
    for t, sub in ride_df.groupby("track_id"):
        spread_ms = (sub['target_time'].max() - sub['target_time'].min()) * 1000
        std_ms = sub['target_time'].std() * 1000
        print(f"  {t:10s}  n={len(sub):2d}   "
              f"mean={sub['target_time'].mean():.3f}s   "
              f"std={std_ms:.0f}ms   range={spread_ms:.0f}ms")

    pred_z, actual_z, pred_ms, actual_ms = loo_predict_z(ride_df)

    observed_mae_z = mean_absolute_error(actual_z, pred_z)
    observed_mae_ms = mean_absolute_error(actual_ms, pred_ms)
    observed_rho, _ = spearmanr(pred_z, actual_z)

    baseline_mae_z = mean_absolute_error(actual_z, np.zeros_like(actual_z))
    track_mean_baseline_ms = []
    track_means_full = ride_df.groupby("track_id")["target_time"].mean().to_dict()
    for i, t in enumerate(ride_df["track_id"].values):
        track_mean_baseline_ms.append(track_means_full[t])
    baseline_mae_ms = mean_absolute_error(actual_ms, track_mean_baseline_ms)

    print(f"\n=== Overall within-track LOO performance (z-scored target) ===")
    print(f"Model MAE (z-units):    {observed_mae_z:.3f}σ")
    print(f"Baseline MAE (z-units): {baseline_mae_z:.3f}σ")
    print(f"Improvement:            {(1 - observed_mae_z/baseline_mae_z)*100:+.1f}%")
    print(f"Spearman ρ:             {float(observed_rho):+.3f}")
    print(f"\nAs back-transformed ms (each ride uses its track's std):")
    print(f"Model MAE:    {observed_mae_ms*1000:.1f}ms")
    print(f"Baseline MAE: {baseline_mae_ms*1000:.1f}ms")

    print("\n=== Per-track breakdown ===")
    tracks_arr = ride_df["track_id"].values
    per_track_stats = {}
    for t in sorted(set(tracks_arr)):
        mask = tracks_arr == t
        if mask.sum() < 2:
            continue
        track_mae_z = mean_absolute_error(actual_z[mask], pred_z[mask])
        track_mae_ms = mean_absolute_error(actual_ms[mask], pred_ms[mask])
        track_rho, track_p = spearmanr(actual_z[mask], pred_z[mask])
        track_range = (ride_df.loc[mask, "target_time"].max() -
                       ride_df.loc[mask, "target_time"].min())
        track_baseline_ms = mean_absolute_error(
            actual_ms[mask], [track_means_full[t]] * mask.sum()
        )
        improvement_ms_pct = ((1 - track_mae_ms / track_baseline_ms) * 100
                              if track_baseline_ms > 0 else 0)
        per_track_stats[t] = {"mae_z": track_mae_z,
                              "mae_ms": track_mae_ms * 1000,
                              "baseline_ms": track_baseline_ms * 1000,
                              "rho": float(track_rho),
                              "p": float(track_p) if not np.isnan(track_p) else 1.0,
                              "range_ms": track_range * 1000,
                              "improvement_pct": improvement_ms_pct}
        sig = "***" if track_p < 0.05 else ("*" if track_p < 0.10 else "")
        print(f"  {t:10s}  n={mask.sum():2d}  "
              f"MAE={track_mae_z:.3f}σ ({track_mae_ms*1000:6.1f}ms)  "
              f"baseline={track_baseline_ms*1000:.0f}ms ({improvement_ms_pct:+.1f}%)  "
              f"ρ={float(track_rho):+.3f} p={float(track_p):.3f}{sig}")

    print(f"\nRunning permutation test ({N_PERMUTATIONS} permutations, within-track shuffle)...")
    perm_maes, perm_rhos, p_mae, p_rho = permutation_test_z(
        ride_df, observed_mae_z, float(observed_rho)
    )
    mae_lower, mae_upper = np.percentile(perm_maes, [2.5, 97.5])
    rho_lower, rho_upper = np.percentile(perm_rhos, [2.5, 97.5])

    print(f"\n=== Permutation test (within-track shuffle, z-scored) ===")
    print(f"Observed MAE: {observed_mae_z:.3f}σ   "
          f"perm CI [{mae_lower:.3f}, {mae_upper:.3f}]   p = {p_mae:.3f}")
    print(f"Observed ρ:   {float(observed_rho):+.3f}   "
          f"perm CI [{rho_lower:+.3f}, {rho_upper:+.3f}]   p = {p_rho:.3f}")

    passes_mae = p_mae < 0.05
    passes_rho = p_rho < 0.05
    passes = passes_mae or passes_rho
    if passes:
        flags = []
        if passes_mae: flags.append("MAE")
        if passes_rho: flags.append("rank")
        print(f"VERDICT: WITHIN-TRACK SIGNAL above noise ({'+'.join(flags)}). Proceeding to SHAP.")
    else:
        print("VERDICT: No within-track signal separable from noise.")

    plot_pred_vs_actual_z(pred_z, actual_z, ride_df["track_id"].tolist(),
                          per_track_stats, out_dir / "pred_vs_actual.png")


    if not passes:
        print("\nGate not passed. Skipping SHAP plots.")
        return None

    train_stats = _compute_track_stats(ride_df, "target_time")
    ride_df["target_z"] = ride_df.apply(
        lambda r: (r["target_time"] - train_stats[r["track_id"]][0])
                  / train_stats[r["track_id"]][1],
        axis=1
    )

    feats = select_features(ride_df, target_col="target_z")
    if not feats:
        print("No features survived final selection.")
        return None

    X_raw = _center_features_by_track(ride_df, feats)
    X_raw = X_raw.fillna(X_raw.median())
    means = X_raw.mean()
    stds = X_raw.std().replace(0, 1)
    X = (X_raw - means) / stds
    y = ride_df["target_z"]

    print(f"\nFinal features (within-track centered, {len(feats)}):")
    for f in feats:
        rho_f, p_f = spearmanr(X_raw[f], y)
        print(f"  - {f}   (within-track ρ = {float(rho_f):+.3f}, p = {float(p_f):.3f})")

    final_model = make_xgb().fit(X, y)

    run_shap_bar(
        final_model, X,
        out_dir / "ride_shap_bar.png",
        f"Vidējā SHAP vērtības - augstākās {len(feats)} metrikas",
        )

    run_shap_summary(
        final_model, X,
        out_dir / "ride_shap_summary.png",
    f"Brauciena snieguma faktori - augstākās {len(feats)} metrikas",
    )

    plot_correlation_matrix(
        X_raw, out_dir / "ride_correlation.png",
    f"Metriku korelācijas matrica - augstākās {len(feats)}",
        method="spearman",
        figsize=(12, 10),
    )

    plot_shap_interaction(
        final_model, X,
        out_path=out_dir / "ride_shap_interactions.png",
        title="SHAP mijiedarbība - braucienu metrikas",
        max_features=5,
    )

    corr_full = X_raw.corr(method="spearman")
    high_corr_pairs = report_high_correlations(corr_full, threshold=0.85, top_n=30)
    print("\n--- Highly correlated feature pairs (|r| >= 0.85) ---")
    if not high_corr_pairs.empty:
        print(high_corr_pairs.to_string(index=False))

    target_corr = feature_target_correlation(X_raw, y, method="spearman")
    print("\n--- Top 15 feature-target correlations (Spearman) ---")
    print(target_corr.head(15)[["feature", "correlation"]].to_string(index=False))
    target_corr.to_csv(out_dir / "feature_target_correlations.csv", index=False)

    print(f"\nSaved plots to {out_dir}/")
    return final_model


if __name__ == "__main__":
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    TRACK_DIRS = {
        "cortina":  PROJECT_ROOT / "DATA" / "A" / "trimmed_rides_cortina",
        "whistler": PROJECT_ROOT / "DATA" / "A" / "trimmed_rides_whistler",
        "undef":    PROJECT_ROOT / "DATA" / "A" / "trimmed_rides_undef",
        "sigulda":  PROJECT_ROOT / "DATA" / "A" / "trimmed_rides_sigulda",
    }

    all_rides = []
    for tid, root in TRACK_DIRS.items():
        if root.is_dir():
            all_rides.extend(discover_rides(root, tid))

    print(f"Discovered {len(all_rides)} rides")

    if all_rides:
        seg_frames, inputs = [], []
        for r in all_rides:
            seg_obj = segment_ride(r["acc"], r["gyro"])
            sdf = build_segment_dataset(r["acc"], r["gyro"], seg_obj, r["ride_id"])
            seg_frames.append(sdf)
            inputs.append(r)

        seg_df = pd.concat(seg_frames) if seg_frames else None
        train_ride_models(seg_df, inputs, output_dir="../DOCS/ride_results")