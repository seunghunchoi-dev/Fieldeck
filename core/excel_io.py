"""세션 목록 엑셀 백업·복원.

- 백업: 세션의 모든 항목을 .xlsx로 저장 (원격 접속·파일 전송·메모·마지막 접속).
  암호 없는 일반 엑셀 (비밀번호 포함 여부는 선택). 예전에 열기 암호를 걸어 만든 백업도 복원 가능 (msoffcrypto-tool).
- 복원: 머리글 이름으로 열을 찾으므로 열 순서가 바뀌어도 된다 → 엑셀에서 직접 작성한 목록도 일괄 등록 가능.
- 빈 입력 양식: export_template().
- 복원 계획(plan_restore)은 순수 함수 — 실제 저장은 호출하는 쪽에서 한다.
"""
import datetime
import io
import shutil
import time
from pathlib import Path

from core.dpapi_store import SESSION_DEFAULTS

SHEET = "세션목록"

# (세션 키, 엑셀 머리글, 열 너비)
COLUMNS = [
    ("name", "이름", 24),
    ("group", "그룹", 16),
    ("site_code", "개소 번호", 12),
    ("flow", "상/하류", 9),
    ("address", "설치 주소", 34),
    ("host", "주소", 18),
    ("rdp_port", "포트", 8),
    ("rdp_user", "계정", 16),
    ("rdp_password", "비밀번호", 16),
    ("resolution", "해상도", 14),
    ("redirect_clipboard", "클립보드 공유", 13),
    ("favorite", "즐겨찾기", 10),
    ("note", "메모", 30),
    ("protocol", "전송 방식", 11),
    ("ft_port", "전송 포트", 10),
    ("ft_user", "전송 계정", 16),
    ("ft_password", "전송 비밀번호", 16),
    ("last_connected", "마지막 접속", 18),
]
# 세션의 모든 항목(dpapi_store.SESSION_DEFAULTS)은 위 목록에 있어야 한다 — tests/test_excel_io.py가 검사
SECRETS = ("rdp_password", "ft_password")        # 파일 암호를 걸 때만 넣는 항목
TEMPLATE_SKIP = SECRETS + ("protocol", "ft_port", "ft_user", "last_connected")   # 빈 입력 양식에서 뺄 열
PROTOCOLS = ("sftp", "ftp")
TIME_FMT = "%Y-%m-%d %H:%M"
HEADER_TO_KEY = {h: k for k, h, _ in COLUMNS}
HEADER_TO_KEY.update({k: k for k, _, _ in COLUMNS})          # 영문 키 머리글도 허용
HEADER_TO_KEY.update({"비밀 번호": "rdp_password", "암호": "rdp_password", "IP": "host", "주소(IP)": "host"})

RES_TO_TEXT = {"auto": "자동", "fit": "창 맞춤"}
TEXT_TO_RES = {"자동": "auto", "자동 축소": "auto", "창 맞춤": "fit", "창에 맞춤": "fit", "": "auto"}
YES, NO = "예", "아니오"


class BackupPasswordError(Exception):
    """암호가 걸린 파일인데 암호가 없거나 틀림."""


# --------------------------------------------------------------------------- 백업
REQUIRED = ("name", "host")


def export_template(path):
    """빈 입력 양식 (세션 없이 머리글·드롭다운·안내만). 채운 뒤 '엑셀에서 복원'으로 불러온다."""
    export_sessions(path, [], template=True)


def export_sessions(path, sessions, include_password=False, file_password=None, template=False):
    """세션 목록을 엑셀로 저장. template=True면 빈 입력 양식.

    화면의 백업은 암호 없는 일반 엑셀로 저장한다.
    file_password를 주면 엑셀 열기 암호를 건다 (지금 화면에서는 쓰지 않음).
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    cols = [c for c in COLUMNS if include_password or c[0] not in SECRETS]
    if template:
        cols = [c for c in cols if c[0] not in TEMPLATE_SKIP]

    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    head_fill = PatternFill("solid", fgColor="2A3042")
    req_fill = PatternFill("solid", fgColor="5B3FD9")      # 필수 열 (이름·주소)
    head_font = Font(bold=True, color="FFFFFF")
    for i, (key, title, width) in enumerate(cols, 1):
        c = ws.cell(row=1, column=i, value=title)
        c.fill, c.font = (req_fill if template and key in REQUIRED else head_fill), head_font
        c.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[c.column_letter].width = width
    ws.row_dimensions[1].height = 22

    for r, s in enumerate(sorted(sessions, key=lambda x: (x.get("group", ""), x.get("name", ""))), 2):
        for i, (key, _, _) in enumerate(cols, 1):
            ws.cell(row=r, column=i, value=_to_cell(key, s.get(key, SESSION_DEFAULTS.get(key))))

    ws.freeze_panes = "B2"
    last_row = max(2, len(sessions) + 1)
    ws.auto_filter.ref = "A1:%s%d" % (ws.cell(row=1, column=len(cols)).column_letter, last_row)
    # 입력 도우미 (엑셀에서 직접 추가할 때 드롭다운)
    idx = {k: i for i, (k, _, _) in enumerate(cols, 1)}
    letter = lambda k: ws.cell(row=1, column=idx[k]).column_letter  # noqa: E731
    yn = DataValidation(type="list", formula1='"%s,%s"' % (YES, NO), allow_blank=True)
    res = DataValidation(type="list", formula1='"자동,창 맞춤,1920x1080,2560x1440,1600x900,1280x720"',
                         allow_blank=True)
    port = DataValidation(type="whole", operator="between", formula1="1", formula2="65535", allow_blank=True)
    proto = DataValidation(type="list", formula1='"%s"' % ",".join(PROTOCOLS), allow_blank=True)
    rules = [(yn, "redirect_clipboard"), (yn, "favorite"), (res, "resolution"), (port, "rdp_port"),
             (port, "ft_port"), (proto, "protocol")]
    for dv in (yn, res, port, proto):
        ws.add_data_validation(dv)
    for dv, key in rules:
        if key in idx:
            dv.add("%s2:%s2000" % (letter(key), letter(key)))

    guide = wb.create_sheet("안내")
    if template:
        lines = [
            "Fieldeck 세션 목록 입력 양식",
            "",
            "• '세션목록' 시트에 한 줄에 PC 하나씩 입력합니다. 보라색 머리글(이름·주소)은 꼭 입력해야 합니다.",
            "• 이름: 화면에 보일 이름 (겹치면 안 됨).  주소: IP 또는 컴퓨터 이름 (예: 192.0.2.119).",
            "• 그룹: 현장·라인 등 묶음 이름 (비우면 '그룹 없음').  포트: 비우면 3389.  계정: 원격 PC 로그인 계정.",
            "• 해상도: 자동 / 창 맞춤 / 1920x1080 처럼 가로x세로 (비우면 자동).",
            "• 클립보드 공유·즐겨찾기: 예 / 아니오 (칸을 누르면 목록에서 고를 수 있음).  메모: 자유롭게.",
            "• 다 채운 뒤 Fieldeck 사이드바 ⋯ → '엑셀에서 복원…'으로 불러옵니다.",
            "• 비밀번호는 보안상 이 양식에 넣지 않습니다. 불러온 뒤 세션 편집에서 입력하세요.",
            "• 머리글(1행)의 이름은 바꾸지 마세요. 열 순서는 바꿔도 됩니다.",
        ]
    else:
        lines = [
            "Fieldeck 세션 목록 백업  (%s, %d개)" % (time.strftime("%Y-%m-%d %H:%M"), len(sessions)),
            "",
            "• '세션목록' 시트의 한 줄 = 세션 하나. 이름·주소는 꼭 입력해야 합니다.",
            "• 엑셀에서 줄을 추가·수정한 뒤 Fieldeck의 '엑셀에서 복원'으로 불러올 수 있습니다.",
            "• 해상도: 자동 / 창 맞춤 / 1920x1080 처럼 가로x세로.  클립보드 공유·즐겨찾기: 예 / 아니오.",
            "• 포트를 비우면 3389.  전송 방식: sftp / ftp,  전송 포트를 비우면 기본값.",
            "• '마지막 접속'도 함께 복원됩니다 (형식 2026-11-03 14:02, 비워도 됨).",
            "• 비밀번호 열(원격·전송)이 없거나 비어 있으면: 이미 있는 세션은 기존 비밀번호를 그대로 둡니다.",
        ]
        if include_password and not file_password:
            lines.append("• 이 파일에는 비밀번호가 암호화 없이 들어 있습니다. 보관·전달에 주의하세요.")
        elif include_password:
            lines.append("• 이 파일에는 비밀번호가 들어 있습니다. 파일 암호를 다른 사람과 공유하지 마세요.")
        else:
            lines.append("• 이 파일에는 비밀번호가 들어 있지 않습니다 (보안).")
    for i, t in enumerate(lines, 1):
        guide.cell(row=i, column=1, value=t)
    guide["A1"].font = Font(bold=True, size=13)
    guide.column_dimensions["A"].width = 100

    buf = io.BytesIO()
    wb.save(buf)
    data = buf.getvalue()
    if file_password:
        data = _encrypt(data, file_password)
    tmp = Path(str(path) + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def _to_cell(key, v):
    if key in ("redirect_clipboard", "favorite"):
        return YES if v else NO
    if key == "resolution":
        return RES_TO_TEXT.get(v, v)
    if key == "last_connected":
        return time.strftime(TIME_FMT, time.localtime(v)) if v else ""
    if key == "rdp_port":
        return int(v or 3389)
    if key == "ft_port":
        return int(v) if v not in (None, "") else ""
    return v if v is not None else ""


def _encrypt(data, password):
    from msoffcrypto.format.ooxml import OOXMLFile
    out = io.BytesIO()
    OOXMLFile(io.BytesIO(data)).encrypt(password, out)
    return out.getvalue()


# --------------------------------------------------------------------------- 읽기
def is_encrypted(path):
    import msoffcrypto
    with open(path, "rb") as f:
        try:
            return msoffcrypto.OfficeFile(f).is_encrypted()
        except Exception:
            return False


def read_sessions(path, file_password=None):
    """엑셀에서 세션 읽기 → (rows, problems, has_password_column).

    rows: 세션 dict 목록 (엑셀에 있던 키만 들어 있음 + 행 번호 '_row')
    problems: ["5행: 주소가 비어 있음", ...]  (그 행은 rows에서 빠짐)
    """
    from openpyxl import load_workbook

    raw = Path(path).read_bytes()
    if is_encrypted(path):
        if not file_password:
            raise BackupPasswordError("암호가 걸린 파일입니다.")
        import msoffcrypto
        office = msoffcrypto.OfficeFile(io.BytesIO(raw))
        out = io.BytesIO()
        try:
            office.load_key(password=file_password)
            office.decrypt(out)
        except Exception:
            raise BackupPasswordError("파일 암호가 맞지 않습니다.")
        raw = out.getvalue()

    wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    ws = wb[SHEET] if SHEET in wb.sheetnames else wb.worksheets[0]
    it = ws.iter_rows(values_only=True)
    header = next(it, None) or ()
    keys = [HEADER_TO_KEY.get(str(h).strip()) if h is not None else None for h in header]
    if "name" not in keys or "host" not in keys:
        wb.close()
        raise ValueError("머리글에 '이름'과 '주소' 열이 있어야 합니다.")

    rows, problems, seen = [], [], {}
    for rn, values in enumerate(it, 2):
        cells = {k: v for k, v in zip(keys, values) if k}
        if all(v in (None, "") for v in cells.values()):
            continue
        s, err = _parse_row(cells)
        if err:
            problems.append("%d행: %s" % (rn, err))
            continue
        if s["name"] in seen:
            problems.append("%d행: 이름 '%s'이(가) %d행과 겹침 (뒤의 줄 사용)" % (rn, s["name"], seen[s["name"]]))
            rows = [r for r in rows if r["name"] != s["name"]]
        seen[s["name"]] = rn
        s["_row"] = rn
        rows.append(s)
    wb.close()
    return rows, problems, any(k in keys for k in SECRETS)


def _text(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _parse_row(cells):
    s = {}
    for key, v in cells.items():
        t = _text(v)
        if key in ("rdp_port", "ft_port"):
            label = "포트" if key == "rdp_port" else "전송 포트"
            if t == "":
                if key == "rdp_port":
                    s[key] = 3389
                continue                    # 전송 포트를 비우면 기존 값/기본값
            try:
                s[key] = int(t)
            except ValueError:
                return None, "%s '%s'이(가) 숫자가 아님" % (label, t)
            if not 1 <= s[key] <= 65535:
                return None, "%s %d이(가) 범위(1~65535)를 벗어남" % (label, s[key])
        elif key == "protocol":
            if t == "":
                continue
            if t.lower() not in PROTOCOLS:
                return None, "전송 방식 '%s'을(를) 알 수 없음 (sftp / ftp)" % t
            s[key] = t.lower()
        elif key in ("redirect_clipboard", "favorite"):
            if t == "":
                continue
            s[key] = t.lower() in ("예", "y", "yes", "true", "1", "o", "○", "on")
        elif key == "resolution":
            r = TEXT_TO_RES.get(t, t.lower().replace("×", "x").replace(" ", ""))
            if r not in ("auto", "fit"):
                try:
                    w, h = (int(x) for x in r.split("x"))
                    assert 640 <= w <= 8192 and 480 <= h <= 8192
                except (ValueError, AssertionError):
                    return None, "해상도 '%s'을(를) 알 수 없음 (자동 / 창 맞춤 / 1920x1080)" % t
            s[key] = r
        elif key == "last_connected":
            if isinstance(v, datetime.datetime):        # 엑셀에서 날짜 칸으로 바뀐 경우
                s[key] = int(v.timestamp())
            elif t:
                try:
                    s[key] = int(time.mktime(time.strptime(t[:16], TIME_FMT)))
                except ValueError:
                    pass                    # 형식이 틀린 기록 시각은 무시 (세션 자체는 복원)
        else:
            s[key] = t
    if not s.get("name"):
        return None, "이름이 비어 있음"
    if not s.get("host"):
        return None, "주소가 비어 있음"
    return s, None


# --------------------------------------------------------------------------- 복원 계획
def plan_restore(existing, rows, mode="merge", on_duplicate="overwrite"):
    """복원 결과(새 세션 목록)와 요약을 계산. 실제 저장은 하지 않는다.

    mode: "merge"(기존 유지 + 추가/갱신) | "replace"(엑셀 내용으로 전부 교체)
    on_duplicate: 같은 이름이 있을 때 "overwrite"(엑셀 값으로 갱신) | "skip"(기존 유지)
    엑셀에 비밀번호가 없거나 비어 있으면 같은 이름 세션의 기존 비밀번호를 유지한다 (replace여도).
    """
    old = {s["name"]: s for s in existing}
    added, updated, skipped = [], [], []
    result = {} if mode == "replace" else {n: dict(s) for n, s in old.items()}
    for r in rows:
        r = {k: v for k, v in r.items() if k != "_row"}
        name = r["name"]
        prev = old.get(name)
        if prev and mode == "merge" and on_duplicate == "skip":
            skipped.append(name)
            continue
        base = dict(prev) if prev else dict(SESSION_DEFAULTS)
        for k in SECRETS:
            if not r.get(k):
                r.pop(k, None)                   # 기존 비밀번호 유지
        base.update(r)
        result[name] = base
        (updated if prev else added).append(name)
    removed = [n for n in old if n not in result]
    return {"sessions": list(result.values()), "added": added, "updated": updated,
            "skipped": skipped, "removed": removed}


def safety_copy(store_path):
    """복원 전에 현재 접속 정보 파일을 config/backup/에 복사 (DPAPI 암호화 그대로). 복사본 경로 반환."""
    src = Path(store_path)
    if not src.exists():
        return None
    dst_dir = src.parent / "backup"
    dst_dir.mkdir(exist_ok=True)
    dst = dst_dir / ("sessions_%s.bin" % time.strftime("%Y%m%d_%H%M%S"))
    shutil.copy2(src, dst)
    return dst
