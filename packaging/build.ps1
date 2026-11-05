# Fieldeck 설치 파일 만들기
#   실행: powershell -ExecutionPolicy Bypass -File packaging\build.ps1
#   결과: dist\Fieldeck\ (프로그램 폴더), dist\Fieldeck-Setup-<버전>.exe (설치 파일)
# 필요: .venv 에 pyinstaller, Inno Setup 6 (winget install JRSoftware.InnoSetup)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"

# 버전: core/appinfo.py 가 기준. version_info.txt 와 다르면 중단.
$ver = & $py -c "from core import appinfo; print(appinfo.VERSION)"
if (-not (Select-String -Path "packaging\version_info.txt" -SimpleMatch "'ProductVersion', '$ver'" -Quiet)) {
    throw "packaging\version_info.txt 의 버전이 appinfo.VERSION($ver)과 다릅니다."
}

# 1) 테스트
& $py -m unittest discover -s tests
if ($LASTEXITCODE -ne 0) { throw "테스트 실패" }

# 2) exe (폴더형)
& $py -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\fieldeck.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 실패" }

# 3) 사용자 데이터가 섞이지 않았는지 확인
$bad = Get-ChildItem -Recurse dist\Fieldeck -Include sessions*.bin, site_rules.json, *.xlsx, *.pptx, conn_*.log -ErrorAction SilentlyContinue
if ($bad) { throw "배포 폴더에 사용자 데이터가 있습니다: $($bad.FullName -join ', ')" }

# 4) 설치 파일
$iscc = Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) { $iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" }
& $iscc "/DAppVersion=$ver" packaging\installer.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup 실패" }
Get-Item "dist\Fieldeck-Setup-$ver.exe" | Select-Object Name, @{n = "MB"; e = { [math]::Round($_.Length / 1MB, 1) } }
