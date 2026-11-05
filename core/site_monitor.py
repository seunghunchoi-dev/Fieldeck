"""현장 장비 상태 감시 (대시보드용). 원격 PC 설정은 건드리지 않고 '응답만' 확인한다.

- 장비마다 따로 일정: 마지막 확인 후 interval초가 지나면 다시 ping (1초마다 차례 확인, 스레드 풀)
  응답하는 장비는 전용 작업자 줄 → 응답 없는 장비 수백 대가 있어도 정해진 간격대로 갱신
  10분 넘게 오프라인인 장비는 5분마다만 ('지금 확인'은 모두 즉시)
- RDP 포트(TCP) 확인: 처음 1번, 이후 5분마다, 또는 ping 상태가 바뀌었을 때만 (원격 부담 최소화)
  ping이 막힌 장비는 TCP 연결 시간으로 대신 판단
- 상태: 정상 / 느림 / RDP 닫힘 / 오프라인 / 확인 중
"""
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from core.net_quality import icmp_ping, resolve, score, tcp_probe

ST_CHECKING = "확인 중"
ST_OK = "정상"
ST_SLOW = "느림"
ST_RDP_CLOSED = "RDP 닫힘"
ST_OFFLINE = "오프라인"
SEVERITY = {ST_OFFLINE: 0, ST_RDP_CLOSED: 1, ST_SLOW: 2, ST_CHECKING: 3, ST_OK: 4}   # 작을수록 심각

HISTORY = 30            # 카드에 보여줄 최근 기록 수
TCP_RECHECK = 300       # RDP 포트 재확인 간격(초)
WORKERS = 16            # 응답 없는 장비·처음 확인용 작업자
FAST_WORKERS = 4        # 응답하는 장비 전용 작업자
# 오래 응답 없는 장비는 덜 자주 확인 (응답 없는 장비 1대 확인에 약 3초 → 수백 대면 한 바퀴가 1분 넘게 걸려
# 정상 장비 갱신이 늦어짐). '지금 확인'을 누르면 모두 바로 확인.
SLOW_AFTER = 600        # 이만큼(초) 계속 오프라인이면
SLOW_RECHECK = 300      # 이 간격(초)으로만 확인


def classify(ping_rtt, port_open, bars):
    """한 번의 확인 결과 → 상태.  ping_rtt: ms 또는 None, port_open: True/False/None(확인 안 함)."""
    if ping_rtt is None and not port_open:
        return ST_OFFLINE
    if port_open is False:
        return ST_RDP_CLOSED
    if 0 <= bars <= 2:
        return ST_SLOW
    return ST_OK


class Device:
    """장비 한 대의 상태 (UI는 읽기만)."""

    def __init__(self, name, host, port):
        self.name, self.host, self.port = name, host, int(port or 3389)
        self.state = ST_CHECKING
        self.since = time.time()           # 현재 상태가 시작된 시각
        self.prev_duration = 0
        self.last_ok = None                 # 마지막으로 응답한 시각
        self.last_check = None
        self.rtt = None
        self.port_open = None
        self.port_checked = 0
        self.ping_blocked = False
        self.samples = deque(maxlen=10)     # 신호 막대 계산용
        self.history = deque(maxlen=HISTORY)  # 상태 기록 (카드 띠)
        self.quality = score([])

    def check(self):
        """네트워크 확인 1회 (작업 스레드에서 호출). 상태가 바뀌면 (이전, 새) 반환."""
        ip = resolve(self.host)
        rtt = None
        if ip and not self.ping_blocked:
            rtt = icmp_ping(ip)
        now = time.time()
        ping_changed = (rtt is None) != (self.rtt is None)
        need_tcp = (self.port_open is None or self.ping_blocked or ping_changed
                    or now - self.port_checked > TCP_RECHECK or rtt is None)
        if ip and need_tcp:
            t = tcp_probe(ip, self.port)
            self.port_open = t is not None
            self.port_checked = now
            if rtt is None and t is not None:
                # ping은 안 되는데 포트는 열림 → ping 막힌 장비. TCP 시간으로 품질 측정
                self.ping_blocked = True
                rtt = t
        elif not ip:
            self.port_open = False
        self.samples.append(rtt)
        self.quality = score(list(self.samples))
        self.rtt = rtt
        self.last_check = now
        if rtt is not None or self.port_open:
            self.last_ok = now
        new = classify(rtt, self.port_open, self.quality["bars"])
        self.history.append(new)
        if new != self.state:
            self.prev_duration = now - self.since     # 이전 상태가 이어진 시간 (로그용)
            old, self.state, self.since = self.state, new, now
            return old, new
        return None


class SiteMonitor:
    """모든 장비를 주기적으로 확인. 콜백은 작업 스레드에서 호출되므로 UI 쪽은 시그널로 넘길 것.

    on_update(device)          확인할 때마다
    on_change(device, old, new) 상태가 바뀔 때 (처음 '확인 중' → X 포함)
    """

    def __init__(self, on_update, on_change, interval=30):
        self.on_update, self.on_change = on_update, on_change
        self.interval = interval
        self.devices = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._force = False
        # 작업자 두 줄: 응답 없는 장비(확인 1번에 약 3초)가 응답하는 장비의 확인을 막지 않게
        self._pool = ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="site")        # 오프라인·확인 중
        self._fast = ThreadPoolExecutor(max_workers=FAST_WORKERS, thread_name_prefix="site-fast")  # 응답하는 장비
        self._inflight = set()          # 확인 중인 장비 (중복 제출 방지)
        self._thread = threading.Thread(target=self._run, daemon=True, name="site-monitor")

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        self._wake.set()
        self._pool.shutdown(wait=False, cancel_futures=True)
        self._fast.shutdown(wait=False, cancel_futures=True)

    def refresh_now(self):
        self._force = True
        self._wake.set()

    @staticmethod
    def due(d, now, interval, force=False):
        """지금 확인할 차례인지. 장비마다 따로 일정을 잡는다:
        보통은 마지막 확인 후 interval초, 오래(SLOW_AFTER) 오프라인인 장비는 SLOW_RECHECK초."""
        if force or d.last_check is None:
            return True
        wait = interval
        if d.state == ST_OFFLINE and now - d.since >= SLOW_AFTER:
            wait = max(interval, SLOW_RECHECK)
        return now - d.last_check >= wait

    def set_interval(self, sec):
        self.interval = sec
        self._wake.set()

    def set_targets(self, sessions):
        """세션 목록이 바뀌면 호출. 주소·포트가 같으면 기존 기록 유지."""
        with self._lock:
            new = {}
            for s in sessions:
                d = self.devices.get(s["name"])
                port = int(s.get("rdp_port") or 3389)
                if d is None or d.host != s["host"] or d.port != port:
                    d = Device(s["name"], s["host"], port)
                new[s["name"]] = d
            self.devices = new
        self._wake.set()

    def _check_one(self, d):
        try:
            if self._stop.is_set():
                return
            try:
                ch = d.check()
            except Exception:      # noqa: BLE001 — 한 장비 오류가 감시 전체를 멈추지 않게
                return
            if self._stop.is_set():
                return
            try:
                self.on_update(d)
                if ch:
                    self.on_change(d, *ch)
            except RuntimeError:   # UI가 이미 닫힘
                self._stop.set()
        finally:
            with self._lock:
                self._inflight.discard(id(d))

    def _run(self):
        """1초마다 차례가 된 장비를 작업자에게 넘긴다 (장비별 일정, 한 바퀴를 기다리지 않음)."""
        while not self._stop.is_set():
            force, self._force = self._force, False
            now = time.time()
            with self._lock:
                todo = [d for d in self.devices.values()
                        if id(d) not in self._inflight and self.due(d, now, self.interval, force)]
                self._inflight.update(id(d) for d in todo)
            # 응답하던 장비 먼저, 응답 없는 장비는 별도 줄
            todo.sort(key=lambda d: d.state in (ST_OFFLINE, ST_CHECKING))
            try:
                for d in todo:
                    pool = self._pool if d.state in (ST_OFFLINE, ST_CHECKING) else self._fast
                    pool.submit(self._check_one, d)
            except RuntimeError:   # 종료 중 (스레드 풀 닫힘)
                return
            self._wake.wait(1.0)
            self._wake.clear()
