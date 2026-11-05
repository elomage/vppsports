import csv
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from observation_analysis import signal_details


class ObservationQualityTests(unittest.TestCase):
    def test_empty_missing_and_invalid_phase_are_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'csv').mkdir();(p/'original').mkdir()
            data=bytearray();rows=[]
            for mid,time,tag in [(138,'2026-08-26T00:00:00Z',None),
                                 (139,'2026-08-26T00:00:00.050Z',2),
                                 (138,'2026-08-26T00:00:02Z',1)]:
                payload=struct.pack('<I',0 if tag is None else 1)+(bytes([tag])*24 if tag else b'')
                rows.append(dict(message_id=mid,utc=time,file_offset=len(data),message_len=len(payload)))
                data.extend(bytes(24)+payload+bytes(4))
            (p/'original/test.BIN').write_bytes(data)
            with (p/'csv/records_index.csv').open('w',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
            def decode(rec,_):
                return 'G01','1C',SimpleNamespace(psr=10.,adr=20. if rec[0]==2 else None,doppler=0.,cn0=35.),0,0
            target='converting.to_rinex.rinex305_toolkit.rinex305_toolkit.rinex305_conversion_full.parse_rangecmp_record'
            with patch(target,side_effect=decode):
                result=signal_details(p)
                main=result['quality']['138'];other=result['quality']['139']
                self.assertEqual(result['records'],2)
                self.assertEqual((main['epochs'],main['empty']),(2,1))
                self.assertEqual(main['chart'][0]['observations'],0)
                self.assertIsNone(main['chart'][0]['code_pct'])
                self.assertIsNone(main['chart'][1]['observations'])
                self.assertEqual(main['chart'][2]['code_pct'],100)
                self.assertEqual(main['chart'][2]['phase_pct'],0)
                self.assertEqual(other['chart'][0]['phase_pct'],100)
                self.assertEqual(main['fewer_than_four_code_satellites'],2)
                t=main['chart'][0]['t']
                clipped=signal_details(p,(t,t+.1))
                self.assertEqual(clipped['quality']['138']['epochs'],1)
                self.assertEqual(clipped['records'],1)


if __name__=='__main__':
    unittest.main()
