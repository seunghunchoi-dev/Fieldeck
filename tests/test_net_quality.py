"""네트워크 품질 점수·재연결 판단 테스트.  실행: .venv\\Scripts\\python.exe -m unittest tests.test_net_quality -v"""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.net_quality import icmp_ping, score, tcp_probe  # noqa: E402


class ScoreTest(unittest.TestCase):
    def test_empty_is_measuring(self):
        self.assertEqual(score([])["bars"], -1)

    def test_good_lan(self):
        q = score([1, 2, 1, 1, 2])
        self.assertEqual(q["bars"], 4)
        self.assertEqual(q["loss"], 0)

    def test_levels_by_latency(self):
        self.assertEqual(score([60] * 5)["bars"], 3)
        self.assertEqual(score([150] * 5)["bars"], 2)
        self.assertEqual(score([400] * 5)["bars"], 1)

    def test_jitter_lowers(self):
        # 평균 30ms라도 크게 흔들리면 4칸이 아님
        self.assertLess(score([5, 55, 5, 55, 5, 55])["bars"], 4)

    def test_loss_lowers(self):
        # 손실 20% = +200ms 취급 → 1칸
        q = score([5, None, 5, 5, None, 5, 5, 5, 5, 5])
        self.assertAlmostEqual(q["loss"], 0.2)
        self.assertEqual(q["bars"], 1)

    def test_dead(self):
        self.assertEqual(score([5, 5, None, None, None])["bars"], 0)
        self.assertEqual(score([None])["bars"], 0)
        self.assertIsNone(score([None, None])["rtt"])


class ProbeTest(unittest.TestCase):
    def test_ping_localhost(self):
        self.assertIsNotNone(icmp_ping("127.0.0.1"))

    def test_tcp_closed_port(self):
        self.assertIsNone(tcp_probe("127.0.0.1", 1, 500))


class SiteClassifyTest(unittest.TestCase):
    """대시보드 장비 상태 판정."""

    def test_classify(self):
        from core.site_monitor import (ST_OFFLINE, ST_OK, ST_RDP_CLOSED, ST_SLOW, classify)
        self.assertEqual(classify(3, True, 4), ST_OK)
        self.assertEqual(classify(3, None, 4), ST_OK)          # 포트 재확인 전
        self.assertEqual(classify(250, True, 1), ST_SLOW)
        self.assertEqual(classify(3, False, 4), ST_RDP_CLOSED)
        self.assertEqual(classify(None, False, 0), ST_OFFLINE)
        self.assertEqual(classify(None, True, 0), ST_SLOW)     # ping 막힘 + 포트 열림, 품질 낮음


class RetryDecisionTest(unittest.TestCase):
    """RdpTab._should_retry — 언제 자동 재연결하는지."""

    def setUp(self):
        from ui.rdp_tab import RdpTab, STATE_CONNECTED, STATE_CONNECTING
        self.f = RdpTab._should_retry
        self.C, self.CI = STATE_CONNECTED, STATE_CONNECTING

    def tab(self, user_stop=False, retry_n=0, reachable=True):
        return SimpleNamespace(_user_stop=user_stop, _retry_n=retry_n, quality={"reachable": reachable})

    def test_drop_after_connected_retries(self):
        self.assertTrue(self.f(self.tab(), self.C, 0))

    def test_user_disconnect_no_retry(self):
        self.assertFalse(self.f(self.tab(user_stop=True), self.C, 0))

    def test_logoff_or_replaced_no_retry(self):
        for ext in (2, 5, 11, 12):
            self.assertFalse(self.f(self.tab(), self.C, ext))

    def test_first_connect_fail(self):
        # 네트워크는 되는데 실패 = 계정·설정 문제 → 재시도 안 함 (계정 잠금 방지)
        self.assertFalse(self.f(self.tab(reachable=True), self.CI, 0))
        # 네트워크가 안 닿음 → 재시도
        self.assertTrue(self.f(self.tab(reachable=False), self.CI, 0))
        # 재연결 시도 중 실패 → 계속
        self.assertTrue(self.f(self.tab(retry_n=3), self.CI, 0))


class ScheduleTest(unittest.TestCase):
    """장비별 확인 일정 (수백 대 중 대부분 오프라인인 현장)."""

    def dev(self, state, since_ago, checked_ago):
        from core.site_monitor import Device
        now = 10000.0
        d = Device("x", "192.0.2.1", 3389)
        d.state, d.since = state, now - since_ago
        d.last_check = None if checked_ago is None else now - checked_ago
        return d, now

    def test_due_rules(self):
        from core.site_monitor import SLOW_RECHECK, SiteMonitor, ST_OFFLINE, ST_OK
        due = SiteMonitor.due
        d, now = self.dev(ST_OK, 100, None)
        self.assertTrue(due(d, now, 30))                       # 처음
        d, now = self.dev(ST_OK, 100, 10)
        self.assertFalse(due(d, now, 30))                      # 간격 전
        d, now = self.dev(ST_OK, 100, 30)
        self.assertTrue(due(d, now, 30))                       # 간격 지남
        d, now = self.dev(ST_OFFLINE, 120, 40)
        self.assertTrue(due(d, now, 30))                       # 막 끊긴 장비는 보통 간격
        d, now = self.dev(ST_OFFLINE, 3600, 60)
        self.assertFalse(due(d, now, 30))                      # 오래 오프라인 → 5분마다
        self.assertTrue(due(d, now, 30, force=True))           # '지금 확인'
        d, now = self.dev(ST_OFFLINE, 3600, SLOW_RECHECK)
        self.assertTrue(due(d, now, 30))


if __name__ == "__main__":
    unittest.main()
