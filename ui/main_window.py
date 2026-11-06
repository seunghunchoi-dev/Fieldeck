"""메인 화면 — 왼쪽 세션 목록 + 오른쪽 원격 화면 탭 (다중 접속).

조작
- 세션 더블클릭/Enter: 접속 (이미 열려 있으면 그 탭으로 이동)
- Ctrl/Shift로 여러 개 선택 후 '선택 접속': 한꺼번에 접속
- 세션 오른쪽 클릭: 접속 / 즐겨찾기 / 그룹 이동 / 편집 / 복제 / 삭제
- 그룹 머리글 클릭: 접기·펼치기, 오른쪽 클릭: 그룹 전체 접속 / 이름 바꾸기 / 모두 접기
- Ctrl+N 새 세션, Ctrl+F 검색 (원격 화면에 포커스가 있을 때는 키가 원격으로 간다)
"""
import getpass
import time

from PySide6.QtCore import QEvent, QPoint, QRect, QSettings, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QMouseEvent
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMainWindow,
                             QMenu, QMessageBox, QPushButton, QSplitter, QStackedWidget, QTabBar, QTabWidget,
                             QVBoxLayout, QWidget)

from ui import icons
from ui.app_icon import app_icon
from core import appinfo
from core.conn_log import ConnLog
from ui.backup_dialog import (backup_logs, backup_to_excel, import_sites, open_log_folder, restore_from_excel,
                              restore_logs, save_template)
from ui.dashboard import DashboardTab
from ui.detached_window import DetachedWindow
from ui.icons import icon

from ui.rdp_tab import (RdpTab, finish_release, STATE_CONNECTED, STATE_CONNECTING, STATE_DISCONNECTED, STATE_IDLE,
                        STATE_RECONNECTING)
from ui.signal_bars import SignalBars, bars_icon
from ui.fullscreen_bar import FullscreenBar
from ui.session_dialog import SessionDialog
from ui.session_list import FAV_KEY, NONE_KEY, SessionList
from ui.theme import C, STATUS_COLOR, dot_icon, group_color, shortcut

SIDEBAR_MIN, SIDEBAR_MAX = 240, 640   # 사이드바 폭 조절 범위 (px)


class DetachTabBar(QTabBar):
    """탭을 탭 줄 바깥으로 끌어내면 detach_requested(인덱스, 화면 좌표)를 보낸다."""
    detach_requested = Signal(int, QPoint)
    MARGIN = 40   # 탭 줄에서 이만큼(px) 벗어나면 분리

    def __init__(self):
        super().__init__()
        self._press_idx = -1

    def mousePressEvent(self, e):
        self._press_idx = self.tabAt(e.position().toPoint()) if e.button() == Qt.MouseButton.LeftButton else -1
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        super().mouseMoveEvent(e)
        if self._press_idx < 0 or not (e.buttons() & Qt.MouseButton.LeftButton):
            return
        if not self.rect().adjusted(-self.MARGIN, -self.MARGIN, self.MARGIN, self.MARGIN).contains(
                e.position().toPoint()):
            idx = self.currentIndex()   # 끄는 동안 순서가 바뀌었을 수 있어 현재 탭 기준
            self._press_idx = -1
            # 탭 줄의 내부 끌기 상태를 끝낸 뒤 분리
            rel = QMouseEvent(QEvent.Type.MouseButtonRelease, e.position(), e.globalPosition(),
                              Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, e.modifiers())
            super().mouseReleaseEvent(rel)
            gpos = e.globalPosition().toPoint()
            QTimer.singleShot(0, lambda: self.detach_requested.emit(idx, gpos))

    def mouseReleaseEvent(self, e):
        self._press_idx = -1
        super().mouseReleaseEvent(e)


class MainWindow(QMainWindow):
    def __init__(self, store, log=None):
        super().__init__()
        self.store = store
        self.log = log or ConnLog()   # 연결 상태 로그 (%LOCALAPPDATA%\Fieldeck\logs, 설계문서 6-8)
        self.log.app("시작", "Windows 사용자 %s, 세션 %d개" % (getpass.getuser(), len(store.sessions)))
        self._full = None   # 전체 화면 진입 전 상태 (사이드바 보임 여부, 최대화 여부)
        self.tabs = {}      # 세션 이름 -> RdpTab (탭에 있든 분리된 창에 있든)
        self.detached = {}  # RdpTab -> DetachedWindow
        self.setWindowTitle(appinfo.APP_NAME)
        self.resize(1480, 900)
        self.setMinimumSize(1000, 640)

        # 사이드바 | 본문 — 경계선을 끌어 사이드바 폭 조절 (폭은 레지스트리에 기억, 2026-11-04)
        self.cfg = QSettings(appinfo.APP_NAME, appinfo.APP_NAME)
        self._wide = None   # 대시보드 '넓게 보기' 전 상태 (사이드바 보임 여부, 최대화 여부)
        root = QSplitter(Qt.Orientation.Horizontal)
        root.setObjectName("root")
        root.setHandleWidth(5)
        root.setChildrenCollapsible(False)
        self.splitter = root
        self.sidebar = self._build_sidebar()
        root.addWidget(self.sidebar)
        root.addWidget(self._build_main())
        root.setStretchFactor(0, 0)
        root.setStretchFactor(1, 1)
        side_w = min(max(self.cfg.value("ui/sidebar_w", 320, type=int), SIDEBAR_MIN), SIDEBAR_MAX)
        root.setSizes([side_w, 1480 - side_w])
        root.splitterMoved.connect(lambda *_: self._save_sidebar_width())
        self.setCentralWidget(root)

        self.statusBar().setSizeGripEnabled(False)
        shortcut(QKeySequence("Ctrl+N"), self, self.add_session)
        shortcut(QKeySequence("Ctrl+F"), self, lambda: self.search.setFocus())
        # F11: 원격 화면에 포커스가 있으면 키가 원격으로 가므로, 그때는 상단 막대로 끝낸다.
        shortcut(QKeySequence(Qt.Key.Key_F11), self, self.toggle_fullscreen)

        # 분리 창을 끌어 올 때 '여기에 놓으면 합쳐짐' 표시 (상단 바·탭 줄 위에 겹쳐 그림)
        self.drop_hint = QLabel("여기에 놓으면 탭으로 합쳐집니다", self)
        self.drop_hint.setObjectName("dropHint")
        self.drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.drop_hint.hide()

        self._full = None   # 전체 화면 진입 전 상태 (사이드바 보임 여부, 최대화 여부)
        self.fsbar = FullscreenBar(self)
        self.fsbar.exit_requested.connect(self.toggle_fullscreen)
        self.fsbar.prev_requested.connect(lambda: self._step_tab(-1))
        self.fsbar.next_requested.connect(lambda: self._step_tab(1))
        self.fsbar.view_requested.connect(self.toggle_view)
        self.fsbar.minimize_requested.connect(self.showMinimized)

        self.reload_sessions()
        self._refresh_chrome()

    # ------------------------------------------------------------------ 구성
    def _build_sidebar(self):
        side = QFrame()
        side.setObjectName("sidebar")
        side.setMinimumWidth(SIDEBAR_MIN)
        side.setMaximumWidth(SIDEBAR_MAX)
        v = QVBoxLayout(side)
        v.setContentsMargins(16, 20, 16, 14)
        v.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(12)
        logo = QLabel()
        pm = app_icon().pixmap(QSize(40, 40))
        logo.setPixmap(pm)
        logo.setFixedSize(40, 40)
        names = QVBoxLayout()
        names.setSpacing(0)
        brand = QLabel(appinfo.APP_NAME)
        brand.setObjectName("brand")
        brand_sub = QLabel("원격 PC 다중 접속  ·  v%s" % appinfo.VERSION)
        brand_sub.setObjectName("brandSub")
        names.addWidget(brand)
        names.addWidget(brand_sub)
        more = QPushButton()
        more.setObjectName("ghost")
        more.setIcon(icon("more", size=20))
        more.setIconSize(QSize(20, 20))
        more.setToolTip("세션 목록 백업 · 복원 / 연결 로그")
        more.setCursor(Qt.CursorShape.PointingHandCursor)
        more_menu = QMenu(more)
        more_menu.addAction(icon("download"), "엑셀로 백업…", self.backup_excel)
        more_menu.addAction(icon("upload"), "엑셀에서 복원…", self.restore_excel)
        more_menu.addAction(icon("rows"), "빈 양식 저장…", lambda: save_template(self))
        more_menu.addSeparator()
        more_menu.addAction(icon("monitors"), "장비 목록 가져오기…", self.import_sites)
        more_menu.addSeparator()
        more_menu.addAction(icon("folder"), "연결 로그 폴더 열기", lambda: open_log_folder(self, self.log))
        more_menu.addAction(icon("download"), "연결 로그 백업…", lambda: backup_logs(self, self.log))
        more_menu.addAction(icon("upload"), "연결 로그 복원…", self.restore_logs)
        more.clicked.connect(lambda: more_menu.exec(more.mapToGlobal(QPoint(0, more.height()))))
        head.addWidget(logo)
        head.addLayout(names, 1)
        head.addWidget(more, alignment=Qt.AlignmentFlag.AlignTop)
        v.addLayout(head)
        v.addSpacing(6)

        self.search = QLineEdit()
        self.search.setPlaceholderText("세션 검색  (Ctrl+F)")
        self.search.setToolTip("이름 · 주소 · 계정 · 그룹 · 메모로 찾기")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icon("search", size=16), QLineEdit.ActionPosition.LeadingPosition)
        v.addWidget(self.search)

        add = QPushButton("새 세션")
        add.setIcon(icon("plus", "#FFFFFF", 16))
        add.setObjectName("primary")
        add.setCursor(Qt.CursorShape.PointingHandCursor)
        add.setToolTip("Ctrl+N")
        add.clicked.connect(self.add_session)
        v.addWidget(add)
        v.addSpacing(4)

        self.slist = SessionList()
        self.slist.activated.connect(self.open_session)
        self.slist.selection_changed.connect(self._refresh_chrome)
        self.slist.menu_requested.connect(self._menu)
        self.search.textChanged.connect(self.slist.set_query)
        shortcut(QKeySequence(Qt.Key.Key_Return), self.slist.list, self.open_selected)
        shortcut(QKeySequence(Qt.Key.Key_Delete), self.slist.list, self._delete_selected)
        v.addWidget(self.slist, 1)

        self.multi_btn = QPushButton("선택한 세션 접속")
        self.multi_btn.setIcon(icon("monitors", C["text"]))
        self.multi_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.multi_btn.setToolTip("Ctrl 또는 Shift로 여러 세션을 고른 뒤 한 번에 접속")
        self.multi_btn.clicked.connect(self.open_selected)
        v.addWidget(self.multi_btn)

        me_row = QHBoxLayout()
        me_row.setSpacing(6)
        me_ico = QLabel()
        me_ico.setPixmap(icons.pixmap("shield", C["ok"], 14))
        me = QLabel("%s  ·  이 계정으로만 복호화" % getpass.getuser())
        me.setObjectName("userBadge")
        tip = "현재 Windows 사용자 — 접속 정보(비밀번호)는 DPAPI로 암호화되어 이 계정으로만 열립니다"
        me.setToolTip(tip)
        me_ico.setToolTip(tip)
        me_row.addWidget(me_ico)
        me_row.addWidget(me, 1)
        v.addLayout(me_row)
        return side

    def _build_main(self):
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self.topbar = QFrame()
        self.topbar.setObjectName("topbar")
        self.topbar.setFixedHeight(52)
        t = QHBoxLayout(self.topbar)
        t.setContentsMargins(16, 0, 12, 0)
        t.setSpacing(8)
        self.side_btn = QPushButton()
        self.side_btn.setObjectName("ghost")
        self.side_btn.setIcon(icon("menu", size=20))
        self.side_btn.setIconSize(QSize(20, 20))
        self.side_btn.setToolTip("사이드바 숨기기/보이기 (집중 모드)")
        self.side_btn.clicked.connect(self.toggle_sidebar)
        self.top_title = QLabel("")
        self.top_title.setObjectName("topTitle")
        self.chip_group = QLabel()
        self.chip_group.setObjectName("chip")
        self.chip_state = QLabel()
        self.chip_state.setObjectName("chip")
        self.signal = SignalBars()
        self.chip_low = QLabel("저속 모드")
        self.chip_low.setObjectName("chipWarn")
        self.chip_low.setToolTip("신호가 약해 16비트 색·화면 효과 끔으로 접속했습니다.\n"
                                 "신호가 좋아진 뒤 '다시 연결'하면 보통 화질로 돌아옵니다.")
        self.chip_clip = QLabel("클립보드 공유")
        self.chip_clip.setObjectName("chip")
        self.chip_clip.setToolTip("내 PC ↔ 원격 PC 간 Ctrl+C / Ctrl+V로 텍스트·파일 복사")
        self.chip_res = QLabel()
        self.chip_res.setObjectName("chip")
        self.chip_res.setToolTip("원격 해상도 · 현재 표시 배율")
        self.btn_view = QPushButton()
        self.btn_view.setObjectName("ghost")
        self.btn_view.clicked.connect(self.toggle_view)
        self.btn_full = QPushButton("전체 화면")
        self.btn_full.setIcon(icon("expand"))
        self.btn_full.setObjectName("ghost")
        self.btn_full.setToolTip("원격 화면을 모니터 전체로 보기 (F11)\n끝낼 때: 화면 맨 위에 마우스를 대면 나오는 막대")
        self.btn_full.clicked.connect(self.toggle_fullscreen)
        self.btn_reconnect = QPushButton("다시 연결")
        self.btn_reconnect.setIcon(icon("refresh"))
        self.btn_reconnect.setObjectName("ghost")
        self.btn_reconnect.clicked.connect(lambda: self.current_tab() and self.current_tab().connect_session())
        self.btn_disconnect = QPushButton("연결 끊기")
        self.btn_disconnect.setIcon(icon("power"))
        self.btn_disconnect.setObjectName("ghost")
        self.btn_disconnect.clicked.connect(lambda: self.current_tab() and self.current_tab().disconnect_session())
        for b in (self.side_btn, self.btn_view, self.btn_full, self.btn_reconnect, self.btn_disconnect):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        center = Qt.AlignmentFlag.AlignVCenter
        t.addWidget(self.side_btn)
        t.addWidget(self.top_title)
        t.addSpacing(6)
        for chip in (self.chip_group, self.chip_state, self.signal, self.chip_low, self.chip_clip):
            t.addWidget(chip, alignment=center)
        t.addStretch(1)
        t.addWidget(self.chip_res, alignment=center)
        t.addWidget(self.btn_view)
        t.addWidget(self.btn_full)
        t.addWidget(self.btn_reconnect)
        t.addWidget(self.btn_disconnect)
        v.addWidget(self.topbar)

        self.stack = QStackedWidget()
        self.tabw = QTabWidget()
        bar = DetachTabBar()
        bar.detach_requested.connect(self.detach_tab)
        bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        bar.customContextMenuRequested.connect(self._tab_menu)
        self.tabw.setTabBar(bar)
        self.tabw.setTabsClosable(True)
        self.tabw.setMovable(True)
        self.tabw.setDocumentMode(True)
        self.tabw.setIconSize(QSize(10, 10))
        self.tabw.tabCloseRequested.connect(self.close_tab_at)
        # 첫 탭 = 현장 대시보드 (닫기·분리 불가)
        self.dashboard = DashboardTab(log=self.log)
        self.dashboard.connect_requested.connect(self.open_session)
        self.dashboard.menu_requested.connect(lambda gpos, name: self._menu(gpos, "session", name))
        self.dashboard.alert.connect(lambda _: QApplication.alert(self, 0))
        self.dashboard.wide_requested.connect(self.toggle_dashboard_wide)
        bar.tabBarDoubleClicked.connect(lambda i: i == 0 and self.toggle_dashboard_wide())
        self.tabw.addTab(self.dashboard, icon("grid", C["accent_hi"]), "대시보드")
        self.tabw.tabBar().setTabButton(0, QTabBar.ButtonPosition.RightSide, None)
        self.tabw.setTabToolTip(0, "현장 대시보드 — 모든 장비 상태 보기 · 바로 접속")
        # 대시보드를 넣은 뒤에 연결 (생성 도중 호출되면 아직 없는 속성을 읽어 프로그램이 종료됨)
        self.tabw.currentChanged.connect(lambda _: self._on_tab_changed())
        self.stack.addWidget(self.tabw)
        v.addWidget(self.stack, 1)
        return wrap

    # ------------------------------------------------------------------ 세션 목록
    def _states(self):
        return {n: t.state for n, t in self.tabs.items()}

    def reload_sessions(self):
        self.slist.set_sessions(self.store.sessions, self._states())
        self.dashboard.set_sessions(self.store.sessions)

    def _rdp_count(self):
        """대시보드를 뺀 원격 화면 탭 수."""
        return sum(1 for i in range(self.tabw.count()) if isinstance(self.tabw.widget(i), RdpTab))

    def _set_session_state(self, name, state):
        """세션 목록·대시보드에 탭 상태 반영 (state=None 이면 탭 닫힘)."""
        self.slist.set_state(name, state or STATE_IDLE)
        self.dashboard.set_open_state(name, state)

    def _save_and_reload(self, select=None):
        self.store.save()
        self.reload_sessions()
        if select:
            self.slist.select(select)
        self._refresh_chrome()

    def _menu(self, gpos, kind, key):
        m = QMenu(self)
        if kind == "group":
            names = self.slist.names_in_group(key)
            m.addAction(icon("monitors"), "이 그룹 전체 접속 (%d)" % len(names), lambda: self._open_many(names))
            if key not in (FAV_KEY, NONE_KEY):
                m.addAction(icon("tag"), "그룹 이름 바꾸기", lambda: self.rename_group(key))
            m.addSeparator()
            m.addAction(icon("collapse"), "모두 접기", lambda: self.slist.set_all_collapsed(True))
            m.addAction(icon("expand_all"), "모두 펼치기", lambda: self.slist.set_all_collapsed(False))
            m.exec(gpos)
            return

        names = self.slist.selected_names()
        if key not in names:
            names = [key]
        if len(names) > 1:
            m.addAction(icon("monitors"), "선택한 %d개 접속" % len(names), lambda: self._open_many(names))
        else:
            m.addAction(icon("monitor"), "접속", lambda: self.open_session(key))
        m.addSeparator()
        all_fav = all(self.store.get(n).get("favorite") for n in names)
        m.addAction(icon("star", C["warn"]), "즐겨찾기 해제" if all_fav else "즐겨찾기",
                    lambda: self.set_favorite(names, not all_fav))
        gm = m.addMenu(icon("folder"), "그룹 이동")
        for g in self.store.groups():
            gm.addAction(dot_icon(group_color(g)), g, lambda g=g: self.move_to_group(names, g))
        if self.store.groups():
            gm.addSeparator()
        gm.addAction(icon("folder_plus"), "새 그룹…", lambda: self.move_to_new_group(names))
        gm.addAction(dot_icon(C["idle"]), "그룹 없음", lambda: self.move_to_group(names, ""))
        if len(names) == 1:
            m.addSeparator()
            m.addAction(icon("edit"), "편집", lambda: self.edit_session(key))
            m.addAction(icon("copy"), "복제", lambda: self.duplicate_session(key))
        m.addSeparator()
        m.addAction(icon("trash", C["err"]), "삭제", lambda: self.delete_sessions(names))
        m.exec(gpos)

    # ------------------------------------------------------------------ 엑셀 백업 / 복원
    def backup_excel(self):
        backup_to_excel(self, self.store)

    def import_sites(self):
        plan = import_sites(self, self.store, list(self.tabs))
        if not plan:
            return
        self._save_and_reload()
        self.statusBar().showMessage("장비 목록: 새로 등록 %d · 갱신 %d" % (len(plan["added"]), len(plan["updated"])),
                                     8000)

    def restore_logs(self):
        if restore_logs(self, self.log):
            self.dashboard.load_history()

    def restore_excel(self):
        plan = restore_from_excel(self, self.store, list(self.tabs))
        if not plan:
            return
        for n in plan["removed"]:
            if n in self.tabs:
                self.close_session(n)
        for n in plan["updated"]:
            tab = self.tabs.get(n)
            if tab:
                tab.session = dict(self.store.get(n))   # 다음 접속부터 적용
        self._save_and_reload()
        msg = "새로 추가 %d · 갱신 %d" % (len(plan["added"]), len(plan["updated"]))
        if plan["skipped"]:
            msg += " · 건너뜀 %d" % len(plan["skipped"])
        if plan["removed"]:
            msg += " · 삭제 %d" % len(plan["removed"])
        QMessageBox.information(self, "복원 완료", "%s\n\n복원 전 목록 보관: %s" % (msg, plan.get("backup") or "(없음)"))

    def set_favorite(self, names, on):
        for n in names:
            self.store.get(n)["favorite"] = on
        self._save_and_reload()

    def move_to_group(self, names, group):
        for n in names:
            self.store.get(n)["group"] = group
        self._save_and_reload()

    def move_to_new_group(self, names):
        g, ok = QInputDialog.getText(self, "새 그룹", "그룹 이름")
        if ok and g.strip():
            self.move_to_group(names, g.strip())

    def rename_group(self, old):
        new, ok = QInputDialog.getText(self, "그룹 이름 바꾸기", "새 이름", text=old)
        new = new.strip()
        if ok and new and new != old:
            for s in self.store.sessions:
                if s.get("group") == old:
                    s["group"] = new
            self._save_and_reload()

    def _current_group(self):
        names = self.slist.selected_names()
        return self.store.get(names[0]).get("group", "") if names else ""

    def add_session(self):
        dlg = SessionDialog(self, existing_names=self.store.names(), groups=self.store.groups(),
                            default_group=self._current_group())
        if dlg.exec():
            s = dlg.result_session()
            self.store.upsert(s)
            self._save_and_reload(select=s["name"])

    def edit_session(self, name):
        old = self.store.get(name)
        dlg = SessionDialog(self, session=old, existing_names=self.store.names(),
                            groups=self.store.groups())
        if not dlg.exec():
            return
        new = dlg.result_session()
        if new["name"] != name:
            self.store.remove(name)
            if name in self.tabs:
                self.tabs[new["name"]] = self.tabs.pop(name)
        self.store.upsert(new)
        tab = self.tabs.get(new["name"])
        if tab:
            tab.session = dict(new)   # 다음 접속(다시 연결)부터 적용
            if tab in self.detached:
                self.detached[tab].refresh()
            else:
                self.tabw.setTabText(self.tabw.indexOf(tab), new["name"])
        self._save_and_reload(select=new["name"])

    def duplicate_session(self, name):
        s = dict(self.store.get(name))
        base, i = s["name"] + " 복사본", 2
        s["name"] = base
        while self.store.get(s["name"]):
            s["name"] = "%s %d" % (base, i)
            i += 1
        s["favorite"], s["last_connected"] = False, 0
        self.store.upsert(s)
        self._save_and_reload(select=s["name"])
        self.edit_session(s["name"])

    def _delete_selected(self):
        names = self.slist.selected_names()
        if names:
            self.delete_sessions(names)

    def delete_sessions(self, names):
        label = names[0] if len(names) == 1 else "%d개 세션" % len(names)
        ok = QMessageBox.question(self, "세션 삭제",
                                  "'%s'을(를) 삭제할까요?\n저장된 접속 정보가 지워지며 되돌릴 수 없습니다." % label)
        if ok != QMessageBox.StandardButton.Yes:
            return
        for n in names:
            self.close_session(n)
            self.store.remove(n)
        self._save_and_reload()

    # ------------------------------------------------------------------ 탭 / 접속
    def open_selected(self):
        self._open_many(self.slist.selected_names())

    def _open_many(self, names):
        for i, n in enumerate(names):
            QTimer.singleShot(i * 300, lambda n=n: self.open_session(n))  # 순차적으로 열기

    def open_session(self, name):
        if name in self.tabs:
            tab = self.tabs[name]
            if tab in self.detached:   # 분리된 창이면 그 창을 앞으로
                w = self.detached[tab]
                if w.isMinimized():
                    w.showNormal()
                w.raise_()
                w.activateWindow()
            else:
                self.tabw.setCurrentWidget(tab)
            if not tab.is_active():
                tab.connect_session()
            return
        s = self.store.get(name)
        if not s:
            return
        try:
            tab = RdpTab(s)
        except RuntimeError as e:
            QMessageBox.warning(self, "접속 불가", str(e))
            return
        tab.state_changed.connect(lambda st, d, t=tab: self._on_state(t, st, d))
        tab.view_changed.connect(lambda t=tab: self._on_view_changed(t))
        tab.quality_changed.connect(lambda q, t=tab: self._on_quality(t, q))
        self.tabs[name] = tab
        idx = self.tabw.addTab(tab, dot_icon(STATUS_COLOR[STATE_IDLE]), name)
        self.tabw.setTabToolTip(idx, "%s  ·  %s" % (s["host"], s.get("rdp_user", "")))
        self.tabw.setCurrentIndex(idx)
        self.stack.setCurrentWidget(self.tabw)
        QTimer.singleShot(150, tab.connect_session)  # 탭 크기가 정해진 뒤 접속 (원격 해상도 결정)

    def close_tab_at(self, idx):
        tab = self.tabw.widget(idx)
        if not isinstance(tab, RdpTab):   # 대시보드는 닫지 않음
            return
        name = self._name_of(tab)
        self._log_session(tab, "탭 닫음", "사용자")
        self.tabw.removeTab(idx)          # 화면에서 먼저 뺀다 → 같은 탭을 또 닫을 수 없음
        self._discard_tab(tab, name)

    def _discard_tab(self, tab, name):
        """화면에서 빠진 탭 정리. 컨트롤 해제는 뒤에서 진행되므로 기다리지 않는다."""
        tab.close_tab()
        tab.deleteLater()
        if name:
            self.tabs.pop(name, None)
            self._set_session_state(name, None)
        self._refresh_chrome()

    def close_session(self, name):
        """탭이든 분리된 창이든 그 세션을 닫는다."""
        tab = self.tabs.get(name)
        if tab is None:
            return
        if tab in self.detached:
            self.detached[tab].close()   # → _close_detached
        else:
            self.close_tab_at(self.tabw.indexOf(tab))

    # ------------------------------------------------------------------ 분리된 창
    def _tab_menu(self, pos):
        idx = self.tabw.tabBar().tabAt(pos)
        if idx < 0:
            return
        m = QMenu(self)
        m.addAction(icon("detach"), "새 창으로 분리", lambda: self.detach_tab(idx, self.tabw.tabBar().mapToGlobal(pos)))
        m.addSeparator()
        m.addAction(icon("close"), "탭 닫기", lambda: self.close_tab_at(idx))
        m.exec(self.tabw.tabBar().mapToGlobal(pos))

    def detach_tab(self, idx, gpos):
        tab = self.tabw.widget(idx)
        if not isinstance(tab, RdpTab):
            return
        size = tab.size()
        self.tabw.removeTab(idx)
        win = DetachedWindow(tab)
        win.dock_requested.connect(self.dock_tab)
        win.close_requested.connect(self._close_detached)
        win.drag_moved.connect(self._on_drag_moved)
        win.drag_released.connect(self._on_drag_released)
        self.detached[tab] = win
        win.resize(max(size.width(), 900), max(size.height() + 48, 600))
        win.move(gpos - QPoint(160, 20))   # 커서가 창 제목 근처에 오도록
        win.show()
        win.activateWindow()
        QTimer.singleShot(300, tab.setFocus)
        self._refresh_chrome()

    # 끌어서 합치기: 분리 창의 제목줄을 잡고 메인 창의 상단 바·탭 줄 위에 놓으면 탭으로 들어온다.
    def _drop_zone(self):
        """합치기 영역 (메인 창 좌표) = 상단 바 + 탭 줄."""
        if self.is_fullscreen() or self.isMinimized() or not self.isVisible():
            return None
        top = self.topbar.mapTo(self, QPoint(0, 0))
        bar = self.tabw.tabBar()
        bottom = bar.mapTo(self, QPoint(0, bar.height())) + QPoint(0, 12)
        return QRect(top.x(), top.y(), self.topbar.width(), bottom.y() - top.y())

    def _drop_hit(self, gpos):
        zone = self._drop_zone()
        return zone is not None and zone.contains(self.mapFromGlobal(gpos))

    def _on_drag_moved(self, tab, gpos):
        win = self.detached.get(tab)
        hit = self._drop_hit(gpos)
        if hit:
            zone = self._drop_zone()
            self.drop_hint.setGeometry(zone)
            self.drop_hint.show()
            self.drop_hint.raise_()
        else:
            self.drop_hint.hide()
        if win:
            win.setWindowOpacity(0.55 if hit else 1.0)   # 놓을 자리가 보이도록 반투명

    def _on_drag_released(self, tab, gpos):
        self.drop_hint.hide()
        win = self.detached.get(tab)
        if win:
            win.setWindowOpacity(1.0)
        if win and self._drop_hit(gpos):
            bar = self.tabw.tabBar()
            at = bar.tabAt(bar.mapFromGlobal(gpos))
            self.dock_tab(tab, max(at, 1) if at >= 0 else -1)   # 대시보드(0번) 앞에는 넣지 않음

    def dock_tab(self, tab, at=-1):
        win = self.detached.pop(tab, None)
        if win is None:
            return
        win.release_tab()
        win.close()
        win.deleteLater()
        name = self._name_of(tab) or tab.session.get("name", "")
        ico = self._tab_icon(tab)
        idx = self.tabw.insertTab(at, tab, ico, name) if at >= 0 else self.tabw.addTab(tab, ico, name)
        self.tabw.setTabToolTip(idx, "%s  ·  %s" % (tab.session["host"], tab.session.get("rdp_user", "")))
        tab.show()
        self.tabw.setCurrentIndex(idx)
        self.stack.setCurrentWidget(self.tabw)
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()
        QTimer.singleShot(300, tab.setFocus)
        self._refresh_chrome()

    def _close_detached(self, tab):
        win = self.detached.pop(tab, None)
        name = self._name_of(tab)
        self._log_session(tab, "탭 닫음", "사용자")
        if win:
            win.deleteLater()
        self._discard_tab(tab, name)

    def _tab_icon(self, tab):
        """연결됨이면 안테나 막대, 아니면 상태 점."""
        if tab.state == STATE_CONNECTED:
            return bars_icon(tab.quality["bars"])
        return dot_icon(STATUS_COLOR.get(tab.state, C["idle"]))

    def _on_quality(self, tab, q):
        if tab in self.detached:
            self.detached[tab].refresh()
            return
        idx = self.tabw.indexOf(tab)
        if idx >= 0:
            self.tabw.setTabIcon(idx, self._tab_icon(tab))
            self.tabw.setTabToolTip(idx, "%s  ·  %s\n%s" % (tab.session["host"], tab.session.get("rdp_user", ""),
                                                             tab.quality_text()))
        if tab is self.current_tab():
            self.signal.set_quality(q)
            if self.is_fullscreen():
                self.fsbar.set_quality(q)

    def _on_view_changed(self, tab):
        if tab in self.detached:
            self.detached[tab].refresh()
        elif tab is self.current_tab():
            self._refresh_chrome()

    def current_tab(self):
        w = self.tabw.currentWidget()
        return w if isinstance(w, RdpTab) else None

    def _name_of(self, tab):
        return next((n for n, t in self.tabs.items() if t is tab), None)

    def _log_session(self, tab, state, detail):
        """원격 접속 탭의 상태를 로그 파일에 기록 (같은 상태·상세가 반복되면 한 번만)."""
        if getattr(tab, "_logged", None) == (state, detail):
            return
        tab._logged = (state, detail)
        s = tab.session
        self.log.session(s.get("name", ""), "%s:%s" % (s.get("host", ""), s.get("rdp_port") or 3389), state, detail)

    def _on_state(self, tab, state, detail):
        self._log_session(tab, state, detail)
        name = self._name_of(tab)
        idx = self.tabw.indexOf(tab)
        if idx >= 0:
            self.tabw.setTabIcon(idx, self._tab_icon(tab))
        if name and state == STATE_CONNECTED and self.store.get(name):
            self.store.get(name)["last_connected"] = int(time.time())
            self.store.save()
        if name:
            self._set_session_state(name, state)
        if tab in self.detached:
            self.detached[tab].refresh()
        self._refresh_chrome()

    def _on_tab_changed(self):
        self._refresh_chrome()
        tab = self.current_tab()
        if tab:
            self.slist.select(self._name_of(tab))

    def toggle_sidebar(self):
        self.sidebar.setVisible(not self.sidebar.isVisible())

    def _save_sidebar_width(self):
        if self.sidebar.isVisible():
            self.cfg.setValue("ui/sidebar_w", self.sidebar.width())

    def toggle_dashboard_wide(self):
        """대시보드 넓게 보기: 사이드바·'최근 변화'를 숨기고 창 최대화. 다시 누르면 원래대로."""
        if self.is_fullscreen():
            return
        if self._wide is None:
            self._wide = (self.sidebar.isVisible(), self.isMaximized())
            self.sidebar.hide()
            self.dashboard.set_wide(True)
            self.showMaximized()
            self.tabw.setCurrentWidget(self.dashboard)
        else:
            side, maxed = self._wide
            self._wide = None
            self.sidebar.setVisible(side)
            self.dashboard.set_wide(False)
            if not maxed:
                self.showNormal()

    def toggle_view(self):
        tab = self.current_tab()
        if tab and tab.can_toggle_view():
            tab.set_view("actual" if tab.view == "fit" else "fit")

    # ------------------------------------------------------------------ 전체 화면
    def is_fullscreen(self):
        return self._full is not None

    def toggle_fullscreen(self):
        if self._full is None:
            if not self.current_tab():
                return
            self._full = (self.sidebar.isVisible(), self.isMaximized())
            for w in (self.sidebar, self.topbar, self.statusBar(), self.tabw.tabBar()):
                w.hide()
            self.showFullScreen()
            self._refresh_chrome()
            self.fsbar.start()
        else:
            side, maxed = self._full
            self._full = None
            self.fsbar.stop()
            self.sidebar.setVisible(side)
            for w in (self.topbar, self.statusBar(), self.tabw.tabBar()):
                w.show()
            self.showMaximized() if maxed else self.showNormal()
            self._refresh_chrome()
        tab = self.current_tab()
        if tab:
            QTimer.singleShot(300, tab.setFocus)   # 키보드 입력이 바로 원격으로 가도록

    def _step_tab(self, d):
        """원격 화면 탭끼리만 이동 (대시보드는 건너뜀)."""
        idxs = [i for i in range(self.tabw.count()) if isinstance(self.tabw.widget(i), RdpTab)]
        if len(idxs) > 1:
            cur = self.tabw.currentIndex()
            pos = idxs.index(cur) if cur in idxs else 0
            self.tabw.setCurrentIndex(idxs[(pos + d) % len(idxs)])

    def _refresh_chrome(self):
        tab = self.current_tab()
        has = tab is not None
        if not has and self.is_fullscreen():
            self.toggle_fullscreen()   # 마지막 탭을 닫으면 전체 화면도 끝냄
            return
        self.btn_full.setVisible(has)
        group = tab.session.get("group", "") if has else ""
        self.chip_group.setVisible(bool(group))
        self.chip_group.setText(group)
        self.chip_state.setVisible(has)
        self.chip_clip.setVisible(has and bool(tab.session.get("redirect_clipboard", True)))
        self.signal.setVisible(has and tab.state != STATE_IDLE)
        if has:
            self.signal.set_quality(tab.quality)
        self.chip_low.setVisible(has and tab.is_active() and tab.low_bandwidth)
        self.btn_reconnect.setVisible(has and not tab.is_active())
        self.btn_disconnect.setVisible(has and tab.is_active())
        live = has and tab.is_active()
        self.chip_res.setVisible(live)
        self.btn_view.setVisible(live and tab.can_toggle_view())
        if live:
            w, h = tab.remote_size()
            pct = "" if not tab.can_toggle_view() else "  ·  %d%%" % round(tab.scale * 100)
            self.chip_res.setText("%d×%d%s" % (w, h, pct))
            self.btn_view.setText("원본 크기로 보기" if tab.view == "fit" else "창에 맞춰 보기")
            self.btn_view.setIcon(icon("actual" if tab.view == "fit" else "fit"))
            self.btn_view.setToolTip("원본 크기: 스크롤로 이동하며 1:1로 보기\n창에 맞춰: 화면 전체를 줄여서 보기")
        if has:
            color = STATUS_COLOR.get(tab.state, C["idle"])
            self.top_title.setText(tab.session["name"])
            self.chip_state.setText("●  " + tab.state)
            self.chip_state.setStyleSheet("color:%s;" % color)
        else:
            self.top_title.setText("현장 대시보드")
        if has and self.is_fullscreen():
            view = ""
            if tab.is_active() and tab.can_toggle_view():
                view = "원본 크기" if tab.view == "fit" else "화면에 맞춤"
            dot = '<span style="color:%s">●</span>' % STATUS_COLOR.get(tab.state, C["idle"])
            self.fsbar.set_info("%s&nbsp;&nbsp;%s&nbsp;&nbsp;<span style='color:%s'>%s</span>"
                                % (dot, tab.session["name"].replace("<", "&lt;"), C["muted"], tab.state),
                                self._rdp_count(), view)
            self.fsbar.set_quality(tab.quality)

        counts = {}
        for t in self.tabs.values():
            counts[t.state] = counts.get(t.state, 0) + 1
        parts = ["열린 탭 %d" % self._rdp_count()]
        if self.detached:
            parts.append("분리된 창 %d" % len(self.detached))
        for st in (STATE_CONNECTED, STATE_CONNECTING, STATE_RECONNECTING, STATE_DISCONNECTED):
            if counts.get(st):
                parts.append("%s %d" % (st, counts[st]))
        self.statusBar().showMessage("   ·   ".join(parts))
        sel = len(self.slist.selected_names())
        self.multi_btn.setText("선택한 %d개 접속" % sel if sel > 1 else "선택한 세션 접속")
        self.multi_btn.setEnabled(sel > 0)

    def closeEvent(self, e):
        self.fsbar.stop()
        self.dashboard.stop()
        for win in list(self.detached.values()):
            win.close()
        for i in reversed(range(self.tabw.count())):
            self.close_tab_at(i)
        self.hide()                       # 남은 정리는 창이 사라진 뒤에
        finish_release()
        self.log.app("종료")
        self.log.flush()                  # 쓰기 스레드에 남은 기록까지 디스크에 확정
        super().closeEvent(e)
