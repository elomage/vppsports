# Luge Data Analysis Suite: Scripts & Programs Documentation

This folder contains programs and scripts used for processing and analyzing luge performance data, primarily focusing on strain gauge data (measuring steering forces/vibrations) and accelerometer data.

The general workflow consists of:
1. **Data Conversion**: Converting raw binary logging data (`.bin`) from ADCs (Analog-to-Digital Converters) and accelerometers into readable text files (`.txt`).
2. **Analysis & Synchronization**: Running Python scripts to filter, synchronize, analyze, and visualize the steering curves, frequency spectra, stability, and sensor fusion.

---

## Data Conversion (C Programs)

These programs compile and run on the host computer to parse raw binary data logged during rides into a standard text format: `Raw=X, Time=Y` (where `X` is the ADC reading and `Y` is the timestamp in microseconds).

### [checkFile.c]
- **Description**: Handles conversion for a single ADC. Supports either a single channel (mode 1) or dual channels (mode 2) interleaved.
- **Outputs**: `output1.txt` (channel 0) and `output2.txt` (channel 1).

### [checkFile2.c]
- **Description**: Converts binary files recorded from two ADCs with one channel each, packed in a paired structure (`timestamp`, `raw_value1`, `raw_value2`).
- **Outputs**: `output1.txt` and `output2.txt`.

### [checkfile3.c]
- **Description**: Converts binary files recorded from three ADCs (`timestamp`, `raw_value1`, `raw_value2`, `raw_value3`).
- **Outputs**: `output1.txt`, `output2.txt`, and `output3.txt`.

### [checkfile4.c]
- **Description**: Converts binary files recorded from four ADCs (`timestamp`, `raw_value1`, `raw_value2`, `raw_value3`, `raw_value4`).
- **Outputs**: `output1.txt`, `output2.txt`, `output3.txt`, and `output4.txt`.

### [checkFile8.c]
- **Description**: Converts binary files recorded from four ADCs, each measuring two channels (8 channels total).
- **Outputs**: `output1.txt` through `output8.txt`.
---

## Data Analysis & Visualization

These scripts process the luge data to find steering, vibrations, corellation with the accelerometer data. Each script works witht the unchanged converted data

### [analyze_curves.py]
- **Description**: Extracts and analyzes individual steering curves (turns) from strain gauge logs. It applies a Butterworth band-pass filter (standard: 0.05 Hz to 50 Hz) to isolate steering signals, detects peaks, and calculates metrics such as amplitude, crest factor, energy, and curve duration. It can compare two runs side-by-side by aligning their peaks.
- EXAMPLE OF USED COMMANDS:
  ```
  python  analyze_curves.py data1 data2 --hp 0.05 --lp 50 --peak-mode max_pos \
  --before -30 --after 25 --compare --plot --peak-height -25000
  ```

###  [frequency_analysis.py]
- **Description**: Performs frequency domain analysis including Fast Fourier Transform (FFT), Power Spectral Density (PSD) using Welch's method, and Spectrograms. Used to analyze steering smoothness, identifying low-frequency proactive steering vs. high-frequency reactive steering (vibrations/jitter > 5 Hz).
-  EXAMPLE OF USED COMMANDS:
  ```
    python frequency_analysis.py --ride1 55 --ride2 56 --channel 2 --before 30 --after 25 --peak-mode max
  ```
###  [sensor_fusion_sync.py]
- **Description**: Synchronizes and fuses high-rate binary accelerometer data with low-rate strain gauge text data. Uses cross-correlation of vertical forces (Z-axis acceleration vs. Y-axis strain gauges) to align timestamps exactly.
-  EXAMPLE OF USED COMMANDS:
  ```
  python sensor_fusion_sync.py --strain data_strain.txt \
  --strain-start 52.2 --strain-end 107.2 \                     --these are used from the curve and frequency analysis since we marked this interval as ride
  --accel-start 50 --accel-end 120
  ```

###  [correlate_channels.py]
- **Description**: Analyzes correlation and stability between different sensor channels (e.g., left and right bridges, vertical and lateral axes). Computes a "Stability Score" representing how independently sensors behave, which relates to active force management.
-  EXAMPLE OF USED COMMANDS:
  ```
    python correlate_channels.py --dir data.txt --start 70 --end 125 --plot  -- Start/end use like in other scripts to be consistent 
  ```
-
###  [compare_rides.py], [compare_rides_all_channels.py], and [compare_rides_multi.py]
- **Description**: Scripts designed to overlay and compare multiple rides side-by-side. 
  - `compare_rides.py` focuses on aligning two rides perfectly for eye comparison.
  - `compare_rides_all_channels.py` and `compare_rides_multi.py` allow comparing multiple channels across multiple runs simultaneously.

###  [find_noise_floor.py]
- **Description**: Estimates the electrical/environmental noise floor. Applies a 0.05 Hz high-pass filter to remove slow thermal drift, and plots the Power Spectral Density (PSD) using Welch's method across wide bands (Steering band 0.5-5Hz, vibration band 5-50Hz, etc.) to verify baseline ice vibration vs. steering signals.

### [fft_analysis.py]
- **Description**: Standard Fast Fourier Transform script to convert raw signals from time-domain to frequency-domain to observe dominant frequencies.

### [jitter_analysis.py]
- **Description**: Computes timestamp jitter statistics from logs to assess the reliability of the ADC hardware sampling rate. Checks if the target interval (e.g., 1.5ms for 667 Hz) is consistently maintained.

### [plot(from-data).py] and [plot_accelerometer.py]
- **Description**: Visual plotting tools.
  - `plot(from-data).py` loads strain gauge data and plots either raw or filtered signals.
  - `plot_accelerometer.py` parses binary accelerometer logs (`uint32` timestamp, `int32` X, Y, Z) and plots the filtered 3-axis acceleration curves.
