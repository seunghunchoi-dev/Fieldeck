"""Fieldeck 앱 아이콘 — 코드로 그려서 어떤 크기에서도 선명하게.

디자인: 보라→파랑 그라데이션 둥근 사각형 위에 겹친 모니터 2대(= 다중 원격 접속).
- 런타임: app_icon() → QIcon (창 제목줄·작업 표시줄)
- 파일: tools/make_icon.py 가 assets/app.ico, assets/app.png 생성 (바로가기용)
"""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QLinearGradient, QPainter, QPixmap

SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def render(size):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 256.0, size / 256.0)
    p.setPen(Qt.PenStyle.NoPen)
    small = size <= 24

    # 배경
    g = QLinearGradient(QPointF(0, 0), QPointF(256, 256))
    g.setColorAt(0.0, QColor("#8B6CFF"))
    g.setColorAt(1.0, QColor("#3B82F6"))
    p.setBrush(QBrush(g))
    pad = 4 if small else 8
    p.drawRoundedRect(QRectF(pad, pad, 256 - 2 * pad, 256 - 2 * pad), 58, 58)

    # 뒤 모니터 (반투명)
    back = QColor(255, 255, 255, 105)
    p.setBrush(back)
    p.drawRoundedRect(QRectF(92, 50, 124, 86), 16, 16)

    # 앞 모니터
    p.setBrush(QColor("white"))
    p.drawRoundedRect(QRectF(40, 88, 148, 102), 18, 18)
    p.setBrush(QColor("#1B1F2C"))
    p.drawRoundedRect(QRectF(54, 102, 120, 72), 9, 9)
    if not small:
        # 화면 속 원격 창 느낌의 선
        p.setBrush(QColor("#7C5CFF"))
        p.drawRoundedRect(QRectF(66, 114, 52, 10), 5, 5)
        p.setBrush(QColor("#38BDF8"))
        p.drawRoundedRect(QRectF(66, 132, 84, 10), 5, 5)
        p.setBrush(QColor("#22C55E"))
        p.drawEllipse(QRectF(150, 150, 14, 14))
    # 받침
    p.setBrush(QColor("white"))
    p.drawRoundedRect(QRectF(100, 190, 28, 18), 4, 4)
    p.drawRoundedRect(QRectF(76, 204, 76, 14), 7, 7)
    p.end()
    return pm


def app_icon():
    icon = QIcon()
    for s in SIZES:
        icon.addPixmap(render(s))
    return icon
