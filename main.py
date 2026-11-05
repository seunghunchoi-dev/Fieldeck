"""진입점.  실행: .venv\\Scripts\\python.exe main.py   (설치본: Fieldeck.exe)

프로그램 접근 제한: allowed_users.txt 가 프로그램 폴더 또는 데이터 폴더의 config 안에 있으면
그 안의 Windows 사용자만 실행 가능 (한 줄에 한 명, 대소문자 무시). 파일이 없으면 제한 없음.
"""
import getpass
import os
import sys

from core import appinfo


def allowed_files():
    return [os.path.join(appinfo.program_dir(), "config", "allowed_users.txt"),
            os.path.join(appinfo.config_dir(), "allowed_users.txt")]


def user_allowed():
    files = [p for p in allowed_files() if os.path.exists(p)]
    if not files:
        return True
    users = set()
    for p in files:
        with open(p, encoding="utf-8") as f:
            users |= {ln.strip().lower() for ln in f if ln.strip() and not ln.startswith("#")}
    return getpass.getuser().lower() in users


def main():
    # 작업 표시줄에 python 아이콘 대신 Fieldeck 아이콘이 보이도록 앱 ID 지정
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(appinfo.APP_ID)
    except Exception:
        pass

    from PySide6.QtWidgets import QApplication, QMessageBox

    from core.dpapi_store import SessionStore
    from ui.app_icon import app_icon
    from ui.main_window import MainWindow
    from ui.theme import QSS, pick_font

    app = QApplication(sys.argv)
    app.setApplicationName(appinfo.APP_NAME)
    app.setApplicationVersion(appinfo.VERSION)
    app.setWindowIcon(app_icon())
    app.setFont(pick_font())
    app.setStyleSheet(QSS)

    if not user_allowed():
        QMessageBox.critical(None, appinfo.APP_NAME,
                             "이 Windows 사용자(%s)는 실행 권한이 없습니다." % getpass.getuser())
        return 1
    try:
        store = SessionStore()
    except OSError:
        QMessageBox.critical(None, appinfo.APP_NAME,
                             "접속 정보 파일을 열 수 없습니다.\n다른 Windows 계정에서 만든 파일일 수 있습니다.\n(%s)"
                             % os.path.join(appinfo.config_dir(), "sessions.bin"))
        return 1

    win = MainWindow(store)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
