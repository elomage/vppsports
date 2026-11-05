import tempfile
import unittest
from collections import Counter, OrderedDict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from converting.to_rinex.rinex305_toolkit.rinex305_toolkit import rinex305_conversion_full as converter
import process_recording_all as pipeline
from process_recording_all import resolve_recording_args


class SourceSelectionTests(unittest.TestCase):
    def convert(self, sources, requested="auto"):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "test.BIN"
            raw.write_bytes(b"")
            args = SimpleNamespace(
                input=raw, output_dir=root, basename=None, no_crc=False,
                obs_source=requested, legacy_bds_codes=False, max_epochs=None,
                obs_profile="rtklib", min_sats=4, gps_week=2438, date=None,
                rinex_version="3.05", marker="TEST", include_all_nav=False, zip=False,
            )
            def read(packets, signal_map, source, max_epochs=None):
                count, psr = sources.get(source, (0, None))
                sats = {f"G{i:02d}": {"1C": converter.Obs(psr, None, None, 35, 1)}
                        for i in range(1, count + 1)}
                return OrderedDict([(1000, sats)]), Counter(), Counter()
            with patch.object(converter, "read_observations", side_effect=read):
                paths = converter.run_conversion(args)
            return paths["REPORT"].read_text(), paths["OBS"].read_text()

    def test_slave_fallback_when_master_has_too_few_satellites(self):
        report, obs = self.convert({"obsvmcmpb": (3, 20000000), "obsvhcmpb": (5, 20000000)})
        self.assertIn("OBS source: obsvhcmpb", report)
        self.assertIn("G05", obs)

    def test_master_preferred_when_usable(self):
        report, _ = self.convert({"obsvmcmpb": (4, 20000000), "obsvhcmpb": (5, 20000000)})
        self.assertIn("OBS source: obsvmcmpb", report)

    def test_signal_strength_only_master_does_not_block_fallback(self):
        report, _ = self.convert({"obsvmcmpb": (8, None), "obsvhcmpb": (5, 20000000)})
        self.assertIn("OBS source: obsvhcmpb", report)

    def test_explicit_source_never_switches_antennas(self):
        with self.assertRaisesRegex(SystemExit, "No usable observations"):
            self.convert({"obsvhcmpb": (5, 20000000)}, "obsvmcmpb")

    def test_no_usable_source_has_clear_error(self):
        with self.assertRaisesRegex(SystemExit, "minimum-satellite filtering"):
            self.convert({})

    def test_comma_separated_recordings(self):
        with patch("process_recording_all.resolve_session_dir", side_effect=lambda value: value):
            self.assertEqual(resolve_recording_args(["first,", "second,third"]),
                             ["first", "second", "third"])

    def test_failed_conversion_skips_dependent_solvers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "original").mkdir()
            (root / "original" / "test.BIN").write_bytes(b"")
            args = SimpleNamespace(python="python", rinex_obs_source="auto",
                                   skip_observation_single=False, base="auto")
            results = [pipeline.StepResult(name, [], code, "", "")
                       for name, code in [("extract", 0), ("filter", 0), ("rinex", 1)]]
            with patch.object(pipeline, "run_step", side_effect=results) as run:
                self.assertEqual(pipeline.process_recording(args, root), 1)
            self.assertEqual(run.call_count, 3)


if __name__ == "__main__":
    unittest.main()
