"""대시보드 카드 배치 테스트 (카드 재사용 방식이 정렬·필터·그룹 이동·삭제를 바르게 반영하는지).

네트워크 감시는 멈추고 장비 상태를 직접 넣는다.
"""
import os
import sys
import tempfile
import unittest

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from core.site_monitor import Device, ST_OFFLINE, ST_OK, ST_SLOW
from ui.dashboard import DashboardTab, DeviceCard

app = QApplication.instance() or QApplication(sys.argv)


def sess(name, group=""):
    return {"name": name, "host": "192.0.2.1", "rdp_port": 3389, "rdp_user": "u", "group": group}


class DashboardLayoutTest(unittest.TestCase):
    def setUp(self):
        self.dash = DashboardTab()
        self.dash.monitor.stop()
        # 실제 레지스트리 대신 임시 설정 파일 (정렬·간단히 바꾸기가 사용자 설정을 덮지 않게)
        self.dash.cfg = QSettings(os.path.join(tempfile.mkdtemp(), "t.ini"), QSettings.Format.IniFormat)
        self.dash.sort_mode = "problem"     # 레지스트리 설정과 무관하게 (각 테스트에서 바꿈)
        self.dash.view = "card"
        self.dash.collapsed = set()
        self.dash.resize(1200, 800)
        self.dash.show()

    def tearDown(self):
        self.dash.close()
        self.dash.deleteLater()
        app.processEvents()

    def load(self, sessions, states):
        self.dash.sessions = {s["name"]: dict(s) for s in sessions}
        devs = {}
        for s in sessions:
            d = Device(s["name"], s["host"], 3389)
            d.state = states.get(s["name"], ST_OK)
            devs[s["name"]] = d
        self.dash.monitor.devices = devs
        self.dash.rebuild()
        app.processEvents()

    def layout(self):
        """화면 순서대로 [(그룹, [보이는 카드 이름...])]"""
        out = []
        lay = self.dash.body_lay
        for i in range(lay.count()):
            w = lay.itemAt(i).widget()
            for g, sec in self.dash._sections.items():
                if w is sec and not sec.isHidden():
                    names = [it.widget().name for it in sec.flow._items if not it.widget().isHidden()]
                    out.append((g, names))
        return out

    def test_order_problem_first_and_groups_sorted(self):
        self.load([sess("b", "A"), sess("a", "A"), sess("c", "B"), sess("z")],
                  {"b": ST_OFFLINE, "a": ST_OK})
        self.assertEqual(self.layout(), [("A", ["b", "a"]), ("B", ["c"]), ("", ["z"])])
        # 상태가 바뀌면 순서가 바뀜 (카드는 같은 객체 재사용)
        card_a = self.dash._pool["a"]
        self.dash.monitor.devices["a"].state = ST_OFFLINE
        self.dash.monitor.devices["b"].state = ST_OK
        self.dash.rebuild()
        self.assertEqual(self.layout()[0], ("A", ["a", "b"]))
        self.assertIs(self.dash._pool["a"], card_a)

    def test_ok_first_puts_reachable_device_and_its_group_on_top(self):
        """대부분 오프라인인 현장: '응답 먼저'면 접속 가능한 장비와 그 그룹이 맨 위."""
        sessions = [sess("RA-%d" % i, "나천") for i in range(3)] + [sess("GA-001", "다천"), sess("GA-002", "다천")]
        self.dash.sort_mode = "ok"
        self.load(sessions, {**{s["name"]: ST_OFFLINE for s in sessions}, "GA-002": ST_OK})
        self.assertEqual(self.layout()[0], ("다천", ["GA-002", "GA-001"]))
        self.dash.sort_mode = "name"
        self.dash.rebuild()
        self.assertEqual(self.layout()[0], ("나천", ["RA-0", "RA-1", "RA-2"]))

    def test_compact_cards_and_site_search(self):
        s = dict(sess("GA-002", "다천"), site_code="GA-002", flow="상류", address="경기도 가나시 다라동 12-3")
        self.load([s, sess("other", "A")], {})
        self.dash._set_compact(True)
        card = self.dash._pool["GA-002"]
        self.assertTrue(card.compact)
        self.assertEqual(card.height(), card.H)
        self.assertEqual(card.sub.text(), "가나시 다라동 12-3")        # 시·도 뺀 짧은 주소
        self.assertEqual(card.flow_chip.text(), "상류")
        self.dash.query = "다라동"                                       # 주소로 검색
        self.dash.rebuild()
        self.assertEqual(self.layout(), [("다천", ["GA-002"])])

    def test_mini_view(self):
        """작은 칸: 한 줄 높이, 접속 버튼·주소는 숨기고 툴팁에 상태."""
        self.load([sess("GA-002", "다천"), sess("other", "A")], {"other": ST_OFFLINE})
        self.dash._set_view("mini")
        app.processEvents()
        card = self.dash._pool["other"]
        self.assertTrue(card.mini)
        self.assertEqual(card.height(), DeviceCard.SIZES["mini"][1])
        self.assertTrue(card.btn.isHidden())
        self.assertIn("오프라인", card.toolTip())
        self.dash.set_open_state("GA-002", "연결됨")
        self.assertEqual(self.dash._pool["GA-002"].ms.text(), "연결됨")
        self.dash._set_view("card")
        self.assertFalse(self.dash._pool["other"].mini)

    def test_group_collapse(self):
        self.load([sess("a1", "A"), sess("b1", "B")], {})
        self.dash._toggle_group("A")
        self.assertTrue(self.dash._sections["A"].box.isHidden())
        self.assertFalse(self.dash._sections["B"].box.isHidden())
        self.assertEqual(self.dash.cfg.value("dash/collapsed", [], type=list), ["A"])
        self.dash.query = "a1"                  # 검색 중에는 접힌 그룹도 펼쳐 보여줌
        self.dash.rebuild()
        self.assertFalse(self.dash._sections["A"].box.isHidden())
        self.dash.query = ""
        self.dash.rebuild()
        self.assertTrue(self.dash._sections["A"].box.isHidden())   # 검색을 지우면 다시 접힘
        self.dash._toggle_fold_all()            # 하나라도 펼쳐져 있으면 모두 접기
        self.assertTrue(all(s.box.isHidden() for s in self.dash._sections.values()))
        self.assertTrue(self.dash._folded)       # 버튼이 '모두 펼치기'로 바뀜
        self.dash._narrow = False
        self.dash._header_texts()
        self.assertEqual(self.dash.fold_btn.text(), "모두 펼치기")
        self.dash._toggle_fold_all()
        self.assertFalse(any(s.box.isHidden() for s in self.dash._sections.values()))

    def test_filter_and_query(self):
        self.load([sess("pc1", "A"), sess("pc2", "B"), sess("srv", "B")], {"pc2": ST_SLOW})
        self.dash._set_filter(ST_SLOW)
        self.assertEqual(self.layout(), [("B", ["pc2"])])
        self.dash._set_filter(None)
        self.dash.query = "pc"
        self.dash.rebuild()
        self.assertEqual(self.layout(), [("A", ["pc1"]), ("B", ["pc2"])])
        self.dash.query = "없는이름"
        self.dash.rebuild()
        self.assertEqual(self.layout(), [])
        self.assertFalse(self.dash._empty.isHidden())
        self.assertIn("조건에 맞는", self.dash._empty.text())

    def test_group_change_delete_and_empty_group_removed(self):
        self.load([sess("x", "A"), sess("y", "A"), sess("w", "C")], {})
        self.dash.sessions["x"]["group"] = "B"          # 그룹 이동
        del self.dash.sessions["w"]                      # 삭제 → 그룹 C도 사라짐
        self.dash.rebuild()
        self.assertEqual(self.layout(), [("A", ["y"]), ("B", ["x"])])
        self.assertNotIn("w", self.dash._pool)
        self.assertNotIn("C", self.dash._sections)
        self.assertTrue(self.dash._empty.isHidden())

    def test_hidden_dashboard_defers_rebuild(self):
        self.load([sess("a", "A")], {})
        self.dash.hide()
        self.dash.sessions["b"] = sess("b", "A")
        self.dash.rebuild()
        self.assertNotIn("b", self.dash._pool)          # 안 보일 때는 미룸
        self.dash.show()
        app.processEvents()
        self.assertEqual(self.layout(), [("A", ["b", "a"])])   # b는 아직 '확인 중' → 정상보다 앞


if __name__ == "__main__":
    unittest.main()
