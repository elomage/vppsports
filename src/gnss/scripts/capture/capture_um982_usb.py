from pathlib import Path
from datetime import datetime
import argparse
import sys
import time
import serial

ROOT = Path(__file__).resolve().parents[2]
IN_DIR = ROOT / "in"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture raw UM982/Unicore data into the project in/ directory."
    )
    parser.add_argument("port", help="Serial/USB port, for example COM7 or /dev/ttyACM0.")
    parser.add_argument(
        "filename",
        nargs="?",
        help="Output filename. Relative names are saved in in/. Defaults to a timestamped BIN file.",
    )
    return parser.parse_args()


def output_path(filename: str | None) -> Path:
    IN_DIR.mkdir(parents=True, exist_ok=True)
    if not filename:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return IN_DIR / f"capture_{stamp}.BIN"

    path = Path(filename)
    if path.is_absolute():
        return path
    return IN_DIR / path.name


args = parse_args()
port = args.port
out_path = output_path(args.filename)

# Baud rate does not really control USB CDC speed,
# but pyserial still requires a value.
baud = 921600

print(f"Opening {port}...")
print(f"Saving raw binary to {out_path}")
print("Press Ctrl+C to stop.\n")

total = 0
last_total = 0
last_time = time.time()

with serial.Serial(port, baudrate=baud, timeout=0.5) as ser:
    # Give USB CDC a moment after opening.
    time.sleep(0.5)

    with open(out_path, "wb", buffering=1024 * 1024) as f:
        try:
            while True:
                data = ser.read(65536)

                if data:
                    f.write(data)
                    total += len(data)

                now = time.time()
                if now - last_time >= 5.0:
                    rate = (total - last_total) / (now - last_time)
                    print(f"total={total} bytes, rate={rate:.0f} B/s")

                    f.flush()

                    last_total = total
                    last_time = now

        except KeyboardInterrupt:
            print("\nStopping...")
            f.flush()

print(f"Done. Saved {total} bytes.")
