"""데이터 위치 테스트 — 실제 사용자 폴더는 건드리지 않는다."""
import os
import unittest
from unittest import mock

from core import appinfo
from core.dpapi_store import default_path


class AppInfoTest(unittest.TestCase):
    def test_paths_under_data_dir(self):
        with mock.patch.dict(os.environ, {"FIELDECK_DATA": "D:\\x"}):
            self.assertEqual(appinfo.config_dir(), os.path.join("D:\\x", "config"))
            self.assertEqual(appinfo.log_dir(), os.path.join("D:\\x", "logs"))
            self.assertEqual(default_path(), os.path.join("D:\\x", "config", "sessions.bin"))

    def test_default_data_dir_is_local_appdata(self):
        env = {k: v for k, v in os.environ.items() if k != "FIELDECK_DATA"}
        env["LOCALAPPDATA"] = "D:\\local"
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(appinfo.data_dir(), os.path.join("D:\\local", "Fieldeck"))


if __name__ == "__main__":
    unittest.main()
