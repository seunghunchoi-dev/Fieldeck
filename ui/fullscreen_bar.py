"""전체 화면용 상단 연결 표시줄 (mstsc의 고정 막대와 비슷한 역할).

원격 화면(ActiveX)은 Windows 네이티브 창이라 같은 창 안의 Qt 위젯을 덮어버린다.
그래서 막대는 별도의 '항상 위' 최상위 창으로 띄운다.
또 원격 화면 위에서는 마우스 이벤트가 Qt로 오지 않으므로, 커서 위치를 타이머로 확인해
화면 맨 위에 커서를 대면 막대가 내려오고, 벗어나면 잠시 뒤 숨는다.
"""
import time

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

from ui.icons import icon
from ui.signal_bars import SignalBars

HIDE_DELAY = 1.2   # 커서가 막대를 벗어난 뒤 숨기까지(초)


class FullscreenBar(QFrame):
    exit_requested = Signal()
    prev_requested = Signal()
    next_requested = Signal()
    view_requested = Signal()
    minimize_requested = Signal()

    def __init__(self, parent):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName("fsBar")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._host = parent
        self._pinned = False
        self._left_at = None

        h = QHBoxLayout(self)
        h.setContentsMargins(10, 6, 10, 6)
        h.setSpacing(4)
        self.btn_pin = self._btn("", "막대 고정 (자동으로 숨기지 않기)", self._toggle_pin, "pin")
        self.btn_pin.setCheckable(True)
        self.btn_prev = self._btn("", "이전 탭", self.prev_requested.emit, "left")
        self.title = QLabel()
        self.title.setObjectName("fsTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setMinimumWidth(220)
        self.signal = SignalBars()
        self.btn_next = self._btn("", "다음 탭", self.next_requested.emit, "right")
        self.btn_view = self._btn("", "원본 크기 ↔ 화면에 맞춤", self.view_requested.emit)
        self.btn_min = self._btn("", "최소화", self.minimize_requested.emit, "minus")
        self.btn_exit = self._btn("전체 화면 끝내기", "전체 화면 끝내기 (F11)", self.exit_requested.emit)
        self.btn_exit.setIcon(icon("shrink", "#FFFFFF", 16))
        self.btn_exit.setObjectName("fsExit")
        for w in (self.btn_pin, self.btn_prev, self.title, self.signal, self.btn_next, self.btn_view,
                  self.btn_min, self.btn_exit):
            h.addWidget(w)

        self._timer = QTimer(self)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._poll)

    def _btn(self, text, tip, slot, ico=None):
        b = QPushButton(text)
        if ico:
            b.setIcon(icon(ico))
        b.setObjectName("fsBtn")
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # 원격 화면의 키보드 포커스를 뺏지 않음
        b.clicked.connect(slot)
        return b

    # ---------------------------------------------------------------- 표시
    def set_info(self, title, tab_count, view_text):
        self.title.setText(title)
        many = tab_count > 1
        self.btn_prev.setVisible(many)
        self.btn_next.setVisible(many)
        self.btn_view.setVisible(bool(view_text))
        self.btn_view.setText(view_text)
        if view_text:
            self.btn_view.setIcon(icon("actual" if view_text == "원본 크기" else "fit"))
        self.adjustSize()
        if self.isVisible():
            self._place()

    def set_quality(self, q):
        self.signal.set_quality(q)

    def start(self):
        """전체 화면 진입: 잠깐 보여주고 자동 숨김 감시 시작."""
        self._reveal()
        self._left_at = time.time() + 1.5   # 처음엔 1.5초 더 보여줌
        self._timer.start()

    def stop(self):
        self._timer.stop()
        self.hide()

    def _place(self):
        g = self._host.screen().geometry()
        self.move(QPoint(g.x() + (g.width() - self.width()) // 2, g.y()))

    def _reveal(self):
        self.adjustSize()
        self._place()
        self.show()
        self.raise_()

    def _toggle_pin(self):
        self._pinned = self.btn_pin.isChecked()

    def _poll(self):
        if not self._host.isActiveWindow() and not self.isActiveWindow():
            # 다른 프로그램으로 전환(Alt+Tab)하면 막대도 숨김
            if self.isVisible():
                self.hide()
            return
        pos = QCursor.pos()
        g = self._host.screen().geometry()
        if not self.isVisible():
            # 화면 맨 위 가운데 쪽에 커서를 대면 내려옴
            if pos.y() <= g.y() + 2 and g.x() <= pos.x() < g.x() + g.width():
                self._reveal()
                self._left_at = None
            return
        if self._pinned or self.frameGeometry().adjusted(0, 0, 0, 12).contains(pos):
            self._left_at = None
            return
        if self._left_at is None:
            self._left_at = time.time()
        elif time.time() - self._left_at > HIDE_DELAY:
            self.hide()
            self._left_at = None
