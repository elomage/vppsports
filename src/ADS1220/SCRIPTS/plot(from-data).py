import re
import argparse
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import os
from scipy.signal import butter, filtfilt

# Example line: Raw=565778, Time=3179, time in us
pattern = re.compile(r"Raw\s*=\s*(-?\d+)\s*,\s*Time\s*=\s*(\d+)")

def load_data(path):
    raw_vals = []
    time_us = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = pattern.search(line)
            if m:
                raw_vals.append(int(m.group(1)))
                time_us.append(int(m.group(2)))
    if not raw_vals:
        return pd.DataFrame()

    df = pd.DataFrame({"time_us": time_us, "raw": raw_vals})
    df["time_s"] = df["time_us"] / 1_000_000.0
    return df

def apply_butterworth_filter(df, cutoff, order=4, highpass=False):
    """Apply Butterworth filter to dataframe. Returns filtered series or None if failed."""
    if len(df) <= 1:
        return None

    sampling_rate = 1 / df["time_s"].diff().mean()
    nyquist = 0.5 * sampling_rate

    if cutoff >= nyquist:
        return None
    if len(df) <= 3 * (order + 1):
        return None

    try:
        normal_cutoff = cutoff / nyquist
        btype = 'high' if highpass else 'low'
        b, a = butter(order, normal_cutoff, btype=btype, analog=False)
        return filtfilt(b, a, df['raw'])
    except Exception:
        return None

def apply_bandpass_filter(df, highpass_cutoff, lowpass_cutoff, order=4):
    """Apply band-pass filter (high-pass then low-pass). Returns filtered series or None if failed."""
    if len(df) <= 1:
        return None

    sampling_rate = 1 / df["time_s"].diff().mean()
    nyquist = 0.5 * sampling_rate

    if highpass_cutoff >= nyquist or lowpass_cutoff >= nyquist:
        return None
    if highpass_cutoff >= lowpass_cutoff:
        return None
    if len(df) <= 3 * (order + 1):
        return None

    try:
        # Apply high-pass first (remove drift)
        normal_cutoff_hp = highpass_cutoff / nyquist
        b_hp, a_hp = butter(order, normal_cutoff_hp, btype='high', analog=False)
        result = filtfilt(b_hp, a_hp, df['raw'].values)

        # Then apply low-pass (remove high-freq noise)
        normal_cutoff_lp = lowpass_cutoff / nyquist
        b_lp, a_lp = butter(order, normal_cutoff_lp, btype='low', analog=False)
        result = filtfilt(b_lp, a_lp, result)

        # Return as pandas Series for consistency with plotting
        return pd.Series(result, index=df.index)
    except Exception:
        return None

def plot_multiple_files(args):
    """Plot multiple files for comparison or interactive viewing."""
    files = args.files

    # Validate files
    if not files:
        print("No files specified with --files")
        return

    # Check which files exist
    valid_files = []
    for f in files:
        if os.path.exists(f):
            valid_files.append(f)
        else:
            print(f"Warning: File not found - {f}")

    if not valid_files:
        print("No valid files found.")
        return

    # Load data from all selected files
    data_dict = {}
    for i, file_path in enumerate(valid_files, 1):
        df = load_data(file_path)
        if not df.empty:
            # Apply time window filter if specified
            if args.start is not None or args.end is not None:
                start_time = args.start if args.start is not None else df["time_s"].min()
                end_time = args.end if args.end is not None else df["time_s"].max()
                df = df[(df["time_s"] >= start_time) & (df["time_s"] <= end_time)]
                if df.empty:
                    print(f"Warning: No data in window [{start_time}s, {end_time}s] for {file_path}")
                    continue
            data_dict[os.path.basename(file_path)] = df

    if not data_dict:
        print("No data loaded from any files.")
        return

    # Create plot
    if args.compare:
        # Plot all channels on same graph with optional filters
        fig, ax = plt.subplots(figsize=(12, 5))
        colors = plt.cm.tab10(np.linspace(0, 1, len(data_dict)))

        for (filename, df), color in zip(data_dict.items(), colors):
            # Plot raw data
            ax.plot(df["time_s"], df["raw"], label=f"{filename} (raw)", alpha=0.3, color=color, linestyle='--')

            # Apply band-pass filter if both high and low cutoff specified
            if args.highpass_cutoff and args.lowpass_cutoff:
                filtered = apply_bandpass_filter(df, args.highpass_cutoff, args.lowpass_cutoff, args.order)
                if filtered is not None:
                    ax.plot(df["time_s"], filtered, label=f"{filename} (Band-Pass {args.highpass_cutoff}-{args.lowpass_cutoff}Hz)",
                           alpha=0.8, color=color, linewidth=2)
                else:
                    ax.plot(df["time_s"], df["raw"], label=f"{filename}", alpha=0.7, color=color)

            # Apply Butterworth filter if requested
            elif args.butterworth:
                highpass = args.highpass if hasattr(args, 'highpass') else False
                filtered = apply_butterworth_filter(df, args.butterworth, args.order, highpass)
                if filtered is not None:
                    ax.plot(df["time_s"], filtered, label=f"{filename} (Butter {args.butterworth}Hz)",
                           alpha=0.8, color=color, linewidth=2)
                else:
                    # Fallback to raw if filter failed
                    ax.plot(df["time_s"], df["raw"], label=f"{filename}", alpha=0.7, color=color)
            else:
                # No filter, just plot raw
                ax.plot(df["time_s"], df["raw"], label=f"{filename}", alpha=0.7, color=color)

        title = f"Multi-Channel Comparison ({len(data_dict)} channels)"
        if args.highpass_cutoff and args.lowpass_cutoff:
            title += f" - Band-Pass {args.highpass_cutoff}-{args.lowpass_cutoff}Hz"
        elif args.butterworth:
            filter_type = "High-Pass" if (hasattr(args, 'highpass') and args.highpass) else "Low-Pass"
            title += f" - Butterworth {filter_type} {args.butterworth}Hz"
        ax.set_title(title)
        ax.set_ylabel("Raw")
        ax.set_xlabel("Time (s)")
        ax.grid(True, alpha=0.3)
        ax.legend()
    elif args.interactive:
        # Interactive mode: switch between channels with keyboard
        plot_interactive_channels(data_dict, args)
        return
    else:
        # Create subplots for each channel with optional filters
        n_plots = len(data_dict)
        n_cols = 1 if n_plots == 1 else 2
        n_rows = (n_plots + n_cols - 1) // n_cols
        fig, axes = plt.subplots(n_rows, n_cols, figsize=(14, 4*n_rows))

        # Flatten axes for easier iteration (always ensure 1D array)
        if axes.ndim == 1:
            axes = axes  # Already 1D array from single row
        elif axes.ndim == 2:
            axes = axes.flatten()  # 2D array, flatten to 1D
        else:
            axes = np.atleast_1d(axes).flatten()  # Fallback

        for ax, (filename, df) in zip(axes, data_dict.items()):
            # Plot raw data
            ax.plot(df["time_s"], df["raw"], color="tab:blue", label="Raw Data", alpha=0.6)

            # Apply band-pass filter if both high and low cutoff specified
            if args.highpass_cutoff and args.lowpass_cutoff:
                filtered = apply_bandpass_filter(df, args.highpass_cutoff, args.lowpass_cutoff, args.order)
                if filtered is not None:
                    ax.plot(df["time_s"], filtered, color="tab:purple",
                           label=f"Band-Pass ({args.highpass_cutoff}-{args.lowpass_cutoff}Hz)", alpha=0.8, linewidth=2)

            # Apply Butterworth filter if requested
            elif args.butterworth:
                highpass = args.highpass if hasattr(args, 'highpass') else False
                filtered = apply_butterworth_filter(df, args.butterworth, args.order, highpass)
                if filtered is not None:
                    filter_type = "HP" if highpass else "LP"
                    ax.plot(df["time_s"], filtered, color="tab:orange",
                           label=f"Butterworth {filter_type} ({args.butterworth}Hz)", alpha=0.8, linewidth=2)

            # Apply smoothing if requested
            if args.smooth and args.smooth > 0:
                smoothed = df['raw'].rolling(window=args.smooth, center=True).mean()
                ax.plot(df["time_s"], smoothed, color="tab:red",
                       label=f"Smooth (w={args.smooth})", alpha=0.7)

            # Apply median if requested
            if args.median and args.median > 0:
                median_filtered = df['raw'].rolling(window=args.median, center=True).median()
                ax.plot(df["time_s"], median_filtered, color="tab:green",
                       label=f"Median (w={args.median})", alpha=0.7)

            ax.set_title(f"Channel: {filename}")
            ax.set_ylabel("Raw")
            ax.set_xlabel("Time (s)")
            ax.grid(True, alpha=0.3)
            ax.legend()

        # Hide unused subplots
        for ax in axes[n_plots:]:
            ax.set_visible(False)

    plt.tight_layout()
    if args.save:
        plt.savefig(args.save, dpi=150)
        print(f"Saved plot to {args.save}")
    if args.show or not args.save:
        plt.show()

def plot_interactive_channels(data_dict, args=None):
    """Interactive plot with keyboard shortcuts to switch between channels and toggle filters."""
    filenames = sorted(data_dict.keys())
    channel_data = [data_dict[f] for f in filenames]

    # State management
    state = {
        'current_idx': 0,
        'show_smooth': args.smooth if (args and args.smooth) else False,
        'smooth_window': args.smooth if (args and args.smooth) else 5,
        'show_median': args.median if (args and args.median) else False,
        'median_window': args.median if (args and args.median) else 5,
        'show_butterworth': args.butterworth if (args and args.butterworth) else False,
        'butterworth_cutoff': args.butterworth if (args and args.butterworth) else 1.0,
        'butterworth_order': args.order if (args and args.order) else 4,
        'butterworth_highpass': args.highpass if (args and hasattr(args, 'highpass')) else False,
        'show_bandpass': (args and args.highpass_cutoff and args.lowpass_cutoff) if args else False,
        'bandpass_hp_cutoff': args.highpass_cutoff if (args and args.highpass_cutoff) else 0.05,
        'bandpass_lp_cutoff': args.lowpass_cutoff if (args and args.lowpass_cutoff) else 5.0,
        'bandpass_order': args.order if (args and args.order) else 4,
        'combined_view': False,  # Toggle between overlaid and combined filters
        'raw_only': False,  # Show only raw data
    }

    fig, ax = plt.subplots(figsize=(12, 5))
    lines = {'raw': None, 'smooth': None, 'median': None, 'butterworth': None}

    def apply_filters(df):
        """Apply selected filters to dataframe and return filtered series."""
        filtered_data = {}
        filtered_data['raw'] = df['raw']
        debug_info = []

        if state['combined_view']:
            # Combined/cumulative mode: apply filters in sequence
            result = df['raw'].copy()

            if state['show_smooth']:
                result = result.rolling(
                    window=state['smooth_window'], center=True
                ).mean()
                debug_info.append(f"✓ Smooth(w={state['smooth_window']})")

            if state['show_median']:
                result = result.rolling(
                    window=state['median_window'], center=True
                ).median()
                debug_info.append(f"✓ Median(w={state['median_window']})")

            if state['show_butterworth']:
                if len(df) > 1:
                    sampling_rate = 1 / df["time_s"].diff().mean()
                    nyquist = 0.5 * sampling_rate
                    cutoff = state['butterworth_cutoff']
                    if cutoff >= nyquist:
                        debug_info.append(f"✗ Butter: cutoff({cutoff}Hz) >= Nyquist({nyquist:.1f}Hz)")
                    elif len(df) <= 3 * (state['butterworth_order'] + 1):
                        debug_info.append(f"✗ Butter: insufficient data ({len(df)} points needed > {3*(state['butterworth_order']+1)})")
                    else:
                        normal_cutoff = cutoff / nyquist
                        btype = 'high' if state['butterworth_highpass'] else 'low'
                        b, a = butter(state['butterworth_order'], normal_cutoff, btype=btype, analog=False)
                        try:
                            result = filtfilt(b, a, result)
                            filter_label = "HP" if state['butterworth_highpass'] else "LP"
                            debug_info.append(f"✓ Butter-{filter_label}(f={cutoff}Hz, Nyquist={nyquist:.1f}Hz)")
                        except Exception as e:
                            debug_info.append(f"✗ Butter: {str(e)[:40]}")

            if state['show_bandpass']:
                if len(df) > 1:
                    bandpass_filtered = apply_bandpass_filter(df, state['bandpass_hp_cutoff'], state['bandpass_lp_cutoff'], state['bandpass_order'])
                    if bandpass_filtered is not None:
                        result = bandpass_filtered
                        debug_info.append(f"✓ BandPass({state['bandpass_hp_cutoff']}-{state['bandpass_lp_cutoff']}Hz)")
                    else:
                        debug_info.append(f"✗ BandPass: filter failed")

            filtered_data['combined'] = result
        else:
            # Overlaid mode: show each filter separately
            if state['show_smooth']:
                filtered_data['smooth'] = df['raw'].rolling(
                    window=state['smooth_window'], center=True
                ).mean()
                debug_info.append(f"✓ Smooth(w={state['smooth_window']})")

            if state['show_median']:
                filtered_data['median'] = df['raw'].rolling(
                    window=state['median_window'], center=True
                ).median()
                debug_info.append(f"✓ Median(w={state['median_window']})")

            if state['show_butterworth']:
                if len(df) > 1:
                    sampling_rate = 1 / df["time_s"].diff().mean()
                    nyquist = 0.5 * sampling_rate
                    cutoff = state['butterworth_cutoff']
                    if cutoff >= nyquist:
                        debug_info.append(f"✗ Butter: cutoff({cutoff}Hz) >= Nyquist({nyquist:.1f}Hz)")
                    elif len(df) <= 3 * (state['butterworth_order'] + 1):
                        debug_info.append(f"✗ Butter: insufficient data ({len(df)} points needed > {3*(state['butterworth_order']+1)})")
                    else:
                        normal_cutoff = cutoff / nyquist
                        btype = 'high' if state['butterworth_highpass'] else 'low'
                        b, a = butter(state['butterworth_order'], normal_cutoff, btype=btype, analog=False)
                        try:
                            filtered_data['butterworth'] = filtfilt(b, a, df['raw'])
                            filter_label = "HP" if state['butterworth_highpass'] else "LP"
                            debug_info.append(f"✓ Butter-{filter_label}(f={cutoff}Hz, Nyquist={nyquist:.1f}Hz)")
                        except Exception as e:
                            debug_info.append(f"✗ Butter: {str(e)[:40]}")

            if state['show_bandpass']:
                bandpass_filtered = apply_bandpass_filter(df, state['bandpass_hp_cutoff'], state['bandpass_lp_cutoff'], state['bandpass_order'])
                if bandpass_filtered is not None:
                    filtered_data['bandpass'] = bandpass_filtered
                    debug_info.append(f"✓ BandPass({state['bandpass_hp_cutoff']}-{state['bandpass_lp_cutoff']}Hz)")
                else:
                    debug_info.append(f"✗ BandPass: filter failed")

        filtered_data['debug'] = debug_info
        return filtered_data

    def update_plot(idx):
        """Update the plot for the given channel index."""
        state['current_idx'] = idx
        ax.clear()

        df = channel_data[idx]
        filtered = apply_filters(df)
        debug_info = filtered.pop('debug', [])

        if state['raw_only']:
            # Show only raw data
            ax.plot(df["time_s"], filtered['raw'], color="gray", linewidth=2, label="Raw Data Only", alpha=0.8)
        elif state['combined_view']:
            # Combined view: show raw + final combined result
            ax.plot(df["time_s"], filtered['raw'], color="gray", label="Raw Data", alpha=0.4, linestyle='--')
            if 'combined' in filtered:
                active_filters = []
                if state['show_smooth']:
                    active_filters.append(f"Smooth(w={state['smooth_window']})")
                if state['show_median']:
                    active_filters.append(f"Median(w={state['median_window']})")
                if state['show_butterworth']:
                    filter_type = "HP" if state['butterworth_highpass'] else "LP"
                    active_filters.append(f"Butter-{filter_type}(f={state['butterworth_cutoff']})")
                if state['show_bandpass']:
                    active_filters.append(f"BandPass({state['bandpass_hp_cutoff']}-{state['bandpass_lp_cutoff']}Hz)")
                label = " → ".join(active_filters) if active_filters else "Combined"
                ax.plot(df["time_s"], filtered['combined'], color="tab:purple", label=label, alpha=0.8, linewidth=2)
        else:
            # Overlaid view: show raw + individual filters
            ax.plot(df["time_s"], filtered['raw'], color="tab:blue", label="Raw Data", alpha=0.6)

            if state['show_smooth'] and 'smooth' in filtered:
                ax.plot(df["time_s"], filtered['smooth'], color="tab:red",
                       label=f"Smooth (w={state['smooth_window']})", alpha=0.7)

            if state['show_median'] and 'median' in filtered:
                ax.plot(df["time_s"], filtered['median'], color="tab:green",
                       label=f"Median (w={state['median_window']})", alpha=0.7)

            if state['show_butterworth'] and 'butterworth' in filtered:
                filter_type = "High-Pass" if state['butterworth_highpass'] else "Low-Pass"
                ax.plot(df["time_s"], filtered['butterworth'], color="tab:orange",
                       label=f"Butterworth {filter_type} (f={state['butterworth_cutoff']} Hz)", alpha=0.7)

            if state['show_bandpass'] and 'bandpass' in filtered:
                ax.plot(df["time_s"], filtered['bandpass'], color="tab:purple",
                       label=f"Band-Pass ({state['bandpass_hp_cutoff']}-{state['bandpass_lp_cutoff']}Hz)", alpha=0.8, linewidth=2)

        # Build title
        mode_text = ""
        if state['raw_only']:
            mode_text = " [RAW ONLY]"
        elif state['combined_view']:
            mode_text = " [COMBINED MODE]"
        else:
            mode_text = " [OVERLAY MODE]"

        # Add debug info to title
        debug_text = " | ".join(debug_info) if debug_info else ""
        if debug_text:
            debug_text = "\nFilters: " + debug_text

        ax.set_title(
            f"Channel {idx + 1}: {filenames[idx]}{mode_text}{debug_text}\n"
            f"[1-8/←→: ch] [x/m/b: filter] [c: combined] [w: raw] [+/-: adjust] [r: reset] [q: quit]",
            fontsize=9
        )
        ax.set_ylabel("Raw")
        ax.set_xlabel("Time (s)")
        ax.grid(True, alpha=0.3)
        ax.legend(loc='best', fontsize=8)
        fig.canvas.draw_idle()

    def on_key(event):
        """Handle keyboard input."""
        if event.key is None:
            return

        if event.key == 'q':
            plt.close(fig)
            return

        # Number keys 1-8 for channel selection
        if event.key.isdigit():
            channel_num = int(event.key)
            if 1 <= channel_num <= len(filenames):
                update_plot(channel_num - 1)
            else:
                print(f"Channel {channel_num} not available (only 1-{len(filenames)} loaded)")
            return

        # Arrow keys for channel navigation
        if event.key == 'right':
            update_plot((state['current_idx'] + 1) % len(filenames))
            return
        elif event.key == 'left':
            update_plot((state['current_idx'] - 1) % len(filenames))
            return

        # Filter toggle keys
        if event.key == 'x':
            state['show_smooth'] = not state['show_smooth']
            print(f"Smooth filter: {'ON' if state['show_smooth'] else 'OFF'}")
            update_plot(state['current_idx'])
        elif event.key == 'm':
            state['show_median'] = not state['show_median']
            print(f"Median filter: {'ON' if state['show_median'] else 'OFF'}")
            update_plot(state['current_idx'])
        elif event.key == 'b':
            state['show_butterworth'] = not state['show_butterworth']
            print(f"Butterworth filter: {'ON' if state['show_butterworth'] else 'OFF'}")
            update_plot(state['current_idx'])
        elif event.key == 'p':
            state['show_bandpass'] = not state['show_bandpass']
            print(f"Band-Pass filter: {'ON' if state['show_bandpass'] else 'OFF'}")
            update_plot(state['current_idx'])
        elif event.key == 'h':
            if state['show_butterworth']:
                state['butterworth_highpass'] = not state['butterworth_highpass']
                filter_type = "HIGH-PASS" if state['butterworth_highpass'] else "LOW-PASS"
                print(f"Butterworth mode: {filter_type}")
                update_plot(state['current_idx'])
            else:
                print("Enable Butterworth filter first (press 'b')")
            return
        elif event.key == 'c':
            state['combined_view'] = not state['combined_view']
            state['raw_only'] = False  # Disable raw_only when switching modes
            mode = "COMBINED" if state['combined_view'] else "OVERLAY"
            print(f"Switched to {mode} mode")
            update_plot(state['current_idx'])
        elif event.key == 'w':
            state['raw_only'] = not state['raw_only']
            if state['raw_only']:
                print("Showing RAW DATA ONLY")
            else:
                print("Showing filters")
            update_plot(state['current_idx'])
        elif event.key == 'r':
            state['show_smooth'] = False
            state['show_median'] = False
            state['show_butterworth'] = False
            state['combined_view'] = False
            state['raw_only'] = False
            print("All filters reset")
            update_plot(state['current_idx'])

        # Adjust filter parameters
        elif event.key == 'plus' or event.key == '=':
            if state['show_smooth']:
                state['smooth_window'] = min(state['smooth_window'] + 2, 101)
                print(f"Smooth window: {state['smooth_window']}")
            elif state['show_median']:
                state['median_window'] = min(state['median_window'] + 2, 101)
                print(f"Median window: {state['median_window']}")
            elif state['show_butterworth']:
                state['butterworth_cutoff'] = min(state['butterworth_cutoff'] + 0.5, 50.0)
                print(f"Butterworth cutoff: {state['butterworth_cutoff']} Hz")
            update_plot(state['current_idx'])
        elif event.key == 'minus' or event.key == '-':
            if state['show_smooth']:
                state['smooth_window'] = max(state['smooth_window'] - 2, 3)
                print(f"Smooth window: {state['smooth_window']}")
            elif state['show_median']:
                state['median_window'] = max(state['median_window'] - 2, 3)
                print(f"Median window: {state['median_window']}")
            elif state['show_butterworth']:
                state['butterworth_cutoff'] = max(state['butterworth_cutoff'] - 0.5, 0.1)
                print(f"Butterworth cutoff: {state['butterworth_cutoff']} Hz")
            update_plot(state['current_idx'])

    fig.canvas.mpl_connect('key_press_event', on_key)
    update_plot(0)

    print(f"\n{'='*70}")
    print(f"✓ Loaded {len(filenames)} channels in INTERACTIVE mode")
    print(f"{'='*70}")
    print("CHANNEL NAVIGATION:")
    print("  1-8: Jump to specific channel")
    print("  ←  →: Previous/Next channel")
    print("\nFILTER CONTROLS:")
    print("  x: Toggle SMOOTH (moving average) filter")
    print("  m: Toggle MEDIAN filter")
    print("  b: Toggle BUTTERWORTH filter")
    print("  p: Toggle BAND-PASS filter")
    print("  h: Toggle BUTTERWORTH mode (LOW-PASS ↔ HIGH-PASS)")
    print("  +/-: Adjust active filter parameters")
    print("\nVIEW MODES:")
    print("  c: Toggle COMBINED mode (chains filters → final result)")
    print("      In combined mode: show raw (gray dashed) + final result (purple)")
    print("  w: Toggle RAW ONLY view (shows only raw data in gray)")
    print("  Default: OVERLAY MODE (show raw + each filter separately)")
    print("\nDEBUG INFO:")
    print("  Each filter shows status in title: ✓ applied, ✗ skipped with reason")
    print("  Check why Butterworth/Median didn't apply if you see ✗")
    print("\nOTHER:")
    print("  r: Reset all filters")
    print("  q: Quit")
    print(f"{'='*70}\n")

    plt.tight_layout()
    plt.show()

def main():
    ap = argparse.ArgumentParser(description="Parse ADS1220 log and plot Raw vs Time.")
    ap.add_argument("input", nargs="?", help="Path to data file containing lines: 'Raw=N, Time=T, time in us'")
    ap.add_argument("--files", nargs="+", help="List of files to process (e.g., output1.txt output2.txt output3.txt)")
    ap.add_argument("--save", help="Optional path to save figure (e.g., plot.png)")
    ap.add_argument("--show", action="store_true", help="Show interactive plot window")
    ap.add_argument("--csv", help="Optional path to save CSV (time_us,raw)")
    ap.add_argument("--analyze", action="store_true", help="Print summary statistics of the raw data")
    ap.add_argument("--start", type=float, metavar="SECONDS", help="Start time in seconds (e.g., 40 for 40.0s)")
    ap.add_argument("--end", type=float, metavar="SECONDS", help="End time in seconds (e.g., 130 for 130.0s)")
    ap.add_argument("--smooth", type=int, metavar="WINDOW", help="Apply a moving average filter with WINDOW size")
    ap.add_argument("--median", type=int, metavar="WINDOW", help="Apply a median filter with WINDOW size")
    ap.add_argument("--butterworth", type=float, metavar="CUTOFF", help="Apply Butterworth low-pass filter with CUTOFF frequency (Hz)")
    ap.add_argument("--order", type=int, default=4, help="Order of the Butterworth filter (default: 4)")
    ap.add_argument("--highpass", action="store_true", help="Use HIGH-PASS filter instead of low-pass (removes drift, keeps impacts)")
    ap.add_argument("--highpass-cutoff", type=float, metavar="CUTOFF", help="High-pass cutoff frequency (Hz) for band-pass filter")
    ap.add_argument("--lowpass-cutoff", type=float, metavar="CUTOFF", help="Low-pass cutoff frequency (Hz) for band-pass filter")
    ap.add_argument("--sum-filters", action="store_true", help="Apply median filter to the smoothed result instead of plotting separately")
    ap.add_argument("--compare", action="store_true", help="Plot multiple channels on the same graph for comparison")
    ap.add_argument("--interactive", action="store_true", help="Interactive mode: switch between channels with keyboard (1-8, arrow keys)")
    args = ap.parse_args()

    # Handle multiple files mode
    if args.files:
        plot_multiple_files(args)
        return

    # Single file mode
    if not args.input:
        ap.print_help()
        return

    df = load_data(args.input)
    if df.empty:
        print("No data parsed. Check file format.")
        return

    # Apply time window filter if specified
    if args.start is not None or args.end is not None:
        start_time = args.start if args.start is not None else df["time_s"].min()
        end_time = args.end if args.end is not None else df["time_s"].max()
        df = df[(df["time_s"] >= start_time) & (df["time_s"] <= end_time)]
        if df.empty:
            print(f"No data found in window [{start_time}s, {end_time}s]")
            return
        print(f"Filtered to [{start_time}s, {end_time}s] ({len(df)} points)")

    sampling_rate = None
    if len(df) > 1:
        sampling_rate = 1 / df["time_s"].diff().mean()

    if args.analyze:
        print("--- Data Analysis ---")
        print(df["raw"].describe())
        
        # Calculate sampling rate
        if sampling_rate:
            print(f"\nAverage Sampling Rate: {sampling_rate:.2f} Hz")
        print("---------------------")


    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(df["time_s"], df["raw"], color="tab:blue", label="Raw Data", alpha=0.6)

    if args.highpass_cutoff and args.lowpass_cutoff:
        if sampling_rate is None:
            print("Cannot apply Band-Pass filter: insufficient data to estimate sampling rate.")
        else:
            filtered = apply_bandpass_filter(df, args.highpass_cutoff, args.lowpass_cutoff, args.order)
            if filtered is not None:
                df['raw_filter'] = filtered
                ax.plot(df["time_s"], df['raw_filter'], color="tab:purple",
                       label=f"Band-Pass ({args.highpass_cutoff}-{args.lowpass_cutoff}Hz, order={args.order})")
                ax.axhline(y=0, color='black', linestyle='--', linewidth=1, alpha=0.5)  # Add this
            else:
                print(f"Error: Could not apply Band-Pass filter (check cutoff frequencies and data length)")

    elif args.butterworth:
        if sampling_rate is None:
            print("Cannot apply Butterworth filter: insufficient data to estimate sampling rate.")
        else:
            highpass = args.highpass if hasattr(args, 'highpass') else False
            filtered = apply_butterworth_filter(df, args.butterworth, args.order, highpass)
            if filtered is not None:
                filter_type = "High-Pass" if highpass else "Low-Pass"
                df['raw_butter'] = filtered
                ax.plot(df["time_s"], df['raw_butter'], color="tab:orange",
                       label=f"Butterworth {filter_type} (cutoff={args.butterworth}Hz, order={args.order})")
                ax.axhline(y=0, color='black', linestyle='--', linewidth=1, alpha=0.5)  # Add this
            else:
                print(f"Error: Could not apply Butterworth filter (check cutoff frequency and data length)")

    if args.sum_filters:
        if not (args.smooth and args.median):
            print("Warning: --sum-filters requires both --smooth and --median to be set. Ignoring.")
        else:
            # Apply smooth filter first, then median filter to the result
            smoothed = df['raw'].rolling(window=args.smooth, center=True).mean()
            combined = smoothed.rolling(window=args.median, center=True).median()
            ax.plot(df["time_s"], combined, color="tab:purple", label=f"Smoothed({args.smooth}) + Median({args.median})")
    else:
        # Original behavior: plot each filter separately
        if args.smooth and args.smooth > 0:
            df['raw_smooth'] = df['raw'].rolling(window=args.smooth, center=True).mean()
            ax.plot(df["time_s"], df['raw_smooth'], color="tab:red", label=f"Smoothed (window={args.smooth})")

        if args.median and args.median > 0:
            df['raw_median'] = df['raw'].rolling(window=args.median, center=True).median()
            ax.plot(df["time_s"], df['raw_median'], color="tab:green", label=f"Median Filter (window={args.median})")

    file_title = os.path.basename(args.input)
    title = f"ADS1220 Raw Codes vs Time\n({file_title})"
    if args.highpass_cutoff and args.lowpass_cutoff:
        title += f"\nBand-Pass {args.highpass_cutoff}-{args.lowpass_cutoff}Hz"
    elif args.butterworth:
        filter_type = "High-Pass" if (hasattr(args, 'highpass') and args.highpass) else "Low-Pass"
        title += f"\nButterworth {filter_type} {args.butterworth}Hz"
    ax.set_title(title)
    ax.set_ylabel("Raw")
    ax.set_xlabel("Time (s)")
    ax.grid(True, alpha=0.3)
    ax.legend()

    plt.tight_layout()
    if args.save:
        plt.savefig(args.save, dpi=150)
        print(f"Saved plot to {args.save}")
    if args.csv:
        df.to_csv(args.csv, index=False, columns=["time_us", "raw"])
        print(f"Saved CSV to {args.csv}")
    if args.show or not args.save:
        plt.show()

if __name__ == "__main__":
    main()