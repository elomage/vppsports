import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import recording_analysis as a


class AcquisitionTests(unittest.TestCase):
    def test_position_sources_share_utc_filter_and_keep_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp); (folder/'ppk').mkdir()
            header='% GPST latitude(deg) longitude(deg) height(m) Q ns\n'
            (folder/'ppk/observation_single.pos').write_text(header+
                '2433 277717.283 57.15 24.84 134 5 6\n'
                '2433 277717.333 57.16 24.85 135 5 6\n'
                '2433 277717.383 57.16 24.85 135 0 0\n'
                '2433 277717.433 57.17 24.86 136 5 6\n')
            first=a.position_track(folder/'ppk/observation_single.pos')[0]['t']
            date=a.datetime.fromtimestamp(first+18,a.timezone.utc).strftime('%Y/%m/%d %H:%M:%S.%f')
            (folder/'ppk/solution.pos').write_text(header+date+' 57.15 24.84 134 2 6\n')
            tracks=a.map_tracks(folder,(first,first+.06))
            self.assertEqual(len(tracks['single']),3)
            self.assertEqual([p['selected'] for p in tracks['single']],[True,True,False])
            self.assertNotEqual(tracks['single'][1]['segment'],tracks['single'][2]['segment'])
            self.assertAlmostEqual(tracks['ppk'][0]['t'],first,places=5)
            self.assertTrue(tracks['ppk'][0]['selected'])
            self.assertEqual(tracks['float'],[])

    def test_gaps_status_and_startup_are_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            folder=root/'out'/'test'/'csv'
            folder.mkdir(parents=True)
            rows=[]
            for time,status in [('1980-01-01T00:00:00Z','INSUFFICIENT_OBS'),
                                ('2026-08-24T00:00:00Z','INSUFFICIENT_OBS'),
                                ('2026-08-24T00:00:00.5Z','SOL_COMPUTED'),
                                ('2026-08-24T00:00:02Z','SOL_COMPUTED'),
                                ('2026-08-24T00:00:02.5Z','INSUFFICIENT_OBS')]:
                rows.append(dict(utc=time,position_solution_status=status,position_type='SINGLE',
                                 x_m=6370000,y_m=0,z_m=0,satellites_used=6,
                                 vx_mps=3,vy_mps=4,vz_mps=0,velocity_solution_status='SOL_COMPUTED'))
            with (folder/'bestnavxyz.csv').open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
            with patch.object(a,'ROOT',root):
                a._cache.clear()
                d=a.analyze('test',False)
                self.assertEqual((d['rows'],d['invalid_time'],d['valid']),(5,1,2))
                self.assertEqual(d['hz'],2)
                self.assertEqual(d['missing'],2)
                self.assertEqual(d['valid_percent'],50)
                self.assertEqual(d['speed']['mean'],18)
                self.assertEqual([g['seconds'] for g in d['outages']],[.5,.5])
                self.assertEqual(len(d['gaps']),1)
                self.assertIsNone(d['sigma']['mean'])
                clipped=a.analyze('test',False,.5,2)
                self.assertEqual((clipped['rows'],clipped['valid'],clipped['invalid_time']),(2,2,0))
                self.assertEqual(clipped['heading']['rows'],0)
                self.assertEqual(len(clipped['track']),2)
                self.assertAlmostEqual(clipped['track'][0]['height'],6370000-6378137,places=5)
                self.assertTrue(all(p['selected'] for p in clipped['track']))
                empty=a.analyze('test',False,1,1.5)
                self.assertEqual(empty['rows'],0)
                self.assertFalse(any(p['selected'] for p in empty['track']))
                with self.assertRaises(ValueError):
                    a.analyze('test',False,2,1)
                with self.assertRaises(ValueError):
                    a.get_session('../')

    def test_rinex_signal_field_is_not_ssi(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'sample.obs'
            p.write_text('G    4 C1C L1C D1C S1C                                       SYS / # / OBS TYPES\n'
                         '                                                            END OF HEADER\n'
                         '> 2026 08 24 00 00 00.0000000  0  1\n'
                         +'G01'+f'{20000000:14.3f}  '+f'{100000:14.3f}17'+f'{0:14.3f}  '+f'{42:14.3f}  '+'\n')
            d=a.rinex_metrics(p)
            self.assertEqual(d['cn0']['median'],42)
            self.assertEqual(d['loss_of_lock_flags'],1)
            self.assertEqual(d['phase_observations'],1)
            self.assertEqual(d['epochs'],1)
            self.assertIsNone(d['hz'])
            utc=a.timestamp('2026-08-23T23:59:42Z')
            self.assertEqual(a.rinex_metrics(p,(utc,utc))['cn0']['n'],1)
            self.assertEqual(a.rinex_metrics(p,(utc+1,utc+2))['cn0']['n'],0)


if __name__=='__main__':
    unittest.main()
