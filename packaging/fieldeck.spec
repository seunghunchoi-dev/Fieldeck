# PyInstaller 빌드 설정 — 실행: packaging\build.ps1
# 폴더형(onedir): PySide6(LGPL) DLL을 사용자가 교체할 수 있어야 하므로 한 파일(onefile)로 묶지 않는다 (설계문서 7장).
# 사용자 데이터(config/·logs)는 넣지 않는다 — 실행 시 %LOCALAPPDATA%\Fieldeck 에 만들어짐.
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    datas=[
        (os.path.join(ROOT, "assets", "app.ico"), "assets"),
        (os.path.join(ROOT, "assets", "app.png"), "assets"),
    ],
    hiddenimports=["PySide6.QtAxContainer"],
    excludes=[
        # 쓰지 않는 큰 모듈 (설치 파일 크기 줄이기)
        "tkinter", "unittest", "pydoc", "paramiko", "bcrypt", "nacl", "invoke",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
        "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.Qt3DCore",
        "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtPdf",
        "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtBluetooth", "PySide6.QtPositioning",
        "PySide6.QtLocation", "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtDesigner",
        "PySide6.QtHelp", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtSvg",
        "PySide6.QtSvgWidgets", "PySide6.QtNetwork", "PySide6.QtXml", "PySide6.QtPrintSupport",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Fieldeck",
    icon=os.path.join(ROOT, "assets", "app.ico"),
    version=os.path.join(SPECPATH, "version_info.txt"),
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Fieldeck", upx=False)
