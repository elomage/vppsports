import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dash import Dash, dcc, html, Input, Output
import dash_bootstrap_components as dbc

sys.path.insert(0, str(Path(__file__).resolve().parent))
from segment_template import TrackTemplate, segment_ride_templated
from segmentation import segment_ride, RideSegmentation
from XGBOOST.features.segment_features import build_segment_dataset
from XGBOOST.features.ride_features import build_ride_dataset
from XGBOOST.features.curve_features import (
    build_curve_dataset, CURVE_BASE_METRICS, CURVE_GYRO_METRICS,
)
from XGBOOST.features.features_naming import (
    FEATURE_FULL_NAMES_LV, PREFIX_NAMES_LV, STAT_NAMES_LV,
    RIDE_LEVEL_NAMES_LV, SEGMENT_LEVEL_NAMES_LV, translate_feature_name
)
from segment_exporter import build_export_dataframes
import base64, io
from dash import State

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = Path(__file__).resolve().parent / "DATA" / "templates"

_template_cache = {}

DATASETS = {
    "Trimmed Rides Cortina (A + G)": PROJECT_ROOT / "DATA" / "AG" / "trimmed_rides_cortina",
    "Trimmed Rides Whistler (A + G)": PROJECT_ROOT / "DATA" / "AG" / "trimmed_rides_whistler",
    "Trimmed Rides Undef (A + G)": PROJECT_ROOT / "DATA" / "AG" / "trimmed_rides_undef",
    "Trimmed Rides Sigulda (A + G)": PROJECT_ROOT / "DATA" / "AG" / "trimmed_rides_sigulda",
    "Trimmed Rides Cortina (A)": PROJECT_ROOT / "DATA" / "A" / "trimmed_rides_cortina",
    "Trimmed Rides Whistler (A)": PROJECT_ROOT / "DATA" / "AG" / "trimmed_rides_whistler",
    "Trimmed Rides Undef (A)": PROJECT_ROOT / "DATA" / "AG" / "trimmed_rides_undef",
    "Trimmed Rides Sigulda (A)": PROJECT_ROOT / "DATA" / "A" / "trimmed_rides_sigulda",
}

EXPECTED_CURVES_PER_TRACK = {
    "Trimmed Rides Cortina (A + G)": 12,
    "Trimmed Rides Whistler (A + G)": 9,
    "Trimmed Rides Undef (A + G)": 10,
    "Trimmed Rides Sigulda (A + G)": 16,
    "Trimmed Rides Cortina (A)": 12,
    "Trimmed Rides Whistler (A)": 9,
    "Trimmed Rides Undef (A)": 10,
    "Trimmed Rides Sigulda (A)": 16,
}

TRACK_ID_FROM_DATASET = {
    "Trimmed Rides Cortina (A + G)": "cortina",
    "Trimmed Rides Whistler (A + G)": "whistler",
    "Trimmed Rides Undef (A + G)": "undef",
    "Trimmed Rides Sigulda (A + G)": "sigulda",
    "Trimmed Rides Cortina (A)": "cortina",
    "Trimmed Rides Whistler (A)": "whistler",
    "Trimmed Rides Undef (A)": "undef",
    "Trimmed Rides Sigulda (A)": "sigulda",
}

SEP = " · "

THEMES = {
    "dark": {
        "BG_BASE": "#0d0f12",
        "BG_SURFACE": "#13161b",
        "BG_RAISED": "#1a1e25",
        "BG_INPUT": "#10131a",
        "BORDER": "#252a35",
        "ACCENT": "#3d8ef0",
        "TEXT_PRI": "#dbeaff",
        "TEXT_SEC": "#cfe3ff",
        "TEXT_DIM": "#8a9ab5",
        "SUCCESS": "#2ecc71",
        "WARNING": "#f39c12",
        "ERROR_C": "#e74c3c",
        "PLOTLY_TEMPLATE": "plotly_dark",
        "SIGNAL_LINE": "#8a9ab5",
        "SEG_OPACITY": 0.12,
        "SEG_COLORS": {
            "start": "#f0913d",
            "curve": "#9b59b6",
            "curve_r": "#2ecc71",
            "curve_l": "#e74c3c",
            "straight": "#3d8ef0",
        },
    },
    "light": {
        "BG_BASE": "#f4f6fa",
        "BG_SURFACE": "#ffffff",
        "BG_RAISED": "#eef1f7",
        "BG_INPUT": "#ffffff",
        "BORDER": "#c2cbdb",
        "ACCENT": "#2563c9",
        "TEXT_PRI": "#0f1620",
        "TEXT_SEC": "#1f2b3d",
        "TEXT_DIM": "#465468",
        "SUCCESS": "#15803d",
        "WARNING": "#b45309",
        "ERROR_C": "#b91c1c",
        "PLOTLY_TEMPLATE": "plotly_white",
        "SIGNAL_LINE": "#3a4658",
        "SEG_OPACITY": 0.28,
        "SEG_COLORS": {
            "start": "#e69e22",
            "curve": "#145922",
            "curve_r": "#0ca678",
            "curve_l": "#e03131",
            "straight": "#1971c2",
        },
    },
}

CURRENT_THEME = "dark"
CURRENT_LANG = "EN"

TRANSLATIONS = {
    "EN": {
        "app_name": "LUGE DATASET GENERATOR",
        "export_csv": "EXPORT CSV",
        "select_dataset": "Select Dataset",
        "rides_loaded": "{n} Rides Loaded",
        "configure": "Configure parameters above.",
        "dataset": "DATASET",
        "rides": "RIDES",
        "seg_mode": "SEGMENTATION MODE",
        "seg_templated": " Templated (track-locked)",
        "seg_independent": " Independent (per-ride)",
        "use_gyro": "USE GYRO IN DETECTION",
        "gyro_off": " Off (accel only)",
        "gyro_on": " On (accel + gyro)",
        "curve_labels": "CURVE LABELS",
        "labels_directional": " Directional (L/R)",
        "labels_normalized": " Normalized (Curve)",
        "expected_curves": "EXPECTED CURVES (TRACK)",
        "auto_track": " Auto from track",
        "off_no_constraint": " Off (no constraint)",
        "show_gyro_plot": "SHOW GYRO PLOT",
        "off": " Off",
        "on": " On",
        "tab_signals": "SIGNALS",
        "tab_segmentation": "SEGMENTATION",
        "tab_features": "FEATURES & XGBOOST",
        "accel_signals": "Accelerometer Signals",
        "gyro_signals": "Gyroscope Signals",
        "gyro_magnitude": "Gyro Magnitude",
        "seg_analysis": "Segmentation Analysis: {name}{suffix}",
        "no_template_found": "independent (no template found)",
        "accel_gyro": "accel+gyro",
        "accel_only": "accel-only",
        "normalized": "normalized",
        "curves_locked": "{n} curves (locked)",
        "no_segments": "No segments produced for this ride.",
        "curve_unavailable": "Curve features unavailable: {err}",
        "no_curves": "No curves found for this ride.",
        "no_curve_features": "No curve-model features available.",
        "curve_model_features": "CURVE MODEL FEATURES (PER CURVE)",
        "stability_hint": "Select 2+ rides for stability.",
        "feature": "feature",
        "feature_stability": "FEATURE STABILITY (CV)",
        "flattened_ride": "FLATTENED RIDE DATASET — {mode} (XGBOOST TARGET)",
        "segment_dataset": "SEGMENT DATASET — {mode} (5-STEP LAG MEMORY)",
        "curve_dataset": "CURVE DATASET — {mode} (CURVE MODEL TARGET)",
        "timeline": "TIMELINE",
        "directional": "directional",
    },
    "LV": {
        "app_name": "KAMANIŅU DATU KOPU ĢENERATORS",
        "export_csv": "EKSPORTĒT CSV",
        "select_dataset": "Izvēlieties datu kopu",
        "rides_loaded": "Ielādēti {n} braucieni",
        "configure": "Konfigurējiet parametrus augšā.",
        "dataset": "DATU KOPA",
        "rides": "BRAUCIENI",
        "seg_mode": "SEGMENTĀCIJAS REŽĪMS",
        "seg_templated": " Šablona (trase fiksēta)",
        "seg_independent": " Neatkarīgs (katram braucienam)",
        "use_gyro": "IZMANTOT ŽIROSKOPU NOTEIKŠANĀ",
        "gyro_off": " Izsl. (tikai akselerometrs)",
        "gyro_on": " Iesl. (akselerometrs + žiroskops)",
        "curve_labels": "VIRĀŽU APZĪMĒJUMI",
        "labels_directional": " Virziena (K/L)",
        "labels_normalized": " Normalizēti (Virāža)",
        "expected_curves": "GAIDĀMĀS VIRĀŽAS (TRASE)",
        "auto_track": " Automātiski no trases",
        "off_no_constraint": " Izsl. (bez ierobežojuma)",
        "show_gyro_plot": "RĀDĪT ŽIROSKOPA GRAFIKU",
        "off": " Izsl.",
        "on": " Iesl.",
        "tab_signals": "SIGNĀLI",
        "tab_segmentation": "SEGMENTĀCIJA",
        "tab_features": "PAZĪMES UN XGBOOST",
        "accel_signals": "Akselerometra signāli",
        "gyro_signals": "Žiroskopa signāli",
        "gyro_magnitude": "Žiroskopa amplitūda",
        "seg_analysis": "Segmentēts brauciens: {name}",
        "no_template_found": "neatkarīgs (šablons nav atrasts)",
        "accel_gyro": "aksel.+žiro.",
        "accel_only": "tikai aksel.",
        "normalized": "normalizēts",
        "curves_locked": "{n} virāžas (fiksētas)",
        "no_segments": "Šim braucienam nav izveidoti segmenti.",
        "curve_unavailable": "Virāžu pazīmes nav pieejamas: {err}",
        "no_curves": "Šim braucienam virāžas nav atrastas.",
        "no_curve_features": "Virāžu modeļa pazīmes nav pieejamas.",
        "curve_model_features": "VIRĀŽU MODEĻA PAZĪMES (UZ VIRĀŽU)",
        "stability_hint": "Izvēlieties 2+ braucienus stabilitātei.",
        "feature": "pazīme",
        "feature_stability": "PAZĪMJU STABILITĀTE (CV)",
        "flattened_ride": "BRAUCIENA DATU KOPA — {mode} (XGBOOST MĒRĶIS)",
        "segment_dataset": "SEGMENTU DATU KOPA — {mode} (5 SOĻU ATMIŅA)",
        "curve_dataset": "VIRĀŽU DATU KOPA — {mode} (VIRĀŽU MODEĻA MĒRĶIS)",
        "timeline": "LAIKA LĪNIJA",
        "directional": "virziena",
    },
}


def tr(key, lang=None, **kwargs):
    lang = lang or CURRENT_LANG
    s = TRANSLATIONS.get(lang, TRANSLATIONS["EN"]).get(key, key)
    if kwargs:
        try:
            return s.format(**kwargs)
        except Exception:
            return s
    return s


def theme(name):
    return THEMES.get(name, THEMES["dark"])


def seg_colors(th):
    return th["SEG_COLORS"]


def plotly_layout(th):
    return dict(
        template=th["PLOTLY_TEMPLATE"],
        paper_bgcolor=th["BG_BASE"],
        plot_bgcolor=th["BG_SURFACE"],
        font=dict(family="Consolas, monospace", color=th["TEXT_SEC"], size=11),
        xaxis=dict(gridcolor=th["BORDER"], zerolinecolor=th["BORDER"], color=th["TEXT_DIM"]),
        yaxis=dict(gridcolor=th["BORDER"], zerolinecolor=th["BORDER"], color=th["TEXT_DIM"]),
        legend=dict(bgcolor=th["BG_RAISED"], bordercolor=th["BORDER"], borderwidth=1),
        margin=dict(l=50, r=20, t=40, b=40),
    )


FEATURE_FULL_NAMES = {
    "az_max": "Vertical G-Force Peak",
    "az_min": "Vertical G-Force Min",
    "az_mean": "Average Vertical G-Force",
    "az_std": "Vertical G-Force Std",
    "az_iqr": "Vertical G-Force IQR",
    "az_p95": "Vertical G-Force 95th Pct",
    "ay_abs_avg": "Average Lateral G-Force",
    "ay_abs_p95": "Lateral G-Force Intensity (95th Pct)",
    "ay_signed_mean": "Average Directional Side-Force",
    "ay_signed_p95": "Peak Directional Side-Force",
    "ay_signed_min": "Min Directional Side-Force",
    "ay_inward_fraction": "Inward Steering Fraction",
    "ay_zero_cross_rate": "Steering Activity / Wobble Rate",
    "ax_std": "Longitudinal G-Force Std",
    "ax_p95_abs": "Peak Longitudinal G-Force",
    "ax_mean": "Average Longitudinal G-Force",
    "ax_zero_cross_rate": "Longitudinal Reversal Rate",
    "ax_jerk_rms": "Longitudinal Smoothness (Jerk)",
    "ay_jerk_rms": "Lateral Smoothness (Jerk)",
    "az_jerk_rms": "Vertical Smoothness (Jerk)",
    "az_peak_position": "Vertical Peak Position",
    "az_fwhm_ratio": "Vertical Peak Width Ratio",
    "g_total_max": "Peak Total Combined G-Force",
    "g_total_mean": "Avg Total Combined G-Force",
    "g_lat_vert_p95": "Lateral-to-Vertical Force Ratio",
    "gyro_mag_peak": "Angular Velocity Peak",
    "gyro_mag_mean": "Avg Angular Velocity",
    "gyro_z_peak_abs": "Yaw Rate Peak",
    "gyro_z_clean_ratio": "Steering Efficiency Ratio",
    "gyro_z_sign_flips_per_s": "Steering Reversal Rate",
    "gyro_x_peak_abs": "Roll Rate Peak",
    "gyro_y_peak_abs": "Pitch Rate Peak",
    "gyro_jerk_rms": "Angular Movement Smoothness",
    "wiggle_count": "Wiggle Count",
    "ride_id": "Ride ID",
    "seg_idx": "Segment Index",
    "kind": "Segment Kind",
    "label": "Segment Label",
    "duration": "Duration (s)",
    "dur_z": "Duration Z-Score",
    "dur_z_source": "Z-Score Source",
    "prev_kind": "Previous Segment Kind",
    "prev_duration": "Previous Segment Duration",
    "prev_is_straight": "Previous Is Straight",
    "prev_is_curve": "Previous Is Curve",
}

PHASE_PREFIXES = ("entry_", "apex_", "exit_")

CURVE_MODEL_IDENTIFIERS = ["ride_id", "seg_idx", "kind", "label"]
CURVE_MODEL_TARGET = ["duration", "dur_z", "dur_z_source"]
CURVE_MODEL_PREV_META = ["prev_kind", "prev_duration", "prev_is_straight", "prev_is_curve"]
CURVE_MODEL_PREV_FEATURES_BASE = ["az_max", "ay_abs_p95", "ax_jerk_rms",
                                  "g_lat_vert_p95", "g_total_max", "gyro_z_clean_ratio"]


def _curve_model_columns(df_cols):
    cols_set = set(df_cols)
    cols = []
    for c in CURVE_MODEL_IDENTIFIERS + CURVE_MODEL_TARGET:
        if c in cols_set:
            cols.append(c)
    for c in CURVE_BASE_METRICS:
        if c in cols_set:
            cols.append(c)
    for c in CURVE_GYRO_METRICS:
        if c in cols_set:
            cols.append(c)
    for prefix in ("entry_", "apex_", "exit_"):
        for base in CURVE_BASE_METRICS + CURVE_GYRO_METRICS:
            name = f"{prefix}{base}"
            if name in cols_set:
                cols.append(name)
    for c in CURVE_MODEL_PREV_META:
        if c in cols_set:
            cols.append(c)
    for base in CURVE_MODEL_PREV_FEATURES_BASE:
        for prefix in ("prev_straight_", "prev_curve_"):
            name = f"{prefix}{base}"
            if name in cols_set:
                cols.append(name)
    seen = set()
    deduped = []
    for c in cols:
        if c not in seen:
            seen.add(c)
            deduped.append(c)
    return deduped


def get_human_label(col: str) -> str:
    prev_prefix = ""
    phase_prefix = ""
    clean = col

    if clean.startswith("prev_straight_"):
        prev_prefix = "Iepr. taisne: "
        clean = clean[len("prev_straight_"):]
    elif clean.startswith("prev_curve_"):
        prev_prefix = "Iepr. virāža: "
        clean = clean[len("prev_curve_"):]
    elif clean.startswith("prev_") and clean not in FEATURE_FULL_NAMES_LV:
        prev_prefix = "Iepriekšējais segments: "
        clean = clean[len("prev_"):]

    phase_prefix_lv = ""
    for p in PHASE_PREFIXES:
        if clean.startswith(p):
            phase_key = p[:-1]
            phase_prefix_lv = f"{PREFIX_NAMES_LV.get(phase_key, p[:-1].title())}: "
            clean = clean[len(p):]
            break

    if clean in FEATURE_FULL_NAMES_LV:
        return f"{prev_prefix}{phase_prefix_lv}{FEATURE_FULL_NAMES_LV[clean]}"

    if col in RIDE_LEVEL_NAMES_LV:
        return RIDE_LEVEL_NAMES_LV[col]
    if col in SEGMENT_LEVEL_NAMES_LV:
        return SEGMENT_LEVEL_NAMES_LV[col]

    en_label = ""
    if clean in FEATURE_FULL_NAMES:
        en_label = FEATURE_FULL_NAMES[clean]
        if en_label in SEGMENT_LEVEL_NAMES_LV:
            return f"{prev_prefix}{phase_prefix_lv}{SEGMENT_LEVEL_NAMES_LV[en_label]}"
        return f"{prev_prefix}{phase_prefix_lv}{en_label}"

    return f"{prev_prefix}{phase_prefix_lv}{clean}"


def humanize_columns(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={c: get_human_label(c) for c in df.columns})


def _load_txt(path: Path):
    rows = []
    try:
        with open(path) as f:
            for line in f:
                parts = line.strip().split(",")
                if len(parts) != 4: continue
                try:
                    rows.append([float(p) for p in parts])
                except ValueError:
                    continue
    except IOError:
        return None
    return np.array(rows) if rows else None


def load_rides(base_path: Path) -> dict:
    accel_dir = base_path / "accel"
    gyro_dir = base_path / "gyro"
    rides = {}
    if not accel_dir.exists(): return rides
    for fname in sorted(os.listdir(accel_dir)):
        if not fname.lower().endswith(".txt"): continue
        acc = _load_txt(accel_dir / fname)
        gyro = _load_txt(gyro_dir / fname) if (gyro_dir / fname).exists() else None
        if acc is not None: rides[fname] = {"accel": acc, "gyro": gyro}
    return rides


def dropdown_style(th):
    return dict(backgroundColor=th["BG_INPUT"], color=th["TEXT_PRI"],
                border=f"1px solid {th['BORDER']}", borderRadius="4px")


def label_style(th):
    return dict(color=th["TEXT_DIM"], fontSize="10px", letterSpacing="1.5px",
                fontFamily="Consolas, monospace", marginBottom="4px")


def card_style(th):
    return dict(backgroundColor=th["BG_SURFACE"], border=f"1px solid {th['BORDER']}",
                borderRadius="6px", padding="14px", marginBottom="12px")


def radio_label_style(th):
    return {"display": "inline-block", "color": th["TEXT_PRI"], "fontSize": "11px",
            "marginRight": "12px", "cursor": "pointer"}


def tab_style(th):
    return {"backgroundColor": th["BG_SURFACE"], "color": th["TEXT_DIM"],
            "border": f"1px solid {th['BORDER']}", "borderBottom": "none",
            "padding": "8px 20px", "fontSize": "11px"}


def tab_sel_style(th):
    return {**tab_style(th), "backgroundColor": th["BG_RAISED"], "color": th["ACCENT"],
            "borderTop": f"2px solid {th['ACCENT']}"}


app = Dash(__name__, external_stylesheets=[dbc.themes.CYBORG], suppress_callback_exceptions=True)


def build_controls(th, lang):
    return html.Div(
        id="controls-bar",
        style={**card_style(th), "margin": "12px 16px", "display": "flex", "gap": "20px",
               "flexWrap": "wrap", "alignItems": "flex-end"},
        children=[
            html.Div([html.Div(tr("dataset", lang), style=label_style(th)),
                      dcc.Dropdown(id="dataset-selector",
                                   options=[{"label": k, "value": k} for k in DATASETS],
                                   style={**dropdown_style(th), "width": "220px"})]),
            html.Div([html.Div(tr("rides", lang), style=label_style(th)),
                      dcc.Dropdown(id="ride-selector", multi=True,
                                   style={**dropdown_style(th), "width": "400px"})]),
            html.Div([
                html.Div(tr("seg_mode", lang), style=label_style(th)),
                dcc.RadioItems(
                    id="segmentation-mode-toggle",
                    options=[
                        {"label": tr("seg_templated", lang), "value": "templated"},
                        {"label": tr("seg_independent", lang), "value": "independent"},
                    ],
                    value="templated",
                    labelStyle=radio_label_style(th),
                    inputStyle={"marginRight": "4px"},
                    style={"padding": "6px 0"},
                ),
            ]),
            html.Div([
                html.Div(tr("use_gyro", lang), style=label_style(th)),
                dcc.RadioItems(
                    id="use-gyro-toggle",
                    options=[
                        {"label": tr("gyro_off", lang), "value": "off"},
                        {"label": tr("gyro_on", lang), "value": "on"},
                    ],
                    value="off",
                    labelStyle=radio_label_style(th),
                    inputStyle={"marginRight": "4px"},
                    style={"padding": "6px 0"},
                ),
            ]),
            html.Div([
                html.Div(tr("curve_labels", lang), style=label_style(th)),
                dcc.RadioItems(
                    id="normalize-toggle",
                    options=[
                        {"label": tr("labels_directional", lang), "value": "directional"},
                        {"label": tr("labels_normalized", lang), "value": "normalized"},
                    ],
                    value="normalized",
                    labelStyle=radio_label_style(th),
                    inputStyle={"marginRight": "4px"},
                    style={"padding": "6px 0"},
                ),
            ]),
            html.Div([
                html.Div(tr("expected_curves", lang), style=label_style(th)),
                dcc.RadioItems(
                    id="expected-curves-toggle",
                    options=[
                        {"label": tr("auto_track", lang), "value": "auto"},
                        {"label": tr("off_no_constraint", lang), "value": "off"},
                    ],
                    value="auto",
                    labelStyle=radio_label_style(th),
                    inputStyle={"marginRight": "4px"},
                    style={"padding": "6px 0"},
                ),
            ]),
            html.Div([
                html.Div(tr("show_gyro_plot", lang), style=label_style(th)),
                dcc.RadioItems(
                    id="show-gyro-plot-toggle",
                    options=[
                        {"label": tr("off", lang), "value": "off"},
                        {"label": tr("on", lang), "value": "on"},
                    ],
                    value="off",
                    labelStyle=radio_label_style(th),
                    inputStyle={"marginRight": "4px"},
                    style={"padding": "6px 0"},
                ),
            ]),
        ]
    )


def build_tabs(th, lang):
    return [
        dcc.Tab(label=tr("tab_signals", lang), value="signals",
                style=tab_style(th), selected_style=tab_sel_style(th)),
        dcc.Tab(label=tr("tab_segmentation", lang), value="segmentation",
                style=tab_style(th), selected_style=tab_sel_style(th)),
        dcc.Tab(label=tr("tab_features", lang), value="features",
                style=tab_style(th), selected_style=tab_sel_style(th)),
    ]


def build_header(th, theme_name, lang):
    return html.Div(
        id="header-bar",
        style={"backgroundColor": th["BG_SURFACE"],
               "borderBottom": f"1px solid {th['BORDER']}", "padding": "0 20px",
               "height": "52px", "display": "flex", "alignItems": "center",
               "justifyContent": "space-between"},
        children=[
            html.Span(tr("app_name", lang), id="app-name-span",
                      style={"color": th["ACCENT"], "fontSize": "13px",
                             "fontWeight": "700", "letterSpacing": "3px"}),
            html.Div([
                dcc.RadioItems(
                    id="lang-toggle",
                    options=[
                        {"label": " EN", "value": "EN"},
                        {"label": " LV", "value": "LV"},
                    ],
                    value=lang,
                    labelStyle={"display": "inline-block", "color": th["TEXT_DIM"],
                                "fontSize": "10px", "letterSpacing": "1.5px",
                                "marginRight": "10px", "cursor": "pointer"},
                    inputStyle={"marginRight": "4px"},
                    style={"marginRight": "16px"},
                ),
                dcc.RadioItems(
                    id="theme-toggle",
                    options=[
                        {"label": " DARK", "value": "dark"},
                        {"label": " LIGHT", "value": "light"},
                    ],
                    value=theme_name,
                    labelStyle={"display": "inline-block", "color": th["TEXT_DIM"],
                                "fontSize": "10px", "letterSpacing": "1.5px",
                                "marginRight": "10px", "cursor": "pointer"},
                    inputStyle={"marginRight": "4px"},
                    style={"marginRight": "16px"},
                ),
                html.Button(tr("export_csv", lang), id="export-button", n_clicks=0,
                            style={"backgroundColor": th["ACCENT"], "color": th["BG_BASE"],
                                   "border": "none", "padding": "6px 14px", "fontSize": "10px",
                                   "letterSpacing": "1.5px", "fontFamily": "Consolas, monospace",
                                   "cursor": "pointer", "borderRadius": "3px",
                                   "marginRight": "16px", "fontWeight": "700"}),
                html.Span(id="status-badge",
                          style={"color": th["TEXT_DIM"], "fontSize": "10px"}),
                dcc.Download(id="export-download"),
            ], style={"display": "flex", "alignItems": "center"}),
        ],
    )


def build_layout(theme_name, lang):
    th = theme(theme_name)
    return html.Div(
        id="root-container",
        style={"backgroundColor": th["BG_BASE"], "minHeight": "100vh",
               "fontFamily": "Consolas, monospace"},
        children=[
            dcc.Store(id="theme-store", data=theme_name),
            dcc.Store(id="lang-store", data=lang),
            html.Div(id="header-container", children=build_header(th, theme_name, lang)),
            html.Div(id="controls-container", children=build_controls(th, lang)),
            dcc.Tabs(id="tabs", value="signals", children=build_tabs(th, lang)),
            html.Div(id="tab-content", style={"padding": "16px"}),
        ]
    )


app.layout = build_layout(CURRENT_THEME, CURRENT_LANG)


@app.callback(
    Output("root-container", "style"),
    Output("header-container", "children"),
    Output("controls-container", "children"),
    Output("tabs", "children"),
    Output("theme-store", "data"),
    Output("lang-store", "data"),
    Input("theme-toggle", "value"),
    Input("lang-toggle", "value"),
)
def apply_theme_lang(theme_name, lang):
    th = theme(theme_name)
    root_style = {"backgroundColor": th["BG_BASE"], "minHeight": "100vh",
                  "fontFamily": "Consolas, monospace"}
    return (root_style, build_header(th, theme_name, lang),
            build_controls(th, lang), build_tabs(th, lang), theme_name, lang)


@app.callback(Output("ride-selector", "options"), Output("status-badge", "children"),
              Input("dataset-selector", "value"),
              Input("lang-store", "data"))
def update_ride_list(dataset_name, lang):
    if not dataset_name: return [], tr("select_dataset", lang)
    rides = load_rides(DATASETS[dataset_name])
    return [{"label": k, "value": k} for k in rides], tr("rides_loaded", lang, n=len(rides))


@app.callback(
    Output("tab-content", "children"),
    [Input("tabs", "value"),
     Input("ride-selector", "value"),
     Input("dataset-selector", "value"),
     Input("normalize-toggle", "value"),
     Input("use-gyro-toggle", "value"),
     Input("expected-curves-toggle", "value"),
     Input("show-gyro-plot-toggle", "value"),
     Input("segmentation-mode-toggle", "value"),
     Input("theme-store", "data"),
     Input("lang-store", "data")]
)
def render_tab(tab, ride_names, dataset_name, normalize_mode, use_gyro_mode,
               expected_mode, show_gyro_plot_mode, seg_mode, theme_name, lang):
    th = theme(theme_name)
    if not ride_names or not dataset_name: return _empty(tr("configure", lang), th)
    data = load_rides(DATASETS[dataset_name])
    rides = [(n, data[n]["accel"], data[n].get("gyro")) for n in ride_names if n in data]
    normalize = (normalize_mode == "normalized")
    use_gyro = (use_gyro_mode == "on")
    show_gyro_plot = (show_gyro_plot_mode == "on")
    expected_n = EXPECTED_CURVES_PER_TRACK.get(dataset_name) if expected_mode == "auto" else None
    use_template = (seg_mode == "templated")
    if tab == "signals": return _render_signals(rides, th, lang)
    if tab == "segmentation": return _render_segmentation(rides, normalize, use_gyro, expected_n,
                                                          show_gyro_plot, dataset_name, use_template, th, lang)
    if tab == "features": return _render_features(rides, normalize, use_gyro, expected_n,
                                                  dataset_name, use_template, th, lang)


def _get_template(dataset_name):
    if not dataset_name:
        return None
    if dataset_name in _template_cache:
        return _template_cache[dataset_name]
    tpl_path = TEMPLATES_DIR / f"{dataset_name}.pkl"
    if not tpl_path.exists():
        _template_cache[dataset_name] = None
        return None
    _template_cache[dataset_name] = TrackTemplate.load(tpl_path)
    return _template_cache[dataset_name]


def _segment(acc, gyro, use_gyro, expected_n, dataset_name=None, use_template=False):
    if use_template:
        tpl = _get_template(dataset_name)
        if tpl is not None:
            seg = segment_ride_templated(acc, gyro if use_gyro else None, tpl)
            return seg, "templated"
    seg = segment_ride(acc, gyro if use_gyro else None,
                       expected_n_curves=expected_n)
    return seg, "independent"


def _render_signals(rides, th, lang):
    acc_fig, gyro_fig = go.Figure(), go.Figure()
    colors = [th["ACCENT"], th["SUCCESS"], th["WARNING"], th["ERROR_C"], "#b8ff57", "#ff6eb4"]
    for idx, (name, acc, gyro) in enumerate(rides):
        c = colors[idx % len(colors)]
        t = acc[:, 0] - acc[0, 0]
        acc_fig.add_trace(go.Scatter(x=t, y=acc[:, 1], name=f"{name} ax", line=dict(color=c, width=1)))
        acc_fig.add_trace(go.Scatter(x=t, y=acc[:, 2], name=f"{name} ay", visible="legendonly", line=dict(color=c)))
        acc_fig.add_trace(go.Scatter(x=t, y=acc[:, 3], name=f"{name} az", visible="legendonly", line=dict(color=c)))
        if gyro is not None:
            tg = gyro[:, 0] - gyro[0, 0]
            gyro_fig.add_trace(go.Scatter(x=tg, y=gyro[:, 1], name=f"{name} gx", line=dict(color=c, width=1)))
            gyro_fig.add_trace(go.Scatter(x=tg, y=gyro[:, 2], name=f"{name} gy", visible="legendonly", line=dict(color=c)))
            gyro_fig.add_trace(go.Scatter(x=tg, y=gyro[:, 3], name=f"{name} gz", visible="legendonly", line=dict(color=c)))
    acc_fig.update_layout(**plotly_layout(th), height=400, title=tr("accel_signals", lang))
    gyro_fig.update_layout(**plotly_layout(th), height=300, title=tr("gyro_signals", lang))
    return html.Div([_card([dcc.Graph(figure=acc_fig)], th), _card([dcc.Graph(figure=gyro_fig)], th)])


def _render_segmentation(rides, normalize, use_gyro, expected_n, show_gyro_plot,
                         dataset_name, use_template, th, lang):
    panels = []
    track_id = TRACK_ID_FROM_DATASET.get(dataset_name, "unknown")
    sc = seg_colors(th)
    seg_opacity = th["SEG_OPACITY"]
    signal_line = th["SIGNAL_LINE"]

    for name, acc, gyro in rides:
        seg, mode_used = _segment(acc, gyro, use_gyro, expected_n,
                                  dataset_name, use_template)
        seg_for_plot = RideSegmentation(
            segments=seg.normalized_segments() if normalize else seg.segments,
            swing_end_idx=seg.swing_end_idx,
            t=seg.t,
            az_smooth=seg.az_smooth,
            threshold=seg.threshold,
            gyro_used=seg.gyro_used,
            converged=seg.converged,
            sensitivity=seg.sensitivity,
        ) if normalize else seg

        seg_list = seg_for_plot.segments

        t0 = acc[0, 0]
        t = acc[:, 0] - t0
        show_gyro_plot_active = show_gyro_plot and gyro is not None
        subtitles = ["AX", "AY", "AZ"]
        if show_gyro_plot_active: subtitles.append(tr("gyro_magnitude", lang))
        n_rows = 4 if show_gyro_plot_active else 3
        fig = make_subplots(rows=n_rows, cols=1, shared_xaxes=True, vertical_spacing=0.03, subplot_titles=subtitles)

        for r, col in enumerate([1, 2, 3], 1):
            fig.add_trace(go.Scatter(x=t, y=acc[:, col], line=dict(color=signal_line, width=1.1), showlegend=False),
                          row=r, col=1)

        if show_gyro_plot_active:
            g_mag = np.sqrt(np.sum(gyro[:, 1:] ** 2, axis=1))
            fig.add_trace(go.Scatter(x=gyro[:, 0] - t0, y=g_mag, line=dict(color=th["SUCCESS"], width=1.1), showlegend=False),
                          row=4, col=1)

        for s in seg_list:
            clr = sc.get(s.kind, th["TEXT_DIM"])
            for r in range(1, n_rows + 1):
                fig.add_vrect(x0=s.t_start - t0, x1=s.t_end - t0, fillcolor=clr, opacity=seg_opacity,
                              line_width=0, row=r, col=1)


        mode_tags = [mode_used]
        if use_template and mode_used == "independent":
            mode_tags[0] = tr("no_template_found", lang)
        mode_tags.append(tr("accel_gyro", lang) if use_gyro else tr("accel_only", lang))
        if normalize: mode_tags.append(tr("normalized", lang))
        if mode_used == "independent" and expected_n is not None:
            n_curves = len(seg.curves)
            tag = f"target={expected_n}, got={n_curves}, sens={seg.sensitivity:.2f}"
            if not seg.converged: tag += " ⚠"
            mode_tags.append(tag)
        elif mode_used == "templated":
            n_curves = len(seg.curves)
            mode_tags.append(tr("curves_locked", lang, n=n_curves))
        joined_tags = SEP.join(mode_tags)
        suffix = f" [{joined_tags}]"
        layout_kwargs = plotly_layout(th)
        layout_kwargs["font"] = dict(family="Consolas, monospace", color=th["TEXT_SEC"], size=13)
        fig.update_layout(**layout_kwargs, height=650,
                          title=tr("seg_analysis", lang, name=name, suffix=suffix))
        fig.update_xaxes(title_text="Laiks (s)", row=n_rows, col=1)
        fig.update_yaxes(title_text="g vienības", row=2, col=1)
        fig.update_annotations(font=dict(size=13, color=th["TEXT_PRI"]), selector=dict(text="AX"))

        ride_id = f"{track_id}__{Path(name).stem}"
        seg_df = build_segment_dataset(acc, gyro, seg_for_plot, ride_id)
        curve_table = _build_curve_features_table(seg_df, track_id, th, lang)

        panels.append(_card([
            dcc.Graph(figure=fig),
            _build_timeline(seg_list, t[-1], th, lang),
            curve_table,
        ], th))

    return html.Div(panels)


def _build_curve_features_table(seg_df, track_id, th, lang):
    if seg_df is None or seg_df.empty:
        return _empty(tr("no_segments", lang), th)
    track_lookup = {rid: track_id for rid in seg_df["ride_id"].unique()}
    try:
        curve_df = build_curve_dataset(seg_df, track_lookup)
    except Exception as e:
        return _empty(tr("curve_unavailable", lang, err=e), th)
    if curve_df is None or curve_df.empty:
        return _empty(tr("no_curves", lang), th)

    keep_cols = _curve_model_columns(curve_df.columns)
    if not keep_cols:
        return _empty(tr("no_curve_features", lang), th)
    curve_df = curve_df[keep_cols]

    return _df_table(humanize_columns(curve_df.round(3)),
                     tr("curve_model_features", lang), th)


def _render_features(rides, normalize, use_gyro, expected_n,
                     dataset_name, use_template, th, lang):
    seg_list, ride_list = [], []
    mode_used_any = None
    track_id = TRACK_ID_FROM_DATASET.get(dataset_name, "unknown")
    for name, acc, gyro in rides:
        s_obj, mode_used = _segment(acc, gyro, use_gyro, expected_n,
                                    dataset_name, use_template)
        mode_used_any = mode_used
        if normalize:
            s_obj = RideSegmentation(
                segments=s_obj.normalized_segments(),
                swing_end_idx=s_obj.swing_end_idx,
                t=s_obj.t,
                az_smooth=s_obj.az_smooth,
                threshold=s_obj.threshold,
                gyro_used=s_obj.gyro_used,
                converged=s_obj.converged,
                sensitivity=s_obj.sensitivity,
            )
        ride_id = f"{track_id}__{Path(name).stem}"
        df_s = build_segment_dataset(acc, gyro, s_obj, ride_id)
        df_r = build_ride_dataset(df_s, acc[-1, 0] - acc[0, 0], ride_id)
        seg_list.append(df_s)
        ride_list.append(df_r)

    final_seg = pd.concat(seg_list)
    final_ride = pd.concat(ride_list)

    track_lookup = {rid: track_id for rid in final_seg["ride_id"].unique()}
    try:
        final_curve = build_curve_dataset(final_seg, track_lookup)
    except Exception:
        final_curve = pd.DataFrame()

    stable = _empty(tr("stability_hint", lang), th)
    if len(ride_list) > 1:
        feat_col = tr("feature", lang)
        st = final_ride.drop(columns=["ride_id", "target_time"], errors="ignore").agg(["mean", "std"]).T
        st["cv"] = st["std"] / (st["mean"].abs() + 1e-6)
        st = st.sort_values("cv").round(4).reset_index().rename(columns={"index": feat_col})
        st[feat_col] = st[feat_col].map(get_human_label)
        stable = _df_table(st, tr("feature_stability", lang), th)

    tags = [(mode_used_any or "independent").upper(),
            tr("normalized", lang).upper() if normalize else tr("directional", lang).upper(),
            tr("accel_gyro", lang).upper() if use_gyro else tr("accel_only", lang).upper()]
    mode_label = SEP.join(tags)

    children = [
        _card([stable], th),
        _card([_df_table(humanize_columns(final_ride.round(3)),
                         tr("flattened_ride", lang, mode=mode_label), th)], th),
        _card([_df_table(humanize_columns(final_seg.round(3)),
                         tr("segment_dataset", lang, mode=mode_label), th)], th),
    ]

    if final_curve is not None and not final_curve.empty:
        keep_cols = _curve_model_columns(final_curve.columns)
        if keep_cols:
            final_curve = final_curve[keep_cols]
            children.append(_card([_df_table(humanize_columns(final_curve.round(3)),
                                             tr("curve_dataset", lang, mode=mode_label), th)], th))

    return html.Div(children)


def _df_table(df, title, th):
    hdr = [html.Th(c, style={"padding": "8px", "borderBottom": f"1px solid {th['BORDER']}",
                             "color": th["TEXT_DIM"]}) for c in df.columns]
    rows = [html.Tr([html.Td(str(v), style={"padding": "6px", "fontSize": "11px",
                                            "color": th["TEXT_PRI"]}) for v in r])
            for r in df.itertuples(index=False)]
    return html.Div([html.Div(title, style=label_style(th)),
                     html.Div(html.Table([html.Thead(html.Tr(hdr)), html.Tbody(rows)], style={"width": "100%"}),
                              style={"overflowX": "auto"})])


def _build_timeline(segments, dur, th, lang):
    sc = seg_colors(th)
    bars = []
    for s in segments:
        w = (s.duration / max(dur, 0.1)) * 100
        bars.append(html.Div(title=f"{s.label}: {s.duration:.2f}s",
                             style={"width": f"{w}%", "backgroundColor": sc.get(s.kind, "#555"),
                                    "height": "20px", "display": "inline-block",
                                    "borderRight": f"1px solid {th['BG_BASE']}"}))
    return html.Div([html.Div(tr("timeline", lang), style=label_style(th)),
                     html.Div(bars, style={"width": "100%", "borderRadius": "4px", "overflow": "hidden"})])


def _card(children, th): return html.Div(children, style=card_style(th))


def _empty(msg, th): return html.Div(msg, style={"color": th["TEXT_DIM"], "textAlign": "center", "padding": "50px"})


@app.callback(
    Output("export-download", "data", allow_duplicate=True),
    Input("export-button", "n_clicks"),
    State("ride-selector", "value"),
    State("dataset-selector", "value"),
    State("normalize-toggle", "value"),
    State("use-gyro-toggle", "value"),
    State("expected-curves-toggle", "value"),
    State("segmentation-mode-toggle", "value"),
    prevent_initial_call=True,
)
@app.callback(
    Output("export-download", "data"),
    Input("export-button", "n_clicks"),
    State("ride-selector", "value"),
    State("dataset-selector", "value"),
    State("normalize-toggle", "value"),
    State("use-gyro-toggle", "value"),
    State("expected-curves-toggle", "value"),
    State("segmentation-mode-toggle", "value"),
    prevent_initial_call=True,
)
def export_rides(n_clicks, ride_names, dataset_name, normalize_mode,
                 use_gyro_mode, expected_mode, seg_mode):
    if not n_clicks or not ride_names or not dataset_name:
        return None
    data = load_rides(DATASETS[dataset_name])
    normalize = (normalize_mode == "normalized")
    use_gyro = (use_gyro_mode == "on")
    expected_n = EXPECTED_CURVES_PER_TRACK.get(dataset_name) if expected_mode == "auto" else None
    use_template = (seg_mode == "templated")

    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in ride_names:
            if name not in data:
                continue
            acc, gyro = data[name]["accel"], data[name].get("gyro")
            seg, _ = _segment(acc, gyro, use_gyro, expected_n, dataset_name, use_template)
            acc_df, gyro_df = build_export_dataframes(
                acc, gyro, segmentation=seg, normalize=normalize
            )
            stem = Path(name).stem
            zf.writestr(f"accel/{stem}.csv", acc_df.to_csv(index=False))
            if gyro_df is not None:
                zf.writestr(f"gyro/{stem}.csv", gyro_df.to_csv(index=False))
    buf.seek(0)
    return dict(
        content=base64.b64encode(buf.read()).decode(),
        filename=f"{dataset_name}_segmented.zip",
        base64=True,
    )


if __name__ == "__main__": app.run(debug=True, port=8050)