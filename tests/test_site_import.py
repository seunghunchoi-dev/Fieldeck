"""장비 목록 가져오기 테스트 (실제 파일과 같은 머리글 구성의 작은 엑셀로)."""
import os
import tempfile
import unittest

from openpyxl import Workbook

from core import site_import
from core.dpapi_store import SESSION_DEFAULTS

HEAD = ['No', '한천명', '개소 번호', '상/하류', '위도', '경도', '주소', 'GateWay', 'SubnetMask', '통신사 IP',
        'L2 Switch', '회전카메라', '고정(상류)', '고정(하류)', '고정(추가)', '전원제어', '접속 IP', None, None]


def row(no, river, code, flow, addr, ai):
    return [no, river, code, flow, 37.2, 127.0, addr, '192.0.2.0', '255.255.255.240', '192.0.2.1', '192.0.2.2',
            '192.0.2.3', '192.0.2.4', '192.0.2.5', None, '192.0.2.6', ai, None, None]


class SiteImportTest(unittest.TestCase):
    def setUp(self):
        # 묶을 하천 목록은 이 PC의 config/site_rules.json 대신 테스트용 값으로 (테스트가 현장 설정에 좌우되지 않게)
        self._merge = site_import.MERGE_RIVERS
        site_import.MERGE_RIVERS = ("가강",)
        self.addCleanup(setattr, site_import, "MERGE_RIVERS", self._merge)
        self.path = os.path.join(tempfile.mkdtemp(), "sites.xlsx")
        wb = Workbook()
        summary = wb.active
        summary.title = "종합"
        summary.append([None, '하천', '카메라', '대상'])
        ws = wb.create_sheet("OO청_설치개소")
        ws.append(HEAD)
        ws.append(row(1, '다천', 'GA-002', '상류', '경기도 가나시 다라동 12-3', '192.0.2.119'))
        ws.append(row(2, '나강(하류) ', 'NA-001', '하류', '서울시 마바구 사아동 45', '192.0.2.231'))
        ws.append(row(3, '나강(하류)', 'NA-002', '하류', '서울시 마바구', None))          # IP 없음
        ws.append(row(4, '나강(하류)', 'NA-003', '하류', '서울시', '192.0.300'))            # 형식 오류
        ws.append(row(5, '나강(하류)', 'NA-004', '하류', '서울시', '192.0.2.231'))         # IP 중복
        ws.append([None] * 19)                                                           # 빈 줄
        wb.create_sheet("Sheet1").append(['ManagementCode', 'SourceIP', 'ID', 'Password'])  # 카메라 계정 — 무시
        wb.save(self.path)

    def test_read_finds_sheet_and_cleans_values(self):
        sites, problems, sheet = site_import.read_sites(self.path)
        self.assertEqual(sheet, "OO청_설치개소")
        self.assertEqual([s["site_code"] for s in sites], ["GA-002", "NA-001"])
        self.assertEqual(sites[1]["river"], "나강(하류)")              # 뒤 공백 정리 → 같은 그룹
        self.assertEqual(sites[0]["ip"], "192.0.2.119")              # 접속 IP 열만 (카메라 IP 아님)
        self.assertEqual(len(problems), 3)
        self.assertTrue(any("NA-002" in p and "IP 없음" in p for p in problems))
        self.assertTrue(any("NA-003" in p and "형식" in p for p in problems))
        self.assertTrue(any("NA-004" in p and "겹침" in p for p in problems))

    def test_merge_keeps_existing_account_and_renames_to_site_code(self):
        sites, _, _ = site_import.read_sites(self.path)
        test = dict(SESSION_DEFAULTS, name="TEST", host="192.0.2.119", rdp_user="operator",
                    rdp_password="pw", resolution="fit", last_connected=123, favorite=True, note="메모")
        other = dict(SESSION_DEFAULTS, name="사무실 PC", host="10.0.0.5")
        plan = site_import.merge_sites([test, other], sites, site_import.pick_account([test, other]))
        by = {s["name"]: s for s in plan["sessions"]}
        self.assertEqual(plan["updated"], ["GA-002"])
        self.assertEqual(plan["added"], ["NA-001"])
        hj = by["GA-002"]
        self.assertEqual((hj["group"], hj["flow"], hj["site_code"]), ("다천", "상류", "GA-002"))
        self.assertEqual((hj["rdp_password"], hj["last_connected"], hj["favorite"], hj["note"]), ("pw", 123, True, "메모"))
        self.assertEqual((by["NA-001"]["rdp_user"], by["NA-001"]["rdp_password"], by["NA-001"]["resolution"]),
                         ("operator", "pw", "fit"))                 # 새 개소는 대표 계정
        self.assertFalse(by["NA-001"]["favorite"])
        self.assertIn("사무실 PC", by)                                  # 목록에 없는 세션은 유지
        # 두 번 가져와도 그대로
        again = site_import.merge_sites(plan["sessions"], sites, None)
        self.assertEqual((again["added"], again["updated"]), ([], []))
        self.assertEqual(len(again["sessions"]), 3)

    def test_name_clash_gets_suffix(self):
        sites, _, _ = site_import.read_sites(self.path)
        clash = dict(SESSION_DEFAULTS, name="NA-001", host="10.9.9.9")
        names = [s["name"] for s in site_import.merge_sites([clash], sites)["sessions"]]
        self.assertIn("NA-001 (2)", names)

    def test_not_a_site_file(self):
        p = os.path.join(tempfile.mkdtemp(), "x.xlsx")
        wb = Workbook()
        wb.active.append(["이름", "주소"])
        wb.save(p)
        with self.assertRaises(ValueError):
            site_import.read_sites(p)

    def test_imjin_units_merge_into_one_group(self):
        self.assertEqual(site_import.river_group("가강(1구역)"), ("가강", "1구역"))
        self.assertEqual(site_import.river_group("가강"), ("가강", ""))
        self.assertEqual(site_import.river_group("나강(하류)"), ("나강(하류)", ""))   # 목록에 없는 하천은 그대로

    def test_merge_rivers_from_local_rules_file(self):
        """묶을 하천 목록은 config/site_rules.json 에서 읽고, 파일이 없거나 깨져도 빈 목록."""
        d = tempfile.mkdtemp()
        old = site_import.RULES_FILE
        self.addCleanup(setattr, site_import, "RULES_FILE", old)
        site_import.RULES_FILE = os.path.join(d, "site_rules.json")
        self.assertEqual(site_import._load_merge_rivers(), ())          # 파일 없음
        with open(site_import.RULES_FILE, "w", encoding="utf-8") as f:
            f.write('{"merge_rivers": ["가강", "나강"], "ip_headers": ["장비 주소"]}')
        self.assertEqual(site_import._load_merge_rivers(), ("가강", "나강"))
        self.assertEqual(site_import._extra_ip_headers(), {"장비주소": "ip"})    # 공백 무시
        with open(site_import.RULES_FILE, "w", encoding="utf-8") as f:
            f.write("{깨진 파일")
        self.assertEqual(site_import._load_merge_rivers(), ())
        site = {"site_code": "KA-001", "river": "가강(5구역)", "flow": "", "address": "", "ip": "10.1.1.1"}
        s = site_import.merge_sites([], [site])["sessions"][0]
        self.assertEqual((s["group"], s["note"]), ("가강", "5구역"))
        mine = dict(s, note="내 메모")                                              # 사용자 메모는 보존
        self.assertEqual(site_import.merge_sites([mine], [site])["sessions"][0]["note"], "내 메모")

    def test_short_address(self):
        self.assertEqual(site_import.short_address("경기도 가나시 다라동 12-3"), "가나시 다라동 12-3")
        self.assertEqual(site_import.short_address("서울시 마바구 사아동 45"), "마바구 사아동 45")
        self.assertEqual(site_import.short_address("가나시 다라동"), "가나시 다라동")


if __name__ == "__main__":
    unittest.main()
