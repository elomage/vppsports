import tempfile
import unittest
from pathlib import Path

import imu_links


def make_session(root: Path) -> Path:
    session = root / "20261103_000000Z_LOG00001"
    (session / "imu").mkdir(parents=True)
    (session / "sync").mkdir()
    for name in ("LOG_004.CSV", "LOG_005.CSV"):
        (session / "imu" / name).write_text("t_ms\n", encoding="utf-8")
    for name in ("SYNC_005.CSV", "SYNC00005.CSV"):
        (session / "sync" / name).write_text("#\n", encoding="utf-8")
    return session


class ImuLinksTests(unittest.TestCase):
    def test_first_file_becomes_default_and_default_can_change(self):
        with tempfile.TemporaryDirectory() as folder:
            session = make_session(Path(folder))
            imu_links.register(session, "LOG_004.CSV", {"kind": "xdk"}, make_default=None)
            imu_links.register(session, "LOG_005.CSV", {"kind": "xdk", "xdk_sync": "sync/SYNC_005.CSV", "gnss_sync": "sync/SYNC00005.CSV"}, make_default=False)
            self.assertEqual(imu_links.default_name(session), "LOG_004.CSV")
            self.assertEqual([l.name for l in imu_links.xdk_links(session)], ["LOG_004.CSV", "LOG_005.CSV"])
            imu_links.set_default(session, "LOG_005.CSV")
            links = imu_links.xdk_links(session)
            self.assertEqual(links[0].name, "LOG_005.CSV")  # the default is listed first
            self.assertTrue(links[0].is_default)
            self.assertEqual(links[0].xdk_sync.name, "SYNC_005.CSV")
            self.assertEqual(imu_links.resolve_xdk(session).name, "LOG_005.CSV")
            self.assertEqual(imu_links.resolve_xdk(session, "LOG_004.CSV").name, "LOG_004.CSV")
            self.assertIsNone(imu_links.resolve_xdk(session, "LOG_009.CSV"))

    def test_unknown_default_is_rejected_and_missing_manifest_is_empty(self):
        with tempfile.TemporaryDirectory() as folder:
            session = make_session(Path(folder))
            self.assertEqual(imu_links.xdk_links(session), [])
            with self.assertRaises(ValueError):
                imu_links.set_default(session, "nope.csv")

    def test_link_to_a_deleted_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            session = make_session(Path(folder))
            imu_links.register(session, "LOG_004.CSV", {"kind": "xdk"}, True)
            (session / "imu" / "LOG_004.CSV").unlink()
            self.assertEqual(imu_links.xdk_links(session), [])


if __name__ == "__main__":
    unittest.main()
