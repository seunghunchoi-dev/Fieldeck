"""네트워크 품질 측정 (원격 PC 설정 변경 없음 — ping 응답만 본다).

- 기본: ICMP ping (iphlpapi IcmpSendEcho, 관리자 권한 불필요)
- ping이 막힌 장비: RDP 포트 TCP 연결 시간으로 대신 측정 (연결 즉시 닫음, 간격 길게)
- 최근 N개 표본으로 응답 시간·흔들림(지터)·손실률 → 안테나 0~4칸

score()는 순수 함수라 단위 테스트한다 (tests/test_net_quality.py).
"""
import ctypes
import ctypes.wintypes as wt
import socket
import threading
import time

WINDOW = 10            # 최근 표본 수
PING_INTERVAL = 2.0    # 초
TCP_INTERVAL = 5.0     # ping이 막혀 TCP로 잴 때 (원격에 부담 적게)
TIMEOUT_MS = 1500

LABELS = {4: "매우 좋음", 3: "좋음", 2: "보통", 1: "나쁨", 0: "끊김", -1: "측정 중"}


# --------------------------------------------------------------------------- 측정
class _IP_OPTION_INFORMATION(ctypes.Structure):
    _fields_ = [("Ttl", ctypes.c_ubyte), ("Tos", ctypes.c_ubyte), ("Flags", ctypes.c_ubyte),
                ("OptionsSize", ctypes.c_ubyte), ("OptionsData", ctypes.c_void_p)]


class _ICMP_ECHO_REPLY(ctypes.Structure):
    _fields_ = [("Address", wt.ULONG), ("Status", wt.ULONG), ("RoundTripTime", wt.ULONG),
                ("DataSize", wt.USHORT), ("Reserved", wt.USHORT), ("Data", ctypes.c_void_p),
                ("Options", _IP_OPTION_INFORMATION)]


_icmp = ctypes.windll.iphlpapi
_icmp.IcmpCreateFile.restype = wt.HANDLE
_icmp.IcmpSendEcho.argtypes = [wt.HANDLE, wt.ULONG, ctypes.c_void_p, wt.WORD, ctypes.c_void_p,
                               ctypes.c_void_p, wt.DWORD, wt.DWORD]
_icmp.IcmpCloseHandle.argtypes = [wt.HANDLE]


def resolve(host):
    try:
        return socket.gethostbyname(host)
    except OSError:
        return None


def icmp_ping(ip, timeout_ms=TIMEOUT_MS):
    """응답 시간(ms) 또는 None."""
    addr = int.from_bytes(socket.inet_aton(ip), "little")
    h = _icmp.IcmpCreateFile()
    if not h or h == wt.HANDLE(-1).value:
        return None
    try:
        data = b"Fieldeck-ping"
        buf = ctypes.create_string_buffer(ctypes.sizeof(_ICMP_ECHO_REPLY) + len(data) + 8)
        n = _icmp.IcmpSendEcho(h, addr, data, len(data), None, buf, len(buf), timeout_ms)
        if n == 0:
            return None
        rep = _ICMP_ECHO_REPLY.from_buffer(buf)
        return float(rep.RoundTripTime) if rep.Status == 0 else None
    finally:
        _icmp.IcmpCloseHandle(h)


def tcp_probe(ip, port, timeout_ms=TIMEOUT_MS):
    """TCP 연결 시간(ms) 또는 None. 연결되면 바로 닫는다."""
    t0 = time.perf_counter()
    try:
        with socket.create_connection((ip, port), timeout=timeout_ms / 1000):
            return (time.perf_counter() - t0) * 1000
    except OSError:
        return None


# --------------------------------------------------------------------------- 점수
def score(samples):
    """samples: 최근 응답 시간 목록 (None = 응답 없음).

    반환 dict: bars(-1~4), rtt, jitter, loss(0~1), label
    체감 지연 = 평균 응답 + 지터×2 + 손실 10%당 100ms
      <40ms 4칸 · <100 3칸 · <200 2칸 · 그 이상 1칸 · 최근 3번 연속 무응답 또는 손실 60%↑ 0칸
    """
    q = {"bars": -1, "rtt": None, "jitter": None, "loss": 0.0}
    if not samples:
        q["label"] = LABELS[-1]
        return q
    ok = [s for s in samples if s is not None]
    q["loss"] = 1 - len(ok) / len(samples)
    if ok:
        q["rtt"] = sum(ok) / len(ok)
        q["jitter"] = (sum(abs(a - b) for a, b in zip(ok, ok[1:])) / (len(ok) - 1)) if len(ok) > 1 else 0.0
    tail_dead = len(samples) >= 3 and all(s is None for s in samples[-3:])
    if not ok or tail_dead or q["loss"] >= 0.6:
        q["bars"] = 0
    else:
        eff = q["rtt"] + 2 * q["jitter"] + q["loss"] * 1000
        q["bars"] = 4 if eff < 40 else 3 if eff < 100 else 2 if eff < 200 else 1
    q["label"] = LABELS[q["bars"]]
    return q


def describe(q):
    """툴팁용 한 줄 설명."""
    if q["bars"] < 0:
        return "네트워크 품질 측정 중…"
    if q["rtt"] is None:
        return "응답 없음 (네트워크 끊김)"
    return "%s  ·  응답 %dms  ·  흔들림 %dms  ·  손실 %d%%  (%s)" % (
        q["label"], round(q["rtt"]), round(q["jitter"] or 0), round(q["loss"] * 100), q.get("method", "ping"))


# --------------------------------------------------------------------------- 감시 스레드
class QualityProbe:
    """백그라운드에서 주기적으로 측정, on_update(q) 콜백 (다른 스레드에서 호출됨).

    ping이 연속 3번 실패하는데 TCP는 되면 ping이 막힌 장비로 보고 TCP 방식으로 바꾼다.
    """

    def __init__(self, host, port, on_update):
        self.host, self.port, self.on_update = host, int(port or 3389), on_update
        self.samples = []
        self.method = "ping"
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="quality-" + host)

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        self._wake.set()

    def poke(self):
        """바로 한 번 더 측정 (재연결 판단 직전 등)."""
        self._wake.set()

    def _measure(self, ip):
        if self.method == "ping":
            r = icmp_ping(ip)
            if r is None and len(self.samples) >= 2 and all(s is None for s in self.samples[-2:]):
                t = tcp_probe(ip, self.port)
                if t is not None:          # ping만 막힘 → TCP 방식으로 전환
                    self.method = "tcp"
                    self.samples = []
                    return t
            return r
        return tcp_probe(ip, self.port)

    def _run(self):
        ip = None
        while not self._stop.is_set():
            ip = ip or resolve(self.host)
            r = self._measure(ip) if ip else None
            if r is None:
                ip = None                 # 이름 해석부터 다시 (DHCP·DNS 변경 대비)
            self.samples = (self.samples + [r])[-WINDOW:]
            q = score(self.samples)
            q["method"] = self.method
            q["reachable"] = r is not None
            if not self._stop.is_set():
                try:
                    self.on_update(q)
                except RuntimeError:      # 받는 쪽 위젯이 이미 삭제됨
                    return
            self._wake.wait(PING_INTERVAL if self.method == "ping" else TCP_INTERVAL)
            self._wake.clear()
