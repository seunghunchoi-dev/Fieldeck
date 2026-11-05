"""엑셀 백업·복원 테스트.  실행: .venv\\Scripts\\python.exe -m unittest tests.test_excel_io -v"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import excel_io  # noqa: E402
from core.dpapi_store import SESSION_DEFAULTS  # noqa: E402


def S(name, **kw):
    s = dict(SESSION_DEFAULTS, name=name, host=kw.pop("host", "10.0.0.%d" % (len(name) % 250)))
    s.update(kw)
    return s


SESSIONS = [
    S("관제서버", group="현장 A", rdp_user="admin", rdp_password="pw1", favorite=True, note="1층"),
    S("카메라 PC", group="현장 B", rdp_port=3390, rdp_user="op", rdp_password="pw2",
      resolution="1920x1080", redirect_clipboard=False, last_connected=1700000000),
]


class ExcelTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "b.xlsx")

    def test_roundtrip_without_password(self):
        excel_io.export_sessions(self.path, SESSIONS)
        self.assertFalse(excel_io.is_encrypted(self.path))
        rows, problems, has_pw = excel_io.read_sessions(self.path)
        self.assertEqual(problems, [])
        self.assertFalse(has_pw)
        by = {r["name"]: r for r in rows}
        self.assertEqual(by["카메라 PC"]["rdp_port"], 3390)
        self.assertEqual(by["카메라 PC"]["resolution"], "1920x1080")
        self.assertFalse(by["카메라 PC"]["redirect_clipboard"])
        self.assertTrue(by["관제서버"]["favorite"])
        self.assertEqual(by["관제서버"]["group"], "현장 A")
        self.assertNotIn("rdp_password", by["관제서버"])
        # 파일 안에 비밀번호 글자가 없어야 함
        import zipfile
        with zipfile.ZipFile(self.path) as z:
            blob = b"".join(z.read(n) for n in z.namelist())
        self.assertNotIn(b"pw1", blob)

    def test_plain_excel_with_passwords(self):
        """화면 백업 방식: 암호 없는 일반 엑셀 + 비밀번호 포함 (2026-11-03 사용자 요청)."""
        excel_io.export_sessions(self.path, SESSIONS, include_password=True)
        self.assertFalse(excel_io.is_encrypted(self.path))
        rows, _, has_pw = excel_io.read_sessions(self.path)          # 암호 없이 바로 읽힘
        self.assertTrue(has_pw)
        self.assertEqual({r["name"]: r["rdp_password"] for r in rows}, {"관제서버": "pw1", "카메라 PC": "pw2"})

    def test_encrypted_roundtrip(self):
        """예전에 열기 암호를 걸어 만든 백업도 계속 복원 가능."""
        excel_io.export_sessions(self.path, SESSIONS, include_password=True, file_password="secret12")
        self.assertTrue(excel_io.is_encrypted(self.path))
        with open(self.path, "rb") as f:
            self.assertNotIn(b"pw1", f.read())
        with self.assertRaises(excel_io.BackupPasswordError):
            excel_io.read_sessions(self.path)
        with self.assertRaises(excel_io.BackupPasswordError):
            excel_io.read_sessions(self.path, "wrong")
        rows, _, has_pw = excel_io.read_sessions(self.path, "secret12")
        self.assertTrue(has_pw)
        self.assertEqual({r["name"]: r["rdp_password"] for r in rows}, {"관제서버": "pw1", "카메라 PC": "pw2"})

    def test_hand_written_sheet(self):
        """엑셀에서 직접 만든 목록 (열 순서 다름, 오류 줄 포함)."""
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(["주소", "이름", "포트", "해상도", "즐겨찾기"])
        ws.append(["192.168.0.10", "A동", None, "자동", "예"])
        ws.append(["192.168.0.11", "B동", "abc", None, None])      # 포트 오류
        ws.append([None, "C동", 3389, None, None])                  # 주소 없음
        ws.append(["192.168.0.13", "D동", 3389, "1280×720", "아니오"])
        ws.append([None, None, None, None, None])                    # 빈 줄
        wb.save(self.path)
        rows, problems, _ = excel_io.read_sessions(self.path)
        self.assertEqual([r["name"] for r in rows], ["A동", "D동"])
        self.assertEqual(rows[0]["rdp_port"], 3389)
        self.assertEqual(rows[1]["resolution"], "1280x720")
        self.assertEqual(len(problems), 2)
        self.assertTrue(problems[0].startswith("3행"))

    def test_plan_merge_keeps_password(self):
        existing = [dict(s) for s in SESSIONS]
        rows = [{"name": "관제서버", "host": "10.9.9.9"}, {"name": "새 PC", "host": "10.1.1.1"}]
        p = excel_io.plan_restore(existing, rows, "merge", "overwrite")
        by = {s["name"]: s for s in p["sessions"]}
        self.assertEqual(p["added"], ["새 PC"])
        self.assertEqual(p["updated"], ["관제서버"])
        self.assertEqual(by["관제서버"]["host"], "10.9.9.9")
        self.assertEqual(by["관제서버"]["rdp_password"], "pw1")   # 엑셀에 없으면 기존 유지
        self.assertIn("카메라 PC", by)                             # 합치기: 기존 유지
        self.assertEqual(by["새 PC"]["rdp_port"], 3389)

    def test_plan_skip_and_replace(self):
        existing = [dict(s) for s in SESSIONS]
        rows = [{"name": "관제서버", "host": "10.9.9.9"}]
        p = excel_io.plan_restore(existing, rows, "merge", "skip")
        self.assertEqual(p["skipped"], ["관제서버"])
        p = excel_io.plan_restore(existing, rows, "replace")
        self.assertEqual(p["removed"], ["카메라 PC"])
        self.assertEqual(len(p["sessions"]), 1)
        self.assertEqual(p["sessions"][0]["rdp_password"], "pw1")


class AllFieldsTest(unittest.TestCase):
    """모든 정보 백업 (2026-11-03): 세션의 모든 항목이 엑셀로 나갔다가 그대로 돌아와야 함."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "all.xlsx")

    def test_every_session_field_has_a_column(self):
        cols = {k for k, _, _ in excel_io.COLUMNS}
        self.assertEqual(set(SESSION_DEFAULTS) - cols, set(),
                         "세션에 새 항목을 추가했으면 excel_io.COLUMNS에도 추가할 것")

    def test_full_roundtrip_with_passwords(self):
        full = S("전체", group="G", rdp_port=3391, rdp_user="u", rdp_password="pw-rdp", resolution="fit",
                 redirect_clipboard=False, favorite=True, note="메모", protocol="ftp", ft_port=2121,
                 ft_user="fu", ft_password="pw-ft", last_connected=1793660400)
        excel_io.export_sessions(self.path, [full], include_password=True)
        rows, problems, has_pw = excel_io.read_sessions(self.path)
        self.assertEqual(problems, [])
        self.assertTrue(has_pw)
        restored = excel_io.plan_restore([], rows, mode="replace")["sessions"][0]
        self.assertEqual(restored, full)

    def test_without_passwords_keeps_existing_ones(self):
        old = S("기존", rdp_password="old-rdp", ft_password="old-ft", ft_user="a")
        new = dict(old, ft_user="b")
        excel_io.export_sessions(self.path, [new])
        rows, _, has_pw = excel_io.read_sessions(self.path)
        self.assertFalse(has_pw)
        got = excel_io.plan_restore([old], rows)["sessions"][0]
        self.assertEqual((got["ft_user"], got["rdp_password"], got["ft_password"]), ("b", "old-rdp", "old-ft"))

    def test_bad_protocol_and_port_reported(self):
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(["이름", "주소", "전송 방식", "전송 포트", "마지막 접속"])
        ws.append(["a", "1.1.1.1", "http", "", ""])
        ws.append(["b", "1.1.1.2", "SFTP", "99999", ""])
        ws.append(["c", "1.1.1.3", "", "", "잘못된 날짜"])
        wb.save(self.path)
        rows, problems, _ = excel_io.read_sessions(self.path)
        self.assertEqual([r["name"] for r in rows], ["c"])        # 날짜가 틀려도 세션은 복원
        self.assertNotIn("last_connected", rows[0])
        self.assertTrue(any("2행" in p and "전송 방식" in p for p in problems))
        self.assertTrue(any("3행" in p and "전송 포트" in p for p in problems))

    def test_template_is_empty_form_and_filled_form_restores(self):
        excel_io.export_template(self.path)
        from openpyxl import load_workbook
        wb = load_workbook(self.path)
        ws = wb["세션목록"]
        heads = [c.value for c in ws[1]]
        self.assertEqual(ws.max_row, 1)                           # 데이터 줄 없음
        self.assertIn("이름", heads)
        for secret in ("비밀번호", "전송 비밀번호", "마지막 접속"):
            self.assertNotIn(secret, heads)
        ws.append({heads.index("이름") + 1: "새 PC", heads.index("주소") + 1: "192.0.2.200",
                   heads.index("그룹") + 1: "현장 A"})
        wb.save(self.path)
        rows, problems, _ = excel_io.read_sessions(self.path)
        self.assertEqual(problems, [])
        s = excel_io.plan_restore([], rows)["sessions"][0]
        self.assertEqual((s["name"], s["host"], s["group"], s["rdp_port"]), ("새 PC", "192.0.2.200", "현장 A", 3389))


if __name__ == "__main__":
    unittest.main()
