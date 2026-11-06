"""엑셀 백업 / 복원 화면.

backup_to_excel(parent, store)                     → 저장한 경로 또는 None
restore_from_excel(parent, store, open_names)      → 복원 요약 dict 또는 None (store는 이미 저장된 상태)
"""
import os
import time

from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout,
                             QInputDialog, QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton,
                             QRadioButton, QVBoxLayout)

from core import excel_io, site_import
from ui.icons import icon
from ui.theme import C


def _docs_dir():
    d = os.path.join(os.path.expanduser("~"), "Documents")
    return d if os.path.isdir(d) else os.path.expanduser("~")


def _label(text, obj=None, wrap=True):
    lb = QLabel(text)
    if obj:
        lb.setObjectName(obj)
    lb.setWordWrap(wrap)
    return lb


# =========================================================================== 백업
class ExportDialog(QDialog):
    def __init__(self, parent, count):
        super().__init__(parent)
        self.setWindowTitle("엑셀로 백업")
        self.setMinimumWidth(460)
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 22, 24, 20)
        v.setSpacing(10)
        t = _label("세션 %d개를 엑셀 파일로 저장합니다" % count, "heroTitle")
        t.setStyleSheet("font-size:17px;")
        v.addWidget(t)
        v.addWidget(_label("이름·그룹·주소·포트·계정·해상도·클립보드·즐겨찾기·메모·파일 전송 설정·마지막 접속까지\n"
                           "모든 항목이 저장됩니다. '엑셀에서 복원'으로 그대로 되살릴 수 있어요.", "heroSub"))
        v.addSpacing(6)
        # 파일 암호 없이 일반 엑셀로 저장. 기본은 비밀번호까지 모두 포함.
        self.inc = QCheckBox("비밀번호(원격·전송)도 포함")
        self.inc.setChecked(True)
        self.inc.toggled.connect(self._toggle)
        v.addWidget(self.inc)
        self.note = _label("", "heroSub")
        self.note.setStyleSheet("font-size:11px;")
        v.addWidget(self.note)
        self._toggle(True)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("취소")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("저장할 위치 선택…")
        ok.setObjectName("primary")
        ok.setIcon(icon("download", "#FFFFFF", 16))
        ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        v.addLayout(row)

    def _toggle(self, on):
        if on:
            self.note.setText("엑셀을 열면 비밀번호가 그대로 보입니다. 파일 보관·전달에 주의하세요.")
            self.note.setStyleSheet("color:%s; font-size:11px;" % C["warn"])
        else:
            self.note.setText("비밀번호 없이 저장합니다. 재설치 후 복원하면 비밀번호는 다시 입력해야 합니다.")
            self.note.setStyleSheet("font-size:11px;")

    def options(self):
        return self.inc.isChecked()


def backup_to_excel(parent, store):
    dlg = ExportDialog(parent, len(store.sessions))
    if not dlg.exec():
        return None
    inc = dlg.options()
    default = os.path.join(_docs_dir(), "Fieldeck_세션백업_%s.xlsx" % time.strftime("%Y%m%d_%H%M"))
    path, _ = QFileDialog.getSaveFileName(parent, "엑셀 백업 저장", default, "Excel 파일 (*.xlsx)")
    if not path:
        return None
    if not path.lower().endswith(".xlsx"):
        path += ".xlsx"
    try:
        excel_io.export_sessions(path, store.sessions, include_password=inc)
    except PermissionError:
        QMessageBox.warning(parent, "백업 실패", "파일을 저장할 수 없습니다.\n엑셀에서 같은 파일이 열려 있으면 닫고 다시 시도해 주세요.")
        return None
    except Exception as e:  # noqa: BLE001 — 사용자에게 원인 표시
        QMessageBox.warning(parent, "백업 실패", "저장 중 오류가 났습니다.\n%s" % e)
        return None
    note = "비밀번호 포함" if inc else "비밀번호 제외"
    box = QMessageBox(parent)
    box.setWindowTitle("백업 완료")
    box.setText("세션 %d개를 저장했습니다. (%s)\n\n%s" % (len(store.sessions), note, path))
    open_btn = box.addButton("폴더 열기", QMessageBox.ButtonRole.ActionRole)
    box.addButton("확인", QMessageBox.ButtonRole.AcceptRole)
    box.exec()
    if box.clickedButton() is open_btn:
        import subprocess
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    return path


def save_template(parent):
    """빈 세션 목록 입력 양식 저장 → 경로 또는 None."""
    default = os.path.join(_docs_dir(), "Fieldeck_세션목록_양식.xlsx")
    path, _ = QFileDialog.getSaveFileName(parent, "세션 목록 양식 저장", default, "Excel 파일 (*.xlsx)")
    if not path:
        return None
    if not path.lower().endswith(".xlsx"):
        path += ".xlsx"
    try:
        excel_io.export_template(path)
    except PermissionError:
        QMessageBox.warning(parent, "저장 실패", "파일을 저장할 수 없습니다.\n엑셀에서 같은 파일이 열려 있으면 닫고 다시 시도해 주세요.")
        return None
    box = QMessageBox(parent)
    box.setWindowTitle("양식 저장 완료")
    box.setText("빈 양식을 저장했습니다.\n\n%s\n\n한 줄에 PC 하나씩 채운 뒤 '엑셀에서 복원'으로 불러오세요.\n"
                "(작성 방법은 파일의 '안내' 시트에 있습니다)" % path)
    open_btn = box.addButton("파일 열기", QMessageBox.ButtonRole.ActionRole)
    box.addButton("확인", QMessageBox.ButtonRole.AcceptRole)
    box.exec()
    if box.clickedButton() is open_btn:
        os.startfile(path)
    return path


# =========================================================================== 복원
class RestoreDialog(QDialog):
    def __init__(self, parent, store, rows, problems, has_pw, path, open_names):
        super().__init__(parent)
        self.store, self.rows, self.open_names = store, rows, set(open_names)
        self.plan = None
        self.setWindowTitle("엑셀에서 복원")
        self.setMinimumWidth(520)
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 22, 24, 20)
        v.setSpacing(10)
        t = _label("세션 %d개를 불러왔어요" % len(rows), "heroTitle")
        t.setStyleSheet("font-size:17px;")
        v.addWidget(t)
        sub = os.path.basename(path) + ("  ·  비밀번호 포함" if has_pw else "  ·  비밀번호 없음 (기존 세션은 기존 비밀번호 유지)")
        v.addWidget(_label(sub, "heroSub"))

        if problems:
            v.addWidget(_label("읽지 못한 줄 %d개 (이 줄들은 빼고 복원합니다)" % len(problems), "fieldLabel"))
            lst = QListWidget()
            lst.addItems(problems)
            lst.setMaximumHeight(110)
            lst.setStyleSheet("QListWidget { color:%s; background:%s; border:1px solid %s; border-radius:8px; }"
                              % (C["warn"], C["surface"], C["border"]))
            v.addWidget(lst)

        v.addSpacing(4)
        v.addWidget(_label("복원 방식", "fieldLabel"))
        self.r_merge = QRadioButton("합치기 — 지금 목록은 그대로 두고, 엑셀의 세션을 추가·갱신")
        self.r_replace = QRadioButton("전체 바꾸기 — 지금 목록을 지우고 엑셀 내용으로 교체")
        self.r_merge.setChecked(True)
        grp = QButtonGroup(self)
        for r in (self.r_merge, self.r_replace):
            grp.addButton(r)
            r.toggled.connect(self._update)
            v.addWidget(r)
        dup_row = QHBoxLayout()
        self.dup_label = QLabel("같은 이름이 이미 있으면")
        self.dup = QComboBox()
        self.dup.addItem("엑셀 내용으로 덮어쓰기", "overwrite")
        self.dup.addItem("건너뛰기 (지금 것 유지)", "skip")
        self.dup.currentIndexChanged.connect(self._update)
        dup_row.addWidget(self.dup_label)
        dup_row.addWidget(self.dup, 1)
        v.addLayout(dup_row)

        self.summary = _label("", "heroSub")
        self.summary.setStyleSheet("font-size:13px; color:%s;" % C["text"])
        self.warn = _label("", "heroSub")
        self.warn.setStyleSheet("color:%s;" % C["err"])
        v.addSpacing(4)
        v.addWidget(self.summary)
        v.addWidget(self.warn)
        v.addWidget(_label("복원하기 전에 지금 목록을 데이터 폴더의 backup에 자동으로 보관합니다.", "heroSub"))

        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("취소")
        cancel.clicked.connect(self.reject)
        self.ok = QPushButton("복원")
        self.ok.setObjectName("primary")
        self.ok.setIcon(icon("upload", "#FFFFFF", 16))
        self.ok.clicked.connect(self._accept)
        row.addWidget(cancel)
        row.addWidget(self.ok)
        v.addLayout(row)
        self._update()

    def _mode(self):
        return "replace" if self.r_replace.isChecked() else "merge"

    def _update(self):
        merge = self._mode() == "merge"
        self.dup.setEnabled(merge)
        self.dup_label.setEnabled(merge)
        self.plan = excel_io.plan_restore(self.store.sessions, self.rows, self._mode(), self.dup.currentData())
        p = self.plan
        parts = ["새로 추가 %d" % len(p["added"]), "갱신 %d" % len(p["updated"])]
        if p["skipped"]:
            parts.append("건너뜀 %d" % len(p["skipped"]))
        if p["removed"]:
            parts.append("삭제 %d" % len(p["removed"]))
        self.summary.setText("결과:  " + "  ·  ".join(parts) + "   →  총 %d개" % len(p["sessions"]))
        warn = []
        if p["removed"]:
            names = ", ".join(p["removed"][:5]) + (" 외 %d개" % (len(p["removed"]) - 5) if len(p["removed"]) > 5 else "")
            warn.append("지금 목록에서 %d개가 지워집니다: %s" % (len(p["removed"]), names))
        closing = [n for n in p["removed"] if n in self.open_names]
        if closing:
            warn.append("그중 열려 있는 %d개 세션은 연결이 끊깁니다." % len(closing))
        self.warn.setText("\n".join(warn))
        self.warn.setVisible(bool(warn))
        self.ok.setEnabled(bool(p["added"] or p["updated"] or p["removed"]))

    def _accept(self):
        if self.plan["removed"]:
            ok = QMessageBox.question(self, "전체 바꾸기 확인",
                                      "지금 목록에서 세션 %d개가 지워집니다.\n(복원 전 목록은 데이터 폴더의 backup에 보관됩니다)\n\n계속할까요?"
                                      % len(self.plan["removed"]))
            if ok != QMessageBox.StandardButton.Yes:
                return
        self.accept()


def restore_from_excel(parent, store, open_names=()):
    path, _ = QFileDialog.getOpenFileName(parent, "복원할 엑셀 파일 선택", _docs_dir(), "Excel 파일 (*.xlsx)")
    if not path:
        return None
    pw = None
    try:
        if excel_io.is_encrypted(path):
            for i in range(3):
                pw, ok = QInputDialog.getText(parent, "파일 암호", "이 백업 파일은 암호가 걸려 있습니다.\n파일 암호:"
                                              if i == 0 else "암호가 맞지 않습니다. 다시 입력해 주세요:",
                                              QLineEdit.EchoMode.Password)
                if not ok:
                    return None
                try:
                    rows, problems, has_pw = excel_io.read_sessions(path, pw)
                    break
                except excel_io.BackupPasswordError:
                    continue
            else:
                QMessageBox.warning(parent, "복원 실패", "파일 암호가 3번 틀렸습니다.")
                return None
        else:
            rows, problems, has_pw = excel_io.read_sessions(path)
    except PermissionError:
        QMessageBox.warning(parent, "복원 실패", "파일을 열 수 없습니다.\n엑셀에서 열려 있으면 닫고 다시 시도해 주세요.")
        return None
    except Exception as e:  # noqa: BLE001
        QMessageBox.warning(parent, "복원 실패", "이 파일을 읽을 수 없습니다.\n%s" % e)
        return None
    if not rows:
        QMessageBox.information(parent, "복원", "불러올 세션이 없습니다." + ("\n\n" + "\n".join(problems[:10]) if problems else ""))
        return None

    dlg = RestoreDialog(parent, store, rows, problems, has_pw, path, open_names)
    if not dlg.exec():
        return None
    plan = dlg.plan
    backup = excel_io.safety_copy(store.path)
    old = store.sessions
    try:
        store.sessions = []
        for s in plan["sessions"]:
            store.upsert(s)
        store.save()
    except Exception as e:  # noqa: BLE001 — 실패하면 원래 목록으로 되돌림
        store.sessions = old
        QMessageBox.warning(parent, "복원 실패", "저장 중 오류가 나서 원래 목록으로 되돌렸습니다.\n%s" % e)
        return None
    plan["backup"] = str(backup) if backup else ""
    return plan


# =========================================================================== 장비 목록 가져오기
def apply_sessions(store, sessions):
    """세션 목록 저장 (실패하면 원래대로). 저장 전 현재 파일을 config/backup/에 보관 → 보관 경로."""
    backup = excel_io.safety_copy(store.path)
    old = store.sessions
    try:
        store.sessions = []
        for s in sessions:
            store.upsert(s)
        store.save()
    except Exception:
        store.sessions = old
        raise
    return backup


def import_sites(parent, store, open_names=()):
    """장비 목록 엑셀 → 세션 등록/갱신. 저장했으면 요약 dict, 아니면 None."""
    path, _ = QFileDialog.getOpenFileName(parent, "장비 목록 엑셀 선택", _docs_dir(), "Excel 파일 (*.xlsx)")
    if not path:
        return None
    try:
        sites, problems, sheet = site_import.read_sites(path)
    except Exception as e:  # noqa: BLE001 — 형식이 다른 파일 등
        QMessageBox.warning(parent, "가져오기 실패", "개소 목록을 읽을 수 없습니다.\n%s" % e)
        return None
    account = site_import.pick_account(store.sessions)
    plan = site_import.merge_sites(store.sessions, sites, account)
    ips, codes = {x["ip"] for x in sites}, {x["site_code"] for x in sites}
    busy = sorted(s["name"] for s in store.sessions if s["name"] in open_names
                  and (s["host"] in ips or s.get("site_code") in codes))   # 이름·주소가 바뀔 수 있는 열린 탭
    if busy:
        QMessageBox.information(parent, "가져오기", "갱신될 세션의 원격 탭이 열려 있습니다. 닫은 뒤 다시 시도해 주세요.\n\n"
                                + ", ".join(busy))
        return None
    msg = ["%s  (시트 '%s')" % (os.path.basename(path), sheet), "",
           "개소 %d곳" % len(sites),
           "  · 새로 등록 %d" % len(plan["added"]),
           "  · 기존 세션 갱신 %d%s" % (len(plan["updated"]),
                                     (" (%s)" % ", ".join(plan["updated"][:5])) if plan["updated"] else ""),
           "  · 변경 없음 %d" % len(plan["unchanged"])]
    if plan["added"]:
        msg += ["", "새 개소의 접속 계정: %s" % (account["rdp_user"] + " (비밀번호 포함, '%s' 세션과 같음)"
                                            % account["name"] if account else "없음 — 접속할 때 입력")]
    msg += ["", "이름 = 개소 번호, 그룹 = 하천명, 접속 주소 = 접속 IP 열.",
            "기존 세션의 계정·비밀번호·즐겨찾기·메모는 그대로 둡니다. 목록에 없는 세션은 지우지 않습니다."]
    if problems:
        msg += ["", "건너뛴 줄 %d개:" % len(problems)] + ["  " + p for p in problems[:8]]
        if len(problems) > 8:
            msg.append("  …")
    box = QMessageBox(parent)
    box.setWindowTitle("장비 목록 가져오기")
    box.setText("\n".join(msg))
    ok = box.addButton("가져오기", QMessageBox.ButtonRole.AcceptRole)
    box.addButton("취소", QMessageBox.ButtonRole.RejectRole)
    box.exec()
    if box.clickedButton() is not ok:
        return None
    try:
        plan["backup"] = str(apply_sessions(store, plan["sessions"]) or "")
    except Exception as e:  # noqa: BLE001
        QMessageBox.warning(parent, "가져오기 실패", "저장 중 오류가 나서 원래 목록으로 되돌렸습니다.\n%s" % e)
        return None
    return plan


# =========================================================================== 연결 로그 (설계문서 6-8)
def _size_text(n):
    return "%.1f MB" % (n / 1048576) if n >= 1048576 else "%d KB" % max(1, n // 1024)


def open_log_folder(parent, log):
    import subprocess
    os.makedirs(log.dir, exist_ok=True)
    subprocess.Popen(["explorer", os.path.normpath(log.dir)])


def backup_logs(parent, log):
    """모든 연결 로그를 zip 하나로 저장 → 경로 또는 None."""
    count, first, last, size = log.summary()
    if not count:
        QMessageBox.information(parent, "연결 로그 백업", "아직 저장된 연결 로그가 없습니다.\n\n%s" % log.dir)
        return None
    default = os.path.join(_docs_dir(), "Fieldeck_연결로그_%s.zip" % time.strftime("%Y%m%d_%H%M"))
    path, _ = QFileDialog.getSaveFileName(parent, "연결 로그 백업 저장", default, "ZIP 파일 (*.zip)")
    if not path:
        return None
    if not path.lower().endswith(".zip"):
        path += ".zip"
    try:
        n = log.export_zip(path)
    except Exception as e:  # noqa: BLE001
        QMessageBox.warning(parent, "백업 실패", "저장 중 오류가 났습니다.\n%s" % e)
        return None
    box = QMessageBox(parent)
    box.setWindowTitle("백업 완료")
    box.setText("연결 로그 %d일치(%s ~ %s, %s)를 저장했습니다.\n\n%s\n\n"
                "프로그램을 다시 설치한 뒤 '연결 로그 복원'으로 불러올 수 있습니다."
                % (n, first, last, _size_text(size), path))
    open_btn = box.addButton("폴더 열기", QMessageBox.ButtonRole.ActionRole)
    box.addButton("확인", QMessageBox.ButtonRole.AcceptRole)
    box.exec()
    if box.clickedButton() is open_btn:
        import subprocess
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    return path


def restore_logs(parent, log):
    """백업 zip의 로그를 현재 로그에 합친다 (기존 기록은 지우지 않음) → 결과 dict 또는 None."""
    path, _ = QFileDialog.getOpenFileName(parent, "연결 로그 백업 열기", _docs_dir(), "ZIP 파일 (*.zip)")
    if not path:
        return None
    try:
        res = log.import_zip(path)
    except Exception as e:  # noqa: BLE001 — 깨진 zip 등
        QMessageBox.warning(parent, "복원 실패", "로그 백업 파일을 읽을 수 없습니다.\n%s" % e)
        return None
    if not res["files"]:
        QMessageBox.warning(parent, "복원 실패", "이 파일에는 연결 로그(conn_날짜.log)가 없습니다.")
        return None
    msg = "%d일치 파일을 확인해 새 기록 %d줄을 합쳤습니다.\n(이미 있던 기록은 그대로 두고, 같은 줄은 한 번만 남깁니다.)" \
          % (res["files"], res["added"])
    if res["skipped"]:
        msg += "\n\n로그가 아니어서 건너뛴 파일 %d개" % len(res["skipped"])
    QMessageBox.information(parent, "복원 완료", msg)
    return res