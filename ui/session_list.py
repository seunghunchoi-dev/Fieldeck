"""사이드바 세션 목록 — 세션이 많아도 찾기·구분이 쉽도록.

- 그룹별 묶음 (접기/펼치기, 그룹 색 자동 배정, 개수·접속 수 표시)
- 즐겨찾기 묶음은 맨 위 고정 (검색 중에도 같은 자리 — 검색은 줄 숨기기만 하므로)
- 정렬: 이름순 / 최근 접속순   보기: 기본 / 간단히
  (전체/즐겨찾기/접속 중 필터는 2026-11-03 제거 — 대시보드의 상태 타일·검색으로 대신)
- 각 세션: 그룹 색 이니셜 아바타 + 상태 점, 이름, 주소·계정·메모, 상태 또는 마지막 접속 시각
- 접기 상태·정렬·보기는 QSettings(레지스트리 HKCU)에 기억
"""
from PySide6.QtCore import QPoint, QSettings, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                             QPushButton, QVBoxLayout, QWidget)

from core import appinfo
from core.site_import import short_address
from ui.icons import icon
from ui.theme import C, STATUS_COLOR, group_color, relative_time

KIND = Qt.ItemDataRole.UserRole          # "group" | "session"
KEY = Qt.ItemDataRole.UserRole + 1       # 그룹 키 또는 세션 이름
FAV_KEY, NONE_KEY = "__fav__", "__none__"
IDLE = "대기"


def _avatar(text, color, state, size):
    """그룹 색 원 + 이니셜 + 오른쪽 아래 상태 점."""
    dpr = 2
    pm = QPixmap(size * dpr, size * dpr)
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    bg = QColor(color)
    bg.setAlpha(46)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(bg)
    p.drawRoundedRect(0, 0, size, size, size * 0.3, size * 0.3)
    f = QFont()
    f.setPixelSize(int(size * 0.42))
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor(color))
    p.drawText(0, 0, size, size, Qt.AlignmentFlag.AlignCenter, text)
    if state != IDLE:
        d = max(8, size // 3)
        p.setPen(QColor(C["sidebar"]))
        p.setBrush(QColor(STATUS_COLOR.get(state, C["idle"])))
        p.drawEllipse(size - d, size - d, d - 1, d - 1)
    p.end()
    return pm


def _initial(name):
    name = name.strip()
    return name[:1].upper() if name else "?"


class SessionCard(QWidget):
    def __init__(self, session, state, compact):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.s = session
        self.compact = compact
        self.size_ = 26 if compact else 34
        self.av = QLabel()
        self.av.setFixedSize(self.size_, self.size_)
        self.title = QLabel()
        self.title.setObjectName("cardTitle")
        self.sub = QLabel()
        self.sub.setObjectName("cardSub")
        self.right = QLabel()
        self.right.setObjectName("cardSub")
        text = QVBoxLayout()
        text.setSpacing(1)
        text.addWidget(self.title)
        if not compact:
            text.addWidget(self.sub)
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 4 if compact else 7, 10, 4 if compact else 7)
        row.setSpacing(10)
        row.addWidget(self.av)
        row.addLayout(text, 1)
        if compact:
            row.addWidget(self.sub)
        row.addWidget(self.right)
        self.refresh(state)

    def refresh(self, state):
        s = self.s
        color = group_color(s.get("group", ""))
        # 아바타: 개소(하천 소속)면 하천 첫 글자, 아니면 이름 첫 글자
        self.av.setPixmap(_avatar(_initial(s.get("group") or s["name"]), color, state, self.size_))
        star = "  ★" if s.get("favorite") else ""
        self.title.setText(s["name"] + star)
        port = "" if int(s.get("rdp_port", 3389)) == 3389 else ":%s" % s["rdp_port"]
        addr = short_address(s.get("address", ""))
        if addr:                           # 현장 개소: 상/하류 · 메모(예: 1구역) · 주소 (IP는 툴팁)
            sub = "  ·  ".join(p for p in (s.get("flow", ""), s.get("note", ""), addr) if p)
        elif self.compact:
            sub = s["host"] + port
        else:
            parts = [s["host"] + port, s.get("rdp_user") or "계정 미지정"]
            if s.get("note"):
                parts.append(s["note"])
            sub = "  ·  ".join(parts)
        self._sub_full = sub
        self._elide_sub()
        tip = [s["name"] + (" (%s)" % s["group"] if s.get("group") else "")]
        if s.get("address"):
            tip.append(s["address"])
        tip.append("%s%s · %s" % (s["host"], port, s.get("rdp_user") or "계정 미지정"))
        if s.get("note"):
            tip.append(s["note"])
        self.setToolTip("\n".join(tip))
        if state != IDLE:
            self.right.setText(state)
            self.right.setStyleSheet("color:%s; font-size:11px; background:transparent;"
                                     % STATUS_COLOR.get(state, C["idle"]))
        else:
            self.right.setText("" if self.compact else relative_time(s.get("last_connected", 0)))
            self.right.setStyleSheet("")

    def _elide_sub(self):
        """사이드바 폭에 맞춰 아래 줄을 … 로 줄임 (길면 오른쪽 글자와 겹치던 문제)."""
        if not hasattr(self, "_sub_full"):
            return
        room = self.width() - self.size_ - 110 if self.width() > 150 else 170
        self.sub.setText(self.sub.fontMetrics().elidedText(self._sub_full, Qt.TextElideMode.ElideRight, room))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._elide_sub()


class GroupHeader(QWidget):
    def __init__(self, title, color, collapsed):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.chev = chev = QLabel("▸" if collapsed else "▾")
        chev.setObjectName("chev")
        chev.setFixedWidth(10)
        bar = QLabel()
        bar.setFixedSize(4, 14)
        bar.setStyleSheet("background:%s; border-radius:2px;" % color)
        name = QLabel(title)
        name.setObjectName("groupName")
        self.cnt = QLabel()
        self.cnt.setObjectName("groupCount")
        row = QHBoxLayout(self)
        row.setContentsMargins(6, 10, 10, 4)
        row.setSpacing(8)
        row.addWidget(chev)
        row.addWidget(bar)
        row.addWidget(name)
        row.addStretch(1)
        row.addWidget(self.cnt)

    def set_collapsed(self, collapsed):
        self.chev.setText("▸" if collapsed else "▾")

    def set_counts(self, total, live):
        self.cnt.setText(("%d" % total) + ("  ·  접속 %d" % live if live else ""))


class SessionList(QWidget):
    activated = Signal(str)                 # 세션 더블클릭 / Enter
    selection_changed = Signal()
    menu_requested = Signal(QPoint, str, str)   # 위치, kind, key

    def __init__(self):
        super().__init__()
        self.cfg = QSettings(appinfo.APP_NAME, appinfo.APP_NAME)
        self.collapsed = set(self.cfg.value("list/collapsed", [], type=list))
        self.cfg.remove("list/mode")     # 없앤 필터의 예전 설정 정리 ('접속 중'에 고정돼 목록이 안 보이던 문제)
        self.sort = self.cfg.value("list/sort", "name")
        self.compact = self.cfg.value("list/compact", False, type=bool)
        self.query = ""
        self.sessions = []
        self.states = {}
        self.cards = {}
        self.headers = {}
        self._hays = {}            # 이름 → 검색용 글자 (rebuild 때 비움)
        self._query_timer = QTimer(self)
        self._query_timer.setSingleShot(True)
        self._query_timer.setInterval(150)     # 타자 멈추면 한 번만 거름
        self._query_timer.timeout.connect(self._on_query)
        self._prefill_timer = QTimer(self)
        self._prefill_timer.setInterval(10)
        self._prefill_timer.timeout.connect(self._prefill)

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        # 개수 + 정렬/보기 버튼
        info_row = QHBoxLayout()
        info_row.setSpacing(2)
        self.info = QLabel()
        self.info.setObjectName("section")
        info_row.addWidget(self.info, 1)
        self.sort_btn = QPushButton()
        self.sort_btn.setObjectName("icon")
        self.sort_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sort_btn.clicked.connect(self._toggle_sort)
        self.sort_btn.setIcon(icon("sort", size=14))
        self.dens_btn = QPushButton()
        self.dens_btn.setIcon(icon("rows", size=14))
        self.dens_btn.setObjectName("icon")
        self.dens_btn.setCheckable(True)
        self.dens_btn.setChecked(self.compact)
        self.dens_btn.setToolTip("간단히 보기 (한 줄)")
        self.dens_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dens_btn.clicked.connect(self._toggle_compact)
        self.dens_btn.setText("간단히")
        info_row.addWidget(self.sort_btn)
        info_row.addWidget(self.dens_btn)
        v.addLayout(info_row)

        self.list = QListWidget()
        self.list.setObjectName("sessions")
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        self.list.itemClicked.connect(self._clicked)
        self.list.itemDoubleClicked.connect(self._double)
        self.list.itemSelectionChanged.connect(self.selection_changed)
        v.addWidget(self.list, 1)

        self.empty = QLabel()
        self.empty.setObjectName("heroSub")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        v.addWidget(self.empty, 1)       # 목록이 숨을 때 빈자리를 안내문이 차지 (다른 줄이 늘어나지 않게)
        self._update_sort_btn()

    # ---------------------------------------------------------------- 공개
    def set_sessions(self, sessions, states):
        self.sessions = sessions
        self.states = states
        self.rebuild()

    def set_query(self, text):
        """타자 칠 때마다 다시 만들지 않고 잠깐 기다렸다가 줄 숨기기만 한다 (한글 조합 중 버벅임 방지)."""
        self.query = text.strip().lower()
        self._query_timer.start()

    def set_state(self, name, state):
        self.states[name] = state
        row = self.cards.get(name)
        if row and row[1]:
            row[1].refresh(state)
        self._refresh_headers()

    def selected_names(self):
        return [it.data(KEY) for it in self.list.selectedItems() if it.data(KIND) == "session"]

    def select(self, name):
        if name in self.cards:
            self.list.setCurrentItem(self.cards[name][0])

    def names_in_group(self, key):
        return [s["name"] for s in self._grouped().get(key, [])]

    def set_all_collapsed(self, collapsed):
        self.collapsed = set(self._grouped(all_=True).keys()) if collapsed else set()
        self._save()
        self._apply_filter()

    # ---------------------------------------------------------------- 구성
    @staticmethod
    def _hay(s):
        return " ".join([s["name"], s["host"], s.get("rdp_user", ""), s.get("note", ""), s.get("group", ""),
                         s.get("site_code", ""), s.get("address", ""), s.get("flow", "")]).lower()

    def _match(self, s):
        if self.query:
            hay = self._hays.get(s["name"])
            if hay is None:
                hay = self._hays[s["name"]] = self._hay(s)
            return self.query in hay
        return True

    def _grouped(self, all_=False):
        """{그룹키: [세션...]} — 즐겨찾기는 맨 위 별도 묶음 (검색 중에도 같은 자리)."""
        out = {}
        for s in self.sessions:
            if not all_ and not self._match(s):
                continue
            if s.get("favorite"):
                key = FAV_KEY
            else:
                key = s.get("group") or NONE_KEY
            out.setdefault(key, []).append(s)
        if self.sort == "recent":
            keyf = lambda s: (-(s.get("last_connected") or 0), s["name"])
        else:
            keyf = lambda s: s["name"]
        for k in out:
            out[k].sort(key=keyf)
        return out

    def _group_order(self, keys):
        named = sorted(k for k in keys if k not in (FAV_KEY, NONE_KEY))
        return ([FAV_KEY] if FAV_KEY in keys else []) + named + ([NONE_KEY] if NONE_KEY in keys else [])

    @staticmethod
    def _group_title(key):
        return {"__fav__": "★ 즐겨찾기", "__none__": "그룹 없음"}.get(key, key)

    def rebuild(self):
        """줄 구성(세션 목록·정렬·보기)을 새로 만든다.

        성능: 검색·그룹 접기는 여기를 거치지 않고 _apply_filter가 줄을 숨기기만 한다.
        세션 카드는 처음 보일 때 만들고, 남는 시간에 조금씩 미리 만들어 둔다 (366개 기준 한 번에 0.6초).
        """
        self._prefill_timer.stop()
        selected = set(self.selected_names())
        scroll = self.list.verticalScrollBar().value()
        # 기존 행 위젯은 지연 삭제되므로 먼저 숨겨 잔상이 남지 않게 한다
        for i in range(self.list.count()):
            w = self.list.itemWidget(self.list.item(i))
            if w:
                w.hide()
                w.deleteLater()
        self.list.clear()
        self.cards = {}            # 이름 → [항목, 카드(아직 안 만들었으면 None), 세션]
        self.headers = {}          # 그룹키 → (항목, 머리글 위젯, [세션 이름...])
        self._hays = {}
        grouped = self._grouped(all_=True)
        for key in self._group_order(grouped.keys()):
            color = C["warn"] if key == FAV_KEY else group_color("" if key == NONE_KEY else key)
            h = QListWidgetItem()
            h.setData(KIND, "group")
            h.setData(KEY, key)
            h.setFlags(Qt.ItemFlag.ItemIsEnabled)
            h.setSizeHint(QSize(0, 34))
            self.list.addItem(h)
            hw = GroupHeader(self._group_title(key), color, key in self.collapsed)
            self.list.setItemWidget(h, hw)
            self.headers[key] = (h, hw, [s["name"] for s in grouped[key]])
            for s in grouped[key]:
                it = QListWidgetItem()
                it.setData(KIND, "session")
                it.setData(KEY, s["name"])
                it.setSizeHint(QSize(0, 36 if self.compact else 54))
                self.list.addItem(it)
                self.cards[s["name"]] = [it, None, s]
                if s["name"] in selected:
                    it.setSelected(True)
        self._apply_filter()
        self.list.verticalScrollBar().setValue(scroll)
        self._prefill_timer.start()

    def _make_card(self, row):
        row[1] = SessionCard(row[2], self.states.get(row[2]["name"], IDLE), self.compact)
        self.list.setItemWidget(row[0], row[1])

    def _prefill(self):
        """아직 안 만든 카드를 조금씩 만든다 (검색·펼치기 때 바로 보이게)."""
        n = 0
        for row in self.cards.values():
            if row[1] is None:
                self._make_card(row)
                n += 1
                if n >= 12:
                    return
        self._prefill_timer.stop()

    def _on_query(self):
        self._apply_filter()
        self.list.scrollToTop()

    def _apply_filter(self):
        """검색어·접힘에 맞춰 줄을 숨기거나 보인다 (위젯은 그대로)."""
        searching = bool(self.query)
        shown = 0
        self.list.setUpdatesEnabled(False)
        for key, (h, hw, names) in self.headers.items():
            collapsed = key in self.collapsed and not searching
            hw.set_collapsed(collapsed)
            hits = 0
            for name in names:
                row = self.cards[name]
                ok = self._match(row[2])
                hits += ok
                vis = ok and not collapsed
                row[0].setHidden(not vis)
                if vis and row[1] is None:
                    self._make_card(row)
            h.setHidden(hits == 0)
            shown += hits
        self.list.setUpdatesEnabled(True)
        self._refresh_headers()

        total = len(self.sessions)
        live = sum(1 for s in self.sessions if self.states.get(s["name"], IDLE) != IDLE)
        txt = "세션 %d" % total if shown == total else "%d / %d개 표시" % (shown, total)
        if live:
            txt += "   ·   접속 %d" % live
        self.info.setText(txt)
        if total == 0:
            self.empty.setText("등록된 세션이 없어요.\n'+ 새 세션'으로 추가해 보세요.")
        elif shown == 0:
            self.empty.setText("검색 결과가 없어요.")
        self.empty.setVisible(shown == 0)
        self.list.setVisible(shown > 0)

    def _refresh_headers(self):
        """머리글 위젯은 그대로 두고 숫자만 갱신 (위젯 교체 시 잔상 방지)."""
        for key, (h, hw, names) in self.headers.items():
            hits = [n for n in names if self._match(self.cards[n][2])]
            hw.set_counts(len(hits), sum(1 for n in hits if self.states.get(n, IDLE) != IDLE))

    # ---------------------------------------------------------------- 이벤트
    def _clicked(self, item):
        if item.data(KIND) == "group":
            key = item.data(KEY)
            if self.query:
                return
            self.collapsed.symmetric_difference_update({key})
            self._save()
            self._apply_filter()

    def _double(self, item):
        if item.data(KIND) == "session":
            self.activated.emit(item.data(KEY))

    def _menu(self, pos):
        item = self.list.itemAt(pos)
        if item:
            self.menu_requested.emit(self.list.mapToGlobal(pos), item.data(KIND), item.data(KEY))

    def _toggle_sort(self):
        self.sort = "recent" if self.sort == "name" else "name"
        self._save()
        self._update_sort_btn()
        self.rebuild()

    def _update_sort_btn(self):
        self.sort_btn.setText("최근순" if self.sort == "recent" else "이름순")
        self.sort_btn.setToolTip("정렬 바꾸기 (이름순 ↔ 최근 접속순)")

    def _toggle_compact(self):
        self.compact = self.dens_btn.isChecked()
        self._save()
        self.rebuild()

    def _save(self):
        self.cfg.setValue("list/collapsed", sorted(self.collapsed))
        self.cfg.setValue("list/sort", self.sort)
        self.cfg.setValue("list/compact", self.compact)
