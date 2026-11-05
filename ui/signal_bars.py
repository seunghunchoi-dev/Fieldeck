"""안테나 막대(신호 세기) 표시 — 휴대폰 안테나처럼 4칸.

4칸 초록(매우 좋음) · 3칸 초록(좋음) · 2칸 노랑(보통) · 1칸 빨강(나쁨) · 0칸 빨강 ✕(끊김) · 회색(측정 중)
"""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from core.net_quality import describe
from ui.theme import C


def bar_color(bars):
    return {4: C["ok"], 3: C["ok"], 2: C["warn"], 1: C["err"], 0: C["err"]}.get(bars, C["idle"])


_cache = {}


def bars_pixmap(bars, size=16, scale=2):
    """막대 4개짜리 그림. bars=-1이면 전부 회색(측정 중). 같은 모양은 한 번만 그린다 (카드·탭이 자주 갱신됨)."""
    key = (bars, size, scale)
    if key not in _cache:
        _cache[key] = _draw_bars(bars, size, scale)
    return _cache[key]


def _draw_bars(bars, size, scale):
    px = int(size * scale)
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(px / 16.0, px / 16.0)
    on, off = QColor(bar_color(bars)), QColor(C["border"])
    if bars < 0:
        on = off = QColor(C["idle"])
    p.setPen(Qt.PenStyle.NoPen)
    w, gap = 2.6, 1.3
    for i in range(4):
        h = 4 + i * 3.4
        x = 1 + i * (w + gap)
        p.setBrush(on if i < bars else off)
        p.drawRoundedRect(QRectF(x, 15 - h, w, h), 0.9, 0.9)
    if bars == 0:   # 끊김 표시
        pen = QPen(QColor(C["err"]), 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QRectF(1, 1, 5, 5).topLeft(), QRectF(1, 1, 5, 5).bottomRight())
        p.drawLine(QRectF(1, 1, 5, 5).topRight(), QRectF(1, 1, 5, 5).bottomLeft())
    p.end()
    pm.setDevicePixelRatio(scale)
    return pm


_icon_cache = {}


def bars_icon(bars, size=16):
    key = (bars, size)
    if key not in _icon_cache:
        _icon_cache[key] = QIcon(bars_pixmap(bars, size))
    return _icon_cache[key]


class SignalBars(QWidget):
    """막대 + 응답 시간 글자. 툴팁에 자세한 값."""

    def __init__(self, show_text=True, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setFixedHeight(24)
        h = QHBoxLayout(self)
        h.setContentsMargins(8, 0, 8, 0)
        h.setSpacing(5)
        self._ico = QLabel()
        self._txt = QLabel()
        self._txt.setObjectName("signalText")
        self._txt.setVisible(show_text)
        h.addWidget(self._ico)
        h.addWidget(self._txt)
        self.setObjectName("signal")
        self.set_quality({"bars": -1, "rtt": None, "jitter": None, "loss": 0.0, "label": "측정 중"})

    def set_quality(self, q):
        self._ico.setPixmap(bars_pixmap(q["bars"], 16))
        if q["bars"] < 0:
            txt = "측정 중"
        elif q.get("rtt") is None or q["bars"] == 0:
            txt = "응답 없음"
        else:
            txt = "%dms" % round(q["rtt"])
        self._txt.setText(txt)
        self._txt.setStyleSheet("color:%s;" % (bar_color(q["bars"]) if q["bars"] >= 0 else C["muted"]))
        tip = "네트워크 신호\n" + describe(q)
        self.setToolTip(tip)
