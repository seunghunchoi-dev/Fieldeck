"""탭 닫기·재연결 회귀 테스트. 실행: .venv\\Scripts\\python.exe -m unittest tests.test_tab_close -v

실제 원격 PC 없이 MsTscAx 컨트롤과 실제 MainWindow 코드로 확인한다.
- 테스트 주소는 접속이 끝나지 않거나 바로 실패하는 로컬 주소만 쓴다.
- MainWindow는 임시 폴더의 데이터만 쓴다 (실제 세션·로그·설정을 건드리지 않음).
"""
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

from PySide6.QtCore import QPoint, QSettings
from PySide6.QtWidgets import QApplication

from core import appinfo


def pump(seconds, until=None):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QApplication.processEvents()
        if until and until():
            return True
        time.sleep(0.01)
    return bool(until and until())


def session(name):
    return {"name": name, "host": "127.0.0.1", "rdp_port": 1, "rdp_user": "nobody", "rdp_password": "x"}


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def released(self):
        from ui import rdp_tab
        self.assertTrue(pump(15, lambda: rdp_tab.releaser().pending() == 0), "컨트롤이 해제되지 않음")


class TestRdpTabClose(Base):
    def test_close_returns_at_once_and_twice_is_harmless(self):
        from ui.rdp_tab import RdpTab, STATE_CONNECTING
        tab = RdpTab(session("A"))
        tab.show()
        tab.connect_session()
        self.assertEqual(tab.state, STATE_CONNECTING)
        t0 = time.monotonic()
        tab.close_tab()
        tab.close_tab()
        self.assertLess(time.monotonic() - t0, 0.5)    # 닫기를 기다리며 화면이 멈추면 안 됨
        self.assertFalse(tab.is_active())
        tab.connect_session()                          # 닫은 뒤에 예약된 접속이 와도 무시
        self.assertFalse(tab.is_active())
        tab.set_view("actual")                         # 닫은 뒤 호출도 안전
        tab._layout_ax()
        tab.deleteLater()
        self.released()

    def test_close_runs_no_event_loop(self):
        """닫기 안에서 이벤트를 돌리면 입력이 끼어든다 (강제 종료의 원인)."""
        from ui.rdp_tab import RdpTab
        tab = RdpTab(session("A"))
        tab.show()
        tab.connect_session()
        with mock.patch.object(QApplication, "processEvents", side_effect=AssertionError("이벤트 처리 금지")):
            tab.close_tab()
        tab.deleteLater()
        self.released()

    def test_tab_deleted_while_release_pending(self):
        """탭이 먼저 삭제돼도 컨트롤 해제가 끝까지 진행된다."""
        from ui.rdp_tab import RdpTab
        tabs = [RdpTab(session("T%d" % i)) for i in range(3)]
        for t in tabs:
            t.show()
            t.connect_session()
        for t in tabs:
            t.close_tab()
            t.deleteLater()
        self.released()

    def test_reconnect_uses_new_control(self):
        from ui.rdp_tab import RdpTab
        tab = RdpTab(session("A"))
        tab.show()
        tab.connect_session()
        first = tab._ax
        tab.disconnect_session()
        tab.connect_session()
        self.assertIsNot(tab._ax, first)
        self.assertEqual(tab._ax.dynamicCall("Server"), "127.0.0.1")
        tab.close_tab()
        tab.deleteLater()
        self.released()

    def test_stuck_connecting_times_out(self):
        from ui import rdp_tab
        tab = rdp_tab.RdpTab(session("A"))
        tab.show()
        states = []
        tab.state_changed.connect(lambda s, d: states.append((s, d)))
        tab.quality["reachable"] = True            # 네트워크는 닿음 → 자동 재시도 대상 아님
        tab.connect_session()
        tab.quality["reachable"] = True
        with mock.patch.object(tab, "_connected_value", return_value=2):   # 컨트롤이 '연결 중'에 멈춤
            tab._connect_since -= rdp_tab.CONNECT_TIMEOUT + 1
            tab._check_state()
        self.assertEqual(tab.state, rdp_tab.STATE_DISCONNECTED)
        self.assertIn("응답이 없어", states[-1][1])
        self.assertTrue(tab._retry.isVisibleTo(tab._page))    # 다시 연결 버튼이 보인다
        tab.connect_session()                                  # 멈췄던 컨트롤은 버리고 다시 시도
        self.assertEqual(tab.state, rdp_tab.STATE_CONNECTING)
        tab.close_tab()
        tab.deleteLater()
        self.released()

    def test_connecting_within_limit_keeps_waiting(self):
        from ui import rdp_tab
        tab = rdp_tab.RdpTab(session("A"))
        tab.show()
        tab.connect_session()
        with mock.patch.object(tab, "_connected_value", return_value=2):
            tab._connect_since -= rdp_tab.CONNECT_TIMEOUT - 30
            tab._check_state()
        self.assertEqual(tab.state, rdp_tab.STATE_CONNECTING)
        tab.close_tab()
        tab.deleteLater()
        self.released()

    def test_finish_release_waits_for_controls(self):
        from ui import rdp_tab
        tab = rdp_tab.RdpTab(session("A"))
        tab.show()
        tab.connect_session()
        tab.close_tab()
        tab.deleteLater()
        self.assertTrue(rdp_tab.finish_release(12))
        self.assertEqual(rdp_tab.releaser().pending(), 0)


class TestMainWindowClose(Base):
    """실제 MainWindow의 탭 관리. 예전에는 닫는 도중 끼어든 닫기가 엉뚱한 탭을 화면에서 없앴다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        patches = [mock.patch.object(appinfo, "data_dir", return_value=self.tmp.name),
                   mock.patch.dict(os.environ, {"LOCALAPPDATA": self.tmp.name})]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        fmt = QSettings.defaultFormat()
        self.addCleanup(QSettings.setDefaultFormat, fmt)
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)   # 실제 레지스트리 설정을 쓰지 않음
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, self.tmp.name)

        from core.dpapi_store import SessionStore
        from ui import main_window
        self.store = SessionStore(os.path.join(self.tmp.name, "sessions.bin"))
        for n in "ABC":
            self.store.upsert(session(n))
        self.win = main_window.MainWindow(self.store)
        self.win.dashboard.monitor.stop()         # 테스트 중 ping 하지 않음
        self.win.show()
        for n in "ABC":
            self.win.open_session(n)
        pump(0.4)

    def tearDown(self):
        self.win.close()
        self.win.deleteLater()
        pump(0.1)
        self.released()
        self.tmp.cleanup()

    def titles(self):
        return [self.win.tabw.tabText(i) for i in range(self.win.tabw.count())][1:]   # 0번은 대시보드

    def assertConsistent(self):
        """탭 줄에 보이는 것과 내부 세션 표가 같아야 한다 (화면 없는 '유령 탭' 금지)."""
        self.assertEqual(sorted(self.titles()), sorted(self.win.tabs))

    def test_close_removes_only_that_tab(self):
        self.win.close_tab_at(2)
        self.assertEqual(self.titles(), ["A", "C"])
        self.assertConsistent()
        self.released()

    def test_repeated_close_clicks(self):
        """빠르게 연달아 닫아도 표시와 내부 상태가 어긋나지 않는다."""
        for _ in range(3):
            self.win.close_tab_at(1)
        self.win.close_tab_at(1)                  # 탭이 없으면 대시보드 또는 범위 밖 → 무시
        self.assertEqual(self.titles(), [])
        self.assertConsistent()
        self.released()

    def test_input_during_close_does_not_lose_other_tab(self):
        """닫는 도중 끼어든 닫기 — 예전에는 옛 번호로 removeTab 해서 다른 탭이 화면에서 사라졌다."""
        target = self.win.tabs["B"]
        real_close = target.close_tab
        interrupted = []

        def close_with_interrupt():
            interrupted.append(self.win.tabw.indexOf(target))    # 이 시점엔 이미 탭 줄에서 빠져 있어야 함
            self.win.close_session("B")                          # 같은 세션을 또 닫음
            real_close()

        with mock.patch.object(target, "close_tab", side_effect=close_with_interrupt):
            self.win.close_tab_at(self.win.tabw.indexOf(target))
        self.assertEqual(interrupted[0], -1)
        self.assertEqual(self.titles(), ["A", "C"])
        self.assertConsistent()
        self.released()

    def test_closing_session_reopens_with_new_tab(self):
        old = self.win.tabs["B"]
        self.win.close_session("B")
        self.win.open_session("B")
        self.assertIsNot(self.win.tabs["B"], old)
        self.assertIn("B", self.titles())
        self.assertConsistent()
        pump(0.3)
        self.released()

    def test_detached_tab_close(self):
        tab = self.win.tabs["B"]
        self.win.detach_tab(self.win.tabw.indexOf(tab), QPoint(100, 100))
        pump(0.1)
        self.win.detached[tab].close()
        self.assertNotIn("B", self.win.tabs)
        self.assertConsistent()
        self.released()


if __name__ == "__main__":
    unittest.main()
