"""core.conn_log 테스트 — 실제 로그 폴더(%LOCALAPPDATA%)는 건드리지 않고 임시 폴더 사용."""
import os
import tempfile
import time
import unittest
import zipfile

from core.conn_log import ConnLog, parse_line


class ConnLogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = ConnLog(os.path.join(self.tmp.name, "logs"))

    def tearDown(self):
        self.tmp.cleanup()

    def _lines(self, day):
        self.log.flush()
        with open(self.log.path_for(day), encoding="utf-8") as f:
            return f.read().splitlines()

    def test_write_format_and_daily_file(self):
        ts = time.mktime((2026, 11, 3, 14, 2, 11, 0, 0, -1))
        self.log.device("SITE-PC", "192.0.2.119:3389", "정상", "오프라인", "정상 2시간 유지", ts=ts)
        lines = self._lines("2026-11-03")
        self.assertEqual(lines, ["2026-11-03 14:02:11 | 장비 | SITE-PC | 192.0.2.119:3389 | 정상 → 오프라인 | "
                                 "정상 2시간 유지"])
        e = parse_line(lines[0])
        self.assertEqual((e["kind"], e["name"], e["event"]), ("장비", "SITE-PC", "정상 → 오프라인"))
        self.assertEqual(e["ts"], ts)

    def test_separator_and_newline_are_cleaned(self):
        self.log.session("A|B", "h:1", "끊김", "첫 줄\n둘째 | 줄")
        e = self.log.recent(1)[0]
        self.assertEqual(e["name"], "A/B")
        self.assertEqual(e["detail"], "첫 줄 둘째 / 줄")

    def test_recent_newest_first_across_days_and_kind_filter(self):
        d1 = time.mktime((2026, 11, 1, 9, 0, 0, 0, 0, -1))
        d2 = time.mktime((2026, 11, 2, 9, 0, 0, 0, 0, -1))
        self.log.device("A", "a", "정상", "오프라인", ts=d1)
        self.log.session("A", "a", "연결됨", ts=d2)
        self.log.device("B", "b", "오프라인", "정상", ts=d2 + 5)
        self.assertEqual([e["name"] for e in self.log.recent(10)], ["B", "A", "A"])
        self.assertEqual([e["ts"] for e in self.log.recent(10, "장비")], [d2 + 5, d1])
        self.assertEqual(len(self.log.recent(1)), 1)

    def test_backup_restore_after_reinstall(self):
        """백업 → 로그 폴더 통째로 사라짐(재설치 가정) → 복원하면 그대로."""
        ts = time.mktime((2026, 11, 3, 8, 0, 0, 0, 0, -1))
        for i in range(5):
            self.log.device("PC%d" % i, "h", "정상", "오프라인", ts=ts + i)
        before = self._lines("2026-11-03")
        z = os.path.join(self.tmp.name, "backup.zip")
        self.assertEqual(self.log.export_zip(z), 1)

        fresh = ConnLog(os.path.join(self.tmp.name, "new_install"))
        res = fresh.import_zip(z)
        self.assertEqual((res["files"], res["added"]), (1, 5))
        with open(fresh.path_for("2026-11-03"), encoding="utf-8") as f:
            self.assertEqual(f.read().splitlines(), before)

    def test_restore_merges_without_losing_or_duplicating(self):
        ts = time.mktime((2026, 11, 3, 8, 0, 0, 0, 0, -1))
        self.log.app("시작", ts=ts)
        self.log.app("종료", ts=ts + 100)
        z = os.path.join(self.tmp.name, "b.zip")
        self.log.export_zip(z)
        # 새로 설치한 PC에 이미 기록이 조금 쌓인 상태에서 예전 백업 복원
        fresh = ConnLog(os.path.join(self.tmp.name, "new_install"))
        fresh.app("시작", ts=ts + 50)
        self.assertEqual(fresh.import_zip(z)["added"], 2)
        self.assertEqual(fresh.import_zip(z)["added"], 0)       # 두 번 복원해도 중복 없음
        with open(fresh.path_for("2026-11-03"), encoding="utf-8") as f:
            events = [parse_line(ln)["ts"] for ln in f]
        self.assertEqual(events, [ts, ts + 50, ts + 100])        # 시간순으로 합쳐짐

    def test_restore_ignores_foreign_and_path_traversal_entries(self):
        z = os.path.join(self.tmp.name, "evil.zip")
        good = "2026-11-03 08:00:00 | 프로그램 |  |  | 시작\n"
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("../../conn_2026-11-03.log", good)     # 경로는 무시하고 이름만 사용
            f.writestr("readme.txt", "x")
            f.writestr("conn_2026-11-04.log", "형식이 아닌 줄\n" + good.replace("11-03", "11-04"))
        res = self.log.import_zip(z)
        self.assertEqual(res["skipped"], ["readme.txt"])
        self.assertEqual(sorted(os.listdir(self.log.dir)), ["conn_2026-11-03.log", "conn_2026-11-04.log"])
        self.assertEqual(len(self._lines("2026-11-04")), 1)
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "conn_2026-11-03.log")))

    def test_write_failure_does_not_raise(self):
        blocker = os.path.join(self.tmp.name, "file")
        open(blocker, "w").close()
        bad = ConnLog(os.path.join(blocker, "logs"))     # 파일 아래 폴더 → 만들 수 없음
        bad.app("시작")
        bad.flush()
        self.assertTrue(bad.error)

    def test_many_writes_from_ui_do_not_block_and_all_land(self):
        """화면 스레드에서 연달아 써도 바로 돌아오고, flush 후에는 빠짐없이 순서대로 저장됨."""
        ts = time.mktime((2026, 11, 3, 8, 0, 0, 0, 0, -1))
        t0 = time.perf_counter()
        for i in range(200):
            self.log.device("PC%03d" % i, "h", "확인 중", "정상", ts=ts)
        self.assertLess(time.perf_counter() - t0, 0.15)      # fsync를 기다리지 않음
        lines = self._lines("2026-11-03")
        self.assertEqual([parse_line(ln)["name"] for ln in lines], ["PC%03d" % i for i in range(200)])


if __name__ == "__main__":
    unittest.main()
