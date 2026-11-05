"""세션 추가/편집 대화상자."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QGridLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QSpinBox, QVBoxLayout)

from ui.icons import icon

RESOLUTIONS = [
    ("자동 축소 (권장 · 모니터 해상도로 접속, 창에 맞춰 줄여 보기)", "auto"),
    ("창 크기에 맞춤 (원격 해상도가 창 크기를 따라감 · 글자 선명)", "fit"),
    ("1920 × 1080 고정 (창에 맞춰 줄여 보기)", "1920x1080"),
    ("2560 × 1440 고정", "2560x1440"),
    ("1600 × 900 고정", "1600x900"),
    ("1280 × 720 고정", "1280x720"),
]


def _label(text):
    lb = QLabel(text)
    lb.setObjectName("fieldLabel")
    return lb


class SessionDialog(QDialog):
    def __init__(self, parent=None, session=None, existing_names=(), groups=(), default_group=""):
        super().__init__(parent)
        self._editing = session is not None
        self._orig_name = session["name"] if session else None
        self._existing = set(existing_names) - {self._orig_name}
        s = session or {}

        self.setWindowTitle("세션 편집" if self._editing else "새 세션")
        self.setMinimumWidth(520)

        title = QLabel("세션 편집" if self._editing else "새 세션 추가")
        title.setObjectName("heroTitle")
        sub = QLabel("원격 PC 접속 정보는 이 Windows 계정으로만 열 수 있게 암호화되어 저장됩니다.")
        sub.setObjectName("heroSub")
        sub.setWordWrap(True)

        self.name = QLineEdit(s.get("name", ""))
        self.name.setPlaceholderText("예: 금강 관제서버")
        self.host = QLineEdit(s.get("host", ""))
        self.host.setPlaceholderText("IP 또는 컴퓨터 이름")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(int(s.get("rdp_port", 3389)))
        self.user = QLineEdit(s.get("rdp_user", ""))
        self.user.setPlaceholderText("계정")
        self.pw = QLineEdit(s.get("rdp_password", ""))
        self.pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw.setPlaceholderText("비우면 접속 시 입력")
        self.pw.setToolTip("비워두면 접속할 때 원격 로그인 화면에서 직접 입력합니다")
        eye = QAction(icon("eye", size=16), "비밀번호 보기", self.pw)
        eye.triggered.connect(self._toggle_pw)
        self.pw.addAction(eye, QLineEdit.ActionPosition.TrailingPosition)
        self.clip = QCheckBox("클립보드 공유 (텍스트·파일 복사/붙여넣기)")
        self.clip.setChecked(bool(s.get("redirect_clipboard", True)))
        self.res = QComboBox()
        for label, val in RESOLUTIONS:
            self.res.addItem(label, val)
        idx = self.res.findData(s.get("resolution", "auto"))
        self.res.setCurrentIndex(idx if idx >= 0 else 0)
        self.note = QLineEdit(s.get("note", ""))
        self.note.setPlaceholderText("메모 (선택)")
        self.group = QComboBox()
        self.group.setEditable(True)
        self.group.addItem("")
        self.group.addItems(list(groups))
        self.group.setCurrentText(s.get("group", "") or default_group)
        self.group.lineEdit().setPlaceholderText("예: 금강 (새 이름을 입력하면 새 그룹)")
        self.fav = QCheckBox("즐겨찾기 (목록 맨 위에 표시)")
        self.fav.setChecked(bool(s.get("favorite", False)))

        g = QGridLayout()
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(6)
        g.addWidget(_label("이름"), 0, 0)
        g.addWidget(_label("그룹"), 0, 1)
        g.addWidget(self.name, 1, 0)
        g.addWidget(self.group, 1, 1)
        g.addWidget(_label("주소"), 2, 0)
        g.addWidget(_label("포트"), 2, 1)
        g.addWidget(self.host, 3, 0)
        g.addWidget(self.port, 3, 1)
        g.addWidget(_label("계정"), 4, 0)
        g.addWidget(_label("비밀번호"), 4, 1)
        g.addWidget(self.user, 5, 0)
        g.addWidget(self.pw, 5, 1)
        g.addWidget(_label("화면 해상도"), 6, 0, 1, 2)
        g.addWidget(self.res, 7, 0, 1, 2)
        g.addWidget(_label("메모"), 8, 0, 1, 2)
        g.addWidget(self.note, 9, 0, 1, 2)
        g.setColumnStretch(0, 3)
        g.setColumnStretch(1, 2)

        self.err = QLabel("")
        self.err.setStyleSheet("color:#F04452; font-size:12px;")

        cancel = QPushButton("취소")
        cancel.setObjectName("ghost")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("저장")
        ok.setObjectName("primary")
        ok.setDefault(True)
        ok.clicked.connect(self._accept)
        for b in (cancel, ok):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        btns = QHBoxLayout()
        btns.addWidget(self.err, 1)
        btns.addWidget(cancel)
        btns.addWidget(ok)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 22)
        root.setSpacing(10)
        root.addWidget(title)
        root.addWidget(sub)
        root.addSpacing(8)
        root.addLayout(g)
        root.addSpacing(4)
        root.addWidget(self.fav)
        root.addWidget(self.clip)
        root.addSpacing(10)
        root.addLayout(btns)

        self._base = dict(s)

    def _toggle_pw(self):
        normal = self.pw.echoMode() == QLineEdit.EchoMode.Normal
        self.pw.setEchoMode(QLineEdit.EchoMode.Password if normal else QLineEdit.EchoMode.Normal)

    def _accept(self):
        name, host = self.name.text().strip(), self.host.text().strip()
        if not name or not host:
            self.err.setText("이름과 주소는 꼭 입력해 주세요.")
            return
        if name in self._existing:
            self.err.setText("같은 이름의 세션이 이미 있어요.")
            return
        self.accept()

    def result_session(self):
        s = dict(self._base)
        s.update({
            "name": self.name.text().strip(),
            "host": self.host.text().strip(),
            "rdp_port": self.port.value(),
            "rdp_user": self.user.text().strip(),
            "rdp_password": self.pw.text(),
            "redirect_clipboard": self.clip.isChecked(),
            "resolution": self.res.currentData(),
            "group": self.group.currentText().strip(),
            "favorite": self.fav.isChecked(),
            "note": self.note.text().strip(),
        })
        return s
