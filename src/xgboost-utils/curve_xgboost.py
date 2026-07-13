from __future__ import annotations
import copy
import warnings
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import xgboost as xgb
import shap
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import GroupKFold
from ANALYSIS_TOOL.segmentation import segment_ride
from XGBOOST.features.curve_features import build_curve_dataset
from XGBOOST.features.segment_features import build_segment_dataset
import seaborn as sns
from XGBOOST.features.features_naming import FEATURE_FULL_NAMES
from XGBOOST.features.features_naming import FEATURE_FULL_NAMES_LV

warnings.filterwarnings("ignore", category=UserWarning)
plt.rcParams["figure.dpi"] = 120
plt.rcParams.update({
    "font.size": 14,
    "axes.titlesize": 16,
    "axes.labelsize": 15,
    "xtick.labelsize": 13,
    "ytick.labelsize": 13,
    "legend.fontsize": 12,
    "figure.titlesize": 17,
})

NON_FEATURE_COLS = {
    "ride_id", "source_ride_id", "rider_id", "track_id", "is_augmented",
    "seg_idx", "kind", "prev_kind",
    "duration", "dur_z", "dur_z_source", "prev_duration",
    "is_curve", "is_straight", "is_start",
    "time_since_start", "frac_ride_elapsed",
    "ride_position",
    "index", "Unnamed: 0", "timestamp",
}

LEAK_SUBSTRINGS = ["duration", "integral", "elapsed", "_dur"]

PHASE_PREFIXES = ("entry_", "apex_", "exit_")

PHASE_PREFIX_LABELS = {
    "entry_": {"en": "Entry: ", "lv": "Ieeja: "},
    "apex_":  {"en": "Apex: ",  "lv": "Apekss: "},
    "exit_":  {"en": "Exit: ",  "lv": "Izeja: "},
}

PHASE_DURATION_LEAK_THRESHOLD = 0.5

COLLINEARITY_THRESHOLD = 0.95

CV_PARAMS = dict(n_estimators=80, max_depth=3, learning_rate=0.05, subsample=0.8)
FINAL_PARAMS = dict(n_estimators=150, max_depth=3, learning_rate=0.05, subsample=0.8)
TOP_K_FEATURES = 12
BOOTSTRAP_ROUNDS = 50
BOOTSTRAP_GROUP_FRAC = 0.8
N_SHUFFLE_REPEATS = 2


def get_human_label(col: str, lang: str = "lv") -> str:
    names = FEATURE_FULL_NAMES if lang == "en" else FEATURE_FULL_NAMES_LV
    prev_prefix = ""
    phase_prefix = ""
    clean = col

    if clean.startswith("prev_straight_"):
        prev_prefix = "Prev Straight: " if lang == "en" else "Iepr. taisne: "
        clean = clean[len("prev_straight_"):]
    elif clean.startswith("prev_curve_"):
        prev_prefix = "Prev Curve: " if lang == "en" else "Iepr. līkums: "
        clean = clean[len("prev_curve_"):]
    elif clean.startswith("prev_"):
        prev_prefix = "Previous Segment: " if lang == "en" else "Iepriekšējais segments: "
        clean = clean[len("prev_"):]

    for p in PHASE_PREFIXES:
        if clean.startswith(p):
            phase_prefix = PHASE_PREFIX_LABELS[p][lang]
            clean = clean[len(p):]
            break

    if clean in names:
        return f"{prev_prefix}{phase_prefix}{names[clean]}"
    return f"{prev_prefix}{phase_prefix}{clean}"


def _localize_shap_summary(fig, lang="lv"):
    if lang != "lv":
        return
    ax = plt.gca()
    ax.set_xlabel("SHAP vērtība (ietekme uz modeļa prognozi)", fontsize=15)
    ax.tick_params(axis="both", labelsize=13)

    for cbar_ax in fig.axes:
        ylabel = cbar_ax.get_ylabel()
        if ylabel == "Feature value":
            cbar_ax.set_ylabel("Metrikas vērtība", fontsize=14)

        yticklabels = [t.get_text() for t in cbar_ax.get_yticklabels()]
        if "High" in yticklabels or "Low" in yticklabels:
            new_labels = []
            for lbl in yticklabels:
                if lbl == "High":
                    new_labels.append("Augsts")
                elif lbl == "Low":
                    new_labels.append("Zems")
                else:
                    new_labels.append(lbl)
            cbar_ax.set_yticklabels(new_labels, fontsize=13)


def _load_txt(path: Path):
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


def audit_phase_features(curve_df, threshold=PHASE_DURATION_LEAK_THRESHOLD, verbose=True):
    if "duration" not in curve_df.columns:
        return [], pd.DataFrame()
    phase_cols = [c for c in curve_df.columns if c.startswith(PHASE_PREFIXES)]
    rows = []
    drops = []
    dur = curve_df["duration"]
    for c in phase_cols:
        if not pd.api.types.is_numeric_dtype(curve_df[c]):
            continue
        r = curve_df[c].corr(dur, method="spearman")
        rows.append({"feature": c, "spearman_with_duration": r})
        if pd.notna(r) and abs(r) >= threshold:
            drops.append(c)
    audit_df = pd.DataFrame(rows).sort_values(
        "spearman_with_duration", key=lambda s: s.abs(), ascending=False
    )
    if verbose:
        print(f"\n--- Phase Feature Duration-Leak Audit (|r| >= {threshold}) ---")
        if drops:
            print(f"Dropping {len(drops)} phase features that encode duration:")
            print(audit_df[audit_df["feature"].isin(drops)].to_string(index=False))
        else:
            print("No phase features exceed the duration-leak threshold.")
    return drops, audit_df


def _feature_keep_priority(col: str) -> tuple:
    has_phase = col.startswith(PHASE_PREFIXES)
    has_prev = col.startswith("prev_")
    derived_tokens = ("g_total", "g_lat_vert", "_p95", "_iqr")
    is_derived = any(tok in col for tok in derived_tokens)
    return (int(has_prev), int(has_phase), int(is_derived), len(col), col)


def prune_collinear(df, feats, threshold=COLLINEARITY_THRESHOLD, verbose=True):
    if len(feats) < 2:
        return list(feats), []
    sub = df[feats].fillna(df[feats].median(numeric_only=True))
    corr = sub.corr(method="spearman").abs()
    ordered = sorted(feats, key=_feature_keep_priority)
    kept = []
    drops = []
    for col in ordered:
        conflict = False
        chosen_rep = None
        for k in kept:
            r = corr.loc[col, k]
            if pd.notna(r) and r >= threshold:
                conflict = True
                chosen_rep = k
                break
        if conflict:
            drops.append((col, chosen_rep, float(corr.loc[col, chosen_rep])))
        else:
            kept.append(col)
    if verbose:
        print(f"\n--- Collinearity Pruning (|r| >= {threshold}) ---")
        print(f"Kept {len(kept)} of {len(feats)} features ({len(drops)} dropped)")
        if drops:
            drop_df = pd.DataFrame(drops, columns=["dropped", "kept_in_favor_of", "abs_corr"])
            drop_df["dropped_human"] = drop_df["dropped"].map(get_human_label)
            drop_df["kept_human"] = drop_df["kept_in_favor_of"].map(get_human_label)
            print(drop_df[["dropped_human", "kept_human", "abs_corr"]].to_string(index=False))
    return kept, drops


def select_features_no_target_leak(curve_df, extra_drops=()):
    extra_drops = set(extra_drops)
    feats = []
    for c in curve_df.columns:
        if c in NON_FEATURE_COLS or c in extra_drops:
            continue
        if any(sub in c.lower() for sub in LEAK_SUBSTRINGS):
            continue
        if not pd.api.types.is_numeric_dtype(curve_df[c]):
            continue
        if curve_df[c].nunique(dropna=True) <= 1:
            continue
        feats.append(c)
    return feats


def _impute_fold(X_train, X_val):
    medians = X_train.median(numeric_only=True)
    return X_train.fillna(medians), X_val.fillna(medians)


def grouped_cv_mae(X, y, groups, params, n_splits=5, shuffle_seeds=None):
    n_splits = min(n_splits, groups.nunique())
    if n_splits < 2:
        return np.array([np.nan])
    gkf = GroupKFold(n_splits=n_splits)

    if shuffle_seeds is None:
        scores = []
        for tr_idx, va_idx in gkf.split(X, y, groups):
            Xtr, Xva = X.iloc[tr_idx], X.iloc[va_idx]
            ytr, yva = y.iloc[tr_idx], y.iloc[va_idx]
            Xtr, Xva = _impute_fold(Xtr, Xva)
            m = xgb.XGBRegressor(**params)
            m.fit(Xtr, ytr)
            scores.append(mean_absolute_error(yva, m.predict(Xva)))
        return np.array(scores)

    all_scores = []
    for seed in shuffle_seeds:
        y_sh = y.sample(frac=1, random_state=seed).reset_index(drop=True)
        for tr_idx, va_idx in gkf.split(X, y_sh, groups):
            Xtr, Xva = X.iloc[tr_idx], X.iloc[va_idx]
            ytr, yva = y_sh.iloc[tr_idx], y_sh.iloc[va_idx]
            Xtr, Xva = _impute_fold(Xtr, Xva)
            m = xgb.XGBRegressor(**params)
            m.fit(Xtr, ytr)
            all_scores.append(mean_absolute_error(yva, m.predict(Xva)))
    return np.array(all_scores)


def bootstrap_feature_stability(
        X, y, groups,
        n_rounds=BOOTSTRAP_ROUNDS,
        top_k=5,
        group_frac=BOOTSTRAP_GROUP_FRAC,
):
    top_feature_counts = {f: 0 for f in X.columns}
    unique_groups = np.array(sorted(groups.unique()))
    n_sample = max(2, int(round(len(unique_groups) * group_frac)))

    rounds_used = 0
    for seed in range(n_rounds):
        rng = np.random.default_rng(seed)
        sampled = rng.choice(unique_groups, size=n_sample, replace=False)
        held_out = np.setdiff1d(unique_groups, sampled)
        if len(held_out) == 0:
            continue

        tr_mask = groups.isin(sampled).values
        ho_mask = groups.isin(held_out).values

        X_tr, X_ho = X.iloc[tr_mask], X.iloc[ho_mask]
        y_tr = y.iloc[tr_mask]
        X_tr, X_ho = _impute_fold(X_tr, X_ho)

        model = xgb.XGBRegressor(**FINAL_PARAMS)
        model.fit(X_tr, y_tr)
        sv = shap.TreeExplainer(model).shap_values(X_ho)
        importance = np.abs(sv).mean(axis=0)
        top_idx = np.argsort(importance)[-top_k:]
        for i in top_idx:
            top_feature_counts[X.columns[i]] += 1
        rounds_used += 1

    series = pd.Series(top_feature_counts).sort_values(ascending=False)
    series.attrs["rounds_used"] = rounds_used
    return series


def _model_with_human_names(model, raw_cols, lang):
    m = copy.deepcopy(model)
    human_labels = [get_human_label(c, lang) for c in raw_cols]
    m.get_booster().feature_names = human_labels
    return m, human_labels


def run_shap_summary(model, X, out_path, title, lang="lv"):
    human_labels = [get_human_label(c, lang) for c in X.columns]
    X_renamed = X.copy()
    X_renamed.columns = human_labels
    model.get_booster().feature_names = human_labels
    sv = shap.TreeExplainer(model).shap_values(X_renamed)

    plt.figure(figsize=(14, max(6, 0.5 * len(X.columns))))
    shap.summary_plot(sv, X_renamed, show=False)

    fig = plt.gcf()
    _localize_shap_summary(fig, lang=lang)

    plt.title(title, fontsize=16)
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight", dpi=200)
    plt.close()
    return sv


def plot_correlation_matrix(X, out_path, title, method="spearman", figsize=(12, 10), lang="lv"):
    human_labels = [get_human_label(c, lang) for c in X.columns]
    X_renamed = X.copy()
    X_renamed.columns = human_labels
    corr = X_renamed.corr(method=method)

    cbar_label = f"{method.title()} correlation" if lang == "en" else f"{method.title()} korelācija"

    fig, ax = plt.subplots(figsize=figsize)
    sns.heatmap(
        corr,
        cmap="RdBu_r",
        center=0,
        vmin=-1, vmax=1,
        square=True,
        linewidths=0.3,
        annot=True,
        fmt=".2f",
        annot_kws={"size": 11},
        cbar_kws={"shrink": 0.7, "label": cbar_label},
        ax=ax,
    )
    ax.set_title(title, fontsize=16)
    ax.tick_params(axis="x", labelsize=12)
    ax.tick_params(axis="y", labelsize=12)
    plt.xticks(rotation=45, ha="right")
    plt.yticks(rotation=0)
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight", dpi=200)
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
    human_labels = [get_human_label(c) for c in X.columns]
    results = []
    for col, human in zip(X.columns, human_labels):
        s = X[col].dropna()
        y_aligned = y.loc[s.index]
        if len(s) < 5 or s.std() < 1e-9:
            continue
        if method == "spearman":
            r = s.corr(y_aligned, method="spearman")
        else:
            r = s.corr(y_aligned, method="pearson")
        results.append({"feature": human, "raw_name": col, "correlation": r})
    df = pd.DataFrame(results).sort_values("correlation", key=abs, ascending=False)
    return df


def plot_shap_interaction(model, X, out_path, title, max_features=5, lang="lv"):
    human_labels = [get_human_label(c, lang) for c in X.columns]
    model.get_booster().feature_names = human_labels
    explainer = shap.TreeExplainer(model)
    interaction_values = explainer.shap_interaction_values(X)

    mean_interactions = np.abs(interaction_values).mean(axis=0)
    np.fill_diagonal(mean_interactions, 0)

    importance = mean_interactions.sum(axis=0)
    top_idx = np.argsort(importance)[-max_features:][::-1]

    sub_matrix = mean_interactions[np.ix_(top_idx, top_idx)]
    sub_labels = [human_labels[i] for i in top_idx]

    cbar_label = "Mean |SHAP interaction|" if lang == "en" else "Vidējā |SHAP mijiedarbība|"

    fig, ax = plt.subplots(figsize=(14, 12))
    sns.heatmap(
        sub_matrix,
        xticklabels=sub_labels,
        yticklabels=sub_labels,
        cmap="viridis",
        annot=True,
        fmt=".3f",
        annot_kws={"size": 12},
        cbar_kws={"label": cbar_label},
        ax=ax,
    )
    ax.set_title(title, fontsize=16)
    ax.tick_params(axis="x", labelsize=12)
    ax.tick_params(axis="y", labelsize=12)
    plt.xticks(rotation=45, ha="right")
    plt.yticks(rotation=0)
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight", dpi=200)
    plt.close()
    return mean_interactions


def run_shap_bar(model, X, out_path, title, color="#FF1493", lang="lv"):
    human_labels = [get_human_label(c, lang) for c in X.columns]
    model.get_booster().feature_names = human_labels
    sv = shap.TreeExplainer(model).shap_values(X)
    mean_abs_shap = np.abs(sv).mean(axis=0)

    order = np.argsort(mean_abs_shap)
    sorted_labels = [human_labels[i] for i in order]
    sorted_values = mean_abs_shap[order]

    fig_height = max(8, 0.55 * len(X.columns))
    plt.figure(figsize=(18, fig_height))
    bars = plt.barh(sorted_labels, sorted_values, color=color)

    for bar, val in zip(bars, sorted_values):
        plt.text(
            val + max(sorted_values) * 0.005,
            bar.get_y() + bar.get_height() / 2,
            f"{val:.2f}",
            va="center", fontsize=13,
            )

    xlabel = "Mean SHAP value" if lang == "en" else "Vidējā SHAP vērtība"
    ylabel = "Feature" if lang == "en" else "Metrika"
    plt.xlabel(xlabel, fontsize=15)
    plt.ylabel(ylabel, fontsize=15)
    plt.title(title, fontsize=16)
    plt.xticks(fontsize=13)
    plt.yticks(fontsize=13)
    plt.grid(axis="x", linestyle="--", alpha=0.4)
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight", dpi=200)
    plt.close()


def train_curve_model(curve_df, output_dir="curve_outputs"):
    out_dir = Path(output_dir)
    out_dir.mkdir(exist_ok=True, parents=True)

    curve_df = curve_df.dropna(subset=["dur_z"]).reset_index(drop=True)

    if "dur_z_source" in curve_df.columns:
        src_counts = curve_df["dur_z_source"].value_counts()
        print("\n--- dur_z source breakdown ---")
        print(src_counts.to_string())

    leaky_phase, phase_audit = audit_phase_features(curve_df)

    candidate_feats = select_features_no_target_leak(curve_df, extra_drops=leaky_phase)
    final_feats, pruned = prune_collinear(curve_df, candidate_feats, threshold=COLLINEARITY_THRESHOLD)

    X_full = curve_df[final_feats]
    y = curve_df["dur_z"]
    ride_groups = curve_df["ride_id"]
    track_groups = curve_df["track_id"]

    print(f"\n--- Curve-Level Dataset ---")
    print(f"Total curves: {len(curve_df)}")
    print(f"Unique rides: {ride_groups.nunique()}")
    print(f"Unique tracks: {track_groups.nunique()}")
    print(f"Curves per ride (mean): {len(curve_df) / ride_groups.nunique():.1f}")
    phase_feats = [c for c in final_feats if c.startswith(PHASE_PREFIXES)]
    print(f"Phase features retained: {len(phase_feats)} (dropped {len(leaky_phase)} as duration-leaking)")
    print(f"Final feature count after collinearity pruning: {len(final_feats)}")

    reg_scores = grouped_cv_mae(X_full, y, ride_groups, CV_PARAMS, n_splits=5)

    shuffle_seeds = list(range(N_SHUFFLE_REPEATS))
    shuffle_scores = grouped_cv_mae(
        X_full, y, ride_groups, CV_PARAMS, n_splits=5, shuffle_seeds=shuffle_seeds
    )

    n_track_groups = track_groups.nunique()
    if n_track_groups >= 2:
        track_scores = grouped_cv_mae(
            X_full, y, track_groups, CV_PARAMS, n_splits=min(n_track_groups, 4)
        )
    else:
        track_scores = None

    X_full_imp = X_full.fillna(X_full.median(numeric_only=True))
    final_full = xgb.XGBRegressor(**FINAL_PARAMS).fit(X_full_imp, y)
    in_sample = mean_absolute_error(y, final_full.predict(X_full_imp))

    print(f"\n--- Full Feature Set ---")
    print(f"Features Used: {len(final_feats)}")
    print(f"Shuffled GroupCV MAE (avg of {N_SHUFFLE_REPEATS} seeds): "
          f"{shuffle_scores.mean():.4f} (+/- {shuffle_scores.std():.4f})")
    print(f"Real GroupCV MAE (ride): {reg_scores.mean():.4f} (+/- {reg_scores.std():.4f})")
    if track_scores is not None:
        print(f"Real GroupCV MAE (track):{track_scores.mean():.4f} (+/- {track_scores.std():.4f})")
    print(f"In-Sample MAE:           {in_sample:.4f}")
    if shuffle_scores.mean() > 1e-9:
        reduction = (1 - reg_scores.mean() / shuffle_scores.mean()) * 100
        print(f"Signal vs Random:        {reduction:.1f}% reduction")

    print(f"\n--- Bootstrap Feature Stability "
          f"({BOOTSTRAP_ROUNDS} rounds, group-subsample @ {BOOTSTRAP_GROUP_FRAC:.0%}, "
          f"SHAP on held-out groups, top-5) ---")
    stability = bootstrap_feature_stability(
        X_full, y, ride_groups,
        n_rounds=BOOTSTRAP_ROUNDS, top_k=5, group_frac=BOOTSTRAP_GROUP_FRAC,
    )
    print(f"Rounds completed: {stability.attrs.get('rounds_used', BOOTSTRAP_ROUNDS)}")
    stability_human = stability.rename(index=lambda c: get_human_label(c))
    print(stability_human.head(25).to_string())

    top_features = stability.head(TOP_K_FEATURES).index.tolist()
    X_top = X_full[top_features]

    reg_scores_top = grouped_cv_mae(X_top, y, ride_groups, CV_PARAMS, n_splits=5)
    X_top_imp = X_top.fillna(X_top.median(numeric_only=True))
    final_top = xgb.XGBRegressor(**FINAL_PARAMS).fit(X_top_imp, y)
    in_sample_top = mean_absolute_error(y, final_top.predict(X_top_imp))

    print(f"\n--- Reduced Feature Set (Top {TOP_K_FEATURES}) ---")
    print(f"Features Used: {len(top_features)}")
    print(f"Real GroupCV MAE (ride): {reg_scores_top.mean():.4f} (+/- {reg_scores_top.std():.4f})")
    print(f"In-Sample MAE:           {in_sample_top:.4f}")

    for lang, suffix in [("en", "en"), ("lv", "lv")]:
        titles = {
            "shap_full": "Curve Performance Drivers - All Features" if lang == "en" else "Virāžu veiktspējas faktori - visas metrikas",
            "shap_top": f"Curve Performance Drivers - Top {TOP_K_FEATURES} Stable Features" if lang == "en" else f"Virāžu veiktspējas faktori - {TOP_K_FEATURES} stabilākās metrikas",
            "bar_full": "Mean SHAP value - All Features" if lang == "en" else "Vidējā SHAP vērtība - visas metrikas",
            "bar_top": f"Mean SHAP value - Top {TOP_K_FEATURES} Stable Features" if lang == "en" else f"Vidējā SHAP vērtība - {TOP_K_FEATURES} stabilākās metrikas",
            "corr_full": "Feature Correlation Matrix - All Features" if lang == "en" else "Metriku korelācijas matrica - visas metrikas",
            "corr_top": f"Feature Correlation Matrix - Top {TOP_K_FEATURES}" if lang == "en" else f"{TOP_K_FEATURES} stabilāko metriku korelācijas matrica",
            "interaction": "SHAP Interaction Effects - Top Features" if lang == "en" else f"SHAP mijiedarbības efekti - stabilākās metrikas",
        }
        run_shap_summary(
            final_full, X_full_imp,
            out_dir / f"curve_shap_full_{suffix}.png",
            titles["shap_full"],
            lang=lang,
            )
        run_shap_summary(
            final_top, X_top_imp,
            out_dir / f"curve_shap_top_{suffix}.png",
            titles["shap_top"],
            lang=lang,
            )
        run_shap_bar(
            final_full, X_full_imp,
            out_dir / f"curve_shap_bar_full_{suffix}.png",
            titles["bar_full"],
            lang=lang,
            )
        run_shap_bar(
            final_top, X_top_imp,
            out_dir / f"curve_shap_bar_top_{suffix}.png",
            titles["bar_top"],
            lang=lang,
            )
        plot_correlation_matrix(
            X_full_imp, out_dir / f"correlation_full_{suffix}.png",
            titles["corr_full"],
            method="spearman",
            figsize=(18, 16),
            lang=lang,
                        )
        plot_correlation_matrix(
            X_top_imp, out_dir / f"correlation_top_{suffix}.png",
            titles["corr_top"],
            method="spearman",
            figsize=(10, 8),
            lang=lang,
                       )
        plot_shap_interaction(
            final_top, X_top_imp,
            out_path=out_dir / f"shap_interactions_top_{suffix}.png",
            title=titles["interaction"],
            max_features=8,
            lang=lang,
        )

    corr_full = X_full_imp.corr(method="spearman")
    high_corr_pairs = report_high_correlations(corr_full, threshold=0.85, top_n=30)
    print("\n--- Highly correlated feature pairs (|r| >= 0.85) ---")
    if not high_corr_pairs.empty:
        print(high_corr_pairs.to_string(index=False))

    target_corr = feature_target_correlation(X_full_imp, y, method="spearman")
    print("\n--- Top 15 feature-target correlations (Spearman) ---")
    print(target_corr.head(15)[["feature", "correlation"]].to_string(index=False))
    target_corr.to_csv(out_dir / "feature_target_correlations.csv", index=False)


    return final_top


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
        try:
            target_time = float(ap.stem.split("_")[-1])
        except Exception:
            target_time = 0.0
        rides.append({
            "ride_id": f"{track_id}__{ap.stem}",
            "track_id": track_id,
            "acc": acc,
            "gyro": gyro,
            "total_time": float(acc[-1, 0] - acc[0, 0]),
            "target_time": target_time,
        })
    return rides


if __name__ == "__main__":
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    TRACK_DIRS = {
        "cortina": PROJECT_ROOT / "DATA" / "AG" / "trimmed_rides_cortina",
        "whistler": PROJECT_ROOT / "DATA" / "AG" / "trimmed_rides_whistler",
        "undef": PROJECT_ROOT / "DATA" / "AG" / "trimmed_rides_undef",
        "sigulda": PROJECT_ROOT / "DATA" / "AG" / "trimmed_rides_sigulda",
    }

    all_rides = []
    for tid, root in TRACK_DIRS.items():
        if root.is_dir():
            all_rides.extend(discover_rides(root, tid))

    if all_rides:
        track_lookup = {r["ride_id"]: r["track_id"] for r in all_rides}

        seg_frames = []
        for r in all_rides:
            seg_obj = segment_ride(r["acc"], r["gyro"])
            sdf = build_segment_dataset(r["acc"], r["gyro"], seg_obj, r["ride_id"])
            if not sdf.empty:
                seg_frames.append(sdf)

        if seg_frames:
            seg_df_all = pd.concat(seg_frames, ignore_index=True)
            curve_df = build_curve_dataset(seg_df_all, track_lookup)
            if not curve_df.empty:
                train_curve_model(curve_df, output_dir="../DOCS/curve_results")
            else:
                print("No curves found in segmentation output.")