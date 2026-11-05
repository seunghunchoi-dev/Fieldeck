"""오픈소스 고지문 생성 도구.

실행: .venv\\Scripts\\python.exe tools\\collect_licenses.py

- 배포본에 들어가는 패키지(SHIPPED)의 라이선스 파일을 licenses/<패키지>/ 로 복사하고
  licenses/THIRD_PARTY_NOTICES.txt 를 새로 만든다.
- 패키지 버전을 올리거나 새 패키지를 쓰게 되면 SHIPPED 를 고친 뒤 다시 실행한다.
- LGPL-3.0.txt / GPL-3.0.txt (gnu.org 원문)는 이 스크립트가 만들지 않는다. 지우지 말 것.
"""
import glob
import os
import shutil
import sys
from importlib import metadata

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "licenses")

# (배포 이름, 용도, 라이선스 표기, 홈페이지)
SHIPPED = [
    ("PySide6_Essentials", "화면(UI), RDP ActiveX 내장(QtAxContainer)", "LGPL-3.0", "https://pyside.org"),
    ("PySide6_Addons", "PySide6 부가 모듈", "LGPL-3.0", "https://pyside.org"),
    ("shiboken6", "PySide6 바인딩 런타임", "LGPL-3.0", "https://pyside.org"),
    ("openpyxl", "엑셀 백업·복원", "MIT", "https://openpyxl.readthedocs.io"),
    ("et_xmlfile", "openpyxl 의존", "MIT", "https://foss.heptapod.net/openpyxl/et_xmlfile"),
    ("msoffcrypto-tool", "엑셀 파일 암호", "MIT", "https://github.com/nolze/msoffcrypto-tool"),
    ("olefile", "msoffcrypto-tool 의존", "BSD-2-Clause", "https://github.com/decalage2/olefile"),
    ("cryptography", "msoffcrypto-tool 의존", "Apache-2.0 OR BSD-3-Clause", "https://github.com/pyca/cryptography"),
    ("cffi", "cryptography 의존", "MIT-0", "https://cffi.readthedocs.io"),
    ("pycparser", "cffi 의존", "BSD-3-Clause", "https://github.com/eliben/pycparser"),
    # 설치본의 Fieldeck.exe 실행기(bootloader). GPL-2.0 + Bootloader Exception: 만든 exe는 어떤 라이선스로도 배포 가능
    ("pyinstaller", "설치본 실행 파일(Fieldeck.exe) 실행기", "GPL-2.0-or-later WITH Bootloader-exception",
     "https://pyinstaller.org"),
]

LGPL_NOTE = """\
[Qt for Python (PySide6) — LGPL-3.0 관련 안내]
본 프로그램은 Qt for Python(PySide6, shiboken6) 및 Qt 라이브러리를 LGPL-3.0 조건으로
수정 없이 사용하며, 이 라이브러리들은 별도 파일(DLL/PYD)로 동적 연결되어 있습니다.
사용자는 이 파일들을 호환되는 다른 버전으로 교체할 수 있습니다.
- 라이선스 원문: LGPL-3.0.txt, GPL-3.0.txt (이 폴더)
- 소스 코드: https://code.qt.io/cgit/pyside/pyside-setup.git/ (태그 v{ver})
             https://download.qt.io/official_releases/QtForPython/
- Qt 구성 요소에 포함된 제3자 소프트웨어 목록: https://doc.qt.io/qt-6/licenses-used-in-qt.html
요청 시 위 라이브러리의 해당 버전 소스 코드를 제공합니다.
"""


def copy_license_files(dist, dest_dir):
    # dist-info 안의 라이선스 파일만. Qt 상용 라이선스 조건 파일은 제외 (LGPL로 사용하므로 혼동 방지)
    files = [f for f in (dist.files or [])
             if ".dist-info" in str(f)
             and os.path.basename(str(f)).upper().startswith(("LICEN", "COPYING", "NOTICE", "AUTHORS"))
             and "Commercial" not in str(f)]
    copied = []
    for f in files:
        src = str(dist.locate_file(f))
        if not os.path.isfile(src):
            continue
        os.makedirs(dest_dir, exist_ok=True)
        name = os.path.basename(src)
        shutil.copyfile(src, os.path.join(dest_dir, name))
        copied.append(name)
    return copied


def main():
    os.makedirs(OUT, exist_ok=True)
    lines = [
        "Fieldeck — 오픈소스 소프트웨어 고지 (Third-Party Notices)",
        "=" * 60,
        "본 프로그램에는 아래 오픈소스 소프트웨어가 포함되어 있습니다.",
        "각 라이선스 원문은 이 폴더의 하위 폴더에 있습니다.",
        "",
    ]
    pyside_ver = None
    missing = []
    for name, use, lic, url in SHIPPED:
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            missing.append(name)
            continue
        ver = dist.version
        if name == "PySide6_Essentials":
            pyside_ver = ver
        sub = name.lower().replace("_", "-")
        copied = ["%s/%s" % (sub, c) for c in copy_license_files(dist, os.path.join(OUT, sub))]
        if not copied and lic.startswith("LGPL"):
            copied = ["LGPL-3.0.txt", "GPL-3.0.txt"]
        lines += [
            "- %s %s" % (name, ver),
            "    용도: %s" % use,
            "    라이선스: %s" % lic,
            "    홈페이지: %s" % url,
            "    라이선스 파일: %s" % (", ".join(copied) or "(없음)"),
            "",
        ]

    # Python 런타임 (배포본에 python312.dll 등이 들어감)
    py_lic = glob.glob(os.path.join(sys.base_prefix, "LICENSE*"))
    if py_lic:
        os.makedirs(os.path.join(OUT, "python"), exist_ok=True)
        shutil.copyfile(py_lic[0], os.path.join(OUT, "python", "LICENSE.txt"))
    lines += [
        "- Python %d.%d.%d" % sys.version_info[:3],
        "    용도: 실행 환경",
        "    라이선스: PSF License (Python Software Foundation License Version 2)",
        "    홈페이지: https://www.python.org",
        "    라이선스 파일: python/LICENSE.txt",
        "",
        LGPL_NOTE.format(ver=pyside_ver or "?"),
    ]
    with open(os.path.join(OUT, "THIRD_PARTY_NOTICES.txt"), "w", encoding="utf-8-sig") as f:
        f.write("\n".join(lines))

    for req in ("LGPL-3.0.txt", "GPL-3.0.txt"):
        if not os.path.exists(os.path.join(OUT, req)):
            print("경고: licenses/%s 없음 — https://www.gnu.org/licenses/ 에서 받아 넣을 것" % req)
    if missing:
        print("경고: 설치되지 않은 패키지:", ", ".join(missing))
        return 1
    print("완료:", os.path.join(OUT, "THIRD_PARTY_NOTICES.txt"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
