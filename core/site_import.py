"""장비 목록(엑셀) 가져오기.

- 머리글에 '개소 번호'와 접속 IP 열('접속 IP' 등)이 있는 시트를 자동으로 찾는다 (시트 이름·열 순서 무관).
- 개소 하나 = 세션 하나.  이름 = 개소 번호,  그룹 = 하천명,  접속 주소 = 접속 IP 열.
- 카메라·스위치 등 다른 IP와 다른 시트(카메라 계정 등)는 읽지 않는다.

합치기 (merge_sites):
- 같은 개소 번호, 없으면 같은 IP의 기존 세션을 찾아 개소 정보(IP·하천·상/하류·주소·이름)만 갱신.
  계정·비밀번호·해상도·즐겨찾기·메모·접속 기록은 그대로 둔다.
- 새 개소는 account(대표 계정)의 계정·비밀번호·해상도로 만든다 (장비는 같은 구성이라고 가정).
- 파일에 없는 기존 세션은 지우지 않는다.
"""
import re
from pathlib import Path

from core.dpapi_store import SESSION_DEFAULTS

IP_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
# 머리글 이름 → 키 (공백·줄바꿈 무시하고 비교)
HEADERS = {
    "개소번호": "site_code", "카메라번호": "site_code",
    "한천명": "river", "하천명": "river",
    "상/하류": "flow",
    "주소": "address",
    "접속ip": "ip", "장비ip": "ip",
}


def _norm(h):
    return re.sub(r"\s+", "", str(h or "")).lower()


def _text(v):
    if v is None:
        return ""
    return " ".join(str(v).split())       # 앞뒤·중복 공백 정리 ("나강(하류) " → "나강(하류)")


def read_sites(path):
    """엑셀에서 개소 읽기 → (sites, problems, sheet_name).

    sites: [{"site_code", "river", "flow", "address", "ip", "_row"}]
    problems: ["12행: 접속 IP 없음", ...]  (그 행은 빠짐)
    """
    from openpyxl import load_workbook

    wb = load_workbook(Path(path), read_only=True, data_only=True)
    try:
        for ws in wb.worksheets:
            rows = ws.iter_rows(values_only=True)
            for hrow_no, header in enumerate(rows, 1):
                keys = [HEADERS.get(_norm(h)) for h in header]
                if "site_code" in keys and "ip" in keys:
                    return _read_rows(rows, keys, hrow_no) + (ws.title,)
                if hrow_no >= 5:          # 머리글은 위쪽 몇 줄 안에 있다
                    break
        raise ValueError("'개소 번호'와 '접속 IP' 열이 있는 시트를 찾지 못했습니다.")
    finally:
        wb.close()


def _read_rows(rows, keys, hrow_no):
    sites, problems, seen_code, seen_ip = [], [], {}, {}
    for rn, values in enumerate(rows, hrow_no + 1):
        cells = {}
        for k, v in zip(keys, values):
            if k and k not in cells:       # 같은 이름 열이 또 있으면 첫 열 사용
                cells[k] = _text(v)
        if not any(cells.values()):
            continue
        code, ip = cells.get("site_code", ""), cells.get("ip", "")
        if not code:
            problems.append("%d행: 개소 번호 없음" % rn)
            continue
        if not ip:
            problems.append("%d행 (%s): 접속 IP 없음" % (rn, code))
            continue
        if not IP_RE.match(ip):
            problems.append("%d행 (%s): 접속 IP '%s' 형식 오류" % (rn, code, ip))
            continue
        if code in seen_code:
            problems.append("%d행: 개소 번호 %s가 %d행과 겹침 (건너뜀)" % (rn, code, seen_code[code]))
            continue
        if ip in seen_ip:
            problems.append("%d행 (%s): IP %s가 %d행과 겹침 (건너뜀)" % (rn, code, ip, seen_ip[ip]))
            continue
        seen_code[code], seen_ip[ip] = rn, rn
        sites.append({"site_code": code, "river": cells.get("river", ""), "flow": cells.get("flow", ""),
                      "address": cells.get("address", ""), "ip": ip, "_row": rn})
    return sites, problems


# 하천명 뒤 괄호로 잘게 나뉜 그룹을 하나로 묶을 하천 ('가강(1구역)' → 그룹 '가강', 메모 '1구역').
# 목록에 없는 하천은 괄호까지 그룹 이름으로 둔다 (예: '나강(상류)'/'나강(하류)'는 따로).
# 실제 하천 목록은 현장 운영 정보라 소스에 넣지 않고 사용자 데이터 폴더의 config\site_rules.json 에 둔다:
#   {"merge_rivers": ["가강"], "ip_headers": ["장비 주소"]}   ip_headers = 접속 IP로 읽을 열 이름 추가
from core import appinfo  # noqa: E402

RULES_FILE = Path(appinfo.config_dir()) / "site_rules.json"


def _load_rules():
    try:
        import json
        with open(RULES_FILE, encoding="utf-8") as f:
            rules = json.load(f)
        return rules if isinstance(rules, dict) else {}
    except (OSError, ValueError):
        return {}


def _load_merge_rivers():
    return tuple(_load_rules().get("merge_rivers", ()))


def _extra_ip_headers():
    return {_norm(h): "ip" for h in _load_rules().get("ip_headers", ())}


MERGE_RIVERS = _load_merge_rivers()
HEADERS.update(_extra_ip_headers())
_PAREN_RE = re.compile(r"^(.+?)\s*\((.+)\)$")


def river_group(river):
    """하천명 → (그룹, 덧붙일 메모)."""
    m = _PAREN_RE.match(river or "")
    if m and m.group(1) in MERGE_RIVERS:
        return m.group(1), m.group(2)
    return river, ""


def merge_sites(existing, sites, account=None):
    """기존 세션 + 개소 목록 → {"sessions", "added", "updated", "unchanged"}.  저장은 호출하는 쪽에서."""
    result = [dict(s) for s in existing]
    by_code = {s.get("site_code"): s for s in result if s.get("site_code")}
    by_host = {s.get("host"): s for s in result}
    names = {s["name"] for s in result}
    acc = {k: (account or {}).get(k, SESSION_DEFAULTS[k]) for k in ("rdp_user", "rdp_password", "resolution")}
    added, updated, unchanged = [], [], []
    for site in sites:
        group, unit = river_group(site["river"])
        info = {"name": site["site_code"], "site_code": site["site_code"], "host": site["ip"],
                "group": group, "flow": site["flow"], "address": site["address"]}
        cur = by_code.get(site["site_code"]) or by_host.get(site["ip"])
        if unit and not (cur or {}).get("note"):     # 메모는 비어 있을 때만 (사용자가 쓴 메모 보존)
            info["note"] = unit
        if cur is not None:
            before = dict(cur)
            want = info.pop("name")
            if want != cur["name"] and want not in names:     # 이름을 개소 번호로 (다른 세션이 쓰고 있으면 그대로)
                names.discard(cur["name"])
                names.add(want)
                cur["name"] = want
            cur.update(info)
            (updated if cur != before else unchanged).append(cur["name"])
            continue
        name = info["name"]
        n = 2
        while name in names:              # 개소 번호와 같은 이름의 다른 세션이 있으면
            name = "%s (%d)" % (info["name"], n)
            n += 1
        s = dict(SESSION_DEFAULTS, **acc)
        s.update(info, name=name)
        result.append(s)
        names.add(name)
        by_host[s["host"]] = s
        added.append(name)
    return {"sessions": result, "added": added, "updated": updated, "unchanged": unchanged}


def pick_account(sessions):
    """새 개소에 쓸 대표 계정: 계정이 있고 가장 최근에 접속한 세션."""
    cands = [s for s in sessions if s.get("rdp_user")]
    return max(cands, key=lambda s: s.get("last_connected") or 0) if cands else None


PROVINCE_RE = re.compile(r"^(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|충청북|충청남|전북|전남|전라북|"
                         r"전라남|경북|경남|경상북|경상남|제주)\S*$")


def short_address(addr):
    """카드용 짧은 주소: 맨 앞 시·도 이름을 뺀다 ('경기도 가나시 다라동 12-3' → '가나시 다라동 12-3')."""
    parts = (addr or "").split()
    if len(parts) >= 3 and PROVINCE_RE.match(parts[0]):
        parts = parts[1:]
    return " ".join(parts)
