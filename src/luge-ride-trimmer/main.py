import sys
import os
import traceback

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton,
    QVBoxLayout, QFileDialog, QTextEdit,
    QComboBox, QSpinBox, QHBoxLayout, QDoubleSpinBox,
    QLineEdit, QProgressBar, QFrame, QSizePolicy,
    QScrollArea, QGroupBox, QCheckBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QTextCursor
import matplotlib as mpl

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas, NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

import helper_functions
from ride_trimmer import detect_indices, process_directory, compute_filtered
from helper_functions import RideDataLoader

THEMES = {
    "dark": {
        "BG_BASE": "#0d0f12",
        "BG_SURFACE": "#13161b",
        "BG_RAISED": "#1a1e25",
        "BG_INPUT": "#10131a",
        "BORDER": "#252a35",
        "ACCENT": "#3d8ef0",
        "ACCENT_DIM": "#1e4a8a",
        "SUCCESS": "#2ecc71",
        "WARNING": "#f39c12",
        "ERROR_C": "#e74c3c",
        "TEXT_PRI": "#dbeaff",
        "TEXT_SEC": "#cfe3ff",
        "TEXT_DIM": "#8a9ab5",
        "BTN_HOVER": "#21262f",
        "BTN_HOVER_BORDER": "#3a4150",
        "BTN_PRESSED": "#171b22",
        "PRIMARY_HOVER": "#5099f5",
        "PRIMARY_PRESSED": "#2a6abf",
        "PRIMARY_DISABLED_TEXT": "#4a6080",
        "INPUT_FOCUS_BG": "#0f1520",
        "RAW_LINE": "#94a6bd",
        "FULL_SIGNAL_LINE": "#2a3a50",
        "ERROR_LOG": "#e05555",
    },
    "light": {
        "BG_BASE": "#f4f6fa",
        "BG_SURFACE": "#ffffff",
        "BG_RAISED": "#eef1f7",
        "BG_INPUT": "#ffffff",
        "BORDER": "#d2d9e6",
        "ACCENT": "#2563c9",
        "ACCENT_DIM": "#b9cdf0",
        "SUCCESS": "#1e9e54",
        "WARNING": "#c87a0a",
        "ERROR_C": "#cc3a2c",
        "TEXT_PRI": "#1a2230",
        "TEXT_SEC": "#33415c",
        "TEXT_DIM": "#6b7a93",
        "BTN_HOVER": "#e3e9f3",
        "BTN_HOVER_BORDER": "#a9b8d0",
        "BTN_PRESSED": "#d6deec",
        "PRIMARY_HOVER": "#3573d9",
        "PRIMARY_PRESSED": "#1c52a8",
        "PRIMARY_DISABLED_TEXT": "#ffffff",
        "INPUT_FOCUS_BG": "#f0f5ff",
        "RAW_LINE": "#5a6b82",
        "FULL_SIGNAL_LINE": "#b8c4d6",
        "ERROR_LOG": "#cc3a2c",
    },
}

CURRENT_THEME = "dark"

TRANSLATIONS = {
    "EN": {
        "app_title": "Luge Ride Trimmer",
        "app_name": "LUGE RIDE TRIMMER",
        "theme": "THEME",
        "language": "LANG",
        "group_paths": "Data Paths",
        "group_filters": "Signal Filters",
        "group_actions": "Actions",
        "group_log": "Output Log",
        "btn_input": "INPUT",
        "btn_output": "OUTPUT",
        "not_selected": "Not selected",
        "folder_name": "FOLDER NAME",
        "folder_placeholder": "e.g.  trimmed_rides",
        "accelerometer": "ACCELEROMETER",
        "gyroscope": "GYROSCOPE",
        "filter": "FILTER",
        "window": "Window",
        "poly": "Poly",
        "load_preview": "Load Rides + Open Preview",
        "run_trimming": "▶   Run Trimming",
        "initialising": "Initialising …",
        "saved_fmt": "✓  {n} rides saved",
        "failed": "✗  Failed",
        "preview_title": "Signal Preview",
        "preview_header": "SIGNAL PREVIEW",
        "no_ride": "No ride loaded",
        "prev": "← PREV",
        "next": "NEXT →",
        "reset": "⤢ RESET",
        "auto_trim": "AUTO-TRIM",
        "axis": "AXIS",
        "title_raw": "RAW  ·  {axis}",
        "title_filtered": "FILTERED + TRIMMED  ·  {axis}",
        "xlabel_time": "time (s)",
        "lbl_full_signal": "full signal",
        "lbl_trim_window": "trim window",
        "lbl_full_no_trim": "full signal (no trim)",
        "lbl_start": "start  {t:.1f}s",
        "lbl_end": "end  {t:.1f}s",
        "log_input": "[INFO] Input {path}",
        "log_output": "[INFO] Output  {path}",
        "log_loading": "[INFO] Loading rides for preview ...",
        "log_select_input_first": "[WARN] Select an input folder first.",
        "log_load_failed": "[ERROR] Failed to load rides: {err}",
        "log_no_rides": "[WARN] No valid rides found in the selected folder.",
        "log_rides_loaded": "[OK] {n} rides loaded opening preview.",
        "log_no_input": "[WARN] No input folder selected.",
        "log_no_output": "[WARN] No output folder selected.",
        "log_empty_name": "[WARN] Output folder name is empty.",
        "log_mkdir_failed": "[ERROR] Could not create output directory: {err}",
        "log_starting": "[INFO] Starting {path}",
        "log_complete": "[OK] Complete {n} rides saved.",
        "log_unexpected": "[ERROR] Unexpected error:\n{tb}",
        "log_preview_err": "[WARN] Preview error for {name} ({axis}): {err}",
        "gyro_unavailable": "Gyroscope data not available for this ride.",
    },
    "LV": {
        "app_title": "Braucienu Apstrādes Rīks",
        "app_name": "BRAUCIENU APSTRĀDES RĪKS",
        "theme": "TĒMA",
        "language": "VAL.",
        "group_paths": "Datu Mape",
        "group_filters": "Signāla Filtri",
        "group_actions": "Darbības",
        "group_log": "Izvades žurnāls",
        "btn_input": "IEEJA",
        "btn_output": "IZEJA",
        "not_selected": "Nav izvēlēts",
        "folder_name": "MAPES NOSAUKUMS",
        "folder_placeholder": "piem.  apgriezti_braucieni",
        "accelerometer": "AKSELEROMETRS",
        "gyroscope": "ŽIROSKOPS",
        "filter": "FILTRS",
        "window": "Logs",
        "poly": "Pakāpe",
        "load_preview": "Ielādēt Braucienus + Atvērt Priekšskatījumu",
        "run_trimming": "Sākt Apgriešanu",
        "initialising": "Inicializē",
        "saved_fmt": "saglabāti {n} braucieni",
        "failed": "Neizdevās",
        "preview_title": "Signāla Priekšskatījums",
        "preview_header": "SIGNĀLA PRIEKŠSKATĪJUMS",
        "no_ride": "Brauciens nav ielādēts",
        "prev": "IEPR.",
        "next": "NĀK.",
        "reset": "ATIESTATĪT",
        "auto_trim": "AUTO-APGRIEŠANA",
        "axis": "ASS",
        "title_raw": "NEAPSTRĀDĀTS SIGNĀLS {axis}",
        "title_filtered": "FILTRĒTS + APGRIEZTS SIGNĀLS {axis}",
        "xlabel_time": "laiks (s)",
        "lbl_full_signal": "pilns signāls",
        "lbl_trim_window": "braciena signāls",
        "lbl_full_no_trim": "pilns signāls (bez apgriešanas)",
        "lbl_start": "brauciena sākums  {t:.1f}s",
        "lbl_end": "brauciena beigas  {t:.1f}s",
        "log_input": "[INFO] Ieeja {path}",
        "log_output": "[INFO] Izeja {path}",
        "log_loading": "[INFO] Ielādē braucienus priekšskatījumam ...",
        "log_select_input_first": "[WARN] Vispirms izvēlieties ieejas mapi.",
        "log_load_failed": "[ERROR] Neizdevās ielādēt braucienus: {err}",
        "log_no_rides": "[WARN] Izvēlētajā mapē nav korektu braucienu.",
        "log_rides_loaded": "[OK] Ielādēti {n} braucieni atver priekšskatījumu.",
        "log_no_input": "[WARN] Ieejas mape nav izvēlēta.",
        "log_no_output": "[WARN] Izejas mape nav izvēlēta.",
        "log_empty_name": "[WARN] Izejas mapes nosaukums ir tukšs.",
        "log_mkdir_failed": "[ERROR] Neizdevās izveidot izejas mapi: {err}",
        "log_starting": "[INFO] Sāk {path}",
        "log_complete": "[OK] Pabeigts saglabāti {n} braucieni.",
        "log_unexpected": "[ERROR] Neparedzēta kļūda:\n{tb}",
        "log_preview_err": "[WARN] Priekšskatījuma kļūda braucienam {name} ({axis}): {err}",
        "gyro_unavailable": "Šim braucienam žiroskopa dati nav pieejami.",
    },
}

CURRENT_LANG = "EN"


def tr(key, lang=None, **kwargs):
    lang = lang or CURRENT_LANG
    s = TRANSLATIONS.get(lang, TRANSLATIONS["EN"]).get(key, key)
    if kwargs:
        try:
            return s.format(**kwargs)
        except Exception:
            return s
    return s


def build_stylesheet(t):
    return f"""
QWidget {{
    background-color: {t['BG_BASE']};
    color: {t['TEXT_PRI']};
    font-family: "JetBrains Mono", "Fira Code", "Cascadia Code", "Consolas", monospace;
    font-size: 12px;
}}
QScrollArea, QScrollArea > QWidget > QWidget {{
    background-color: transparent;
    border: none;
}}
QGroupBox {{
    background-color: {t['BG_SURFACE']};
    border: 1px solid {t['BORDER']};
    border-radius: 6px;
    margin-top: 14px;
    padding: 14px 12px 10px 12px;
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 1.5px;
    color: {t['TEXT_SEC']};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    top: 6px;
    padding: 0 6px;
    background-color: {t['BG_BASE']};
    color: {t['TEXT_SEC']};
}}
QLabel {{
    background: transparent;
    color: {t['TEXT_SEC']};
    font-size: 11px;
}}
QLabel#path_label {{
    color: {t['TEXT_PRI']};
    font-size: 11px;
    padding: 6px 10px;
    background: {t['BG_INPUT']};
    border: 1px solid {t['BORDER']};
    border-radius: 4px;
}}
QPushButton {{
    background-color: {t['BG_RAISED']};
    color: {t['TEXT_PRI']};
    border: 1px solid {t['BORDER']};
    border-radius: 4px;
    padding: 7px 14px;
    font-size: 11px;
    font-weight: 500;
    min-height: 28px;
}}
QPushButton:hover {{
    background-color: {t['BTN_HOVER']};
    border-color: {t['BTN_HOVER_BORDER']};
    color: {t['TEXT_PRI']};
}}
QPushButton:pressed {{
    background-color: {t['BTN_PRESSED']};
    border-color: {t['ACCENT']};
}}
QPushButton:disabled {{
    background-color: {t['BG_INPUT']};
    color: {t['TEXT_DIM']};
    border-color: {t['TEXT_DIM']};
}}
QPushButton#primary_btn {{
    background-color: {t['ACCENT']};
    color: #ffffff;
    border: none;
    font-weight: 600;
    letter-spacing: 0.3px;
}}
QPushButton#primary_btn:hover {{
    background-color: {t['PRIMARY_HOVER']};
}}
QPushButton#primary_btn:pressed {{
    background-color: {t['PRIMARY_PRESSED']};
}}
QPushButton#primary_btn:disabled {{
    background-color: {t['ACCENT_DIM']};
    color: {t['PRIMARY_DISABLED_TEXT']};
}}
QPushButton#ghost_btn {{
    background: transparent;
    border: 1px solid {t['BORDER']};
    color: {t['TEXT_SEC']};
    font-size: 11px;
    padding: 5px 10px;
}}
QPushButton#ghost_btn:hover {{
    border-color: {t['ACCENT']};
    color: {t['ACCENT']};
    background: rgba(61,142,240,0.08);
}}
QLineEdit, QSpinBox, QDoubleSpinBox {{
    background-color: {t['BG_INPUT']};
    color: {t['TEXT_PRI']};
    border: 1px solid {t['BORDER']};
    border-radius: 4px;
    padding: 5px 8px;
    font-size: 12px;
    min-height: 26px;
    selection-background-color: {t['ACCENT_DIM']};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {t['ACCENT']};
    background-color: {t['INPUT_FOCUS_BG']};
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background: {t['BG_RAISED']};
    border: none;
    border-left: 1px solid {t['BORDER']};
    width: 18px;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {t['ACCENT_DIM']};
}}
QComboBox {{
    background-color: {t['BG_INPUT']};
    color: {t['TEXT_PRI']};
    border: 1px solid {t['BORDER']};
    border-radius: 4px;
    padding: 5px 8px;
    font-size: 12px;
    min-height: 26px;
}}
QComboBox:focus {{
    border-color: {t['ACCENT']};
}}
QComboBox::drop-down {{
    border: none;
    width: 28px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {t['TEXT_SEC']};
    width: 0; height: 0;
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {t['BG_RAISED']};
    color: {t['TEXT_PRI']};
    border: 1px solid {t['BORDER']};
    selection-background-color: {t['ACCENT_DIM']};
    outline: none;
    padding: 4px;
}}
QProgressBar {{
    background-color: {t['BG_INPUT']};
    border: 1px solid {t['BORDER']};
    border-radius: 4px;
    height: 10px;
    text-align: center;
    font-size: 10px;
    color: {t['TEXT_SEC']};
    letter-spacing: 0.5px;
}}
QProgressBar::chunk {{
    background-color: {t['ACCENT']};
    border-radius: 3px;
}}
QTextEdit#log_box {{
    background-color: {t['BG_INPUT']};
    color: {t['TEXT_SEC']};
    border: 1px solid {t['BORDER']};
    border-radius: 4px;
    padding: 8px;
    font-family: "JetBrains Mono", "Fira Code", "Cascadia Code", "Consolas", monospace;
    font-size: 11px;
    selection-background-color: {t['ACCENT_DIM']};
}}
QFrame#divider {{
    background-color: {t['BORDER']};
    max-height: 1px;
    border: none;
}}
QToolBar {{
    background-color: {t['BG_SURFACE']};
    border: 1px solid {t['BORDER']};
    border-radius: 4px;
    padding: 2px;
    spacing: 2px;
}}
QToolButton {{
    background-color: transparent;
    color: {t['TEXT_SEC']};
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 4px 6px;
    margin: 1px;
}}
QToolButton:hover {{
    background-color: {t['BG_RAISED']};
    border-color: {t['BORDER']};
    color: {t['ACCENT']};
}}
QToolButton:checked {{
    background-color: {t['ACCENT_DIM']};
    border-color: {t['ACCENT']};
    color: #ffffff;
}}
QScrollBar:vertical {{
    background: {t['BG_BASE']}; width: 6px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {t['BORDER']}; border-radius: 3px; min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: {t['TEXT_SEC']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: {t['BG_BASE']}; height: 6px;
}}
QScrollBar::handle:horizontal {{
    background: {t['BORDER']}; border-radius: 3px; min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{ background: {t['TEXT_SEC']}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
"""


def apply_mpl_theme(t):
    mpl.rcParams.update({
        "axes.facecolor": t["BG_SURFACE"],
        "figure.facecolor": t["BG_BASE"],
        "axes.edgecolor": t["BORDER"],
        "axes.labelcolor": t["TEXT_SEC"],
        "xtick.color": t["TEXT_DIM"],
        "ytick.color": t["TEXT_DIM"],
        "grid.color": t["BORDER"],
        "grid.linewidth": 0.6,
        "text.color": t["TEXT_PRI"],
        "axes.titlecolor": t["TEXT_PRI"],
        "legend.facecolor": t["BG_RAISED"],
        "legend.edgecolor": t["BORDER"],
        "legend.labelcolor": t["TEXT_PRI"],
    })


apply_mpl_theme(THEMES[CURRENT_THEME])


def _divider():
    f = QFrame()
    f.setObjectName("divider")
    f.setFrameShape(QFrame.Shape.HLine)
    return f


def _small_label(text, t):
    l = QLabel(text)
    l.setStyleSheet(f"color:{t['TEXT_DIM']}; font-size:11px; letter-spacing:0.8px;")
    return l


class TrimWorker(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)
    finished_signal = pyqtSignal(int)
    error_signal = pyqtSignal(str)

    def __init__(self, accel_dir, gyro_dir, output_dir, accel_params, gyro_params):
        super().__init__()
        self.accel_dir = accel_dir
        self.gyro_dir = gyro_dir
        self.output_dir = output_dir
        self.accel_params = accel_params
        self.gyro_params = gyro_params

    def run(self):
        helper_functions.set_log_callback(self.log_signal.emit)
        try:
            processed = process_directory(
                accel_dir=self.accel_dir,
                gyro_dir=self.gyro_dir,
                output_dir=self.output_dir,
                accel_params=self.accel_params,
                gyro_params=self.gyro_params,
                save_gyro=True,
                progress_callback=lambda cur, tot: self.progress_signal.emit(cur, tot),
            )
            self.finished_signal.emit(processed)
        except Exception:
            self.error_signal.emit(traceback.format_exc())
        finally:
            helper_functions.set_log_callback(None)


class PreviewWindow(QWidget):
    def __init__(self, get_data_callback, get_params_callback, log_fn,
                 get_theme_callback, get_lang_callback):
        super().__init__()
        self.get_data = get_data_callback
        self.get_params = get_params_callback
        self.log = log_fn
        self.get_theme = get_theme_callback
        self.get_lang = get_lang_callback
        self.rides = []
        self.index = 0

        self.setWindowTitle(tr("preview_title", self.get_lang()))
        self.resize(1340, 820)
        self.setStyleSheet(build_stylesheet(self.get_theme()))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setSpacing(12)

        self.title = QLabel(tr("preview_header", self.get_lang()))

        self.ride_label = QLabel(tr("no_ride", self.get_lang()))
        self.ride_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_row.addWidget(self.title)
        title_row.addWidget(self.ride_label, stretch=1)
        layout.addLayout(title_row)
        layout.addWidget(_divider())

        self.fig = Figure(figsize=(12, 7), tight_layout=True)
        self.canvas = FigureCanvas(self.fig)
        self.ax1 = self.fig.add_subplot(2, 1, 1)
        self.ax2 = self.fig.add_subplot(2, 1, 2)
        self.fig.tight_layout(pad=2.0)

        self.toolbar = NavigationToolbar(self.canvas, self)

        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas, stretch=1)

        self.canvas.mpl_connect('scroll_event', self._on_scroll)

        layout.addWidget(_divider())
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)

        self.prev_btn = QPushButton(tr("prev", self.get_lang()))
        self.prev_btn.setObjectName("ghost_btn")
        self.prev_btn.setFixedWidth(110)

        self.next_btn = QPushButton(tr("next", self.get_lang()))
        self.next_btn.setObjectName("ghost_btn")
        self.next_btn.setFixedWidth(110)

        self.reset_zoom_btn = QPushButton(tr("reset", self.get_lang()))
        self.reset_zoom_btn.setObjectName("ghost_btn")
        self.reset_zoom_btn.setFixedWidth(130)
        self.reset_zoom_btn.clicked.connect(self._reset_zoom)

        self.axis_lbl = QLabel(tr("axis", self.get_lang()))

        self.axis_box = QComboBox()
        self.axis_box.addItems(["ax", "ay", "az", "gx", "gy", "gz"])
        self.axis_box.setFixedWidth(80)
        self.axis_box.currentTextChanged.connect(self.update_plot)

        self.auto_detect_cb = QCheckBox(tr("auto_trim", self.get_lang()))
        self.auto_detect_cb.setChecked(True)
        self.auto_detect_cb.toggled.connect(self.update_plot)

        self.duration_label = QLabel("")

        ctrl.addWidget(self.prev_btn)
        ctrl.addWidget(self.next_btn)
        ctrl.addWidget(self.reset_zoom_btn)
        ctrl.addWidget(self.auto_detect_cb)
        ctrl.addStretch()
        ctrl.addWidget(self.duration_label)
        ctrl.addStretch()
        ctrl.addWidget(self.axis_lbl)
        ctrl.addWidget(self.axis_box)
        layout.addLayout(ctrl)

        self.prev_btn.clicked.connect(self.prev)
        self.next_btn.clicked.connect(self.next)

        self.apply_theme_styles()

    def apply_theme_styles(self):
        t = self.get_theme()
        self.setStyleSheet(build_stylesheet(t))
        self.title.setStyleSheet(
            f"color:{t['ACCENT']}; font-size:11px; font-weight:700; letter-spacing:2.5px;")
        self.ride_label.setStyleSheet(f"color:{t['TEXT_PRI']}; font-size:12px;")
        self.axis_lbl.setStyleSheet(f"color:{t['TEXT_DIM']}; font-size:10px; letter-spacing:1px;")
        self.auto_detect_cb.setStyleSheet(
            f"color:{t['TEXT_DIM']}; font-size:10px; letter-spacing:1px; spacing:6px;")
        self.duration_label.setStyleSheet(f"""
            color: {t['SUCCESS']};
            font-size: 11px;
            padding: 4px 10px;
            background: rgba(46,204,113,0.08);
            border: 1px solid rgba(46,204,113,0.25);
            border-radius: 3px;
        """)
        self.toolbar.setStyleSheet(f"""
            QToolBar {{
                background-color: {t['BG_SURFACE']};
                border: 1px solid {t['BORDER']};
                border-radius: 4px;
                padding: 2px;
            }}
            QToolBar QLabel {{
                color: {t['TEXT_DIM']};
                font-size: 10px;
                padding: 0 6px;
            }}
        """)

    def refresh_theme(self):
        self.apply_theme_styles()
        if self.rides:
            self.update_plot()

    def refresh_language(self):
        lang = self.get_lang()
        self.setWindowTitle(tr("preview_title", lang))
        self.title.setText(tr("preview_header", lang))
        if not self.rides:
            self.ride_label.setText(tr("no_ride", lang))
        self.prev_btn.setText(tr("prev", lang))
        self.next_btn.setText(tr("next", lang))
        self.reset_zoom_btn.setText(tr("reset", lang))
        self.axis_lbl.setText(tr("axis", lang))
        self.auto_detect_cb.setText(tr("auto_trim", lang))
        if self.rides:
            self.update_plot()

    def _on_scroll(self, event):
        if event.inaxes is None:
            return
        ax = event.inaxes
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        xdata = event.xdata
        ydata = event.ydata
        if xdata is None or ydata is None:
            return
        scale = 1.2 if event.button == 'down' else 1 / 1.2
        new_width = (xlim[1] - xlim[0]) * scale
        new_height = (ylim[1] - ylim[0]) * scale
        relx = (xlim[1] - xdata) / (xlim[1] - xlim[0])
        rely = (ylim[1] - ydata) / (ylim[1] - ylim[0])
        ax.set_xlim([xdata - new_width * (1 - relx), xdata + new_width * relx])
        ax.set_ylim([ydata - new_height * (1 - rely), ydata + new_height * rely])
        self.canvas.draw_idle()

    def _reset_zoom(self):
        self.update_plot()

    def load(self, rides):
        self.rides = rides
        self.index = 0
        self.update_plot()

    def next(self):
        if self.rides:
            self.index = (self.index + 1) % len(self.rides)
            self.update_plot()

    def prev(self):
        if self.rides:
            self.index = (self.index - 1) % len(self.rides)
            self.update_plot()

    def update_plot(self):
        if not self.rides:
            return

        t = self.get_theme()
        lang = self.get_lang()
        name, acc, gyro = self.rides[self.index]
        axis = self.axis_box.currentText()

        self.ride_label.setText(
            f"<span style='color:{t['TEXT_DIM']}; font-size:10px;'>{self.index + 1} / {len(self.rides)}</span>"
            f"&nbsp;&nbsp;<span style='color:{t['TEXT_PRI']}'>{name}</span>"
        )
        self.ride_label.setTextFormat(Qt.TextFormat.RichText)

        params = self.get_params()

        auto_on = self.auto_detect_cb.isChecked()

        try:
            t_acc, ax, ay, az, t_gyro, gx, gy, gz = compute_filtered(
                acc, gyro,
                accel_filter=params["accel_filter"],
                gyro_filter=params["gyro_filter"],
            )
            if auto_on:
                start, end = detect_indices(t_acc, ax, ay, az, t_gyro, gx, gy, gz)
                t_start = t_acc[start]
                t_end = t_acc[end - 1]
            else:
                t_start = t_acc[0]
                t_end = t_acc[-1]

            if axis in ["ax", "ay", "az"]:
                raw = acc[:, {"ax": 1, "ay": 2, "az": 3}[axis]]
                filtered_full = {"ax": ax, "ay": ay, "az": az}[axis]
                t_raw = t_acc
                mask = (t_acc >= t_start) & (t_acc <= t_end)
                t_trim = t_acc[mask]
            else:
                if gyro is None or len(gyro) == 0:
                    raise ValueError(tr("gyro_unavailable", lang))
                raw = gyro[:, {"gx": 1, "gy": 2, "gz": 3}[axis]]
                filtered_full = {"gx": gx, "gy": gy, "gz": gz}[axis]
                t_raw = t_gyro
                mask = (t_gyro >= t_start) & (t_gyro <= t_end)
                t_trim = t_gyro[mask]

            offset = t_raw[0]
            t_raw_plot = t_raw - offset
            t_trim_plot = t_trim - offset
            start_plot = t_start - offset
            end_plot = t_end - offset
            duration = t_end - t_start

        except Exception as e:
            self.fig.set_facecolor(t["BG_BASE"])
            for ax_obj in (self.ax1, self.ax2):
                ax_obj.clear()
                ax_obj.set_facecolor(t["BG_SURFACE"])
            self.ax2.text(0.5, 0.5, str(e), transform=self.ax2.transAxes,
                          color=t["ERROR_C"], ha="center", va="center", fontsize=11)
            self.canvas.draw()
            self.log(tr("log_preview_err", lang, name=name, axis=axis, err=e))
            return

        self.duration_label.setText(f"\u23f1  {duration:.2f} s")

        self.fig.set_facecolor(t["BG_BASE"])
        for ax_obj in (self.ax1, self.ax2):
            ax_obj.clear()
            ax_obj.set_facecolor(t["BG_SURFACE"])
            ax_obj.tick_params(colors=t["TEXT_DIM"], labelsize=11)
            for spine in ax_obj.spines.values():
                spine.set_edgecolor(t["BORDER"])

        self.ax1.plot(t_raw_plot, raw, color=t["RAW_LINE"], linewidth=1.0, alpha=1.0)
        self.ax1.set_title(tr("title_raw", lang, axis=axis), fontsize=14, loc="left",
                           color=t["TEXT_SEC"], fontweight="bold", pad=8)
        self.ax1.set_ylabel(axis, color=t["TEXT_DIM"], fontsize=12)
        self.ax1.grid(True, alpha=0.3, linestyle=":")

        if auto_on:
            self.ax2.plot(t_raw_plot, filtered_full,
                          color=t["FULL_SIGNAL_LINE"], linewidth=0.7, alpha=0.6,
                          label=tr("lbl_full_signal", lang))
            self.ax2.plot(t_trim_plot, filtered_full[mask],
                          color=t["ACCENT"], linewidth=1.4,
                          label=tr("lbl_trim_window", lang))
            self.ax2.axvline(start_plot, color=t["SUCCESS"], linestyle="--", linewidth=1.1,
                             alpha=0.85, label=tr("lbl_start", lang, t=start_plot))
            self.ax2.axvline(end_plot, color=t["ERROR_C"], linestyle="--", linewidth=1.1,
                             alpha=0.85, label=tr("lbl_end", lang, t=end_plot))
            self.ax2.axvspan(start_plot, end_plot, alpha=0.06, color=t["ACCENT"], linewidth=0)
        else:
            self.ax2.plot(t_raw_plot, filtered_full,
                          color=t["ACCENT"], linewidth=1.0,
                          label=tr("lbl_full_no_trim", lang))
        self.ax2.set_title(tr("title_filtered", lang, axis=axis), fontsize=14, loc="left",
                           color=t["TEXT_SEC"], fontweight="bold", pad=8)
        self.ax2.set_ylabel(axis, color=t["TEXT_DIM"], fontsize=12)
        self.ax2.set_xlabel(tr("xlabel_time", lang), color=t["TEXT_DIM"], fontsize=12)
        self.ax2.grid(True, alpha=0.3, linestyle=":")
        legend = self.ax2.legend(fontsize=11, framealpha=0.85,
                                 facecolor=t["BG_RAISED"], edgecolor=t["BORDER"])
        for text in legend.get_texts():
            text.set_color(t["TEXT_SEC"])

        self.fig.tight_layout(pad=2.0)
        self.canvas.draw()


class TrimmingApp(QWidget):
    def __init__(self):
        super().__init__()
        self.theme_name = CURRENT_THEME
        self.lang = CURRENT_LANG
        self.input_dir = ""
        self.output_dir = ""
        self.rides = []
        self._worker = None

        self.setWindowTitle(tr("app_title", self.lang))
        self.setMinimumWidth(540)
        self.setMinimumHeight(920)
        self.setStyleSheet(build_stylesheet(self.theme()))

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.header = QWidget()
        self.header.setFixedHeight(52)
        hl = QHBoxLayout(self.header)
        hl.setContentsMargins(16, 0, 16, 0)

        self.app_name = QLabel(tr("app_name", self.lang))

        self.lang_box = QComboBox()
        self.lang_box.addItems(["EN", "LV"])
        self.lang_box.setFixedWidth(70)
        self.lang_box.setCurrentText(self.lang)
        self.lang_box.currentTextChanged.connect(self._on_lang_change)

        self.theme_box = QComboBox()
        self.theme_box.addItems(["DARK", "LIGHT"])
        self.theme_box.setFixedWidth(100)
        self.theme_box.setCurrentText(self.theme_name.upper())
        self.theme_box.currentTextChanged.connect(self._on_theme_change)

        self.lang_lbl = QLabel(tr("language", self.lang))
        self.theme_lbl = QLabel(tr("theme", self.lang))

        hl.addWidget(self.app_name)
        hl.addStretch()
        hl.addWidget(self.lang_lbl)
        hl.addWidget(self.lang_box)
        hl.addSpacing(10)
        hl.addWidget(self.theme_lbl)
        hl.addWidget(self.theme_box)
        root.addWidget(self.header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(scroll)

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        scroll.setWidget(inner)

        self.io_group = QGroupBox(tr("group_paths", self.lang))
        io_layout = QVBoxLayout(self.io_group)
        io_layout.setSpacing(8)

        self.input_btn = QPushButton(tr("btn_input", self.lang))
        self.input_btn.setObjectName("ghost_btn")
        self.input_btn.setFixedWidth(90)
        self.input_btn.clicked.connect(self.select_input)
        self.input_label = QLabel(tr("not_selected", self.lang))
        self.input_label.setObjectName("path_label")
        self.input_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.input_label.setMinimumHeight(30)
        row_in = QHBoxLayout()
        row_in.setSpacing(8)
        row_in.addWidget(self.input_btn)
        row_in.addWidget(self.input_label)
        io_layout.addLayout(row_in)

        self.output_btn = QPushButton(tr("btn_output", self.lang))
        self.output_btn.setObjectName("ghost_btn")
        self.output_btn.setFixedWidth(90)
        self.output_btn.clicked.connect(self.select_output)
        self.output_label = QLabel(tr("not_selected", self.lang))
        self.output_label.setObjectName("path_label")
        self.output_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.output_label.setMinimumHeight(30)
        row_out = QHBoxLayout()
        row_out.setSpacing(8)
        row_out.addWidget(self.output_btn)
        row_out.addWidget(self.output_label)
        io_layout.addLayout(row_out)

        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        self.folder_name_lbl = _small_label(tr("folder_name", self.lang), self.theme())
        self.folder_name_lbl.setFixedWidth(140)
        self.output_name = QLineEdit()
        self.output_name.setPlaceholderText(tr("folder_placeholder", self.lang))
        name_row.addWidget(self.folder_name_lbl)
        name_row.addWidget(self.output_name)
        io_layout.addLayout(name_row)
        layout.addWidget(self.io_group)

        self.filter_group = QGroupBox(tr("group_filters", self.lang))
        fl = QVBoxLayout(self.filter_group)
        fl.setSpacing(10)

        self.accel_header = _small_label(tr("accelerometer", self.lang), self.theme())
        fl.addWidget(self.accel_header)
        accel_top = QHBoxLayout()
        accel_top.setSpacing(8)
        self.accel_filter_lbl = _small_label(tr("filter", self.lang), self.theme())
        accel_top.addWidget(self.accel_filter_lbl)
        self.filter_box = QComboBox()
        self.filter_box.addItems(["none", "kalman", "savgol"])
        self.filter_box.currentTextChanged.connect(self.update_filter_ui)
        accel_top.addWidget(self.filter_box)
        fl.addLayout(accel_top)

        self.kalman_q = QDoubleSpinBox()
        self.kalman_q.setRange(1e-6, 1e6)
        self.kalman_q.setValue(1e-1)
        self.kalman_q.setDecimals(6)
        self.kalman_r = QDoubleSpinBox()
        self.kalman_r.setRange(1e-6, 1e6)
        self.kalman_r.setValue(1e-4)
        self.kalman_r.setDecimals(6)
        self.kalman_widget = QWidget()
        kl = QHBoxLayout(self.kalman_widget)
        kl.setContentsMargins(0, 0, 0, 0)
        kl.setSpacing(8)
        kl.addWidget(_small_label("Q", self.theme()))
        kl.addWidget(self.kalman_q)
        kl.addWidget(_small_label("R", self.theme()))
        kl.addWidget(self.kalman_r)
        fl.addWidget(self.kalman_widget)

        self.savgol_window = QSpinBox()
        self.savgol_window.setRange(3, 15000)
        self.savgol_window.setValue(500)
        self.savgol_poly = QSpinBox()
        self.savgol_poly.setRange(1, 1000)
        self.savgol_poly.setValue(4)
        self.savgol_widget = QWidget()
        sl = QHBoxLayout(self.savgol_widget)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(8)
        self.savgol_window_lbl = _small_label(tr("window", self.lang), self.theme())
        self.savgol_poly_lbl = _small_label(tr("poly", self.lang), self.theme())
        sl.addWidget(self.savgol_window_lbl)
        sl.addWidget(self.savgol_window)
        sl.addWidget(self.savgol_poly_lbl)
        sl.addWidget(self.savgol_poly)
        fl.addWidget(self.savgol_widget)

        fl.addWidget(_divider())

        self.gyro_header = _small_label(tr("gyroscope", self.lang), self.theme())
        fl.addWidget(self.gyro_header)
        gyro_top = QHBoxLayout()
        gyro_top.setSpacing(8)
        self.gyro_filter_lbl = _small_label(tr("filter", self.lang), self.theme())
        gyro_top.addWidget(self.gyro_filter_lbl)
        self.gyro_filter_box = QComboBox()
        self.gyro_filter_box.addItems(["none", "kalman", "savgol"])
        self.gyro_filter_box.currentTextChanged.connect(self.update_filter_ui)
        gyro_top.addWidget(self.gyro_filter_box)
        fl.addLayout(gyro_top)

        self.gyro_kalman_q = QDoubleSpinBox()
        self.gyro_kalman_q.setRange(1e-6, 1e6)
        self.gyro_kalman_q.setValue(1e-1)
        self.gyro_kalman_q.setDecimals(6)
        self.gyro_kalman_r = QDoubleSpinBox()
        self.gyro_kalman_r.setRange(1e-6, 1e6)
        self.gyro_kalman_r.setValue(1e-4)
        self.gyro_kalman_r.setDecimals(6)
        self.gyro_kalman_widget = QWidget()
        gkl = QHBoxLayout(self.gyro_kalman_widget)
        gkl.setContentsMargins(0, 0, 0, 0)
        gkl.setSpacing(8)
        gkl.addWidget(_small_label("Q", self.theme()))
        gkl.addWidget(self.gyro_kalman_q)
        gkl.addWidget(_small_label("R", self.theme()))
        gkl.addWidget(self.gyro_kalman_r)
        fl.addWidget(self.gyro_kalman_widget)

        self.gyro_savgol_window = QSpinBox()
        self.gyro_savgol_window.setRange(3, 15000)
        self.gyro_savgol_window.setValue(50)
        self.gyro_savgol_poly = QSpinBox()
        self.gyro_savgol_poly.setRange(1, 1000)
        self.gyro_savgol_poly.setValue(4)
        self.gyro_savgol_widget = QWidget()
        gsl = QHBoxLayout(self.gyro_savgol_widget)
        gsl.setContentsMargins(0, 0, 0, 0)
        gsl.setSpacing(8)
        self.gyro_savgol_window_lbl = _small_label(tr("window", self.lang), self.theme())
        self.gyro_savgol_poly_lbl = _small_label(tr("poly", self.lang), self.theme())
        gsl.addWidget(self.gyro_savgol_window_lbl)
        gsl.addWidget(self.gyro_savgol_window)
        gsl.addWidget(self.gyro_savgol_poly_lbl)
        gsl.addWidget(self.gyro_savgol_poly)
        fl.addWidget(self.gyro_savgol_widget)

        layout.addWidget(self.filter_group)

        self.act_group = QGroupBox(tr("group_actions", self.lang))
        al = QVBoxLayout(self.act_group)
        al.setSpacing(8)

        self.load_btn = QPushButton(tr("load_preview", self.lang))
        self.load_btn.setObjectName("ghost_btn")
        self.load_btn.setMinimumHeight(34)
        self.load_btn.clicked.connect(self.open_preview)

        self.run_btn = QPushButton(tr("run_trimming", self.lang))
        self.run_btn.setObjectName("primary_btn")
        self.run_btn.setMinimumHeight(38)
        self.run_btn.clicked.connect(self.run_trimming)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(12)

        al.addWidget(self.load_btn)
        al.addWidget(self.run_btn)
        al.addWidget(self.progress_bar)
        layout.addWidget(self.act_group)

        self.log_group = QGroupBox(tr("group_log", self.lang))
        ll = QVBoxLayout(self.log_group)
        ll.setContentsMargins(8, 8, 8, 8)

        self.log_box = QTextEdit()
        self.log_box.setObjectName("log_box")
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(100)
        self.log_box.setMaximumHeight(200)
        ll.addWidget(self.log_box)
        layout.addWidget(self.log_group)
        layout.addStretch()

        helper_functions.set_log_callback(self.append_log)
        self.preview = PreviewWindow(self.get_current_data, self.get_params,
                                     self.append_log, self.theme, self.get_lang)
        self.update_filter_ui()
        self._apply_header_styles()

    def theme(self):
        return THEMES[self.theme_name]

    def get_lang(self):
        return self.lang

    def _apply_header_styles(self):
        t = self.theme()
        self.header.setStyleSheet(
            f"background-color:{t['BG_SURFACE']}; border-bottom:1px solid {t['BORDER']};")
        self.app_name.setStyleSheet(
            f"color:{t['ACCENT']}; font-size:13px; font-weight:700; letter-spacing:3px;")
        self.lang_lbl.setStyleSheet(f"color:{t['TEXT_DIM']}; font-size:10px; letter-spacing:1px;")
        self.theme_lbl.setStyleSheet(f"color:{t['TEXT_DIM']}; font-size:10px; letter-spacing:1px;")

    def _on_theme_change(self, name):
        self.theme_name = name.lower()
        global CURRENT_THEME
        CURRENT_THEME = self.theme_name
        apply_mpl_theme(self.theme())
        self.setStyleSheet(build_stylesheet(self.theme()))
        self._apply_header_styles()
        self.preview.refresh_theme()

    def _on_lang_change(self, name):
        self.lang = name
        global CURRENT_LANG
        CURRENT_LANG = self.lang
        self._retranslate_ui()
        self.preview.refresh_language()

    def _retranslate_ui(self):
        lang = self.lang
        self.setWindowTitle(tr("app_title", lang))
        self.app_name.setText(tr("app_name", lang))
        self.lang_lbl.setText(tr("language", lang))
        self.theme_lbl.setText(tr("theme", lang))
        self.io_group.setTitle(tr("group_paths", lang))
        self.filter_group.setTitle(tr("group_filters", lang))
        self.act_group.setTitle(tr("group_actions", lang))
        self.log_group.setTitle(tr("group_log", lang))
        self.input_btn.setText(tr("btn_input", lang))
        self.output_btn.setText(tr("btn_output", lang))
        not_selected_values = {TRANSLATIONS["EN"]["not_selected"],
                               TRANSLATIONS["LV"]["not_selected"]}
        if self.input_label.text() in not_selected_values:
            self.input_label.setText(tr("not_selected", lang))
        if self.output_label.text() in not_selected_values:
            self.output_label.setText(tr("not_selected", lang))
        self.folder_name_lbl.setText(tr("folder_name", lang))
        self.output_name.setPlaceholderText(tr("folder_placeholder", lang))
        self.accel_header.setText(tr("accelerometer", lang))
        self.gyro_header.setText(tr("gyroscope", lang))
        self.accel_filter_lbl.setText(tr("filter", lang))
        self.gyro_filter_lbl.setText(tr("filter", lang))
        self.savgol_window_lbl.setText(tr("window", lang))
        self.savgol_poly_lbl.setText(tr("poly", lang))
        self.gyro_savgol_window_lbl.setText(tr("window", lang))
        self.gyro_savgol_poly_lbl.setText(tr("poly", lang))
        self.load_btn.setText(tr("load_preview", lang))
        self.run_btn.setText(tr("run_trimming", lang))

    def append_log(self, msg: str):
        t = self.theme()
        cursor = self.log_box.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        dash = "\u2500"
        if msg.strip().startswith(dash) or msg.strip() == dash:
            line = dash * 62
            cursor.insertHtml(f'<span style="color:{t["BORDER"]};">{line}</span><br>')
            self.log_box.setTextCursor(cursor)
            self.log_box.ensureCursorVisible()
            QApplication.processEvents()
            return

        if msg.startswith("[ERROR]"):
            color, tag, rest = t["ERROR_LOG"], "[ERROR]", msg[7:]
        elif msg.startswith("[WARN]"):
            color, tag, rest = t["WARNING"], "[WARN] ", msg[6:]
        elif msg.startswith("[OK]"):
            color, tag, rest = t["SUCCESS"], "[ OK ] ", msg[4:]
        else:
            color, tag = t["TEXT_SEC"], "[INFO] "
            rest = msg[6:] if msg.startswith("[INFO]") else msg

        safe = rest.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        cursor.insertHtml(
            f'<span style="color:{t["TEXT_DIM"]};">{tag}</span>'
            f'<span style="color:{color};">{safe}</span><br>'
        )
        self.log_box.setTextCursor(cursor)
        self.log_box.ensureCursorVisible()
        QApplication.processEvents()

    def update_filter_ui(self):
        f = self.filter_box.currentText()
        gf = self.gyro_filter_box.currentText()
        self.kalman_widget.setVisible(f == "kalman")
        self.savgol_widget.setVisible(f == "savgol")
        self.gyro_kalman_widget.setVisible(gf == "kalman")
        self.gyro_savgol_widget.setVisible(gf == "savgol")

    def select_input(self):
        f = QFileDialog.getExistingDirectory(self)
        if f:
            self.input_dir = f
            self.input_label.setText(f if len(f) < 55 else "\u2026" + f[-52:])
            self.append_log(tr("log_input", self.lang, path=f))

    def select_output(self):
        f = QFileDialog.getExistingDirectory(self)
        if f:
            self.output_dir = f
            self.output_label.setText(f if len(f) < 55 else "\u2026" + f[-52:])
            self.append_log(tr("log_output", self.lang, path=f))

    def get_params(self):
        f = self.filter_box.currentText()
        accel_params = {"filter_type": "none"}
        if f == "kalman":
            accel_params = {"filter_type": "kalman",
                            "q": self.kalman_q.value(), "r": self.kalman_r.value()}
        elif f == "savgol":
            win = self.savgol_window.value()
            poly = self.savgol_poly.value()
            if win % 2 == 0: win += 1
            if poly >= win:  poly = win - 1
            accel_params = {"filter_type": "savgol", "savgol_window": win, "savgol_poly": poly}

        gf = self.gyro_filter_box.currentText()
        gyro_params = {"filter_type": "none"}
        if gf == "kalman":
            gyro_params = {"filter_type": "kalman",
                           "q": self.gyro_kalman_q.value(), "r": self.gyro_kalman_r.value()}
        elif gf == "savgol":
            win = self.gyro_savgol_window.value()
            poly = self.gyro_savgol_poly.value()
            if win % 2 == 0: win += 1
            if poly >= win:  poly = win - 1
            gyro_params = {"filter_type": "savgol", "savgol_window": win, "savgol_poly": poly}

        return {"accel_filter": accel_params, "gyro_filter": gyro_params}

    def resolve_input_structure(self):
        accel_dir = os.path.join(self.input_dir, "accel")
        gyro_dir = os.path.join(self.input_dir, "gyro")
        if os.path.isdir(accel_dir):
            return accel_dir, (gyro_dir if os.path.isdir(gyro_dir) else None)
        return self.input_dir, self.input_dir

    def get_current_data(self):
        return self.rides

    def open_preview(self):
        if not self.input_dir:
            self.append_log(tr("log_select_input_first", self.lang))
            return
        accel_dir, gyro_dir = self.resolve_input_structure()
        self.append_log(tr("log_loading", self.lang))
        try:
            acc = dict(RideDataLoader(accel_dir).load_rides())
            gyro = {}
            if gyro_dir:
                gyro = dict(RideDataLoader(gyro_dir).load_rides())
        except Exception as e:
            self.append_log(tr("log_load_failed", self.lang, err=e))
            return

        all_keys = set(acc.keys()) | set(gyro.keys())
        self.rides = [
            (k, acc.get(k), gyro.get(k))
            for k in sorted(all_keys) if acc.get(k) is not None
        ]
        if not self.rides:
            self.append_log(tr("log_no_rides", self.lang))
            return

        self.append_log(tr("log_rides_loaded", self.lang, n=len(self.rides)))
        self.preview.load(self.rides)
        self.preview.show()
        self.preview.raise_()

    def run_trimming(self):
        if not self.input_dir:
            self.append_log(tr("log_no_input", self.lang))
            return
        if not self.output_dir:
            self.append_log(tr("log_no_output", self.lang))
            return
        if not self.output_name.text().strip():
            self.append_log(tr("log_empty_name", self.lang))
            return

        accel_dir, gyro_dir = self.resolve_input_structure()
        final_output_dir = os.path.join(self.output_dir, self.output_name.text().strip())

        try:
            os.makedirs(final_output_dir, exist_ok=True)
        except Exception as e:
            self.append_log(tr("log_mkdir_failed", self.lang, err=e))
            return

        params = self.get_params()
        self.append_log("\u2500")
        self.append_log(tr("log_starting", self.lang, path=final_output_dir))

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(tr("initialising", self.lang))
        self.run_btn.setEnabled(False)

        self._worker = TrimWorker(
            accel_dir=accel_dir, gyro_dir=gyro_dir,
            output_dir=final_output_dir,
            accel_params=params["accel_filter"],
            gyro_params=params["gyro_filter"],
        )
        self._worker.log_signal.connect(self.append_log)
        self._worker.progress_signal.connect(self._on_progress)
        self._worker.finished_signal.connect(self._on_trimming_done)
        self._worker.error_signal.connect(self._on_trimming_error)
        self._worker.start()

    def _on_progress(self, current: int, total: int):
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
            self.progress_bar.setFormat(f"{current} / {total}")

    def _on_trimming_done(self, processed: int):
        self.progress_bar.setFormat(tr("saved_fmt", self.lang, n=processed))
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.run_btn.setEnabled(True)
        self.append_log(tr("log_complete", self.lang, n=processed))
        self.append_log("\u2500")

    def _on_trimming_error(self, tb: str):
        self.progress_bar.setFormat(tr("failed", self.lang))
        self.run_btn.setEnabled(True)
        self.append_log(tr("log_unexpected", self.lang, tb=tb))
        self.append_log("\u2500")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = TrimmingApp()
    w.show()
    sys.exit(app.exec())