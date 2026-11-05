"""RDP 원격 화면 탭 — Windows 원격 데스크톱 ActiveX(MsTscAx)를 QAxWidget으로 내장.

주의:
- ActiveX 이벤트(OnConnected/OnDisconnected)에 기대지 않는다 (PyQt6 시절 전달 안 됨을 확인).
  → 1초마다 `Connected` 속성(0=끊김, 1=연결, 2=연결 중)을 읽어 상태를 판단한다.
- COM 속성 설정은 _put(대상, "속성명", 값)만 사용한다.
  PySide6에서는 dynamicCall("속성", "문자열")로 넘기면 문자열이 전달되지 않는다(주소·계정이 빈 값이 됨, 실기 확인).
  값을 리스트로 감싸 dynamicCall("속성", [값])으로 넘겨야 정상 반영된다.
- UI 라이브러리: PySide6 (LGPL, 2026-11-03 PyQt6(GPL)에서 교체 — 설계문서 7장).
"""
import time

from PySide6.QtAxContainer import QAxWidget
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QStackedLayout, QVBoxLayout, QWidget)

from core.net_quality import QualityProbe, describe
from ui.icons import icon

PROGID = "MsTscAx.MsTscAx"

STATE_IDLE = "대기"
STATE_CONNECTING = "연결 중"
STATE_CONNECTED = "연결됨"
STATE_DISCONNECTED = "끊김"
STATE_RECONNECTING = "재연결 대기"

_CONNECTED_MAP = {0: STATE_DISCONNECTED, 1: STATE_CONNECTED, 2: STATE_CONNECTING}

# ---- 불안정한 네트워크 대응 (설계문서 6-5 참고) ----
# 1) RDP 자체 기능: 네트워크 자동 감지·대역폭 측정, 비트맵 캐시·압축, keep-alive,
#    순간 끊김 시 세션을 유지한 채 자동 재접속(ARC, 컨트롤이 직접 처리)
# 2) 그래도 끊기면 프로그램이 재연결: 대기 시간을 늘려 가며(지수 백오프) 시도하고,
#    ping이 다시 응답할 때까지는 시도하지 않는다 (헛시도·계정 잠금 방지)
# 3) 신호가 나쁠 때(안테나 0~1칸) 다시 연결하면 저속 모드(16비트 색, 화면 효과 끔)로 접속
BACKOFF = [2, 4, 8, 15, 30]   # 초, 이후 30초 반복
MAX_RETRIES = 10
MAX_WAIT_NET = 600            # 네트워크 응답을 기다리는 최대 시간(초) — 넘으면 자동 재연결 중단
NET_TYPE_AUTODETECT = 7       # CONNECTION_TYPE_AUTODETECT
NET_TYPE_MODEM = 1            # 가장 낮은 대역폭 기준 (저속 모드)
# 재연결하면 안 되는 끊김 (ExtendedDisconnectReason): 사용자/관리자가 끊음·로그아웃,
# 다른 곳에서 같은 계정으로 접속(서로 밀어내기 방지), 권한·자격 증명 문제
NO_RETRY_EXT = {1, 2, 5, 7, 9, 10, 11, 12}


def _put(obj, name, value):
    """ActiveX(COM) 속성 설정. PySide6는 값을 리스트로 감싸야 문자열이 제대로 전달된다."""
    obj.dynamicCall(name, [value])


class _Holder(QWidget):
    """스크롤 영역 안 받침 — 크기가 바뀌면 원격 화면 위치를 다시 계산."""

    def __init__(self, tab):
        super().__init__()
        self._tab = tab

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._tab._layout_ax()


class RdpTab(QWidget):
    """세션 하나 = 탭 하나. state_changed(상태문자열, 상세메시지) 시그널을 낸다."""

    state_changed = Signal(str, str)
    view_changed = Signal()   # 보기 방식·배율 변경
    quality_changed = Signal(dict)   # 네트워크 품질 (core.net_quality.score 결과)
    _quality_from_thread = Signal(dict)

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = dict(session)
        self.state = STATE_IDLE
        self.quality = {"bars": -1, "rtt": None, "jitter": None, "loss": 0.0, "label": "측정 중"}
        self.low_bandwidth = False   # 이번 접속이 저속 모드인지
        self._probe = None
        self._user_stop = False      # 사용자가 직접 끊었는지 (그럼 자동 재연결 안 함)
        self._retry_n = 0
        self._ever_connected = False
        self._last_ext = 0            # 마지막 끊김 사유 코드 (ExtendedDisconnectReason, 로그용)
        self._countdown = 0
        self._wait_since = None
        self._quality_from_thread.connect(self._on_quality)
        self._retry_timer = QTimer(self)
        self._retry_timer.setInterval(1000)
        self._retry_timer.timeout.connect(self._retry_tick)

        self._stack = QStackedLayout(self)

        # 안내 화면 (연결 전 / 끊김 / 실패)
        self._page = QWidget()
        lay = QVBoxLayout(self._page)
        lay.addStretch(1)
        self._title = QLabel("연결 준비 중")
        self._title.setObjectName("heroTitle")
        self._msg = QLabel("")
        self._msg.setObjectName("heroSub")
        self._msg.setWordWrap(True)
        for w in (self._title, self._msg):
            w.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(w)
        self._retry = QPushButton("다시 연결")
        self._retry.setObjectName("primary")
        self._retry.setIcon(icon("refresh", "#FFFFFF", 16))
        self._retry.setCursor(Qt.CursorShape.PointingHandCursor)
        self._retry.setMinimumWidth(160)
        self._retry.clicked.connect(self._manual_retry)
        self._retry.hide()
        self._cancel = QPushButton("자동 재연결 취소")
        self._cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel.clicked.connect(self.cancel_auto_retry)
        self._cancel.hide()
        btns = QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(self._retry)
        btns.addWidget(self._cancel)
        btns.addStretch(1)
        lay.addSpacing(16)
        lay.addLayout(btns)
        lay.addStretch(1)

        # 원격 화면: 스크롤 영역 > 받침(holder) > ActiveX
        #  - 축소 보기: ActiveX를 화면 비율 유지한 채 창에 맞게 줄여 가운데 배치 (SmartSizing)
        #  - 원본 크기: ActiveX를 원격 해상도 그대로 두고 스크롤
        self._scroll = QScrollArea()
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._holder = _Holder(self)
        self._holder.setObjectName("rdpHolder")
        self._scroll.setWidget(self._holder)
        self._ax = QAxWidget(self._holder)
        if not self._ax.setControl(PROGID):
            raise RuntimeError("원격 데스크톱 ActiveX(MsTscAx)를 불러올 수 없습니다.")
        self._stack.addWidget(self._page)
        self._stack.addWidget(self._scroll)

        self.view = "fit"        # "fit" 축소 보기 | "actual" 원본 크기(스크롤)
        self.scale = 1.0

        self._poll = QTimer(self)
        self._poll.setInterval(1000)
        self._poll.timeout.connect(self._check_state)

        # 창 크기 변경 → 원격 해상도 따라가기 (멈춘 뒤 0.5초 후 1번만 적용)
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(500)
        self._resize_timer.timeout.connect(self._apply_resize)
        self._last_applied = None

    # --- 해상도 ---
    def _fit_mode(self):
        """원격 해상도가 창 크기를 따라가는 모드인지."""
        return self.session.get("resolution", "auto") == "fit"

    def _desktop_size(self):
        """접속 해상도.
        auto = 이 PC 모니터 해상도 (창에 맞춰 축소 표시)
        fit  = 탭 크기 (창 크기를 바꾸면 원격 해상도도 변경)
        'WxH' = 고정 (창에 맞춰 축소 표시)
        """
        res = self.session.get("resolution", "auto")
        if res == "fit":
            sz = self.size()
            return max(800, sz.width()) // 2 * 2, max(600, sz.height()) // 2 * 2
        if res != "auto":
            try:
                w, h = (int(x) for x in res.lower().split("x"))
                return w, h
            except ValueError:
                pass
        scr = self.screen() or QApplication.primaryScreen()
        g, dpr = scr.geometry(), scr.devicePixelRatio()
        return int(g.width() * dpr) // 2 * 2, int(g.height() * dpr) // 2 * 2

    def remote_size(self):
        return self._last_applied or self._desktop_size()

    def can_toggle_view(self):
        """창 크기를 따라가는 모드가 아니면 축소/원본 전환 가능."""
        return not self._fit_mode()

    def set_view(self, view):
        self.view = view
        if self.state in (STATE_CONNECTING, STATE_CONNECTED):
            adv = self._ax.querySubObject("AdvancedSettings9")
            _put(adv, "SmartSizing", view == "fit")
        self._layout_ax()

    def _layout_ax(self):
        """현재 보기 방식에 맞게 ActiveX 크기·위치 결정."""
        if not hasattr(self, "view"):   # 생성 도중 호출 무시
            return
        dw, dh = self.remote_size()
        vp = self._scroll.viewport().size()
        if self._fit_mode():
            self._scroll.setWidgetResizable(True)
            self._ax.setGeometry(0, 0, self._holder.width(), self._holder.height())
            self.scale = 1.0
        elif self.view == "fit":
            self._scroll.setWidgetResizable(True)
            self.scale = min(vp.width() / dw, vp.height() / dh, 1.0)
            w, h = int(dw * self.scale), int(dh * self.scale)
            hw, hh = self._holder.width(), self._holder.height()
            self._ax.setGeometry((hw - w) // 2, (hh - h) // 2, w, h)
        else:
            self._scroll.setWidgetResizable(False)
            self._holder.resize(dw, dh)
            self._ax.setGeometry(0, 0, dw, dh)
            self.scale = 1.0
        self.view_changed.emit()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._fit_mode() and self.state == STATE_CONNECTED:
            self._resize_timer.start()

    def _apply_resize(self):
        if self.state != STATE_CONNECTED or not self._fit_mode():
            return
        w, h = self._desktop_size()
        if (w, h) == self._last_applied:
            return
        # IMsRdpClient9::UpdateSessionDisplaySettings (원격 PC가 Windows 8.1 / 2012 R2 이상일 때 동작)
        self._ax.dynamicCall("UpdateSessionDisplaySettings(uint,uint,uint,uint,uint,uint,uint)",
                             [w, h, 0, 0, 0, 100, 100])
        self._last_applied = (w, h)
        self.view_changed.emit()

    # --- 공개 메서드 ---
    def connect_session(self):
        if self.is_active():
            return
        self._retry_timer.stop()
        self._user_stop = False
        self._start_probe()
        s = self.session
        ax = self._ax
        w, h = self._desktop_size()
        self._last_applied = (w, h)
        # 신호가 나쁜 상태에서 (재)연결하면 저속 모드
        self.low_bandwidth = 0 <= self.quality["bars"] <= 1
        _put(ax, "Server", s["host"])
        _put(ax, "UserName", s["rdp_user"])
        _put(ax, "DesktopWidth", w)
        _put(ax, "DesktopHeight", h)
        _put(ax, "ColorDepth", 16 if self.low_bandwidth else 32)

        adv = ax.querySubObject("AdvancedSettings9")
        _put(adv, "RDPPort", int(s.get("rdp_port") or 3389))
        _put(adv, "EnableCredSspSupport", True)   # NLA 지원
        _put(adv, "AuthenticationLevel", 2)       # 서버 인증 실패 시 경고 후 선택
        _put(adv, "SmartSizing", self.view == "fit")  # 축소 보기일 때 창에 맞춰 축소
        # 클립보드 공유: 로컬 ↔ 원격 텍스트·파일 복사/붙여넣기 (원격 PC 설정 변경 없음)
        _put(adv, "RedirectClipboard", bool(s.get("redirect_clipboard", True)))
        # 불안정한 네트워크 대응 (이번 접속에만 적용, 원격 PC 설정은 바꾸지 않음)
        # 자동 감지(7) = 접속 중 대역폭·지연을 재서 화질·화면 효과를 스스로 조절
        _put(adv, "NetworkConnectionType", NET_TYPE_MODEM if self.low_bandwidth else NET_TYPE_AUTODETECT)
        _put(adv, "EnableAutoReconnect", True)    # 순간 끊김 → 세션 유지한 채 자동 재접속
        _put(adv, "MaxReconnectAttempts", 20)
        _put(adv, "keepAliveInterval", 15000)     # 15초마다 연결 확인 (끊김을 빨리 감지)
        _put(adv, "BitmapPeristence", 1)          # 화면 조각 디스크 캐시 (API 이름 철자 그대로)
        _put(adv, "Compress", 1)
        if s.get("rdp_password"):
            _put(adv, "ClearTextPassword", s["rdp_password"])  # 메모리로만 전달

        self._stack.setCurrentWidget(self._scroll)
        self._layout_ax()
        self._set_state(STATE_CONNECTING, "저속 모드" if self.low_bandwidth else "")
        ax.dynamicCall("Connect()")
        self._poll.start()

    def disconnect_session(self):
        self._user_stop = True
        self._retry_timer.stop()
        self._retry_n = 0
        self._poll.stop()
        if self._connected_value() != 0:
            self._ax.dynamicCall("Disconnect()")
        detail = "연결을 끊었습니다."
        self._show_page("연결 끊김", detail, retry=True)
        self._set_state(STATE_DISCONNECTED, detail)

    def cancel_auto_retry(self):
        self._retry_timer.stop()
        self._retry_n = 0
        detail = "자동 재연결을 취소했습니다."
        self._show_page("연결이 끊겼어요", detail, retry=True)
        self._set_state(STATE_DISCONNECTED, detail)

    def _manual_retry(self):
        self._retry_n = 0
        self.connect_session()

    def is_active(self):
        return self.state in (STATE_CONNECTING, STATE_CONNECTED)

    # --- 네트워크 품질 ---
    def _start_probe(self):
        if self._probe is None:
            self._probe = QualityProbe(self.session["host"], self.session.get("rdp_port", 3389),
                                       self._quality_from_thread.emit).start()

    def stop_probe(self):
        if self._probe:
            self._probe.stop()
            self._probe = None

    def _on_quality(self, q):
        self.quality = q
        self.quality_changed.emit(q)
        if self.state == STATE_RECONNECTING:
            self._update_retry_page()

    # --- 자동 재연결 ---
    def _should_retry(self, prev, ext):
        if self._user_stop or ext in NO_RETRY_EXT:
            return False
        if prev == STATE_CONNECTED:
            return True               # 로그인까지 됐던 연결 → 네트워크 문제로 판단
        if self._retry_n > 0:
            return True               # 재연결 시도 중 실패 → 계속
        # 처음 접속 실패: 네트워크가 안 닿을 때만 재시도 (계정·설정 문제면 재시도하지 않음)
        return not self.quality.get("reachable", True)

    def _schedule_retry(self):
        if self._retry_n >= MAX_RETRIES:
            self._retry_n = 0
            return False
        self._countdown = BACKOFF[min(self._retry_n, len(BACKOFF) - 1)]
        self._retry_n += 1
        self._wait_since = None
        code = "끊김 코드 %d, " % self._last_ext if self._last_ext else ""
        self._set_state(STATE_RECONNECTING, "%s자동 재연결 %d/%d회 (%d초 후)"
                        % (code, self._retry_n, MAX_RETRIES, self._countdown))
        self._update_retry_page()
        self._retry_timer.start()
        return True

    def _retry_tick(self):
        if self._countdown > 0:
            self._countdown -= 1
            self._update_retry_page()
            return
        if not self.quality.get("reachable", False):
            # ping이 돌아올 때까지는 접속 시도 안 함 (시도 횟수도 쓰지 않음)
            if self._wait_since is None:
                self._wait_since = time.time()
                if self._probe:
                    self._probe.poke()
            if time.time() - self._wait_since > MAX_WAIT_NET:
                self._retry_timer.stop()
                self._retry_n = 0
                detail = "네트워크가 %d분 넘게 응답하지 않아 자동 재연결을 멈췄습니다." % (MAX_WAIT_NET // 60)
                self._show_page("연결할 수 없어요", detail, retry=True)
                self._set_state(STATE_DISCONNECTED, detail)
                return
            self._update_retry_page()
            return
        self._retry_timer.stop()
        self.connect_session()

    def _update_retry_page(self):
        q = self.quality
        sig = "현재 신호: %s" % (q.get("label") or "-")
        if q.get("rtt") is not None:
            sig += " (%dms)" % round(q["rtt"])
        if self._countdown > 0:
            msg = "%d초 후 자동으로 다시 연결합니다  (%d/%d)" % (self._countdown, self._retry_n, MAX_RETRIES)
        else:
            msg = "네트워크 응답을 기다리는 중… 응답이 오면 바로 연결합니다  (%d/%d)" % (self._retry_n, MAX_RETRIES)
        low = "\n신호가 약하면 저속 모드(16비트 색, 화면 효과 끔)로 연결합니다." if 0 <= q["bars"] <= 1 else ""
        title = "네트워크가 불안정해 연결이 끊겼어요" if self._ever_connected else "원격 PC가 응답하지 않아요"
        self._show_page(title, "%s\n%s%s" % (msg, sig, low), retry=True, cancel=True)
        self._retry.setText("지금 다시 연결")

    def close_tab(self, timeout=10.0):
        """탭 닫기 전 호출 — 연결 해제가 끝날 때까지 기다린 뒤 ActiveX 해제.

        Disconnect()는 비동기라 바로 clear()하면 컨트롤이 멈출 수 있다 (실기 테스트에서 확인).
        """
        import time
        from PySide6.QtWidgets import QApplication

        self._poll.stop()
        self._retry_timer.stop()
        self.stop_probe()
        try:
            if self._connected_value() != 0:
                self._ax.dynamicCall("Disconnect()")
                end = time.time() + timeout
                while self._connected_value() != 0 and time.time() < end:
                    QApplication.processEvents()
                    time.sleep(0.05)
        finally:
            self._ax.clear()

    # --- 내부 ---
    def _connected_value(self):
        v = self._ax.dynamicCall("Connected")
        return int(v) if v is not None else 0

    def _check_state(self):
        new = _CONNECTED_MAP.get(self._connected_value(), STATE_DISCONNECTED)
        if new == self.state:
            return
        detail = ""
        if new == STATE_DISCONNECTED:
            self._poll.stop()
            ext = int(self._ax.dynamicCall("ExtendedDisconnectReason") or 0)
            self._last_ext = ext
            if self._should_retry(self.state, ext) and self._schedule_retry():
                return
            code = f"  (코드 {ext})" if ext else ""
            if self.state == STATE_CONNECTING:
                title = "연결하지 못했어요"
                detail = "주소·포트·계정과 원격 PC의 원격 데스크톱 허용 여부를 확인해 주세요." + code
            else:
                title = "연결이 끊겼어요"
                detail = "원격 PC에서 로그아웃했거나 네트워크가 끊겼습니다." + code
            self._show_page(title, detail, retry=True)
        elif new == STATE_CONNECTED:
            self._retry_n = 0
            self._ever_connected = True
            if self.low_bandwidth:
                detail = "저속 모드"
            self._ax.setFocus()  # 접속 직후 Ctrl+C/V가 원격으로 바로 전달되도록
            if self._fit_mode():
                self._resize_timer.start()  # 연결 중에 창 크기가 바뀌었으면 반영
        self._set_state(new, detail)

    def _show_page(self, title, msg, retry=False, cancel=False):
        self._title.setText(title)
        self._msg.setText(msg)
        self._retry.setText("다시 연결")
        self._retry.setVisible(retry)
        self._cancel.setVisible(cancel)
        self._stack.setCurrentWidget(self._page)

    def quality_text(self):
        return describe(self.quality)

    def _set_state(self, state, detail):
        self.state = state
        self.state_changed.emit(state, detail)


if __name__ == "__main__":
    # 수동 확인용:
    #   등록된 세션:  .venv\Scripts\python.exe -m ui.rdp_tab "세션이름"
    #   직접 입력:    .venv\Scripts\python.exe -m ui.rdp_tab 192.0.2.119 operator
    #                 (비밀번호는 실행 후 입력, 화면에 안 보임 / 엔터만 치면 원격 로그인 화면에서 입력)
    import getpass
    import sys
    from PySide6.QtWidgets import QApplication
    from core.dpapi_store import SessionStore

    store = SessionStore()
    if len(sys.argv) == 3:
        session = {"name": sys.argv[1], "host": sys.argv[1], "rdp_user": sys.argv[2],
                   "rdp_password": getpass.getpass("RDP 비밀번호: ")}
    elif len(sys.argv) == 2 and store.get(sys.argv[1]):
        session = store.get(sys.argv[1])
    else:
        print("사용법: python -m ui.rdp_tab <세션이름>  또는  <주소> <계정>   등록된 세션:", store.names())
        sys.exit(1)
    app = QApplication(sys.argv)
    tab = RdpTab(session)
    session = None
    tab.resize(1280, 800)
    tab.setWindowTitle(tab.session["name"])
    tab.state_changed.connect(lambda s, d: print("상태:", s, d))
    tab.show()
    QTimer.singleShot(100, tab.connect_session)
    app.aboutToQuit.connect(tab.close_tab)
    sys.exit(app.exec())
