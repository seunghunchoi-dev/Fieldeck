"""실행: .venv\\Scripts\\python.exe -m unittest tests.test_rdp -v
실제 원격 PC 없이 확인 가능한 부분만 검사한다.
"""
import sys
import time
import unittest

from core.rdp_launcher import build_rdp_text


class TestRdpFile(unittest.TestCase):
    def test_no_password_in_rdp(self):
        s = {"host": "10.0.0.5", "rdp_port": 3390, "rdp_user": "admin", "rdp_password": "secret"}
        text = build_rdp_text(s)
        self.assertIn("full address:s:10.0.0.5:3390", text)
        self.assertNotIn("secret", text)

    def test_clipboard_flag(self):
        base = {"host": "h", "rdp_user": "u"}
        self.assertIn("redirectclipboard:i:1", build_rdp_text(base))
        self.assertIn("redirectclipboard:i:0", build_rdp_text(dict(base, redirect_clipboard=False)))

    def test_default_port_omitted(self):
        text = build_rdp_text({"host": "h", "rdp_port": 3389, "rdp_user": "u"})
        self.assertIn("full address:s:h\r\n", text)


class TestRdpTab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_failed_connect_reports_disconnected(self):
        """열리지 않은 포트로 접속 → '연결 중' 후 '끊김'으로 바뀌어야 한다."""
        from ui.rdp_tab import RdpTab, STATE_CONNECTING, STATE_DISCONNECTED
        tab = RdpTab({"host": "127.0.0.1", "rdp_port": 1, "rdp_user": "nobody",
                      "rdp_password": "x"})
        states = []
        tab.state_changed.connect(lambda s, d: states.append(s))
        tab.resize(800, 600)
        tab.show()
        tab.connect_session()
        # 접속 정보가 컨트롤에 실제로 들어갔는지 (PySide6 문자열 전달 문제 재발 방지)
        self.assertEqual(tab._ax.dynamicCall("Server"), "127.0.0.1")
        self.assertEqual(tab._ax.dynamicCall("UserName"), "nobody")
        adv = tab._ax.querySubObject("AdvancedSettings9")
        self.assertEqual(adv.dynamicCall("RDPPort"), 1)
        self.assertTrue(adv.dynamicCall("RedirectClipboard"))
        deadline = time.time() + 60
        while time.time() < deadline and STATE_DISCONNECTED not in states:
            self.app.processEvents()
            time.sleep(0.05)
        tab.close_tab()
        self.assertEqual(states[0], STATE_CONNECTING)
        self.assertIn(STATE_DISCONNECTED, states)


if __name__ == "__main__":
    unittest.main()
