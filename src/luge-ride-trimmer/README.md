# Luge Ride Trimming Tool

A PyQt6-based desktop application for visualizing, filtering, and trimming ride sensor data (accelerometer and gyroscope). The tool provides an interactive preview to inspect signals and automatically detect meaningful segments before exporting trimmed datasets.

---

## Installation & Launch

### Requirements

- Python 3.9 or newer

### 1. Clone the repository

```bash
git clone https://github.com/elomage/vppsports.git
cd luge-ride-trimmer
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv .venv
```

Activate it:

| Platform | Command |
|----------|---------|
| macOS / Linux | `source .venv/bin/activate` |
| Windows (CMD) | `.venv\Scripts\activate.bat` |
| Windows (PowerShell) | `.venv\Scripts\Activate.ps1` |

### 3. Install dependencies

```bash
pip install PyQt6 numpy scipy pandas matplotlib
```

### 4. Launch the app

```bash
python main.py
```

---

## Features

- **Load** ride data from structured folders
- **Visualize** raw vs. filtered signals interactively
- **Filter** signals using configurable algorithms:
    - Kalman filter
    - Savitzky–Golay filter
- **Detect** ride segments automatically
- **Preview** trimming results before processing
- **Export** trimmed data via batch processing

---

## Input Data Format

The app supports two folder structures:

**Option 1 — Structured (recommended)**

```
input_folder/
├── accel/
│   ├── ride1.txt
│   ├── ride2.txt
│   └── ...
└── gyro/
    ├── ride1.txt
    ├── ride2.txt
    └── ...
```

**Option 2 — Flat**

```
input_folder/
├── ride1_accel.txt
├── ride1_gyro.txt
└── ...
```

---

## Usage

### 1. Select Input Folder

Choose the directory containing your ride data.

### 2. Select Output Folder

Choose where processed files will be saved.

### 3. Configure Output Name

Enter a name for the output dataset, e.g. `trimmed_rides`.

### 4. Choose Filters

**Accelerometer Filter** — select one of:

| Option | Parameters |
|--------|------------|
| `none` | — |
| `kalman` | Q (process noise), R (measurement noise) |
| `savgol` | Window length, polynomial order |

**Gyroscope Filter** — same options as above.

### 5. Preview Rides

1. Click **Load Rides + Open Preview**
2. Navigate between rides using **← Prev** / **Next →**
3. Select an axis to inspect: `ax`, `ay`, `az`, `gx`, `gy`, `gz`

The preview displays:
- Raw signal
- Filtered signal
- Detected trim window with start/end markers

### 6. Run Trimming

Click **Run Trimming**. Processed files are saved to the output folder you selected in step 2.

---

## Notes

- Gyroscope data is optional but recommended. If missing, only accelerometer signals are used for segment detection.
- Invalid filter parameters are automatically corrected where possible.