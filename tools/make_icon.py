"""아이콘 파일 생성: assets/app.ico (여러 크기), assets/app.png (256px)

실행: .venv\\Scripts\\python.exe -m tools.make_icon
ICO는 크기별 PNG를 묶는 방식(Windows Vista 이상 지원)으로 직접 작성한다.
"""
import os
import struct
import sys

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtWidgets import QApplication

from ui.app_icon import SIZES, render

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(BASE, "assets")


def png_bytes(pm):
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pm.save(buf, "PNG")
    return bytes(buf.data())


def write_ico(path, sizes):
    images = [(s, png_bytes(render(s))) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for s, data in images:
        dim = 0 if s >= 256 else s
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
        blobs += data
    with open(path, "wb") as f:
        f.write(header + entries + blobs)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    os.makedirs(ASSETS, exist_ok=True)
    write_ico(os.path.join(ASSETS, "app.ico"), [s for s in SIZES if s in (16, 20, 24, 32, 40, 48, 64, 256)])
    render(256).save(os.path.join(ASSETS, "app.png"))
    print("생성:", os.path.join(ASSETS, "app.ico"))


if __name__ == "__main__":
    main()
