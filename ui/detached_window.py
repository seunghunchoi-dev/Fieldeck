"""탭에서 떼어 낸 원격 화면을 담는 별도 창.

- 메인 창의 탭을 바깥으로 끌어내거나, 탭 오른쪽 클릭 '새 창으로 분리'로 만든다.
- 접속은 끊기지 않는다 (RdpTab 위젯을 그대로 옮김, 실기 확인).
- '탭으로 합치기' 버튼 또는 제목줄을 잡고 메인 창의 탭 줄 위에 놓으면 메인 창에 되돌리고, 창을 닫으면 그 세션 연결을 끊는다 (탭 닫기와 같음).
"""
import ctypes
import ctypes.wintypes

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QKeySequence
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget

from ui.fullscreen_bar import FullscreenBar
from core import appinfo
from ui.icons import icon
from ui.signal_bars import SignalBars
from ui.theme import C, STATUS_COLOR, shortcut

# 창 끌기(제목줄) 감지용 Windows 메시지
WM_MOVING = 0x0216
WM_EXITSIZEMOVE = 0x0232


class DetachedWindow(QMainWindow):
    dock_requested = Signal(object)    # RdpTab
    close_requested = Signal(object)   # RdpTab
    drag_moved = Signal(object, QPoint)      # (RdpTab, 커서 화면 좌표) — 제목줄로 창을 끄는 중
    drag_released = Signal(object, QPoint)   # 끌기를 놓음

    def __init__(self, tab):
        super().__init__()
        self.tab = tab
        self._docking = False
        self._full = None
        self._dragging = False
        self.setMinimumSize(640, 420)

        root = QWidget()
        root.setObjectName("root")
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self.topbar = QFrame()
        self.topbar.setObjectName("topbar")
        self.topbar.setFixedHeight(48)
        t = QHBoxLayout(self.topbar)
        t.setContentsMargins(14, 0, 10, 0)
        t.setSpacing(8)
        self.title = QLabel()
        self.title.setObjectName("topTitle")
        self.chip_state = QLabel()
        self.chip_state.setObjectName("chip")
        self.signal = SignalBars()
        self.chip_low = QLabel("저속 모드")
        self.chip_low.setObjectName("chipWarn")
        self.chip_low.setToolTip("신호가 약해 16비트 색·화면 효과 끔으로 접속했습니다.")
        self.chip_res = QLabel()
        self.chip_res.setObjectName("chip")
        self.chip_res.setToolTip("원격 해상도 · 현재 표시 배율")
        self.btn_dock = self._btn("탭으로 합치기", "메인 창의 탭으로 되돌리기 (접속 유지)\n"
                                  "또는 이 창 제목줄을 잡고 메인 창의 탭 줄 위에 놓기",
                                  lambda: self.dock_requested.emit(self.tab), "dock")
        self.btn_view = self._btn("", "원본 크기: 스크롤로 1:1 보기\n창에 맞춰: 전체를 줄여서 보기", self.toggle_view)
        self.btn_full = self._btn("전체 화면", "모니터 전체로 보기 (F11)", self.toggle_fullscreen, "expand")
        self.btn_reconnect = self._btn("다시 연결", "", lambda: self.tab.connect_session(), "refresh")
        self.btn_disconnect = self._btn("연결 끊기", "", lambda: self.tab.disconnect_session(), "power")
        center = Qt.AlignmentFlag.AlignVCenter
        t.addWidget(self.title)
        t.addWidget(self.chip_state, alignment=center)
        t.addWidget(self.signal, alignment=center)
        t.addWidget(self.chip_low, alignment=center)
        t.addStretch(1)
        t.addWidget(self.chip_res, alignment=center)
        for b in (self.btn_view, self.btn_full, self.btn_dock, self.btn_reconnect, self.btn_disconnect):
            t.addWidget(b)
        v.addWidget(self.topbar)
        v.addWidget(tab, 1)
        tab.show()
        self.setCentralWidget(root)

        self.fsbar = FullscreenBar(self)
        self.fsbar.exit_requested.connect(self.toggle_fullscreen)
        self.fsbar.view_requested.connect(self.toggle_view)
        self.fsbar.minimize_requested.connect(self.showMinimized)
        shortcut(QKeySequence(Qt.Key.Key_F11), self, self.toggle_fullscreen)
        self.refresh()

    def _btn(self, text, tip, slot, ico=None):
        b = QPushButton(text)
        b.setObjectName("ghost")
        if ico:
            b.setIcon(icon(ico))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        if tip:
            b.setToolTip(tip)
        b.clicked.connect(slot)
        return b

    # ---------------------------------------------------------------- 동작
    def toggle_view(self):
        if self.tab.can_toggle_view():
            self.tab.set_view("actual" if self.tab.view == "fit" else "fit")

    def toggle_fullscreen(self):
        if self._full is None:
            self._full = self.isMaximized()
            self.topbar.hide()
            self.showFullScreen()
            self.refresh()
            self.fsbar.start()
        else:
            maxed, self._full = self._full, None
            self.fsbar.stop()
            self.topbar.show()
            self.showMaximized() if maxed else self.showNormal()
        QTimer.singleShot(300, self.tab.setFocus)

    def release_tab(self):
        """탭 위젯을 창에서 떼어 돌려준다 (합치기용). 이후 창은 닫아도 접속에 영향 없음."""
        self._docking = True
        self.fsbar.stop()
        self.tab.setParent(None)
        return self.tab

    def refresh(self):
        tab = self.tab
        name = tab.session.get("name", "")
        self.setWindowTitle("%s — %s" % (name, appinfo.APP_NAME))
        self.title.setText(name)
        color = STATUS_COLOR.get(tab.state, C["idle"])
        self.chip_state.setText("●  " + tab.state)
        self.chip_state.setStyleSheet("color:%s;" % color)
        live = tab.is_active()
        self.signal.set_quality(tab.quality)
        self.signal.setToolTip("네트워크 신호\n" + tab.quality_text())
        self.chip_low.setVisible(live and tab.low_bandwidth)
        self.btn_reconnect.setVisible(not live)
        self.btn_disconnect.setVisible(live)
        self.chip_res.setVisible(live)
        can_view = live and tab.can_toggle_view()
        self.btn_view.setVisible(can_view)
        view = ""
        if live:
            w, h = tab.remote_size()
            pct = "  ·  %d%%" % round(tab.scale * 100) if tab.can_toggle_view() else ""
            self.chip_res.setText("%d×%d%s" % (w, h, pct))
            self.btn_view.setText("원본 크기로 보기" if tab.view == "fit" else "창에 맞춰 보기")
            self.btn_view.setIcon(icon("actual" if tab.view == "fit" else "fit"))
            if can_view:
                view = "원본 크기" if tab.view == "fit" else "화면에 맞춤"
        if self._full is not None:
            dot = '<span style="color:%s">●</span>' % color
            self.fsbar.set_info("%s&nbsp;&nbsp;%s&nbsp;&nbsp;<span style='color:%s'>%s</span>"
                                % (dot, name.replace("<", "&lt;"), C["muted"], tab.state), 1, view)
            self.fsbar.set_quality(tab.quality)

    def nativeEvent(self, event_type, message):
        """제목줄로 창을 끄는 동안/놓을 때를 메인 창에 알린다 (끌어서 탭으로 합치기)."""
        if bytes(event_type) == b"windows_generic_MSG" and self._full is None:
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_MOVING:
                self._dragging = True
                self.drag_moved.emit(self.tab, QCursor.pos())
            elif msg.message == WM_EXITSIZEMOVE and self._dragging:
                self._dragging = False
                pos = QCursor.pos()
                QTimer.singleShot(0, lambda: self.drag_released.emit(self.tab, pos))
        return False, 0

    def closeEvent(self, e):
        self.fsbar.stop()
        if not self._docking:
            self.close_requested.emit(self.tab)   # 창 닫기 = 그 세션 연결 끊기
        super().closeEvent(e)
