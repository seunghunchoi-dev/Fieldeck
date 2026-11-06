"""디자인 토큰 + 스타일시트. 색을 바꾸려면 C 딕셔너리만 수정한다."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPixmap, QShortcut


# ---- PySide6 도우미 (생성자에서 시그널을 바로 연결하는 문법 대신) ----
def shortcut(key, parent, slot):
    """단축키 만들고 연결. 반환값을 보관하지 않아도 parent가 소유한다."""
    sc = QShortcut(key, parent)
    sc.activated.connect(slot)
    return sc


def timer(parent, ms, slot, single=False):
    t = QTimer(parent)
    t.setInterval(ms)
    t.setSingleShot(single)
    t.timeout.connect(slot)
    return t

C = {
    "bg": "#0E1016",
    "sidebar": "#141722",
    "surface": "#1B1F2C",
    "surface_hi": "#232838",
    "border": "#2A3042",
    "text": "#E7E9F0",
    "muted": "#8B92A6",
    "accent": "#7C5CFF",
    "accent_hi": "#9479FF",
    "ok": "#22C55E",
    "warn": "#F5A524",
    "err": "#F04452",
    "idle": "#5B6275",
}

STATUS_COLOR = {"대기": C["idle"], "연결 중": C["warn"], "연결됨": C["ok"], "끊김": C["err"],
                "재연결 대기": C["warn"]}

# 그룹 색 — 그룹 이름으로 자동 배정 (같은 이름은 항상 같은 색). 상태색(초록/노랑/빨강)과 겹치지 않게 고름.
GROUP_COLORS = ["#7C5CFF", "#38BDF8", "#F472B6", "#2DD4BF", "#A78BFA", "#FB923C",
                "#60A5FA", "#E879F9", "#34D399", "#FBBF24"]


def group_color(name):
    if not name:
        return C["idle"]
    import zlib
    return GROUP_COLORS[zlib.crc32(name.encode("utf-8")) % len(GROUP_COLORS)]


def relative_time(ts):
    import time
    if not ts:
        return ""
    d = int(time.time() - ts)
    if d < 60:
        return "방금"
    if d < 3600:
        return "%d분 전" % (d // 60)
    if d < 86400:
        return "%d시간 전" % (d // 3600)
    if d < 86400 * 30:
        return "%d일 전" % (d // 86400)
    return time.strftime("%Y.%m.%d", time.localtime(ts))


def pick_font():
    fams = set(QFontDatabase.families())
    for name in ("Pretendard", "Pretendard Variable", "Malgun Gothic", "Segoe UI"):
        if name in fams:
            f = QFont(name, 10)
            f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
            return f
    return QFont()


_dot_cache = {}


def dot_icon(color, size=10):
    """상태 점 아이콘 (색·크기별로 한 번만 그림)."""
    key = (color, size)
    if key not in _dot_cache:
        _dot_cache[key] = _draw_dot(color, size)
    return _dot_cache[key]


def _draw_dot(color, size):
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(size // 2, size // 2, size, size)
    p.end()
    return QIcon(pm)


QSS = """
* {{ color: {text}; outline: none; }}
QMainWindow, QWidget#root {{ background: {bg}; }}
QToolTip {{ background: {surface_hi}; color: {text}; border: 1px solid {border}; padding: 6px 8px; border-radius: 6px; }}

/* 사이드바 */
QFrame#sidebar {{ background: {sidebar}; border-right: 1px solid {border}; }}
QSplitter#root::handle {{ background: {bg}; }}
QSplitter#root::handle:hover {{ background: {accent}; }}
QLabel#brand {{ font-size: 17px; font-weight: 700; }}
QLabel#brandSub {{ color: {muted}; font-size: 11px; }}
QLabel#section {{ color: {muted}; font-size: 11px; font-weight: 600; letter-spacing: 1px; }}
QLabel#userBadge {{ color: {muted}; font-size: 11px; }}

QLineEdit {{
    background: {surface}; border: 1px solid {border}; border-radius: 10px;
    padding: 9px 12px; selection-background-color: {accent};
}}
QLineEdit:focus {{ border: 1px solid {accent}; }}
QSpinBox {{
    background: {surface}; border: 1px solid {border}; border-radius: 10px; padding: 8px 10px;
}}
QSpinBox:focus {{ border: 1px solid {accent}; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}
QComboBox {{
    background: {surface}; border: 1px solid {border}; border-radius: 10px; padding: 8px 12px;
}}
QComboBox:focus {{ border: 1px solid {accent}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {surface}; border: 1px solid {border}; selection-background-color: {surface_hi}; padding: 4px;
}}

QPushButton {{
    background: {surface_hi}; border: 1px solid {border}; border-radius: 10px;
    padding: 9px 14px; font-weight: 600;
}}
QPushButton:hover {{ background: {border}; }}
QPushButton:disabled {{ color: {muted}; background: {surface}; }}
QPushButton#primary {{ background: {accent}; border: none; color: white; }}
QPushButton#primary:hover {{ background: {accent_hi}; }}
QPushButton#danger {{ background: transparent; border: 1px solid {err}; color: {err}; }}
QPushButton#ghost {{ background: transparent; border: none; color: {muted}; padding: 6px 10px; }}
QPushButton#ghost:hover {{ color: {text}; background: {surface_hi}; }}

/* 세션 목록 */
QListWidget#sessions {{ background: transparent; border: none; }}
QListWidget#sessions::item {{ border-radius: 12px; margin: 2px 0; }}
QListWidget#sessions::item:hover {{ background: {surface}; }}
QListWidget#sessions::item:selected {{ background: {surface_hi}; }}
QLabel#cardTitle {{ font-size: 13px; font-weight: 600; background: transparent; }}
QLabel#cardSub {{ color: {muted}; font-size: 11px; background: transparent; }}
QLabel#groupName {{ font-size: 12px; font-weight: 700; background: transparent; }}
QLabel#groupCount {{ color: {muted}; font-size: 11px; background: transparent; }}
QLabel#chev {{ color: {muted}; font-size: 10px; background: transparent; }}

/* 세그먼트(필터) 버튼 */
QPushButton#seg {{
    background: transparent; border: none; border-radius: 8px; padding: 6px 10px;
    color: {muted}; font-weight: 600; font-size: 12px;
}}
QPushButton#seg:hover {{ color: {text}; }}
QPushButton#seg:checked {{ background: {surface_hi}; color: {text}; }}
QFrame#segWrap {{ background: {surface}; border: 1px solid {border}; border-radius: 10px; }}
QPushButton#icon {{
    background: transparent; border: none; border-radius: 8px; padding: 4px 8px; color: {muted};
    font-size: 11px; font-weight: 600;
}}
QPushButton#icon:hover {{ background: {surface_hi}; color: {text}; }}
QPushButton#icon:checked {{ color: {accent_hi}; }}

/* 탭 */
QTabWidget::pane {{ border: none; background: {bg}; }}
QTabBar {{ background: {bg}; }}
QTabBar::tab {{
    background: transparent; color: {muted}; padding: 9px 14px; margin: 6px 2px 0 2px;
    border-top-left-radius: 10px; border-top-right-radius: 10px; min-width: 120px;
}}
QTabBar::tab:hover {{ color: {text}; background: {sidebar}; }}
QTabBar::tab:selected {{ color: {text}; background: {surface}; }}
QTabBar::close-button {{ subcontrol-position: right; }}

QWidget#rdpHolder {{ background: #07080C; }}
QScrollArea {{ background: #07080C; border: none; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {border}; border-radius: 4px; min-width: 30px; }}

/* 상단 바 / 상태 바 */
QFrame#topbar {{ background: {surface}; border-bottom: 1px solid {border}; }}
QLabel#topTitle {{ font-size: 13px; font-weight: 600; }}
QLabel#chip {{
    background: {surface_hi}; color: {muted}; border-radius: 9px; padding: 3px 9px; font-size: 11px;
}}
QStatusBar {{ background: {sidebar}; color: {muted}; border-top: 1px solid {border}; }}

/* 빈 화면 / 메시지 */
QLabel#heroTitle {{ font-size: 22px; font-weight: 700; }}
QLabel#heroSub {{ color: {muted}; font-size: 13px; }}
QLabel#kbd {{
    background: {surface}; border: 1px solid {border}; border-radius: 6px;
    padding: 3px 8px; color: {muted}; font-size: 11px;
}}

/* 대화상자 */
QDialog {{ background: {sidebar}; }}
QLabel#fieldLabel {{ color: {muted}; font-size: 11px; font-weight: 600; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1px solid {border}; background: {surface}; }}
QCheckBox::indicator:checked {{ background: {accent}; border: 1px solid {accent}; }}

QMenu {{ background: {surface}; border: 1px solid {border}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 8px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {surface_hi}; }}
QMenu::separator {{ height: 1px; background: {border}; margin: 4px 8px; }}

QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {border}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QMessageBox {{ background: {sidebar}; }}

/* 신호 세기 (안테나 막대) */
QWidget#signal {{ background: {surface_hi}; border-radius: 9px; }}
QLabel#signalText {{ font-size: 11px; font-weight: 600; background: transparent; }}
QLabel#chipWarn {{
    background: rgba(245, 165, 36, 0.15); color: {warn}; border-radius: 9px; padding: 3px 9px; font-size: 11px;
}}

/* 현장 대시보드 */
QWidget#dashboard, QWidget#dashBody {{ background: {bg}; }}
QPushButton#kpi {{
    background: {surface}; border: 1px solid {border}; border-radius: 14px; padding: 0; text-align: left;
}}
QPushButton#kpi:hover {{ background: {surface_hi}; }}
QPushButton#kpi:checked {{ border: 1px solid {accent}; background: {surface_hi}; }}
QLabel#kpiNum {{ font-size: 24px; font-weight: 800; background: transparent; }}
QLabel#kpiLabel {{ color: {muted}; font-size: 12px; font-weight: 600; background: transparent; }}
QFrame#devCard {{ background: {surface}; border: 1px solid {border}; border-radius: 12px; }}
QFrame#devCard:hover {{ background: {surface_hi}; }}
QLabel#devStatus {{ font-size: 12px; font-weight: 600; }}
QLabel#cardAddr {{ color: {text}; font-size: 12px; background: transparent; }}
QLabel#flowChip {{
    color: {muted}; border: 1px solid {border}; border-radius: 7px; padding: 0px 6px;
    font-size: 10px; font-weight: 600; background: transparent;
}}
QPushButton#toggle {{
    background: transparent; border: 1px solid {border}; border-radius: 8px; color: {muted}; padding: 5px 10px;
}}
QPushButton#toggle:hover {{ color: {text}; background: {surface_hi}; }}
QPushButton#toggle:checked {{ color: {accent_hi}; border: 1px solid {accent}; background: {surface_hi}; }}
QLabel#devBadge {{
    background: rgba(124, 92, 255, 0.18); color: {accent_hi}; border-radius: 8px; padding: 2px 8px;
    font-size: 11px; font-weight: 600;
}}
QPushButton#devConnect {{
    background: {accent}; border: none; border-radius: 8px; padding: 5px 12px; color: white; font-size: 12px;
}}
QPushButton#devConnect:hover {{ background: {accent_hi}; }}
QFrame#eventPanel {{ background: {surface}; border: 1px solid {border}; border-radius: 14px; }}
QListWidget#events {{ background: transparent; border: none; font-size: 12px; }}
QListWidget#events::item {{ padding: 6px 4px; border-bottom: 1px solid {border}; }}
QTableWidget#historyTable {{
    background: {surface}; color: {text}; border: 1px solid {border}; border-radius: 10px; font-size: 12px;
    selection-background-color: {surface_hi}; selection-color: {text};
}}
QTableWidget#historyTable::item {{ padding: 4px 8px; border-bottom: 1px solid {border}; }}
QTableWidget#historyTable QHeaderView::section {{
    background: {surface_hi}; color: {muted}; border: none; padding: 6px 8px; font-size: 12px;
}}

/* 분리 창 끌어서 합치기 표시 */
QLabel#dropHint {{
    background: rgba(124, 92, 255, 0.22); border: 2px dashed {accent_hi}; border-radius: 12px;
    color: {text}; font-size: 14px; font-weight: 700;
}}

/* 전체 화면 상단 막대 */
QFrame#fsBar {{
    background: {surface}; border: 1px solid {border}; border-top: none;
    border-bottom-left-radius: 12px; border-bottom-right-radius: 12px;
}}
QLabel#fsTitle {{ font-size: 13px; font-weight: 600; padding: 0 10px; }}
QPushButton#fsBtn {{
    background: transparent; border: none; border-radius: 8px; padding: 6px 10px;
    color: {muted}; font-weight: 600;
}}
QPushButton#fsBtn:hover {{ background: {surface_hi}; color: {text}; }}
QPushButton#fsBtn:checked {{ color: {accent_hi}; background: {surface_hi}; }}
QPushButton#fsExit {{
    background: {accent}; border: none; border-radius: 8px; padding: 6px 12px; color: white; font-weight: 600;
}}
QPushButton#fsExit:hover {{ background: {accent_hi}; }}
""".format(**C)
