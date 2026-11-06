"""제품 이름·버전·데이터 위치 (한 곳에서 관리).

데이터는 프로그램 폴더가 아니라 사용자 폴더에 둔다 — 설치형(쓰기 제한)·업데이트·제거에도 남도록.
    %LOCALAPPDATA%\\Fieldeck\\config\\sessions.bin      접속 정보 (DPAPI)
    %LOCALAPPDATA%\\Fieldeck\\config\\backup\\           복원 전 보관본
    %LOCALAPPDATA%\\Fieldeck\\config\\site_rules.json    현장 규칙 (하천 묶기)
    %LOCALAPPDATA%\\Fieldeck\\logs\\                     연결 상태 로그
"""
import os
import sys

APP_NAME = "Fieldeck"
APP_NAME_KO = "필덱"
APP_ID = "Fieldeck.App"                 # Windows 작업 표시줄 앱 ID (바로가기와 같은 값)
VERSION = "1.0.2"
TAGLINE = "원격 PC 다중 접속 · 현장 대시보드"


def _local_appdata():
    return os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")


def program_dir():
    """프로그램 파일 위치 (exe로 묶였으면 exe 폴더, 아니면 소스 폴더)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir():
    """사용자 데이터 위치. 시험용으로 FIELDECK_DATA 환경 변수로 바꿀 수 있다."""
    return os.environ.get("FIELDECK_DATA") or os.path.join(_local_appdata(), APP_NAME)


def config_dir():
    return os.path.join(data_dir(), "config")


def log_dir():
    return os.path.join(data_dir(), "logs")
