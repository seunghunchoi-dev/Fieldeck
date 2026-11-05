"""접속 정보 저장소 — Windows DPAPI(CurrentUser)로 암호화.

- 파일: %LOCALAPPDATA%\\Fieldeck\\config\\sessions.bin (JSON 전체를 DPAPI로 감싼 바이너리, core.appinfo)
- 같은 Windows 사용자 계정에서만 복호화된다. 키 파일 관리 불필요.
- 외부 라이브러리 없이 ctypes로 crypt32.dll을 직접 호출한다.
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import tempfile

from core import appinfo

# 추가 엔트로피(다른 프로그램의 DPAPI 데이터와 구분). 바꾸면 기존 파일을 못 연다 — 제품 이름이 바뀌어도 그대로 둘 것.
_ENTROPY = b"RemoteDesktopManager.v1"
CRYPTPROTECT_UI_FORBIDDEN = 0x1


def default_path():
    return os.path.join(appinfo.config_dir(), "sessions.bin")

# 세션 필드 기본값 (설계문서 2장)
SESSION_DEFAULTS = {
    "name": "",
    "host": "",
    "rdp_port": 3389,
    "rdp_user": "",
    "rdp_password": "",
    "redirect_clipboard": True,  # 클립보드 공유 (텍스트·파일 복사/붙여넣기)
    "resolution": "auto",        # "auto"=이 PC 모니터 해상도+창에 맞춰 축소 / "fit"=창 크기 따라 원격 해상도 변경 / "1920x1080" 등 고정
    "protocol": "sftp",  # "sftp" | "ftp"
    "ft_port": 22,
    "ft_user": "",
    "ft_password": "",
    "note": "",
    "group": "",            # 목록 묶음 (예: 금강, 낙동). 빈 값 = 그룹 없음
    "favorite": False,      # 즐겨찾기 → 목록 맨 위
    "last_connected": 0,    # 마지막 접속 성공 시각 (epoch 초)
    # 현장 개소 정보 (장비 목록 엑셀에서 가져옴)
    "site_code": "",        # 개소 번호 (예: GA-001)
    "flow": "",             # 상류 / 하류
    "address": "",          # 설치 주소
}


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _to_blob(data):
    buf = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


_crypt32 = ctypes.windll.crypt32
_kernel32 = ctypes.windll.kernel32
_kernel32.LocalFree.argtypes = [ctypes.c_void_p]


def protect(data):
    """bytes -> DPAPI 암호문 bytes"""
    blob_in, _b1 = _to_blob(data)
    blob_ent, _b2 = _to_blob(_ENTROPY)
    blob_out = _Blob()
    if not _crypt32.CryptProtectData(
        ctypes.byref(blob_in), "RDM", ctypes.byref(blob_ent),
        None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        _kernel32.LocalFree(blob_out.pbData)


def unprotect(data):
    """DPAPI 암호문 bytes -> bytes. 다른 사용자/PC면 OSError."""
    blob_in, _b1 = _to_blob(data)
    blob_ent, _b2 = _to_blob(_ENTROPY)
    blob_out = _Blob()
    if not _crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, ctypes.byref(blob_ent),
        None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        _kernel32.LocalFree(blob_out.pbData)


class SessionStore:
    """세션 목록을 메모리에 들고 있다가 save() 시 암호화 저장."""

    def __init__(self, path=None):
        self.path = path or default_path()
        self.sessions = []
        self.load()

    def load(self):
        if not os.path.exists(self.path):
            self.sessions = []
            return
        with open(self.path, "rb") as f:
            raw = unprotect(f.read())
        data = json.loads(raw.decode("utf-8"))
        self.sessions = [dict(SESSION_DEFAULTS, **s) for s in data.get("sessions", [])]

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        raw = json.dumps({"version": 1, "sessions": self.sessions}, ensure_ascii=False).encode("utf-8")
        enc = protect(raw)
        # 임시 파일에 쓴 뒤 교체 → 저장 중 끊겨도 기존 파일 보존
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path), suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(enc)
            os.replace(tmp, self.path)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise

    # --- 편의 함수 ---
    def names(self):
        return [s["name"] for s in self.sessions]

    def groups(self):
        return sorted({s.get("group", "") for s in self.sessions if s.get("group")})

    def get(self, name):
        for s in self.sessions:
            if s["name"] == name:
                return s
        return None

    def upsert(self, session):
        """이름이 같으면 갱신, 없으면 추가."""
        s = dict(SESSION_DEFAULTS, **session)
        if not s["name"] or not s["host"]:
            raise ValueError("name과 host는 필수입니다.")
        if s["protocol"] not in ("sftp", "ftp"):
            raise ValueError("protocol은 'sftp' 또는 'ftp'여야 합니다.")
        for i, old in enumerate(self.sessions):
            if old["name"] == s["name"]:
                self.sessions[i] = s
                return
        self.sessions.append(s)

    def remove(self, name):
        before = len(self.sessions)
        self.sessions = [s for s in self.sessions if s["name"] != name]
        return len(self.sessions) < before
