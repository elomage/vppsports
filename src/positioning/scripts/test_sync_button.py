import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sync_button
from sync_button import Press, compute_button_sync, pair_presses, read_gnss_sync, read_xdk_sync

UTC0 = 1_793_747_000.0  # receiver UTC at Pico clock 0
XDK_CLOCK0 = UTC0 + 40.0  # the XDK clock reads 0 at this UTC


class FakeClock:
    """rx_bytes -> UTC, 30 000 bytes per second from Pico time 0, in a 10 MB 'BIN'."""

    size = 10_000_000

    def __init__(self, _path):
        pass

    def utc_at(self, rx):
        return UTC0 + rx / 30_000.0


def write(folder: Path, name: str, lines: list[str]) -> Path:
    path = folder / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class PairingTests(unittest.TestCase):
    def test_extra_gnss_press_is_ignored(self):
        gnss = [Press(1, 10.0, 0), Press(2, 10.6, 0), Press(3, 14.0, 0), Press(4, 70.0, 0)]
        xdk = [Press(1, 5.0, 0), Press(2, 9.0, 0), Press(3, 65.0, 0)]
        pairs = pair_presses(gnss, xdk)
        self.assertEqual([(g.seq, x.seq) for g, x, _ in pairs], [(1, 1), (3, 2), (4, 3)])

    def test_no_common_spacing_gives_no_pairs_beyond_the_anchor(self):
        gnss = [Press(1, 0.0, 0), Press(2, 3.0, 0)]
        xdk = [Press(1, 0.0, 0), Press(2, 7.0, 0)]
        self.assertEqual(len(pair_presses(gnss, xdk)), 1)


class ButtonSyncTests(unittest.TestCase):
    def test_clock_zero_is_recovered(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(sync_button, "ByteClock", FakeClock):
            folder = Path(folder)
            presses_pico = [60.0, 60.5, 200.0, 201.0]
            gnss_lines = ["# type,time_us,seq,rx_bytes"] + [
                f"SYNC,{int(t * 1e6)},{i + 1},{int((UTC0 + t - UTC0) * 30_000)}" for i, t in enumerate(presses_pico)
            ]
            xdk_lines = ["# type,t_ms,seq,rows"] + [
                f"SYNC,{int((UTC0 + t - XDK_CLOCK0) * 1000)},{i + 1},0" for i, t in enumerate(presses_pico)
            ]
            sync = compute_button_sync(write(folder, "SYNC1.CSV", gnss_lines), write(folder, "SYNC_1.CSV", xdk_lines), folder / "x.BIN")
        self.assertAlmostEqual(sync.xdk_clock0_utc, XDK_CLOCK0, delta=0.01)
        self.assertEqual(len(sync.pairs), 4)
        self.assertEqual(sync.confidence, "high")
        self.assertLess(sync.spread_ms, 5.0)
        # every press is listed with its UTC, paired or not (the GUI draws them)
        self.assertEqual(len(sync.gnss_press_list), 4)
        self.assertEqual(len(sync.xdk_press_list), 4)
        self.assertTrue(all(g["paired"] for g in sync.gnss_press_list))
        self.assertAlmostEqual(sync.xdk_press_list[0]["utc"], UTC0 + 60.0, delta=0.01)
        self.assertAlmostEqual(sync.gnss_press_list[0]["utc"], UTC0 + 60.0, delta=0.01)

    def test_empty_gnss_sync_file_is_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            g = write(folder, "SYNC1.CSV", ["# type,time_us,seq,rx_bytes", "# log=0:/LOGS/LOG00001.BIN"])
            x = write(folder, "SYNC_1.CSV", ["# type,t_ms,seq,rows", "SYNC,1000,1,10"])
            with self.assertRaises(SystemExit) as caught:
                compute_button_sync(g, x, folder / "x.BIN")
            self.assertIn("did not see the button", str(caught.exception))

    def test_readers_use_seconds(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            g = write(folder, "SYNC1.CSV", ["# x", "SYNC,2500000,3,77"])
            x = write(folder, "SYNC_1.CSV", ["# x", "SYNC,2500,3,77"])
            self.assertEqual(read_gnss_sync(g)[0].t_s, 2.5)
            self.assertEqual(read_xdk_sync(x)[0].t_s, 2.5)


if __name__ == "__main__":
    unittest.main()
