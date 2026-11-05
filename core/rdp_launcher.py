"""예비 경로: 외부 mstsc 창으로 접속 (탭 내장 ActiveX가 안 되는 PC용).

흐름 (설계문서 3장):
1. cmdkey로 TERMSRV/<host> 자격 증명 등록
2. 비밀번호 없는 임시 .rdp 생성 → mstsc 실행
3. mstsc 종료 후 cmdkey 삭제, 임시 .rdp 삭제
비밀번호가 cmdkey 명령줄에 잠깐 노출되는 한계가 있다 (2차: CredWrite 검토).
"""
import os
import subprocess
import tempfile
import threading

_NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW


def _target(host):
    return "TERMSRV/" + host


def build_rdp_text(session):
    port = int(session.get("rdp_port") or 3389)
    addr = session["host"] if port == 3389 else "%s:%d" % (session["host"], port)
    lines = [
        "full address:s:" + addr,
        "username:s:" + session.get("rdp_user", ""),
        "prompt for credentials:i:0",
        "authentication level:i:2",
        "enablecredsspsupport:i:1",
        "redirectclipboard:i:%d" % (1 if session.get("redirect_clipboard", True) else 0),
        "screen mode id:i:1",
        "smart sizing:i:1",
    ]
    return "\r\n".join(lines) + "\r\n"


def _cmdkey(args):
    subprocess.run(["cmdkey"] + args, capture_output=True, creationflags=_NO_WINDOW)


def launch_external(session, on_exit=None):
    """mstsc 창을 띄우고 즉시 반환. 종료 시 정리 후 on_exit(returncode) 호출."""
    host = session["host"]
    if session.get("rdp_password"):
        _cmdkey(["/generic:" + _target(host), "/user:" + session.get("rdp_user", ""),
                 "/pass:" + session["rdp_password"]])

    fd, rdp_path = tempfile.mkstemp(suffix=".rdp")
    with os.fdopen(fd, "w", encoding="utf-16") as f:
        f.write(build_rdp_text(session))

    proc = subprocess.Popen(["mstsc", rdp_path])

    def _wait():
        try:
            rc = proc.wait()
        finally:
            _cmdkey(["/delete:" + _target(host)])
            try:
                os.remove(rdp_path)
            except OSError:
                pass
        if on_exit:
            on_exit(rc)

    threading.Thread(target=_wait, daemon=True).start()
    return proc
