"""접속 이력 창 — 로그 파일의 '접속' 기록을 표로 보여준다 (읽기 전용).

기록은 로그 파일에 있으므로 프로그램을 껐다 켜도 그대로 나온다. 검색은 전체 로그를 대상으로 한다.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from core.conn_log import KIND_SESSION
from ui.theme import C, STATUS_COLOR, timer

LIMIT = 2000             # 한 번에 보여줄 최대 줄 수 (최신순)
STATES = ["연결됨", "끊김", "재연결 대기", "연결 중", "탭 닫음"]
COLUMNS = ["시각", "장비", "주소", "상태", "상세"]


def load_entries(log, text="", state=""):
    """접속 기록을 최신순으로. text는 장비 이름·주소에서 찾고(대소문자 무시), state는 상태가 같은 줄만."""
    text = text.strip().lower()

    def match(e):
        if state and e["event"] != state:
            return False
        return not text or text in e["name"].lower() or text in e["addr"].lower()

    return log.recent(LIMIT, KIND_SESSION, where=match)


class HistoryDialog(QDialog):
    def __init__(self, parent, log):
        super().__init__(parent)
        self.log = log
        self.setWindowTitle("접속 이력")
        self.resize(900, 600)
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 22, 24, 20)
        v.setSpacing(10)

        title = QLabel("접속 이력")
        title.setObjectName("heroTitle")
        title.setStyleSheet("font-size:17px;")
        v.addWidget(title)
        self.summary = QLabel()
        self.summary.setObjectName("heroSub")
        v.addWidget(self.summary)

        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("장비 이름이나 주소로 찾기")
        self.search.setClearButtonEnabled(True)
        self.state_box = QComboBox()
        self.state_box.addItem("모든 상태", "")
        for s in STATES:
            self.state_box.addItem(s, s)
        refresh = QPushButton("새로고침")
        row.addWidget(self.search, 1)
        row.addWidget(self.state_box)
        row.addWidget(refresh)
        v.addLayout(row)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setObjectName("historyTable")
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        head = self.table.horizontalHeader()
        for i in range(len(COLUMNS) - 1):
            head.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        head.setStretchLastSection(True)
        v.addWidget(self.table, 1)

        close = QPushButton("닫기")
        close.setObjectName("primary")
        close.clicked.connect(self.accept)
        foot = QHBoxLayout()
        foot.addStretch(1)
        foot.addWidget(close)
        v.addLayout(foot)

        self._search_timer = timer(self, 250, self.reload, single=True)   # 글자마다 파일을 읽지 않게
        self.search.textChanged.connect(lambda _: self._search_timer.start())
        self.state_box.currentIndexChanged.connect(lambda _: self.reload())
        refresh.clicked.connect(self.reload)
        self.reload()

    def reload(self):
        entries = load_entries(self.log, self.search.text(), self.state_box.currentData() or "")
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(entries))
        for r, e in enumerate(entries):
            for c, text in enumerate((e["time"], e["name"], e["addr"], e["event"], e["detail"])):
                item = QTableWidgetItem(text)
                if c == 3:
                    item.setForeground(QColor(STATUS_COLOR.get(text, C["muted"])))
                self.table.setItem(r, c, item)
        self.table.setUpdatesEnabled(True)
        if not entries:
            self.summary.setText("조건에 맞는 접속 기록이 없습니다.")
        elif len(entries) >= LIMIT:
            self.summary.setText("최근 %d건만 표시합니다. 더 오래된 기록은 검색하거나 로그 폴더에서 볼 수 있습니다." % LIMIT)
        else:
            self.summary.setText("%d건 (가장 오래된 기록 %s)" % (len(entries), entries[-1]["time"]))
