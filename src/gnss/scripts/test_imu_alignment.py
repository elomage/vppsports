import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from imu_alignment import preview, save_alignment
from imu_kalman import GnssSample, ImuSample


class AlignmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.session = Path(self.temp.name)
        self.imu = self.session / 'ride.csv'
        self.points = [GnssSample(datetime(2026, 9, 27, 12, 0, t, tzinfo=timezone.utc),
                                  57, 24, 0, 3*t, 4*t, 5, 0) for t in (0, 10)]
        self.samples = [ImuSample(t, 0, 0, 9.81) for t in (0, 1, 2)]
        for name, value in [('load_gnss', self.points), ('read_samples', self.samples)]:
            mock = patch('imu_alignment.'+name, return_value=value)
            mock.start()
            self.addCleanup(mock.stop)

    def test_positive_offset_and_reload(self):
        saved = save_alignment(self.session, self.imu, 'observation', 1.234)
        self.assertEqual(saved['imu_start_utc'], '2026-09-27T12:00:01.234000+00:00')
        result = preview(self.session, self.imu, 'observation')
        self.assertEqual(result['saved']['time_offset_s'], 1.234)
        self.assertEqual(result['gnss'][-1][1], 50)
        self.assertEqual(result['gnss'][-1][3], 0)

    def test_reject_invalid_offsets(self):
        for offset in (float('nan'), float('inf'), 11, -3):
            with self.assertRaises(ValueError):
                save_alignment(self.session, self.imu, 'observation', offset)

    def test_reject_timer_reset(self):
        self.samples.append(ImuSample(0, 0, 0, 9.81))
        with self.assertRaises(ValueError):
            preview(self.session, self.imu, 'observation')


if __name__ == '__main__':
    unittest.main()
