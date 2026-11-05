"""버튼·메뉴용 선 아이콘 모음 (외부 파일·라이브러리 없이 코드로 그림).

사용: icon("plus"), icon("power", C["err"]), icon("menu", size=20)
- 24×24 좌표계에 그린 뒤 크기에 맞춰 확대/축소, 고해상도 화면용으로 2배로 그린다.
- 새 아이콘은 _DRAW에 함수 하나 추가하면 된다 (p = QPainter, 선 굵기·색은 이미 설정됨).
"""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

from ui.theme import C

_cache = {}


def _poly(p, *pts, close=False):
    path = QPainterPath(QPointF(*pts[0]))
    for x, y in pts[1:]:
        path.lineTo(x, y)
    if close:
        path.closeSubpath()
    p.drawPath(path)


def _menu(p):
    for y in (6, 12, 18):
        p.drawLine(QPointF(4, y), QPointF(20, y))


def _plus(p):
    p.drawLine(QPointF(12, 5), QPointF(12, 19))
    p.drawLine(QPointF(5, 12), QPointF(19, 12))


def _search(p):
    p.drawEllipse(QPointF(10.5, 10.5), 6, 6)
    p.drawLine(QPointF(15, 15), QPointF(20, 20))


def _expand(p):          # 전체 화면
    _poly(p, (4, 9), (4, 4), (9, 4))
    _poly(p, (15, 4), (20, 4), (20, 9))
    _poly(p, (20, 15), (20, 20), (15, 20))
    _poly(p, (9, 20), (4, 20), (4, 15))


def _shrink(p):          # 전체 화면 끝내기
    _poly(p, (9, 4), (9, 9), (4, 9))
    _poly(p, (15, 4), (15, 9), (20, 9))
    _poly(p, (20, 15), (15, 15), (15, 20))
    _poly(p, (9, 20), (9, 15), (4, 15))


def _actual(p):          # 원본 크기 (1:1 돋보기)
    p.drawEllipse(QPointF(10.5, 10.5), 6.5, 6.5)
    p.drawLine(QPointF(15.5, 15.5), QPointF(20, 20))
    p.drawLine(QPointF(10.5, 7.5), QPointF(10.5, 13.5))
    p.drawLine(QPointF(7.5, 10.5), QPointF(13.5, 10.5))


def _fit(p):             # 창에 맞춤 (화면 안쪽으로 모이는 화살표)
    p.drawRoundedRect(QRectF(3, 5, 18, 14), 2.5, 2.5)
    p.drawRoundedRect(QRectF(8, 9, 8, 6), 1.2, 1.2)


def _refresh(p):
    path = QPainterPath()
    path.arcMoveTo(QRectF(5, 5, 14, 14), 60)
    path.arcTo(QRectF(5, 5, 14, 14), 60, 280)
    p.drawPath(path)
    _poly(p, (15.5, 3.5), (15.5, 6.9), (19, 7))


def _power(p):
    path = QPainterPath()
    path.arcMoveTo(QRectF(5, 5.5, 14, 14), 125)
    path.arcTo(QRectF(5, 5.5, 14, 14), 125, 290)
    p.drawPath(path)
    p.drawLine(QPointF(12, 3.5), QPointF(12, 11))


def _dock(p):            # 탭으로 합치기 (창 안으로 들어가는 화살표)
    p.drawRoundedRect(QRectF(9, 4, 12, 16), 2.5, 2.5)
    p.drawLine(QPointF(3, 12), QPointF(14, 12))
    _poly(p, (11, 9), (14, 12), (11, 15))


def _detach(p):          # 새 창으로 분리 (밖으로 나가는 화살표)
    _poly(p, (11, 5), (6, 5), (4, 7), (4, 18), (6, 20), (17, 20), (19, 18), (19, 13))
    p.drawLine(QPointF(11, 13), QPointF(20, 4))
    _poly(p, (14, 4), (20, 4), (20, 10))


def _pin(p):
    _poly(p, (9, 4), (15, 4))
    _poly(p, (10, 4), (10, 10), (7, 14), (17, 14), (14, 10), (14, 4))
    p.drawLine(QPointF(12, 14), QPointF(12, 20))


def _chev_left(p):
    _poly(p, (15, 5), (8, 12), (15, 19))


def _chev_right(p):
    _poly(p, (9, 5), (16, 12), (9, 19))


def _minus(p):
    p.drawLine(QPointF(6, 12), QPointF(18, 12))


def _close(p):
    p.drawLine(QPointF(6, 6), QPointF(18, 18))
    p.drawLine(QPointF(18, 6), QPointF(6, 18))


def _clipboard(p):
    p.drawRoundedRect(QRectF(5, 5, 14, 16), 2.5, 2.5)
    p.drawRoundedRect(QRectF(9, 3, 6, 4), 1.2, 1.2)
    p.drawLine(QPointF(9, 12), QPointF(15, 12))
    p.drawLine(QPointF(9, 16), QPointF(13, 16))


def _monitor(p):         # 접속
    p.drawRoundedRect(QRectF(3, 4, 18, 12), 2, 2)
    p.drawLine(QPointF(12, 16), QPointF(12, 20))
    p.drawLine(QPointF(8, 20), QPointF(16, 20))


def _monitors(p):        # 여러 개 접속
    p.drawRoundedRect(QRectF(7, 3, 14, 10), 2, 2)
    p.drawRoundedRect(QRectF(3, 8, 14, 10), 2, 2)
    p.drawLine(QPointF(10, 18), QPointF(10, 21))
    p.drawLine(QPointF(7, 21), QPointF(13, 21))


def _star(p):
    import math
    pts = []
    for i in range(10):
        r = 8.5 if i % 2 == 0 else 3.8
        a = math.radians(-90 + i * 36)
        pts.append(QPointF(12 + r * math.cos(a), 12.6 + r * math.sin(a)))
    p.drawPolygon(QPolygonF(pts))


def _edit(p):
    _poly(p, (15, 5), (19, 9), (9, 19), (5, 19), (5, 15), close=True)
    p.drawLine(QPointF(13, 7), QPointF(17, 11))


def _copy(p):
    p.drawRoundedRect(QRectF(8, 8, 12, 12), 2.5, 2.5)
    _poly(p, (16, 8), (16, 6), (14, 4), (6, 4), (4, 6), (4, 14), (6, 16), (8, 16))


def _trash(p):
    p.drawLine(QPointF(4, 7), QPointF(20, 7))
    _poly(p, (9, 7), (9, 4), (15, 4), (15, 7))
    _poly(p, (6, 7), (7, 20), (17, 20), (18, 7))
    p.drawLine(QPointF(10, 11), QPointF(10, 16))
    p.drawLine(QPointF(14, 11), QPointF(14, 16))


def _folder(p):
    _poly(p, (3, 7), (3, 18), (5, 20), (19, 20), (21, 18), (21, 10), (19, 8), (12, 8), (10, 5), (5, 5), (3, 7),
          close=True)


def _folder_plus(p):
    _folder(p)
    p.drawLine(QPointF(12, 11), QPointF(12, 17))
    p.drawLine(QPointF(9, 14), QPointF(15, 14))


def _tag(p):             # 그룹 이름
    _poly(p, (4, 4), (12, 4), (20, 12), (12, 20), (4, 12), close=True)
    p.drawEllipse(QPointF(8.5, 8.5), 1.3, 1.3)


def _collapse(p):
    _poly(p, (7, 9), (12, 4), (17, 9))
    _poly(p, (7, 15), (12, 20), (17, 15))
    p.drawLine(QPointF(5, 12), QPointF(19, 12))


def _expand_all(p):
    _poly(p, (7, 8), (12, 3), (17, 8))
    _poly(p, (7, 16), (12, 21), (17, 16))


def _sort(p):
    p.drawLine(QPointF(7, 4), QPointF(7, 20))
    _poly(p, (4, 7), (7, 4), (10, 7))
    p.drawLine(QPointF(17, 4), QPointF(17, 20))
    _poly(p, (14, 17), (17, 20), (20, 17))


def _rows(p):            # 간단히 보기
    for y in (5, 10, 15, 20):
        p.drawLine(QPointF(4, y - 1), QPointF(20, y - 1))


def _user(p):
    p.drawEllipse(QPointF(12, 8.5), 4, 4)
    path = QPainterPath(QPointF(4.5, 20))
    path.cubicTo(5.5, 14, 18.5, 14, 19.5, 20)
    p.drawPath(path)


def _eye(p):
    path = QPainterPath(QPointF(2.5, 12))
    path.cubicTo(7, 4.5, 17, 4.5, 21.5, 12)
    path.cubicTo(17, 19.5, 7, 19.5, 2.5, 12)
    p.drawPath(path)
    p.drawEllipse(QPointF(12, 12), 3, 3)


def _shield(p):          # 보안(DPAPI)
    _poly(p, (12, 3), (19, 6), (19, 12), (12, 21), (5, 12), (5, 6), close=True)
    _poly(p, (9, 12), (11, 14), (15, 10))


def _download(p):       # 백업 (내려받기)
    p.drawLine(QPointF(12, 4), QPointF(12, 15))
    _poly(p, (7.5, 10.5), (12, 15), (16.5, 10.5))
    _poly(p, (4, 15), (4, 19), (6, 21), (18, 21), (20, 19), (20, 15))


def _upload(p):         # 복원 (불러오기)
    p.drawLine(QPointF(12, 15), QPointF(12, 4))
    _poly(p, (7.5, 8.5), (12, 4), (16.5, 8.5))
    _poly(p, (4, 15), (4, 19), (6, 21), (18, 21), (20, 19), (20, 15))


def _more(p):           # ⋯ 메뉴
    for x in (6, 12, 18):
        p.drawEllipse(QPointF(x, 12), 1.1, 1.1)


def _grid(p):           # 대시보드
    for x, y in ((4, 4), (13, 4), (4, 13), (13, 13)):
        p.drawRoundedRect(QRectF(x, y, 7, 7), 1.6, 1.6)


def _pulse(p):          # 상태 확인
    _poly(p, (3, 12), (7, 12), (9.5, 6), (13.5, 18), (16, 12), (21, 12))


_DRAW = {
    "download": _download, "upload": _upload, "more": _more, "grid": _grid, "pulse": _pulse,
    "menu": _menu, "plus": _plus, "search": _search, "expand": _expand, "shrink": _shrink,
    "actual": _actual, "fit": _fit, "refresh": _refresh, "power": _power, "dock": _dock,
    "detach": _detach, "pin": _pin, "left": _chev_left, "right": _chev_right, "minus": _minus,
    "close": _close, "clipboard": _clipboard, "monitor": _monitor, "monitors": _monitors,
    "star": _star, "edit": _edit, "copy": _copy, "trash": _trash, "folder": _folder,
    "folder_plus": _folder_plus, "tag": _tag, "collapse": _collapse, "expand_all": _expand_all,
    "sort": _sort, "rows": _rows, "user": _user, "eye": _eye, "shield": _shield,
}


def pixmap(name, color=None, size=18, scale=2):
    color = color or C["muted"]
    px = int(size * scale)
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(px / 24.0, px / 24.0)
    pen = QPen(QColor(color), 1.8)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    _DRAW[name](p)
    p.end()
    pm.setDevicePixelRatio(scale)
    return pm


def icon(name, color=None, size=18):
    """보통 상태는 color(기본 회색), 마우스를 올리거나 눌렀을 때(Active/Selected)는 밝은 글자색."""
    key = (name, color, size)
    if key not in _cache:
        ic = QIcon()
        ic.addPixmap(pixmap(name, color, size), QIcon.Mode.Normal)
        hi = C["text"] if color in (None, C["muted"]) else color
        ic.addPixmap(pixmap(name, hi, size), QIcon.Mode.Active)
        ic.addPixmap(pixmap(name, hi, size), QIcon.Mode.Selected)
        ic.addPixmap(pixmap(name, C["idle"], size), QIcon.Mode.Disabled)
        _cache[key] = ic
    return _cache[key]
