# Fieldeck (필덱)

여러 Windows 원격 PC(RDP)에 한 프로그램에서 동시에 접속하고, 현장 장비 상태를 한눈에 보는 Windows용 관리 프로그램입니다.

## 주요 기능
- 다중 원격 접속: 탭으로 여러 PC에 동시 접속, 탭 분리·합치기, 전체 화면
- 현장 대시보드: 모든 장비의 응답 상태(정상·느림·RDP 닫힘·오프라인)를 주기적으로 확인, 그룹별 보기·접기, 작은 칸 보기
- 접속 정보 보호: 비밀번호를 Windows DPAPI로 암호화해 현재 Windows 계정에서만 열림
- 불안정한 네트워크 대응: 신호 막대, 자동 재연결, 저속 모드
- 세션 목록 엑셀 백업·복원, 연결 상태 로그 저장

## 설치 (사용자)
1. [Releases](https://github.com/seunghunchoi-dev/Fieldeck/releases) 에서 `Fieldeck-Setup-<버전>.exe` 를 내려받아 실행합니다.
   - 관리자 권한 없이 설치됩니다 (`%LOCALAPPDATA%\Programs\Fieldeck`).
   - 코드 서명이 없어 Windows가 "PC 보호" 경고를 띄울 수 있습니다. **추가 정보 → 실행** 을 누르면 설치됩니다.
2. 시작 메뉴 또는 바탕화면의 **Fieldeck** 으로 실행합니다.
3. 처음에는 세션 목록이 비어 있습니다. 왼쪽 '새 세션'으로 접속할 PC를 추가하세요.

데이터(접속 정보·로그)는 `%LOCALAPPDATA%\Fieldeck` 에 저장되며, 프로그램을 지우거나 업데이트해도 남습니다.
Windows 10/11 64비트에서 동작합니다.

## 사용 설명서
[Fieldeck Wiki](https://github.com/seunghunchoi-dev/Fieldeck/wiki)에서 바로 읽을 수 있습니다. 화면 구성, 대시보드, 원격 접속, 백업·로그, 자주 묻는 문제를 다룹니다.
내려받아 보려면 [PDF](docs/Fieldeck-manual-ko.pdf)를 받으세요. 설명서의 화면은 가상 장비로 만든 예시입니다.

## 소스에서 실행 (개발)
```
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```
테스트: `.venv\Scripts\python.exe -m unittest discover -s tests`

설치 파일 만들기 (PyInstaller + Inno Setup 6 필요):
```
.venv\Scripts\python.exe -m pip install pyinstaller
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

## 라이선스
이 소프트웨어는 **PolyForm Internal Use License 1.0.0**으로 공개합니다. 전문은 [LICENSE.md](LICENSE.md)를 보세요.

- 할 수 있는 것: 내려받아 설치·사용, 자신 또는 소속 조직의 업무를 위해 고쳐서 사용
- 할 수 없는 것: 원본이든 고친 것이든 **다른 사람에게 배포**(재배포·판매·다른 곳에 올리기 등)

다른 조건으로 쓰고 싶으면 저작권자에게 문의하세요.

사용한 오픈소스 구성 요소(PySide6 등)의 라이선스는 `licenses/` 폴더(설치본은 설치 폴더의 `licenses`)에 있으며,
각 구성 요소는 그 라이선스를 따릅니다.
