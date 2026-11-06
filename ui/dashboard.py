"""현장 대시보드 탭 — 저장된 모든 장비의 상태를 한눈에 보고 바로 접속.

구성: 요약 타일(누르면 그 상태만 보기) / 그룹별 장비 카드 / 오른쪽 '최근 변화' 기록
- 상태 확인은 core.site_monitor (ping + RDP 포트, 원격 설정 변경 없음)
- 카드 더블클릭 또는 '접속' → 탭으로 접속, 오른쪽 클릭 → 세션 메뉴(편집·즐겨찾기 등)
"""
import time

from PySide6.QtCore import QPoint, QRect, QSettings, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QLayout, QLineEdit,
                             QListWidget, QListWidgetItem, QPushButton, QScrollArea, QSizePolicy,
                             QVBoxLayout, QWidget)

from core import appinfo
from core.conn_log import ARROW, KIND_DEVICE, duration_text
from core.site_import import short_address
from core.site_monitor import (SEVERITY, ST_CHECKING, ST_OFFLINE, ST_OK, ST_RDP_CLOSED, ST_SLOW,
                               SiteMonitor)
from ui.icons import icon
from ui.signal_bars import bars_pixmap
from ui.theme import C, group_color, timer

STATE_COLOR = {ST_OK: C["ok"], ST_SLOW: C["warn"], ST_RDP_CLOSED: "#FB923C", ST_OFFLINE: C["err"],
               ST_CHECKING: C["idle"]}
STATE_HINT = {
    ST_OK: "ping 응답 · 원격 데스크톱 포트 열림",
    ST_SLOW: "응답은 있지만 느리거나 끊김이 있음",
    ST_RDP_CLOSED: "PC는 켜져 있지만 원격 데스크톱 포트가 닫힘 (원격 데스크톱 꺼짐·방화벽)",
    ST_OFFLINE: "ping·원격 데스크톱 모두 응답 없음 (전원·네트워크 확인)",
    ST_CHECKING: "확인 중",
}
INTERVALS = [("10초마다", 10), ("30초마다", 30), ("1분마다", 60), ("5분마다", 300)]
SORTS = [("응답 먼저", "ok"), ("문제 먼저", "problem"), ("번호순", "name")]
VIEWS = [("기본 카드", "card"), ("간단히", "compact"), ("작은 칸", "mini")]
# '응답 먼저' 순서: 접속 가능한 장비가 위 (대부분 오프라인인 현장에서 쓸 수 있는 장비를 바로 찾게)
OK_FIRST = {ST_OK: 0, ST_SLOW: 1, ST_RDP_CLOSED: 2, ST_CHECKING: 3, ST_OFFLINE: 4}


def ago(ts):
    if not ts:
        return "-"
    d = int(time.time() - ts)
    if d < 60:
        return "%d초" % max(d, 1)
    if d < 3600:
        return "%d분" % (d // 60)
    if d < 86400:
        return "%d시간 %d분" % (d // 3600, d % 3600 // 60)
    return "%d일" % (d // 86400)


# --------------------------------------------------------------------------- 흐름 배치
class FlowLayout(QLayout):
    """카드를 가로로 채우다 넘치면 다음 줄로."""

    def __init__(self, parent=None, spacing=12):
        super().__init__(parent)
        self._items = []
        self._sp = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._do(QRect(0, 0, w, 0), True)

    def setGeometry(self, r):
        super().setGeometry(r)
        self._do(r, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self._items:
            if not it.isEmpty():
                s = s.expandedTo(it.minimumSize())
        return s

    def remove(self, widget):
        """위젯을 배치에서 뺀다 (위젯 자체는 지우지 않음)."""
        self._items = [it for it in self._items if it.widget() is not widget]
        self.invalidate()

    def reorder(self, widgets):
        """위젯 순서만 바꾼다 (부모를 바꾸지 않아 빠름). 목록에 없는 위젯은 뒤로."""
        rank = {id(w): i for i, w in enumerate(widgets)}
        self._items.sort(key=lambda it: rank.get(id(it.widget()), len(rank)))
        self.invalidate()

    def _do(self, r, test):
        """카드를 줄마다 채운다. 카드는 모두 같은 기본 폭 → 한 줄에 들어갈 칸 수를 정하고
        남는 폭을 칸마다 나눠 화면 폭을 고르게 채운다 (오른쪽 빈 공간 없음, 모든 그룹 칸 폭 동일)."""
        x, y, line_h = r.x(), r.y(), 0
        base = next((it.sizeHint().width() for it in self._items if not it.isEmpty()), 0)
        if base:
            cols = max(1, (r.width() + self._sp) // (base + self._sp))
            col_w = max(base, (r.width() - self._sp * (cols - 1)) // cols)
        for it in self._items:
            if it.isEmpty():                # 숨긴 카드는 자리 차지 안 함
                continue
            sz = QSize(col_w, it.sizeHint().height())
            if x + sz.width() > r.right() + 1 and line_h > 0:
                x, y, line_h = r.x(), y + line_h + self._sp, 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), sz))
            x += sz.width() + self._sp
            line_h = max(line_h, sz.height())
        return y + line_h - r.y()


# --------------------------------------------------------------------------- 카드 부품
class HistoryStrip(QWidget):
    """최근 상태 기록 띠 (왼쪽=오래된 것, 오른쪽=최근)."""

    def __init__(self, slots=30):
        super().__init__()
        self.slots = slots
        self.states = []
        self.setFixedHeight(10)

    def set_states(self, states):
        self.states = list(states)[-self.slots:]
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        gap = 2
        w = (self.width() - gap * (self.slots - 1)) / self.slots
        pad = self.slots - len(self.states)
        for i in range(self.slots):
            st = self.states[i - pad] if i >= pad else None
            col = QColor(STATE_COLOR.get(st, C["border"])) if st else QColor(C["border"])
            if st is None:
                col.setAlpha(110)
            p.setBrush(col)
            p.drawRoundedRect(int(i * (w + gap)), 0, max(int(w), 2), self.height(), 2, 2)
        p.end()


class DeviceCard(QFrame):
    """장비 카드. 보기 3가지:
    card(기본): 번호·상/하류·주소·IP·상태·기록 띠 / compact(간단히): 두 줄 (번호·상태 + 주소·접속) /
    mini(작은 칸): 한 줄 (상태 점·번호·ms) — 수백 개소를 한 화면에. 자세한 내용은 툴팁, 더블클릭 = 접속."""
    connect_clicked = Signal(str)
    menu_clicked = Signal(QPoint, str)

    SIZES = {"card": (276, 172), "compact": (276, 62), "mini": (138, 34)}   # (기본 폭, 높이) — 폭은 화면에 맞춰 늘어남

    def __init__(self, session, view="card"):
        super().__init__()
        if isinstance(view, bool):          # 예전 호출 방식 (compact=True/False)
            view = "compact" if view else "card"
        self.name = session["name"]
        self.group = session.get("group", "")   # 지금 들어 있는 그룹 묶음
        self.view = view
        self.compact = view == "compact"
        self.mini = view == "mini"
        compact = self.compact
        self.W, self.H = self.SIZES[view]
        self.setObjectName("devCard")
        self.setFixedHeight(self.H)
        self.setMinimumWidth(self.W)          # 폭은 대시보드 너비에 맞춰 늘어남 (FlowLayout)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._state = None
        self._open_state = None
        v = QVBoxLayout(self)
        if self.mini:
            v.setContentsMargins(10, 0, 8, 0)
        elif compact:
            v.setContentsMargins(12, 7, 10, 7)
        else:
            v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(3 if compact else 4)

        # 1줄: 상태 점 · 개소 번호 · 상/하류 · (간단히: 상태) · 신호
        top = QHBoxLayout()
        top.setSpacing(7)
        self.dot = QLabel("●")
        self.title = QLabel()
        self.title.setObjectName("cardTitle")
        self.flow_chip = QLabel()
        self.flow_chip.setObjectName("flowChip")
        self.bars = QLabel()
        self.ms = QLabel()
        self.ms.setObjectName("cardSub")
        self.status = QLabel()
        self.status.setObjectName("devStatus")
        top.addWidget(self.dot)
        top.addWidget(self.title)
        if not self.mini:
            top.addWidget(self.flow_chip)
        top.addStretch(1)
        if compact:
            top.addWidget(self.status)      # 간단히: 상태는 오른쪽 위에 짧게
        if not self.mini:
            top.addWidget(self.bars)
        top.addWidget(self.ms)
        v.addLayout(top)

        self.sub = QLabel()                 # 설치 주소 (주소가 없으면 IP · 계정)
        self.sub.setObjectName("cardAddr")
        self.sub2 = QLabel()                # IP · 계정 (기본 카드만)
        self.sub2.setObjectName("cardSub")
        self.badge = QLabel()
        self.badge.setObjectName("devBadge")
        self.btn = QPushButton("접속")
        self.btn.setObjectName("devConnect")
        self.btn.setIcon(icon("monitor", "#FFFFFF", 14))
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn.clicked.connect(lambda: self.connect_clicked.emit(self.name))
        self.strip = HistoryStrip()
        if self.mini:                       # 한 줄: 나머지 부품은 만들어만 두고 숨김 (갱신 코드 공용)
            for w in (self.flow_chip, self.bars, self.status, self.sub, self.sub2, self.badge, self.btn, self.strip):
                w.setParent(self)
                w.hide()
        elif compact:
            row = QHBoxLayout()
            row.setSpacing(6)
            row.addWidget(self.sub, 1)
            row.addWidget(self.badge)
            row.addWidget(self.btn)
            v.addLayout(row)
            self.sub2.hide()
            self.strip.hide()
        else:
            v.addWidget(self.sub)
            v.addWidget(self.sub2)
            v.addWidget(self.status)
            v.addWidget(self.strip)
            v.addStretch(1)
            bottom = QHBoxLayout()
            bottom.setSpacing(6)
            bottom.addWidget(self.badge)
            bottom.addStretch(1)
            bottom.addWidget(self.btn)
            v.addLayout(bottom)
        self.set_session(session)

    def set_session(self, s):
        self.session = s
        self._state = None              # 그룹 색 등이 바뀌었을 수 있으니 다음 갱신 때 스타일 다시 적용
        port = int(s.get("rdp_port") or 3389)
        host = s["host"] + ("" if port == 3389 else ":%d" % port)
        ip_user = "  ·  ".join([host] + ([s["rdp_user"]] if s.get("rdp_user") else []))
        addr = short_address(s.get("address", ""))
        if addr:
            self._sub_text = addr
            self._sub2_text = "  ·  ".join(p for p in (ip_user, s.get("note", "")) if p)
        else:                               # 개소 정보가 없는 일반 세션
            self._sub_text, self._sub2_text = ip_user, s.get("note", "")
        self.flow_chip.setText(s.get("flow", ""))
        self.flow_chip.setVisible(bool(s.get("flow")))
        tip = [s["name"]]
        if s.get("group"):
            tip.append("하천/그룹: %s" % s["group"])
        if s.get("address"):
            tip.append("주소: %s" % s["address"])
        tip.append("접속: %s" % ip_user)
        if s.get("note"):
            tip.append("메모: %s" % s["note"])
        if s.get("flow"):
            tip.insert(1, "상/하류: %s" % s["flow"])
        self._tip = "\n".join(tip)
        self.setToolTip(self._tip)
        self._elide()

    def _elide(self):
        """이름·주소가 길면 카드 폭에 맞춰 … 로 줄임 (카드 폭은 화면에 따라 바뀜)."""
        w = max(self.width(), self.W)
        star = (" ★" if self.mini else "  ★") if self.session.get("favorite") else ""
        reserve = 80 if self.mini else 200 if self.compact else 150
        self.title.setText(self.title.fontMetrics().elidedText(
            self.session["name"], Qt.TextElideMode.ElideRight, w - reserve) + star)
        sub_w = w - (120 if self.compact else 30)
        self.sub.setText(self.sub.fontMetrics().elidedText(self._sub_text, Qt.TextElideMode.ElideRight, sub_w))
        self.sub2.setText(self.sub2.fontMetrics().elidedText(self._sub2_text, Qt.TextElideMode.ElideRight, w - 30))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if e.oldSize().width() != e.size().width():
            self._elide()

    def sizeHint(self):
        return QSize(self.W, self.H)

    def update_device(self, d, open_state=None):
        st = d.state
        col = STATE_COLOR.get(st, C["idle"])
        if st != self._state:           # 스타일시트 적용은 비싸므로 상태가 바뀔 때만
            self._state = st
            self.dot.setStyleSheet("color:%s; font-size:12px; background:transparent;" % col)
            # RDP 닫힘(켜져 있는데 접속 불가 → 손볼 일)만 테두리로 강조.
            # 오프라인은 흐리게: 대부분 오프라인인 현장에서 화면이 온통 빨갛게 되어 접속 가능한 장비가 묻히지 않게.
            border = col if st == ST_RDP_CLOSED else C["border"]
            css = "QFrame#devCard { border: 1px solid %s; border-left: 4px solid %s; }" % (
                border, group_color(self.session.get("group", "")))
            if st == ST_OFFLINE:
                css += ("QLabel#cardTitle, QLabel#cardAddr { color: %s; }"
                        "QPushButton#devConnect { background: transparent; border: 1px solid %s; color: %s; }"
                        "QPushButton#devConnect:hover { background: %s; color: %s; }"
                        % (C["muted"], C["border"], C["muted"], C["surface_hi"], C["text"]))
            self.setStyleSheet(css)
            self.btn.setIcon(icon("monitor", C["muted"] if st == ST_OFFLINE else "#FFFFFF", 14))
            self.status.setStyleSheet("color:%s; background:transparent;" % col)
            self.status.setToolTip(STATE_HINT.get(st, ""))
        q = d.quality
        self.bars.setPixmap(bars_pixmap(q["bars"] if st != ST_CHECKING else -1, 14))
        self.ms.setText("%dms" % round(d.rtt) if d.rtt is not None else "")
        if st == ST_CHECKING:
            text = "확인 중…"
        elif self.compact:                  # 간단히: 상태 + 지속 시간만
            text = "정상" if st == ST_OK else "%s · %s째" % (st, ago(d.since))
        elif st == ST_OFFLINE:
            text = "오프라인 · %s째" % ago(d.since)
            if d.last_ok:                   # 응답한 적이 있을 때만 (없으면 모든 카드에 같은 말이 반복됨)
                text += "  (마지막 응답 %s)" % time.strftime("%H:%M", time.localtime(d.last_ok))
        elif st == ST_RDP_CLOSED:
            text = "원격 데스크톱 닫힘 · %s째" % ago(d.since)
        elif st == ST_SLOW:
            text = "느림 · 손실 %d%% · %s째" % (round(q["loss"] * 100), ago(d.since))
        else:
            text = "정상 · %s째" % ago(d.since)
        self.status.setText(text)
        if self.mini:                       # 작은 칸: 상태 문장은 툴팁으로
            self.setToolTip("%s\n상태: %s" % (self._tip, text))
        else:
            self.strip.set_states(d.history)
        self.set_open_state(open_state)

    def set_open_state(self, open_state):
        self._open_state = open_state
        if self.mini:                       # 작은 칸: 접속 중이면 ms 자리에 표시
            if open_state:
                self.ms.setText(open_state)
                self.ms.setStyleSheet("color:%s;" % C["accent_hi"])
            else:
                self.ms.setStyleSheet("")
            return
        if open_state:
            self.badge.setText("● " + open_state)
            self.badge.show()
            self.btn.setText("탭 보기")
        else:
            self.badge.hide()
            self.btn.setText("접속")

    def mouseDoubleClickEvent(self, e):
        self.connect_clicked.emit(self.name)

    def contextMenuEvent(self, e):
        self.menu_clicked.emit(e.globalPos(), self.name)


class KpiTile(QPushButton):
    def __init__(self, key, label, color):
        super().__init__()
        self.key = key
        self.setObjectName("kpi")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(74)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 10, 16, 10)
        v.setSpacing(0)
        self.num = QLabel("0")
        self.num.setObjectName("kpiNum")
        self.num.setStyleSheet("color:%s;" % color)
        lb = QLabel(label)
        lb.setObjectName("kpiLabel")
        for w in (self.num, lb):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            v.addWidget(w)

    def set_value(self, n):
        self.num.setText(str(n))


class _GroupHead(QWidget):
    clicked = Signal()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


class GroupSection(QWidget):
    """그룹 머리글(접기 표시·색 막대·이름·대수) + 카드 흐름 배치. 한 번 만들어 재사용.
    머리글을 누르면 접기/펼치기 (toggled 신호, 상태는 대시보드가 기억)."""
    toggled = Signal(str)

    def __init__(self, g):
        super().__init__()
        self.g = g
        self.collapsed = False
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        head = _GroupHead()
        head.setCursor(Qt.CursorShape.PointingHandCursor)
        head.setToolTip("눌러서 접기 / 펼치기")
        head.clicked.connect(lambda: self.toggled.emit(self.g))
        h = QHBoxLayout(head)
        h.setContentsMargins(0, 8, 0, 0)
        h.setSpacing(8)
        self.chev = QLabel("▾")             # 사이드바 그룹 머리글과 같은 표시
        self.chev.setObjectName("chev")
        self.chev.setFixedWidth(10)
        h.addWidget(self.chev)
        bar = QFrame()
        bar.setFixedSize(4, 16)
        bar.setStyleSheet("background:%s; border-radius:2px;" % group_color(g))
        name = QLabel(g or "그룹 없음")
        name.setObjectName("groupName")
        name.setStyleSheet("font-size:13px;")
        self.info = QLabel()
        self.info.setObjectName("groupCount")
        h.addWidget(bar)
        h.addWidget(name)
        h.addWidget(self.info)
        h.addStretch(1)
        v.addWidget(head)
        self.box = QWidget()
        self.flow = FlowLayout(self.box)
        v.addWidget(self.box)

    def set_collapsed(self, on):
        if on != self.collapsed:
            self.collapsed = on
            self.box.setVisible(not on)
            self.chev.setText("▸" if on else "▾")

    def set_counts(self, devs):
        counts = {}
        for d in devs:
            st = d.state if d else ST_CHECKING
            counts[st] = counts.get(st, 0) + 1
        parts = ["%d대" % len(devs)]
        for st in (ST_OK, ST_SLOW, ST_RDP_CLOSED, ST_OFFLINE):   # 접었을 때도 그룹 상태가 한눈에
            if counts.get(st):
                parts.append("<span style='color:%s'>%s %d</span>" % (STATE_COLOR[st], st, counts[st]))
        self.info.setText("  ·  ".join(parts))


# --------------------------------------------------------------------------- 대시보드
class DashboardTab(QWidget):
    connect_requested = Signal(str)
    menu_requested = Signal(QPoint, str)
    alert = Signal(str)                 # 장비가 오프라인이 됨 (작업 표시줄 깜빡임용)
    wide_requested = Signal()           # '넓게 보기' 버튼 (사이드바 숨김·최대화는 메인 창이 처리)
    _sig_update = Signal(object)
    _sig_change = Signal(object, str, str)

    def __init__(self, interval=30, log=None):
        super().__init__()
        self.setObjectName("dashboard")
        self.log = log                  # core.conn_log.ConnLog (없으면 파일 기록 안 함)
        self.sessions = {}
        self.cards = {}                 # 지금 화면에 놓인 카드 (이름 → 카드)
        self._pool = {}                 # 만들어 둔 모든 카드 (재사용)
        self._sections = {}             # 그룹 이름 → GroupSection (재사용)
        self._dirty = True              # 안 보이는 동안 rebuild가 미뤄짐
        self.open_states = {}
        self.filter = None
        self.query = ""
        self._sig_update.connect(self._on_update)
        self._sig_change.connect(self._on_change)
        self.monitor = SiteMonitor(self._sig_update.emit, self._sig_change.emit, interval)

        root = QHBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(16)
        main = QVBoxLayout()
        main.setSpacing(12)
        root.addLayout(main, 1)

        # 머리글 — 큰 제목은 위쪽 막대·탭 이름과 겹쳐서 뺌 (2026-11-03). 마지막 확인 시각만 표시
        head = QHBoxLayout()
        self.sub = QLabel("")
        self.sub.setObjectName("heroSub")
        self.sub.setStyleSheet("font-size:12px;")
        self.sub.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)   # 좁으면 잘림 (버튼과 겹치지 않게)
        self.sub.setMinimumWidth(0)
        head.addWidget(self.sub, 1, Qt.AlignmentFlag.AlignVCenter)
        self.search = QLineEdit()
        self.search.setPlaceholderText("장비 검색")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icon("search", size=16), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setMinimumWidth(130)    # 좁으면 줄어듦 (사이드바를 넓혀도 버튼이 겹치지 않게)
        self.search.setMaximumWidth(220)
        self.search.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.search.textChanged.connect(self._set_query)
        self.interval = QComboBox()
        for label, sec in INTERVALS:
            self.interval.addItem(label, sec)
        self.interval.setCurrentIndex(next((i for i, (_, s) in enumerate(INTERVALS) if s == interval), 1))
        self.interval.setToolTip("상태 확인 간격")
        self.interval.currentIndexChanged.connect(lambda _: self.monitor.set_interval(self.interval.currentData()))
        refresh = QPushButton("지금 확인")
        refresh.setIcon(icon("refresh"))
        refresh.setObjectName("ghost")
        refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh.setToolTip("모든 장비를 바로 다시 확인\n(오래 응답 없는 장비는 평소 5분마다만 확인)")
        refresh.clicked.connect(self.monitor.refresh_now)
        self.refresh_btn = refresh
        self._narrow = False            # 좁은 화면: 머리글 버튼은 아이콘만 (resizeEvent)
        # 정렬·간단히 보기 (설정은 레지스트리에 기억)
        self.cfg = QSettings(appinfo.APP_NAME, appinfo.APP_NAME)
        self.sort_mode = self.cfg.value("dash/sort", "ok")
        old = "compact" if self.cfg.value("dash/compact", False, type=bool) else "card"   # 예전 '간단히' 설정
        self.view = self.cfg.value("dash/view", old)
        if self.view not in DeviceCard.SIZES:
            self.view = "card"
        self.collapsed = set(self.cfg.value("dash/collapsed", [], type=list) or [])   # 접은 그룹
        self.sort_box = QComboBox()
        for label, key in SORTS:
            self.sort_box.addItem(label, key)
        self.sort_box.setCurrentIndex(max(0, self.sort_box.findData(self.sort_mode)))
        self.sort_box.setToolTip("카드 순서\n응답 먼저: 접속 가능한 장비가 위로\n문제 먼저: 끊긴 장비가 위로")
        self.sort_box.currentIndexChanged.connect(self._set_sort)
        self.view_box = QComboBox()
        for label, key in VIEWS:
            self.view_box.addItem(label, key)
        self.view_box.setCurrentIndex(max(0, self.view_box.findData(self.view)))
        self.view_box.setToolTip("카드 크기\n기본 카드: 주소·IP·기록 띠까지\n간단히: 두 줄\n"
                                 "작은 칸: 번호만 한 줄 — 수백 개소를 한 화면에 (자세한 내용은 마우스를 올리면)")
        self.view_box.currentIndexChanged.connect(lambda _: self._set_view(self.view_box.currentData()))
        self.fold_btn = QPushButton()
        self.fold_btn.setObjectName("ghost")
        self.fold_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fold_btn.setToolTip("모든 그룹 접기 / 펼치기\n(그룹 이름을 누르면 하나씩 접힘)")
        self.fold_btn.clicked.connect(self._toggle_fold_all)
        self.wide_btn = QPushButton("넓게 보기")
        self.wide_btn.setObjectName("ghost")
        self.wide_btn.setIcon(icon("expand"))
        self.wide_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.wide_btn.setToolTip("왼쪽 목록·최근 변화를 숨기고 창을 최대화\n(대시보드 탭을 두 번 눌러도 됨)")
        self.wide_btn.clicked.connect(self.wide_requested.emit)
        self._wide = self._folded = False
        for b in (self.fold_btn, refresh, self.wide_btn):
            b.setMinimumWidth(36)       # 좁아지면 글자를 빼고 아이콘만 (_header_texts) — 최소 폭이 글자에 묶이지 않게
        for w in (self.search, self.sort_box, self.view_box, self.fold_btn, self.interval, refresh, self.wide_btn):
            head.addWidget(w, alignment=Qt.AlignmentFlag.AlignVCenter)
        main.addLayout(head)

        # 요약 타일
        kpis = QHBoxLayout()
        kpis.setSpacing(10)
        self.tiles = {}
        for key, label, col in ((None, "전체", C["text"]), (ST_OK, "정상", C["ok"]), (ST_SLOW, "느림", C["warn"]),
                                (ST_RDP_CLOSED, "RDP 닫힘", STATE_COLOR[ST_RDP_CLOSED]),
                                (ST_OFFLINE, "오프라인", C["err"]), ("open", "접속 중", C["accent_hi"])):
            tile = KpiTile(key, label, col)
            tile.setToolTip("눌러서 이 상태만 보기" if key else "모두 보기")
            tile.clicked.connect(lambda _, k=key: self._set_filter(k))
            self.tiles[key] = tile
            kpis.addWidget(tile)
        self.tiles[None].setChecked(True)
        main.addLayout(kpis)

        # 카드 영역
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.body = QWidget()
        self.body.setObjectName("dashBody")
        self.body_lay = QVBoxLayout(self.body)
        self.body_lay.setContentsMargins(0, 0, 6, 0)
        self.body_lay.setSpacing(10)
        self._empty = QLabel()          # '등록된 세션이 없습니다' 등 (그룹 묶음은 이 앞에 들어감)
        self._empty.setObjectName("heroSub")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body_lay.addWidget(self._empty)
        self.body_lay.addStretch(1)
        self.scroll.setWidget(self.body)
        main.addWidget(self.scroll, 1)

        # 최근 변화
        side = QFrame()
        self.event_panel = side
        side.setObjectName("eventPanel")
        side.setFixedWidth(260)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(14, 14, 14, 14)
        sv.setSpacing(8)
        et = QLabel("최근 변화")
        et.setObjectName("section")
        sv.addWidget(et)
        self.events = QListWidget()
        self.events.setObjectName("events")
        self.events.setWordWrap(True)
        sv.addWidget(self.events, 1)
        self.events_empty = QLabel("아직 상태 변화가 없습니다.\n장비가 끊기거나 다시 살아나면\n여기에 시간과 함께 기록됩니다.\n"
                                   "(로그 파일로도 저장됩니다)")
        self.events_empty.setObjectName("heroSub")
        self.events_empty.setStyleSheet("font-size:12px;")
        self.events_empty.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        sv.addWidget(self.events_empty, 1)   # 비어 있을 때는 목록 대신 제목 바로 아래에 안내
        self.events.hide()
        root.addWidget(side)

        self._rebuild_timer = timer(self, 600, self.rebuild, single=True)
        self._kpi_timer = timer(self, 300, self._update_kpis, single=True)
        self._query_timer = timer(self, 200, self.rebuild, single=True)
        self._tick = timer(self, 15000, self._refresh_texts)   # '3분째' 갱신
        self._tick.start()
        self._last_check = None
        self.load_history()
        self.monitor.start()

    # ---------------------------------------------------------------- 외부에서 호출
    def set_sessions(self, sessions):
        self.sessions = {s["name"]: dict(s) for s in sessions}
        self.monitor.set_targets(sessions)
        self.rebuild()

    def set_open_state(self, name, state):
        """탭 상태 반영 (None = 탭 닫힘)."""
        if state:
            self.open_states[name] = state
        else:
            self.open_states.pop(name, None)
        card = self.cards.get(name)
        if card:
            card.set_open_state(state)
        self._kpi_timer.start()
        if self.filter == "open":
            self._rebuild_timer.start()

    def stop(self):
        self._tick.stop()
        self.monitor.stop()

    # ---------------------------------------------------------------- 표시
    def _set_query(self, text):
        self.query = text.strip().lower()
        self._query_timer.start()       # 타자 치는 동안은 기다렸다가 한 번만

    def _set_filter(self, key):
        self.filter = key
        for k, t in self.tiles.items():
            t.setChecked(k == key)
        self.rebuild()

    def _rank(self, d):
        """현재 정렬 방식에서 장비의 순위 (작을수록 위). 번호순이면 모두 같음."""
        st = d.state if d else ST_CHECKING
        if self.sort_mode == "ok":
            return OK_FIRST.get(st, 9)
        if self.sort_mode == "problem":
            return SEVERITY.get(st, 9)
        return 0

    def _set_sort(self):
        self.sort_mode = self.sort_box.currentData()
        self.cfg.setValue("dash/sort", self.sort_mode)
        self.rebuild()

    def _set_compact(self, on):
        self._set_view("compact" if on else "card")

    def _set_view(self, view):
        """카드 모양이 달라서 카드를 새로 만든다."""
        if view == self.view and all(c.view == view for c in self._pool.values()):
            return
        self.view = view
        self.cfg.setValue("dash/view", view)
        i = self.view_box.findData(view)
        if self.view_box.currentIndex() != i:
            self.view_box.blockSignals(True)
            self.view_box.setCurrentIndex(i)
            self.view_box.blockSignals(False)
        for card in self._pool.values():
            self._section(card.group).flow.remove(card)
            card.deleteLater()
        self._pool = {}
        self.rebuild()

    # ---------------------------------------------------------------- 그룹 접기 · 넓게 보기
    def _save_collapsed(self):
        self.cfg.setValue("dash/collapsed", sorted(self.collapsed))

    def _toggle_group(self, g):
        if self.query:                  # 검색 중에는 모두 펼쳐 보여줌 (접기 상태는 그대로 둠)
            return
        self.collapsed.symmetric_difference_update({g})
        self._save_collapsed()
        sec = self._sections.get(g)
        if sec:
            sec.set_collapsed(g in self.collapsed)
        self._update_fold_btn()

    def _toggle_fold_all(self):
        shown = [g for g, sec in self._sections.items() if not sec.isHidden()]
        if self.query or any(g not in self.collapsed for g in shown):
            self.collapsed.update(self._sections)          # 하나라도 펼쳐져 있으면 모두 접기
        else:
            self.collapsed.clear()
        self._save_collapsed()
        self.rebuild()

    def _update_fold_btn(self):
        shown = [g for g, sec in self._sections.items() if not sec.isHidden()]
        self._folded = bool(self.query == "" and shown and all(g in self.collapsed for g in shown))
        self.fold_btn.setIcon(icon("expand_all" if self._folded else "collapse"))
        self._header_texts()

    def set_wide(self, on):
        """넓게 보기: '최근 변화'를 숨겨 카드 영역을 넓힘 (사이드바·최대화는 메인 창)."""
        self._wide = on
        self.event_panel.setVisible(not on)
        self.wide_btn.setIcon(icon("shrink" if on else "expand"))
        self._header_texts()

    def _header_texts(self):
        """버튼 글자. 좁으면(사이드바를 넓혔을 때 등) 아이콘만 — 글자는 툴팁 첫 줄과 같음."""
        texts = {self.fold_btn: "모두 펼치기" if self._folded else "모두 접기",
                 self.refresh_btn: "지금 확인",
                 self.wide_btn: "원래대로" if self._wide else "넓게 보기"}
        for b, t in texts.items():
            b.setText("" if self._narrow else t)

    NARROW_W = 1230                     # 이보다 좁으면 머리글 버튼을 아이콘만으로 ('최근 변화' 보일 때 기준)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        limit = self.NARROW_W - (0 if self.event_panel.isVisible() else self.event_panel.width() + 16)
        narrow = self.width() < limit
        if narrow != self._narrow:
            self._narrow = narrow
            self._header_texts()

    def _visible(self, s, d):
        if self.query:
            hay = " ".join(str(s.get(k, "")) for k in ("name", "host", "rdp_user", "group", "note", "site_code",
                                                         "address", "flow")).lower()
            if self.query not in hay:
                return False
        if self.filter == "open":
            return s["name"] in self.open_states
        if self.filter:
            return d is not None and d.state == self.filter
        return True

    def showEvent(self, e):
        super().showEvent(e)
        if self._dirty:
            self.rebuild()
        else:
            self._refresh_texts()      # 안 보이는 동안 건너뛴 카드 갱신

    def rebuild(self):
        """카드 배치를 다시 계산 (정렬·필터·그룹 숫자).

        성능: 카드와 그룹 묶음은 한 번 만들어 두고, 여기서는 순서 바꾸기·숨기기만 한다.
        위젯을 다른 부모로 옮기는 일(가장 비쌈)은 세션의 그룹이 바뀔 때만 생긴다.
        대시보드가 안 보이면(원격 화면을 보는 중) 미뤘다가 다시 보일 때 한 번에 한다.
        """
        if not self.isVisible():
            self._dirty = True
            return
        self._dirty = False
        devs = self.monitor.devices

        # 1) 카드 준비: 삭제된 세션 카드 제거, 새 세션 카드 생성, 그룹 바뀐 카드 이동
        for n in [n for n in self._pool if n not in self.sessions]:
            card = self._pool.pop(n)
            self._section(card.group).flow.remove(card)
            card.deleteLater()
        for s in self.sessions.values():
            g = s.get("group", "")
            card = self._pool.get(s["name"])
            if card is None:
                card = DeviceCard(s, self.view)
                card.connect_clicked.connect(self.connect_requested.emit)
                card.menu_clicked.connect(self.menu_requested.emit)
                self._pool[s["name"]] = card
                card.group = g
                self._section(g).flow.addWidget(card)
            elif card.group != g:
                self._section(card.group).flow.remove(card)
                card.group = g
                self._section(g).flow.addWidget(card)
            if card.session != s:
                card.set_session(s)
        for g in [g for g, sec in self._sections.items() if not sec.flow.count()]:   # 빈 그룹 정리
            sec = self._sections.pop(g)
            self.body_lay.removeWidget(sec)
            sec.deleteLater()

        # 2) 보일 카드·순서 계산
        groups = {}
        for s in self.sessions.values():
            d = devs.get(s["name"])
            if self._visible(s, d):
                groups.setdefault(s.get("group", ""), []).append((s, d))
        self.cards = {}
        shown = set()
        rank = self._rank
        for g in groups:
            groups[g].sort(key=lambda sd: (rank(sd[1]), sd[0]["name"]))
        if self.sort_mode == "ok":       # 응답하는 장비가 있는 그룹을 위로
            order = sorted(groups, key=lambda x: (rank(groups[x][0][1]), x == "", x))
        else:
            order = sorted(groups, key=lambda x: (x == "", x))
        for g in order:
            items = groups[g]
            sec = self._sections[g]
            sec.set_counts([d for _, d in items])
            sec.set_collapsed(g in self.collapsed and not self.query)
            sec.flow.reorder([self._pool[s["name"]] for s, _ in items])
            for s, d in items:
                card = self._pool[s["name"]]
                self.cards[s["name"]] = card
                shown.add(s["name"])
                if d:
                    card.update_device(d, self.open_states.get(s["name"]))
                else:
                    card.set_open_state(self.open_states.get(s["name"]))
        for n, card in self._pool.items():
            card.setVisible(n in shown)

        # 3) 그룹 묶음 순서·표시 (같은 부모 안에서 순서만 바꿈)
        for g, sec in self._sections.items():
            sec.setVisible(g in groups)
        for i, g in enumerate(order):
            sec = self._sections[g]
            if self.body_lay.indexOf(sec) != i:
                self.body_lay.removeWidget(sec)
                self.body_lay.insertWidget(i, sec)
        if not groups:
            self._empty.setText("등록된 세션이 없습니다. 왼쪽 '새 세션'으로 추가하세요." if not self.sessions
                                else "조건에 맞는 장비가 없습니다.")
        self._empty.setVisible(not groups)
        self._update_fold_btn()
        self._update_kpis()

    def _section(self, g):
        sec = self._sections.get(g)
        if sec is None:
            sec = GroupSection(g)
            sec.toggled.connect(self._toggle_group)
            self._sections[g] = sec
            self.body_lay.insertWidget(0, sec)     # 순서는 rebuild에서 맞춤
        return sec


    def _update_kpis(self):
        devs = self.monitor.devices
        counts = {}
        for n in self.sessions:
            d = devs.get(n)
            st = d.state if d else ST_CHECKING
            counts[st] = counts.get(st, 0) + 1
        self.tiles[None].set_value(len(self.sessions))
        for st in (ST_OK, ST_SLOW, ST_RDP_CLOSED, ST_OFFLINE):
            self.tiles[st].set_value(counts.get(st, 0))
        self.tiles["open"].set_value(len([n for n in self.open_states if n in self.sessions]))
        checking = counts.get(ST_CHECKING, 0)
        last = time.strftime("%H:%M:%S", time.localtime(self._last_check)) if self._last_check else "-"
        txt = "마지막 확인 %s  ·  %s" % (last, self.interval.currentText())
        if checking:
            txt += "  ·  확인 중 %d대" % checking
        self.sub.setText(txt)

    def _refresh_texts(self):
        if not self.isVisible():
            return
        devs = self.monitor.devices
        for n, card in self.cards.items():
            d = devs.get(n)
            if d:
                card.update_device(d, self.open_states.get(n))

    # ---------------------------------------------------------------- 감시 결과 (메인 스레드)
    def _on_update(self, d):
        if self.monitor.devices.get(d.name) is not d:
            return
        self._last_check = d.last_check
        card = self.cards.get(d.name)
        if card and self.isVisible():   # 안 보일 때는 건너뜀 (다시 보일 때 한꺼번에 갱신)
            card.update_device(d, self.open_states.get(d.name))
        self._kpi_timer.start()

    def _on_change(self, d, old, new):
        if self.monitor.devices.get(d.name) is not d:
            return
        self._rebuild_timer.start()     # 정렬(문제 먼저)·그룹 숫자·필터 다시 계산
        if self.log:
            self.log.device(d.name, "%s:%d" % (d.host, d.port), old, new, self._log_detail(d, old, new))
        if old == ST_CHECKING:
            return                      # 처음 확인 결과는 화면 목록에 넣지 않음 (로그에는 기록)
        s = self.sessions.get(d.name, {})
        self._add_event(time.time(), d.name, old, new, "%s  ·  %s" % (s.get("group") or "그룹 없음", d.host))
        if new == ST_OFFLINE:
            self.alert.emit(d.name)

    @staticmethod
    def _log_detail(d, old, new):
        parts = []
        if old == ST_CHECKING:
            parts.append("첫 확인")
        else:
            parts.append("%s %s 유지" % (old, duration_text(d.prev_duration)))
        if new == ST_OFFLINE:
            parts.append("마지막 응답 %s" % (time.strftime("%m-%d %H:%M:%S", time.localtime(d.last_ok))
                                          if d.last_ok else "없음"))
        elif d.rtt is not None:
            parts.append("응답 %dms" % round(d.rtt))
        return ", ".join(parts)

    def _add_event(self, ts, name, old, new, tip, at_top=True):
        fmt = "%H:%M:%S" if time.strftime("%Y%m%d", time.localtime(ts)) == time.strftime("%Y%m%d") \
            else "%m-%d %H:%M:%S"
        item = QListWidgetItem("%s   %s\n%s  →  %s" % (time.strftime(fmt, time.localtime(ts)), name, old, new))
        item.setForeground(QColor(STATE_COLOR.get(new, C["text"])))
        item.setToolTip("%s\n%s" % (tip, STATE_HINT.get(new, "")))
        if at_top:
            self.events.insertItem(0, item)
        else:
            self.events.addItem(item)
        while self.events.count() > 300:
            self.events.takeItem(self.events.count() - 1)
        self.events_empty.hide()
        self.events.show()

    def load_history(self):
        """로그 파일에서 지난 상태 변화를 '최근 변화'에 채운다 (시작할 때·로그 복원 후)."""
        self.events.clear()
        self.events.hide()
        self.events_empty.show()
        if not self.log:
            return
        def is_change(e):
            # 시작할 때마다 장비 수만큼 쌓이는 '첫 확인' 줄은 300개 한도에서 뺀다
            old, _, new = e["event"].partition(ARROW)
            return bool(new) and old != ST_CHECKING

        for e in self.log.recent(300, KIND_DEVICE, where=is_change):          # 최신순
            old, _, new = e["event"].partition(ARROW)
            self._add_event(e["ts"], e["name"], old, new, "%s  ·  %s" % (e["addr"], e["detail"]), at_top=False)
