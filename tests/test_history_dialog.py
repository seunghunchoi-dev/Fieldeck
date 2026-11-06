"""접속 이력 창 테스트 — 임시 로그 폴더 사용."""
import os
import sys
import tempfile
import time
import unittest

from PySide6.QtWidgets import QApplication

from core.conn_log import ConnLog
from ui.history_dialog import HistoryDialog, load_entries

app = QApplication.instance() or QApplication(sys.argv)


class HistoryDialogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "logs")
        self.log = ConnLog(self.dir)
        ts = time.mktime((2026, 11, 3, 9, 0, 0, 0, 0, -1))
        self.log.session("SITE-A", "192.0.2.1:3389", "연결 중", ts=ts)
        self.log.session("SITE-A", "192.0.2.1:3389", "연결됨", ts=ts + 1)
        self.log.session("SITE-B", "192.0.2.2:3389", "끊김", "네트워크", ts=ts + 2)
        self.log.device("SITE-A", "192.0.2.1:3389", "정상", "오프라인", ts=ts + 3)
        self.log.flush()

    def tearDown(self):
        self.tmp.cleanup()

    def test_shows_only_session_entries_after_restart(self):
        """프로그램을 다시 켠 것처럼 새 ConnLog로 열어도 기록이 나오고, 장비 상태 줄은 섞이지 않음."""
        dlg = HistoryDialog(None, ConnLog(self.dir))
        self.assertEqual(dlg.table.rowCount(), 3)
        self.assertEqual(dlg.table.item(0, 1).text(), "SITE-B")      # 최신순
        self.assertEqual(dlg.table.item(0, 3).text(), "끊김")
        self.assertEqual(dlg.table.item(0, 4).text(), "네트워크")
        dlg.deleteLater()

    def test_search_by_name_and_address(self):
        self.assertEqual(len(load_entries(self.log, "site-a")), 2)
        self.assertEqual(len(load_entries(self.log, "192.0.2.2")), 1)
        self.assertEqual(load_entries(self.log, "없는장비"), [])

    def test_state_filter(self):
        got = load_entries(self.log, state="연결됨")
        self.assertEqual([e["name"] for e in got], ["SITE-A"])

    def test_filter_in_dialog_and_empty_message(self):
        dlg = HistoryDialog(None, self.log)
        dlg.search.setText("없는장비")
        dlg.reload()
        self.assertEqual(dlg.table.rowCount(), 0)
        self.assertIn("없습니다", dlg.summary.text())
        dlg.deleteLater()


if __name__ == "__main__":
    unittest.main()
