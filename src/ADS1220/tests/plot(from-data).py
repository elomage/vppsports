import re
import argparse
import matplotlib.pyplot as plt

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
    return raw_vals, time_us

def main():
    ap = argparse.ArgumentParser(description="Parse ADS1220 log and plot Raw vs Time.")
    ap.add_argument("input", help="Path to data file containing lines: 'Raw=N, Time=T, time in us'")
    ap.add_argument("--save", help="Optional path to save figure (e.g., plot.png)")
    ap.add_argument("--show", action="store_true", help="Show interactive plot window")
    ap.add_argument("--csv", help="Optional path to save CSV (time_us,raw)")
    args = ap.parse_args()

    raw, t_us = load_data(args.input)
    if not raw:
        print("No data parsed. Check file format.")
        return

    # Time axis in seconds for readability
    t_s = [x / 1_000_000.0 for x in t_us]

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(t_s, raw, color="tab:blue")
    ax.set_title("ADS1220 Raw Codes vs Time")
    ax.set_ylabel("Counts")
    ax.set_xlabel("Time (s)")
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    if args.save:
        plt.savefig(args.save, dpi=150)
        print(f"Saved plot to {args.save}")
    if args.csv:
        import csv
        with open(args.csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["time_us", "raw"])
            w.writerows(zip(t_us, raw))
        print(f"Saved CSV to {args.csv}")
    if args.show or not args.save:
        plt.show()

if __name__ == "__main__":
    main()