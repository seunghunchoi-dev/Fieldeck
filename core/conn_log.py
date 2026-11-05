"""장비 연결 상태 로그 — 텍스트 로그 파일로 디스크에 바로 저장 (설계문서 6-8).

저장 위치: %LOCALAPPDATA%\\Fieldeck\\logs\\conn_YYYY-MM-DD.log  (하루 1파일, UTF-8)
- 프로그램 폴더 밖이라 프로그램을 지우거나 다시 설치해도 남는다.
- 기록은 별도 스레드가 곧바로 디스크에 확정(flush+fsync) → 화면은 멈추지 않고, 갑자기 꺼져도 그 전 기록은 남음.
- 자동 삭제 없음.

한 줄 형식 ( | 로 구분, 메모장·엑셀에서 바로 읽힘):
    2026-11-03 14:02:11 | 장비 | SITE-PC | 192.0.2.119:3389 | 정상 → 오프라인 | 정상 2시간 3분 유지
    시각 | 구분(프로그램/장비/접속) | 이름 | 주소 | 내용 | 상세

백업: export_zip(경로) → 모든 로그를 zip 하나로.
복원: import_zip(경로) → 같은 날짜 파일은 줄 단위로 합침(중복 제거, 시간순). 기존 기록은 지우지 않는다.
"""
import io
import os
import queue
import re
import threading
import time
import zipfile

KIND_APP = "프로그램"
KIND_DEVICE = "장비"
KIND_SESSION = "접속"
ARROW = " → "
SEP = " | "

NAME_RE = re.compile(r"^conn_(\d{4}-\d{2}-\d{2})\.log$")
LINE_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \| ")
MAX_IMPORT_FILE = 50 * 1024 * 1024    # 복원 시 파일 하나 최대 크기 (손상·이상 파일 방지)


def default_dir():
    from core import appinfo
    return appinfo.log_dir()


def _clean(v):
    """칸 구분자·줄바꿈이 섞이지 않게 정리."""
    return " ".join(str(v if v is not None else "").replace("|", "/").split())


def duration_text(sec):
    sec = int(max(sec, 0))
    if sec < 60:
        return "%d초" % sec
    if sec < 3600:
        return "%d분" % (sec // 60)
    if sec < 86400:
        return "%d시간 %d분" % (sec // 3600, sec % 3600 // 60)
    return "%d일 %d시간" % (sec // 86400, sec % 86400 // 3600)


def parse_line(line):
    """한 줄 → dict (형식이 아니면 None)."""
    line = line.rstrip("\r\n")
    if not LINE_RE.match(line):
        return None
    parts = line.split(SEP, 5)
    while len(parts) < 6:
        parts.append("")
    ts_txt, kind, name, addr, event, detail = parts
    try:
        ts = time.mktime(time.strptime(ts_txt, "%Y-%m-%d %H:%M:%S"))
    except ValueError:
        return None
    return {"ts": ts, "time": ts_txt, "kind": kind, "name": name, "addr": addr,
            "event": event, "detail": detail}


class ConnLog:
    def __init__(self, folder=None):
        self.dir = folder or default_dir()
        self._lock = threading.Lock()      # 파일 쓰기·복원이 겹치지 않게
        self._q = queue.Queue()
        self._writer = None
        self.error = None          # 마지막 쓰기 오류 (화면에 알릴 때 사용)

    # ------------------------------------------------------------------ 쓰기
    # 화면이 멈추지 않도록 실제 디스크 쓰기는 별도 스레드가 한다 (fsync가 줄마다 약 3ms).
    # 대기 중인 줄을 모아 파일마다 한 번만 fsync → 장비 여러 대가 동시에 바뀌어도 빠름.
    def path_for(self, day):
        return os.path.join(self.dir, "conn_%s.log" % day)

    def write(self, kind, name="", addr="", event="", detail="", ts=None):
        ts = time.time() if ts is None else ts
        lt = time.localtime(ts)
        line = SEP.join([time.strftime("%Y-%m-%d %H:%M:%S", lt), _clean(kind), _clean(name), _clean(addr),
                         _clean(event), _clean(detail)]).rstrip() + "\n"
        self._q.put((self.path_for(time.strftime("%Y-%m-%d", lt)), line))
        if self._writer is None:
            self._writer = threading.Thread(target=self._run, daemon=True, name="conn-log")
            self._writer.start()

    def flush(self):
        """대기 중인 기록이 모두 디스크에 확정될 때까지 기다림 (종료·백업·읽기 전에 호출)."""
        if self._writer is not None:
            self._q.join()

    def _run(self):
        while True:
            batch = [self._q.get()]
            while True:
                try:
                    batch.append(self._q.get_nowait())
                except queue.Empty:
                    break
            by_path = {}
            for path, line in batch:
                by_path.setdefault(path, []).append(line)
            with self._lock:
                try:
                    os.makedirs(self.dir, exist_ok=True)
                    for path, lines in by_path.items():
                        with open(path, "a", encoding="utf-8", newline="\n") as f:
                            f.write("".join(lines))
                            f.flush()
                            os.fsync(f.fileno())
                    self.error = None
                except OSError as e:     # 로그 실패가 프로그램을 멈추게 하지 않는다
                    self.error = str(e)
            for _ in batch:
                self._q.task_done()

    def app(self, event, detail="", ts=None):
        self.write(KIND_APP, event=event, detail=detail, ts=ts)

    def device(self, name, addr, old, new, detail="", ts=None):
        self.write(KIND_DEVICE, name, addr, "%s%s%s" % (old, ARROW, new), detail, ts)

    def session(self, name, addr, state, detail="", ts=None):
        self.write(KIND_SESSION, name, addr, state, detail, ts)

    # ------------------------------------------------------------------ 읽기
    def files(self):
        """[(날짜, 경로)] 날짜순. (잠금 안에서 부르지 말 것 — flush가 쓰기 스레드를 기다림)"""
        self.flush()
        try:
            names = os.listdir(self.dir)
        except OSError:
            return []
        out = [(m.group(1), os.path.join(self.dir, n)) for n in names for m in [NAME_RE.match(n)] if m]
        return sorted(out)

    def recent(self, limit=300, kind=None):
        """최근 기록부터 최대 limit개 (dict 목록, 최신순)."""
        out = []
        for _, path in reversed(self.files()):
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
            except OSError:
                continue
            for ln in reversed(lines):
                e = parse_line(ln)
                if e and (kind is None or e["kind"] == kind):
                    out.append(e)
                    if len(out) >= limit:
                        return out
        return out

    def summary(self):
        """(파일 수, 첫 날짜, 마지막 날짜, 전체 바이트)"""
        fs = self.files()
        size = sum(os.path.getsize(p) for _, p in fs if os.path.exists(p))
        return len(fs), (fs[0][0] if fs else None), (fs[-1][0] if fs else None), size

    # ------------------------------------------------------------------ 백업·복원
    def export_zip(self, zpath):
        """모든 로그를 zip으로. 반환: 파일 수."""
        fs = self.files()
        tmp = zpath + ".tmp"
        with self._lock:
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
                for _, p in fs:
                    z.write(p, os.path.basename(p))
            os.replace(tmp, zpath)
        return len(fs)

    def import_zip(self, zpath):
        """zip의 로그를 합쳐 넣는다. 반환: {'files': 처리 파일 수, 'added': 추가된 줄 수, 'skipped': [건너뛴 이름]}"""
        res = {"files": 0, "added": 0, "skipped": []}
        self.flush()                   # 잠금 전에: 대기 중인 기록부터 확정
        with zipfile.ZipFile(zpath) as z:
            members = []
            for info in z.infolist():
                base = info.filename.replace("\\", "/").rsplit("/", 1)[-1]   # 폴더 경로 무시 (zip 경로 공격 방지)
                if info.is_dir():
                    continue
                if not NAME_RE.match(base) or info.file_size > MAX_IMPORT_FILE:
                    res["skipped"].append(info.filename)
                    continue
                members.append((base, info))
            with self._lock:
                os.makedirs(self.dir, exist_ok=True)
                for base, info in members:
                    text = io.TextIOWrapper(z.open(info), encoding="utf-8", errors="replace").read()
                    incoming = [ln.rstrip("\r\n") for ln in text.splitlines() if LINE_RE.match(ln)]
                    res["added"] += self._merge(os.path.join(self.dir, base), incoming)
                    res["files"] += 1
        return res

    def _merge(self, path, incoming):
        existing = []
        if os.path.exists(path):
            with open(path, encoding="utf-8", errors="replace") as f:
                existing = [ln.rstrip("\r\n") for ln in f if ln.strip()]
        have = set(existing)
        new = []
        for ln in incoming:
            if ln not in have:
                have.add(ln)
                new.append(ln)
        if not new:
            return 0
        # 시각(앞 19자) 기준 정렬. 같은 시각은 원래 순서 유지 (sorted는 안정 정렬)
        merged = sorted(existing + new, key=lambda s: s[:19])
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(merged) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        return len(new)
