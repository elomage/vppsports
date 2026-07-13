#!/usr/bin/env python3
"""
Frequency Domain Analysis for Luge/Bobsled Strain Gauge Data
=============================================================
This script performs FFT, PSD, and Spectrogram analysis to compare
steering behavior between rides.

- Ride 54: Reactive micro-corrections (high frequency content)
- Ride 55: Proactive smooth steering (low frequency content)

The spectrograms mathematically prove the difference in steering technique.
"""

import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from scipy.signal import butter, filtfilt, welch, spectrogram
from scipy import signal
import argparse
import os

# Pattern to parse data lines
PATTERN = re.compile(r"Raw\s*=\s*(-?\d+)\s*,\s*Time\s*=\s*(\d+)")

# ============================================================================
# DATA LOADING
# ============================================================================

def load_data(path):
    """Load data from file and return DataFrame with time in seconds."""
    raw_vals = []
    time_us = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = PATTERN.search(line)
            if m:
                raw_vals.append(int(m.group(1)))
                time_us.append(int(m.group(2)))

    if not raw_vals:
        return pd.DataFrame()

    df = pd.DataFrame({"time_us": time_us, "raw": raw_vals})
    df["time_s"] = df["time_us"] / 1_000_000.0
    df["time_s"] = df["time_s"] - df["time_s"].iloc[0]  # Start from 0
    return df


def calculate_sampling_rate(df):
    """Calculate the sampling rate from the data."""
    if len(df) < 2:
        return 0
    duration = df["time_s"].iloc[-1] - df["time_s"].iloc[0]
    return len(df) / duration


# ============================================================================
# SIGNAL PROCESSING
# ============================================================================

def apply_bandpass_filter(data, sampling_rate, highpass=0.05, lowpass=50.0, order=4):
    """Apply band-pass filter to remove drift and high-frequency noise."""
    nyquist = 0.5 * sampling_rate

    if highpass >= nyquist or lowpass >= nyquist:
        lowpass = min(lowpass, nyquist * 0.9)
        highpass = min(highpass, lowpass * 0.1)

    if len(data) <= 3 * (order + 1):
        return data

    try:
        # High-pass to remove drift
        hp_cutoff = highpass / nyquist
        b_hp, a_hp = butter(order, hp_cutoff, btype='high', analog=False)
        result = filtfilt(b_hp, a_hp, data)

        # Low-pass to remove high-freq noise
        lp_cutoff = lowpass / nyquist
        b_lp, a_lp = butter(order, lp_cutoff, btype='low', analog=False)
        result = filtfilt(b_lp, a_lp, result)

        return result
    except Exception as e:
        print(f"Filter error: {e}")
        return data


def find_active_window(data, time_s, threshold_percentile=60, min_duration=30):
    """Find the active ride window based on signal magnitude."""
    magnitude = np.abs(data)
    threshold = np.percentile(magnitude, threshold_percentile)

    active_indices = np.where(magnitude > threshold)[0]
    if len(active_indices) == 0:
        return 0, len(data) - 1

    return active_indices[0], active_indices[-1]


def find_first_positive_peak(data, time_s, threshold=50000):
    """
    Find the START of the FIRST continuous segment ABOVE threshold.
    This is the first significant positive peak (e.g., braking/setup event).
    Returns (peak_idx, peak_time).
    """
    indices = np.where(data > threshold)[0]

    if len(indices) == 0:
        print(f"Warning: No data found above threshold {threshold}")
        return 0, time_s[0]

    # Find continuous segments above threshold
    gaps = np.where(np.diff(indices) > 100)[0]  # Gap > 100 samples = separate events

    if len(gaps) == 0:
        first_crossing_idx = indices[0]
    else:
        first_crossing_idx = indices[0]

    return first_crossing_idx, time_s[first_crossing_idx]


def find_max_positive_peak(data, time_s):
    """Find the maximum positive peak. Returns (peak_idx, peak_time)."""
    peak_idx = np.argmax(data)
    return peak_idx, time_s[peak_idx]


def create_window_around_peak(data, time_s, peak_time, before_seconds=30, after_seconds=30):
    """
    Create a time window around the peak.
    Returns (windowed_data, windowed_time, aligned_time) where aligned_time has peak at t=0.
    """
    time_relative = time_s - peak_time
    window_mask = (time_relative >= -before_seconds) & (time_relative <= after_seconds)

    if not window_mask.any():
        print(f"Warning: No data in window [{-before_seconds}s, {after_seconds}s] around peak")
        return data, time_s, time_s - peak_time

    windowed_data = data[window_mask]
    windowed_time = time_s[window_mask]
    aligned_time = windowed_time - peak_time  # Peak at t=0

    return windowed_data, windowed_time, aligned_time


# ============================================================================
# FREQUENCY ANALYSIS
# ============================================================================

def compute_psd(data, sampling_rate, nperseg=None):
    """
    Compute Power Spectral Density using Welch's method.
    Returns frequencies and power values.
    """
    if nperseg is None:
        nperseg = min(len(data) // 4, 4096)

    frequencies, psd = welch(data, fs=sampling_rate, nperseg=nperseg,
                             noverlap=nperseg//2, scaling='density')
    return frequencies, psd


def compute_spectrogram(data, sampling_rate, nperseg=None, noverlap=None):
    """
    Compute spectrogram (time-frequency representation).
    Returns frequencies, times, and power matrix.
    """
    if nperseg is None:
        nperseg = min(len(data) // 8, 2048)
    if noverlap is None:
        noverlap = nperseg * 3 // 4

    frequencies, times, Sxx = spectrogram(
        data,
        fs=sampling_rate,
        nperseg=nperseg,
        noverlap=noverlap,
        scaling='spectrum',
        mode='magnitude'
    )
    return frequencies, times, Sxx


def compute_frequency_bands(frequencies, psd):
    """
    Compute energy in different frequency bands.
    Returns dict with band energies.
    """
    bands = {
        'very_low': (0.05, 0.5),    # Very slow movements (body position)
        'low': (0.5, 2.0),           # Smooth steering input
        'medium': (2.0, 5.0),        # Active steering
        'high': (5.0, 15.0),         # Micro-corrections / jitter
        'very_high': (15.0, 50.0)    # Vibrations / noise
    }

    band_energy = {}
    for band_name, (f_low, f_high) in bands.items():
        mask = (frequencies >= f_low) & (frequencies < f_high)
        band_energy[band_name] = np.trapezoid(psd[mask], frequencies[mask]) if mask.any() else 0

    return band_energy


# ============================================================================
# VISUALIZATION
# ============================================================================

def plot_comparison_spectrograms(ride1_data, ride2_data, ride1_time, ride2_time,
                                  ride1_fs, ride2_fs, ride1_name, ride2_name,
                                  max_freq=20, output_path=None):
    """
    Create side-by-side spectrogram comparison.
    This is the key visualization showing frequency content over time.
    """
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))

    # ---- Spectrograms (top row) ----
    for idx, (data, fs, time_arr, name, ax) in enumerate([
        (ride1_data, ride1_fs, ride1_time, ride1_name, axes[0, 0]),
        (ride2_data, ride2_fs, ride2_time, ride2_name, axes[0, 1])
    ]):
        freqs, times, Sxx = compute_spectrogram(data, fs)

        # Limit frequency range
        freq_mask = freqs <= max_freq
        freqs_limited = freqs[freq_mask]
        Sxx_limited = Sxx[freq_mask, :]

        # Convert to dB for better visualization
        Sxx_db = 10 * np.log10(Sxx_limited + 1e-10)

        # Plot spectrogram
        im = ax.pcolormesh(times, freqs_limited, Sxx_db,
                          shading='gouraud', cmap='inferno')
        ax.set_ylabel('Frequency (Hz)', fontsize=11)
        ax.set_xlabel('Time (s)', fontsize=11)
        ax.set_title(f'{name}\nSpectrogram (Frequency vs Time)', fontsize=12, fontweight='bold')
        ax.set_ylim(0, max_freq)

        # Add colorbar
        cbar = plt.colorbar(im, ax=ax, label='Power (dB)')

    # ---- PSD Comparison (bottom left) ----
    ax_psd = axes[1, 0]

    freqs1, psd1 = compute_psd(ride1_data, ride1_fs)
    freqs2, psd2 = compute_psd(ride2_data, ride2_fs)

    # Limit to max_freq
    mask1 = freqs1 <= max_freq
    mask2 = freqs2 <= max_freq

    ax_psd.semilogy(freqs1[mask1], psd1[mask1], 'b-', linewidth=2,
                    label=ride1_name, alpha=0.8)
    ax_psd.semilogy(freqs2[mask2], psd2[mask2], 'r-', linewidth=2,
                    label=ride2_name, alpha=0.8)

    # Add frequency band markers
    band_colors = {'Very Low\n(0.05-0.5Hz)': '#2ecc71', 'Low\n(0.5-2Hz)': '#3498db',
                   'Medium\n(2-5Hz)': '#f39c12', 'High\n(5-15Hz)': '#e74c3c'}
    band_edges = [0.05, 0.5, 2.0, 5.0, 15.0]

    for i, (label, color) in enumerate(band_colors.items()):
        ax_psd.axvspan(band_edges[i], band_edges[i+1], alpha=0.15, color=color)

    ax_psd.set_xlabel('Frequency (Hz)', fontsize=11)
    ax_psd.set_ylabel('Power Spectral Density', fontsize=11)
    ax_psd.set_title('Power Spectral Density Comparison\n(Higher = More Energy at That Frequency)',
                     fontsize=12, fontweight='bold')
    ax_psd.legend(loc='upper right', fontsize=10)
    ax_psd.grid(True, alpha=0.3)
    ax_psd.set_xlim(0, max_freq)

    # ---- Frequency Band Energy Bar Chart (bottom right) ----
    ax_bars = axes[1, 1]

    bands1 = compute_frequency_bands(freqs1, psd1)
    bands2 = compute_frequency_bands(freqs2, psd2)

    band_names = ['Very Low\n0.05-0.5Hz', 'Low\n0.5-2Hz', 'Medium\n2-5Hz', 'High\n5-15Hz', 'Very High\n15-50Hz']
    band_keys = ['very_low', 'low', 'medium', 'high', 'very_high']

    x = np.arange(len(band_names))
    width = 0.35

    vals1 = [bands1[k] for k in band_keys]
    vals2 = [bands2[k] for k in band_keys]

    # Normalize for comparison
    total1 = sum(vals1)
    total2 = sum(vals2)
    vals1_pct = [v/total1*100 for v in vals1]
    vals2_pct = [v/total2*100 for v in vals2]

    bars1 = ax_bars.bar(x - width/2, vals1_pct, width, label=ride1_name, color='blue', alpha=0.7)
    bars2 = ax_bars.bar(x + width/2, vals2_pct, width, label=ride2_name, color='red', alpha=0.7)

    ax_bars.set_ylabel('Energy Distribution (%)', fontsize=11)
    ax_bars.set_title('Frequency Band Energy Distribution\n(Where is the Steering Energy?)',
                      fontsize=12, fontweight='bold')
    ax_bars.set_xticks(x)
    ax_bars.set_xticklabels(band_names, fontsize=9)
    ax_bars.legend(loc='upper right', fontsize=10)
    ax_bars.grid(True, alpha=0.3, axis='y')

    # Add value labels on bars
    for bar, val in zip(bars1, vals1_pct):
        ax_bars.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                    f'{val:.1f}%', ha='center', va='bottom', fontsize=8)
    for bar, val in zip(bars2, vals2_pct):
        ax_bars.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                    f'{val:.1f}%', ha='center', va='bottom', fontsize=8)

    plt.tight_layout()

    if output_path:
        plt.savefig(output_path, dpi=200, bbox_inches='tight', facecolor='white')
        print(f"Saved: {output_path}")

    return fig


def plot_detailed_spectrograms(ride1_data, ride2_data, ride1_fs, ride2_fs,
                                ride1_name, ride2_name, max_freq=15, output_path=None):
    """
    Create publication-quality side-by-side spectrograms.
    Perfect for thesis/paper inclusion.
    """
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), layout='constrained')

    # Common color scale for comparison
    all_Sxx_db = []
    spectro_data = []

    for data, fs in [(ride1_data, ride1_fs), (ride2_data, ride2_fs)]:
        freqs, times, Sxx = compute_spectrogram(data, fs)
        freq_mask = freqs <= max_freq
        Sxx_limited = Sxx[freq_mask, :]
        Sxx_db = 10 * np.log10(Sxx_limited + 1e-10)
        all_Sxx_db.append(Sxx_db)
        spectro_data.append((freqs[freq_mask], times, Sxx_db))

    # Find global min/max for consistent colorbar
    vmin = min(np.percentile(s, 5) for s in all_Sxx_db)
    vmax = max(np.percentile(s, 95) for s in all_Sxx_db)

    for idx, ((freqs, times, Sxx_db), name, ax) in enumerate([
        (spectro_data[0], ride1_name, axes[0]),
        (spectro_data[1], ride2_name, axes[1])
    ]):
        im = ax.pcolormesh(times, freqs, Sxx_db,
                          shading='gouraud', cmap='viridis',
                          vmin=vmin, vmax=vmax)
        ax.set_ylabel('Frequency (Hz)', fontsize=12)
        ax.set_xlabel('Time (s)', fontsize=12)
        ax.set_title(name, fontsize=14, fontweight='bold')
        ax.set_ylim(0, max_freq)

        # Add horizontal lines for frequency bands
        ax.axhline(y=2, color='white', linestyle='--', alpha=0.5, linewidth=1)
        ax.axhline(y=5, color='white', linestyle='--', alpha=0.5, linewidth=1)

        # Labels for bands
        ax.text(times[-1] * 0.95, 1, 'Smooth', ha='right', va='center',
                color='white', fontsize=9, fontweight='bold')
        ax.text(times[-1] * 0.95, 3.5, 'Active', ha='right', va='center',
                color='white', fontsize=9, fontweight='bold')
        ax.text(times[-1] * 0.95, 10, 'Jitter', ha='right', va='center',
                color='white', fontsize=9, fontweight='bold')

    # Add colorbar
    cbar = fig.colorbar(im, ax=axes, label='Power (dB)', shrink=0.8)

    fig.suptitle('Steering Frequency Analysis: Spectrogram Comparison\n' +
                 'High-frequency content = Reactive micro-corrections | Low-frequency = Smooth proactive steering',
                 fontsize=12, fontweight='bold', y=1.02)

    #plt.tight_layout()

    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white')
        print(f"Saved: {output_path}")

    return fig


def compute_time_domain_stats(data):
    """
    Compute time-domain statistics: RMS, Standard Deviation, Crest Factor, Peak-to-Peak.
    """
    rms = np.sqrt(np.mean(data ** 2))
    std = np.std(data)
    peak_abs = max(abs(np.max(data)), abs(np.min(data)))
    crest_factor = peak_abs / rms if rms > 0 else 0  # Peak / RMS
    peak_to_peak = np.max(data) - np.min(data)

    return {
        'rms': rms,
        'std': std,
        'crest_factor': crest_factor,
        'peak_to_peak': peak_to_peak,
        'max': np.max(data),
        'min': np.min(data)
    }


def print_frequency_analysis(ride_name, freqs, psd, bands, data=None):
    """Print detailed frequency analysis."""
    total_energy = sum(bands.values())

    print(f"\n{'='*60}")
    print(f"FREQUENCY ANALYSIS: {ride_name}")
    print(f"{'='*60}")

    # Time-domain statistics (if data provided)
    if data is not None:
        stats = compute_time_domain_stats(data)
        print("\nTime-Domain Statistics:")
        print("-" * 40)
        print(f"  RMS (steering energy):     {stats['rms']:>12,.0f}")
        print(f"  Standard Deviation:        {stats['std']:>12,.0f}")
        print(f"  Crest Factor (peak/RMS):   {stats['crest_factor']:>12.2f}")
        print(f"  Peak-to-Peak amplitude:    {stats['peak_to_peak']:>12,.0f}")
        print(f"  Max positive:              {stats['max']:>12,.0f}")
        print(f"  Max negative:              {stats['min']:>12,.0f}")

    print("\nFrequency Band Energy Distribution:")
    print("-" * 40)

    band_labels = {
        'very_low': 'Very Low (0.05-0.5 Hz) - Body position',
        'low': 'Low (0.5-2 Hz)         - Smooth steering',
        'medium': 'Medium (2-5 Hz)        - Active steering',
        'high': 'High (5-15 Hz)         - Micro-corrections',
        'very_high': 'Very High (15-50 Hz)   - Vibrations/noise'
    }

    for key, label in band_labels.items():
        pct = bands[key] / total_energy * 100
        bar = '#' * int(pct / 2)
        print(f"{label}: {pct:5.1f}% {bar}")

    # Find dominant frequency
    dominant_idx = np.argmax(psd[1:]) + 1  # Skip DC component
    dominant_freq = freqs[dominant_idx]
    print(f"\nDominant frequency: {dominant_freq:.2f} Hz")

    # High frequency ratio (indicator of jittery steering)
    high_freq_ratio = (bands['high'] + bands['very_high']) / total_energy * 100
    low_freq_ratio = (bands['very_low'] + bands['low']) / total_energy * 100

    print(f"\nSteering smoothness indicator:")
    print(f"  Low-frequency energy:  {low_freq_ratio:.1f}%")
    print(f"  High-frequency energy: {high_freq_ratio:.1f}%")

    if high_freq_ratio > low_freq_ratio:
        print(f"  => REACTIVE steering (more micro-corrections)")
    else:
        print(f"  => PROACTIVE steering (smoother, anticipatory)")


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Frequency Domain Analysis for Luge/Bobsled Strain Gauge Data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 frequency_analysis.py                           # Compare ride 54 vs 55 (default, with peak alignment)
  python3 frequency_analysis.py --channel 6               # Use channel 6 data
  python3 frequency_analysis.py --ride1 54 --ride2 55     # Specify rides
  python3 frequency_analysis.py --before 30 --after 30    # Window: 30s before/after peak
  python3 frequency_analysis.py --threshold 40000         # Peak detection threshold
  python3 frequency_analysis.py --no-align                # Skip peak alignment (use full data)
  python3 frequency_analysis.py --max-freq 25             # Show up to 25 Hz
        """
    )

    parser.add_argument('--ride1', type=str, default='54',
                       help='First ride number or path (default: 54)')
    parser.add_argument('--ride2', type=str, default='55',
                       help='Second ride number or path (default: 55)')
    parser.add_argument('--channel', type=int, default=6,
                       help='Channel number to analyze (default: 6)')
    parser.add_argument('--max-freq', type=float, default=15,
                       help='Maximum frequency to display in Hz (default: 15)')

    # Peak alignment options
    parser.add_argument('--before', type=float, default=30,
                       help='Seconds before peak to include (default: 30)')
    parser.add_argument('--after', type=float, default=30,
                       help='Seconds after peak to include (default: 30)')
    parser.add_argument('--threshold', type=int, default=50000,
                       help='Threshold for first positive peak detection (default: 50000)')
    parser.add_argument('--peak-mode', type=str, default='max', choices=['first', 'max'],
                       help='Peak detection: "first" above threshold or "max" peak (default: max)')
    parser.add_argument('--no-align', action='store_true',
                       help='Skip peak alignment (analyze full ride)')

    # Manual time window (overrides peak alignment)
    parser.add_argument('--start', type=float, default=None,
                       help='Start time in seconds for BOTH rides (overrides peak alignment)')
    parser.add_argument('--end', type=float, default=None,
                       help='End time in seconds for BOTH rides (overrides peak alignment)')

    # Per-ride manual windows (overrides --start/--end)
    parser.add_argument('--start1', type=float, default=None,
                       help='Start time in seconds for ride1 (overrides --start)')
    parser.add_argument('--end1', type=float, default=None,
                       help='End time in seconds for ride1 (overrides --end)')
    parser.add_argument('--start2', type=float, default=None,
                       help='Start time in seconds for ride2 (overrides --start)')
    parser.add_argument('--end2', type=float, default=None,
                       help='End time in seconds for ride2 (overrides --end)')

    parser.add_argument('--no-filter', action='store_true',
                       help='Skip bandpass filtering')
    parser.add_argument('--output', type=str, default=None,
                       help='Output path for plots (default: auto-generated)')
    parser.add_argument('--no-show', action='store_true',
                       help='Do not show interactive plots (just save files)')

    args = parser.parse_args()

    # Build paths
    base_path = "/Users/ricardsbubiss/Desktop/VPP SPORTS/testFile/DATA"

    # Check if it's an existing file path
    if os.path.isfile(args.ride1):
        ride1_path = args.ride1
    else:
        # Assume it's a ride number, build path to channel file
        ride1_path = f"{base_path}/{args.ride1}/output{args.channel}.txt"

    if os.path.isfile(args.ride2):
        ride2_path = args.ride2
    else:
        ride2_path = f"{base_path}/{args.ride2}/output{args.channel}.txt"

    ride1_name = f"Ride {args.ride1} (Channel {args.channel})"
    ride2_name = f"Ride {args.ride2} (Channel {args.channel})"

    print("="*70)
    print("FREQUENCY DOMAIN ANALYSIS - Steering Technique Comparison")
    print("="*70)
    print(f"\nRide 1: {ride1_path}")
    print(f"Ride 2: {ride2_path}")

    # Load data
    print("\nLoading data...")
    df1 = load_data(ride1_path)
    df2 = load_data(ride2_path)

    if df1.empty or df2.empty:
        print("Error: Could not load data files")
        return

    fs1 = calculate_sampling_rate(df1)
    fs2 = calculate_sampling_rate(df2)

    print(f"Ride 1: {len(df1)} samples, {df1['time_s'].iloc[-1]:.1f}s, {fs1:.1f} Hz sampling rate")
    print(f"Ride 2: {len(df2)} samples, {df2['time_s'].iloc[-1]:.1f}s, {fs2:.1f} Hz sampling rate")

    # Extract raw values
    data1 = df1['raw'].values.astype(float)
    data2 = df2['raw'].values.astype(float)
    time1 = df1['time_s'].values
    time2 = df2['time_s'].values

    # Apply bandpass filter BEFORE peak detection (like compare_rides.py)
    if not args.no_filter:
        print("\nApplying bandpass filter (0.05 - 50 Hz)...")
        data1_filtered = apply_bandpass_filter(data1, fs1)
        data2_filtered = apply_bandpass_filter(data2, fs2)
    else:
        data1_filtered = data1
        data2_filtered = data2

    # Determine windowing mode
    use_manual_window = args.start is not None or args.end is not None or \
                       args.start1 is not None or args.end1 is not None or \
                       args.start2 is not None or args.end2 is not None
    window_info = {}  # Store window info for later summary

    if use_manual_window:
        # Manual time window (overrides peak alignment)
        # Per-ride windows take precedence, fall back to shared --start/--end
        start1 = args.start1 if args.start1 is not None else (args.start or 0)
        end1 = args.end1 if args.end1 is not None else (args.end or time1[-1])
        start2 = args.start2 if args.start2 is not None else (args.start or 0)
        end2 = args.end2 if args.end2 is not None else (args.end or time2[-1])

        mask1 = (time1 >= start1) & (time1 <= end1)
        mask2 = (time2 >= start2) & (time2 <= end2)

        data1_window = data1_filtered[mask1]
        data2_window = data2_filtered[mask2]
        time1_aligned = time1[mask1]
        time2_aligned = time2[mask2]

        window_info['ride1'] = f"{time1[mask1][0]:.1f}s to {time1[mask1][-1]:.1f}s" if len(time1[mask1]) > 0 else "N/A"
        window_info['ride2'] = f"{time2[mask2][0]:.1f}s to {time2[mask2][-1]:.1f}s" if len(time2[mask2]) > 0 else "N/A"

        if args.start1 is not None or args.start2 is not None:
            print(f"\nManual time window (per-ride):")
            print(f"  Ride 1: {start1}s to {end1}s")
            print(f"  Ride 2: {start2}s to {end2}s")
        else:
            print(f"\nManual time window (shared): {start1}s to {min(end1, end2)}s")

    elif not args.no_align:
        # Peak alignment mode (default)
        print(f"\n--- Peak Alignment Mode ---")
        print(f"Finding peaks (mode: {args.peak_mode}, threshold: {args.threshold})...")

        if args.peak_mode == 'first':
            peak_idx1, peak_time1 = find_first_positive_peak(data1_filtered, time1, args.threshold)
            peak_idx2, peak_time2 = find_first_positive_peak(data2_filtered, time2, args.threshold)
        else:
            peak_idx1, peak_time1 = find_max_positive_peak(data1_filtered, time1)
            peak_idx2, peak_time2 = find_max_positive_peak(data2_filtered, time2)

        print(f"Ride 1 peak: {peak_time1:.1f}s (value: {data1_filtered[peak_idx1]:,.0f})")
        print(f"Ride 2 peak: {peak_time2:.1f}s (value: {data2_filtered[peak_idx2]:,.0f})")

        # Create windows around peaks
        print(f"Creating windows: {args.before}s before peak, {args.after}s after peak")

        data1_window, time1_window_orig, time1_aligned = create_window_around_peak(
            data1_filtered, time1, peak_time1, args.before, args.after
        )
        data2_window, time2_window_orig, time2_aligned = create_window_around_peak(
            data2_filtered, time2, peak_time2, args.before, args.after
        )

        window_info['ride1'] = f"{time1_window_orig[0]:.1f}s to {time1_window_orig[-1]:.1f}s" if len(time1_window_orig) > 0 else "N/A"
        window_info['ride2'] = f"{time2_window_orig[0]:.1f}s to {time2_window_orig[-1]:.1f}s" if len(time2_window_orig) > 0 else "N/A"

        print(f"Ride 1 window: {len(data1_window)} samples ({time1_aligned[0]:.1f}s to {time1_aligned[-1]:.1f}s)")
        print(f"Ride 2 window: {len(data2_window)} samples ({time2_aligned[0]:.1f}s to {time2_aligned[-1]:.1f}s)")

    else:
        # No alignment - use full data
        data1_window = data1_filtered
        data2_window = data2_filtered
        time1_aligned = time1
        time2_aligned = time2

        window_info['ride1'] = f"{time1[0]:.1f}s to {time1[-1]:.1f}s"
        window_info['ride2'] = f"{time2[0]:.1f}s to {time2[-1]:.1f}s"

        print("\nNo alignment - using full ride data")

    # Compute PSD and frequency bands
    print("\nComputing frequency analysis...")
    freqs1, psd1 = compute_psd(data1_window, fs1)
    freqs2, psd2 = compute_psd(data2_window, fs2)

    bands1 = compute_frequency_bands(freqs1, psd1)
    bands2 = compute_frequency_bands(freqs2, psd2)

    # Print analysis
    print_frequency_analysis(ride1_name, freqs1, psd1, bands1, data1_window)
    print_frequency_analysis(ride2_name, freqs2, psd2, bands2, data2_window)

    # Comparison summary
    print(f"\n{'='*60}")
    print("COMPARISON SUMMARY")
    print(f"{'='*60}")

    # Window information
    print(f"\n--- Analysis Window (Original File Times) ---")
    print(f"{ride1_name}:  {window_info['ride1']}")
    print(f"{ride2_name}:  {window_info['ride2']}")

    # Time-domain stats comparison
    stats1 = compute_time_domain_stats(data1_window)
    stats2 = compute_time_domain_stats(data2_window)

    print(f"\n--- Time-Domain Comparison ---")
    print(f"{'Metric':<25} {ride1_name:>15} {ride2_name:>15} {'Difference':>12}")
    print("-" * 70)

    rms_diff = (stats1['rms'] - stats2['rms']) / stats2['rms'] * 100 if stats2['rms'] != 0 else 0
    std_diff = (stats1['std'] - stats2['std']) / stats2['std'] * 100 if stats2['std'] != 0 else 0
    crest_diff = (stats1['crest_factor'] - stats2['crest_factor']) / stats2['crest_factor'] * 100 if stats2['crest_factor'] != 0 else 0

    print(f"{'RMS (energy)':<25} {stats1['rms']:>15,.0f} {stats2['rms']:>15,.0f} {rms_diff:>+11.1f}%")
    print(f"{'Standard Deviation':<25} {stats1['std']:>15,.0f} {stats2['std']:>15,.0f} {std_diff:>+11.1f}%")
    print(f"{'Crest Factor':<25} {stats1['crest_factor']:>15.2f} {stats2['crest_factor']:>15.2f} {crest_diff:>+11.1f}%")
    print(f"{'Peak-to-Peak':<25} {stats1['peak_to_peak']:>15,.0f} {stats2['peak_to_peak']:>15,.0f}")

    total1 = sum(bands1.values())
    total2 = sum(bands2.values())

    high1 = (bands1['high'] + bands1['very_high']) / total1 * 100
    high2 = (bands2['high'] + bands2['very_high']) / total2 * 100
    low1 = (bands1['very_low'] + bands1['low']) / total1 * 100
    low2 = (bands2['very_low'] + bands2['low']) / total2 * 100

    print(f"\n--- Frequency Distribution Comparison ---")
    print(f"{ride1_name}:")
    print(f"  Smooth steering (low freq):   {low1:.1f}%")
    print(f"  Micro-corrections (high freq): {high1:.1f}%")

    print(f"\n{ride2_name}:")
    print(f"  Smooth steering (low freq):   {low2:.1f}%")
    print(f"  Micro-corrections (high freq): {high2:.1f}%")

    # Conclusions
    print(f"\n--- Conclusions ---")
    if high1 > high2:
        diff = high1 - high2
        print(f"=> {ride1_name} has {diff:.1f}% MORE high-frequency content")
        print(f"   This indicates MORE reactive micro-corrections (jittery steering)")
    else:
        diff = high2 - high1
        print(f"=> {ride2_name} has {diff:.1f}% MORE high-frequency content")
        print(f"   This indicates MORE reactive micro-corrections (jittery steering)")

    if stats1['crest_factor'] > stats2['crest_factor']:
        print(f"=> {ride1_name} has {crest_diff:.1f}% HIGHER crest factor ({stats1['crest_factor']:.2f} vs {stats2['crest_factor']:.2f})")
        print(f"   This indicates MORE sudden spikes/peaks relative to average")
    else:
        print(f"=> {ride2_name} has {abs(crest_diff):.1f}% HIGHER crest factor ({stats2['crest_factor']:.2f} vs {stats1['crest_factor']:.2f})")
        print(f"   This indicates MORE sudden spikes/peaks relative to average")

    # Generate plots
    print("\nGenerating visualizations...")

    output_dir = base_path

    # Full comparison plot
    output1 = args.output or f"{output_dir}/frequency_comparison54_55.png"
    fig1 = plot_comparison_spectrograms(
        data1_window, data2_window, time1_aligned, time2_aligned, fs1, fs2,
        ride1_name, ride2_name,
        max_freq=args.max_freq,
        output_path=output1
    )

    print(f"\n{'='*60}")
    print("DONE! Generated files:")
    print(f"  1. {output1}")
    print(f"{'='*60}")

    if not args.no_show:
        plt.show()


if __name__ == "__main__":
    main()
