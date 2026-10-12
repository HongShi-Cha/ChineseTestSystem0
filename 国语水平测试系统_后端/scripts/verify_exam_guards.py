"""第 9 步考试闭环加固的端到端验证（连真实 MySQL，跑完自动清理）。

覆盖：
    1. 超时自动交卷：旧考试超过"时长 + 宽限"后，重新进入考试页会先被服务端结算
    2. 超时后提交被拒：返回业务码 410，且考试记录被自动交卷
    3. 重考次数上限：MAX_EXAM_ATTEMPTS 用满后开始考试被拒
    4. 重复提交复用：同一题提交两次只评分一次，第二次直接返回首次成绩
    5. 上传大小上限：超过 MAX_UPLOAD_BYTES 直接拒绝
    6. 录音清理：只删过期录音，误伤不了别的文件

用法：
    .venv\\Scripts\\python.exe scripts\\verify_exam_guards.py
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import delete, select  # noqa: E402

import app.services.exam_service as exam_module  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.constants import (  # noqa: E402
    CODE_EXAM_EXPIRED,
    ROLE_STUDENT,
    STATUS_FINISHED,
    STATUS_IN_PROGRESS,
)
from app.core.errors import BizException  # noqa: E402
from app.core.security import random_salt, hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.exam_record import ExamRecord  # noqa: E402
from app.models.exam_section_score import ExamSectionScore  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.exam_service import ExamService  # noqa: E402
from app.services.file_cleanup import cleanup_expired_uploads  # noqa: E402
from app.services.scoring.mock import MockScoringService  # noqa: E402

PROBE_USERNAME = "guard_probe"
PASSED: list[str] = []
FAILED: list[str] = []


class FakeUpload:
    """替掉 FastAPI 的 UploadFile（只需要 filename + file.read()）。"""

    def __init__(self, content: bytes = b"", filename: str = "rec_probe.pcm") -> None:
        self.file = io.BytesIO(content)
        self.filename = filename


def check(ok: bool, label: str, detail: str = "") -> None:
    mark = "[PASS]" if ok else "[FAIL]"
    print(f"{mark} {label}{('  -> ' + detail) if detail else ''}", flush=True)
    (PASSED if ok else FAILED).append(label)


def cleanup(db) -> None:
    """把本次验证造出来的用户/记录/成绩清干净，保证数据库回到基线。"""
    user = db.scalar(select(User).where(User.username == PROBE_USERNAME))
    if user is None:
        return
    record_ids = list(
        db.scalars(select(ExamRecord.id).where(ExamRecord.student_id == user.id)).all()
    )
    if record_ids:
        db.execute(
            delete(ExamSectionScore).where(ExamSectionScore.record_id.in_(record_ids))
        )
        db.execute(delete(ExamRecord).where(ExamRecord.id.in_(record_ids)))
    db.execute(delete(User).where(User.id == user.id))
    db.commit()


def main() -> int:
    print("=" * 62)
    print("第 9 步 考试闭环加固 - 端到端验证")
    print("=" * 62)

    # 用模拟评分跑，避免无谓消耗讯飞额度
    exam_module.get_scoring_service = lambda: MockScoringService()

    original_max = settings.max_upload_bytes
    original_attempts = settings.max_exam_attempts
    db = SessionLocal()
    try:
        cleanup(db)
        salt = random_salt()
        user = User(
            username=PROBE_USERNAME,
            password=hash_password("probe-pwd", salt),
            salt=salt,
            name="闭环验证",
            role=ROLE_STUDENT,
            student_no=PROBE_USERNAME,
            class_name="验证班",
            created_at=datetime.now(),
        )
        db.add(user)
        db.commit()
        student_id = user.id

        service = ExamService(db)
        over_deadline = settings.exam_deadline_seconds + 60

        # ---------- 1. 超时自动交卷 ----------
        paper = service.start_exam(student_id)
        stale_id = paper["record_id"]
        check(
            paper["duration_seconds"] == settings.exam_duration_seconds,
            "组卷返回的倒计时取自服务端配置",
            f"duration_seconds={paper['duration_seconds']}",
        )

        stale = db.get(ExamRecord, stale_id)
        stale.started_at = datetime.now() - timedelta(seconds=over_deadline)
        db.commit()

        paper2 = service.start_exam(student_id)
        stale = db.get(ExamRecord, stale_id)
        check(
            stale.status == STATUS_FINISHED,
            "超时的旧考试被服务端自动交卷",
            f"record={stale_id} status={stale.status} score={stale.total_score}",
        )
        check(
            stale.finished_at is not None
            and abs((stale.finished_at - stale.started_at).total_seconds()
                    - settings.exam_duration_seconds) < 1,
            "自动交卷的结束时间记为真正到点的时刻（不含宽限）",
            f"finished_at={stale.finished_at}",
        )
        check(
            paper2["record_id"] != stale_id and paper2["status"] == STATUS_IN_PROGRESS,
            "重新进入考试会开一场新考试，而不是接着旧的无限加时",
            f"new_record={paper2['record_id']}",
        )

        # ---------- 2. 超时后提交被拒 ----------
        live = db.get(ExamRecord, paper2["record_id"])
        live.started_at = datetime.now() - timedelta(seconds=over_deadline)
        db.commit()

        code = None
        try:
            service.submit_section(student_id, paper2["record_id"], 1, FakeUpload(b"pcm"))
        except BizException as exc:
            code = exc.code
        check(
            code == CODE_EXAM_EXPIRED,
            "超时后提交单题被拒（业务码 410）",
            f"code={code}",
        )
        live = db.get(ExamRecord, paper2["record_id"])
        check(
            live.status == STATUS_FINISHED,
            "被拒的同时服务端已经把这场考试结算掉",
            f"status={live.status} score={live.total_score}",
        )

        # ---------- 3. 重考次数上限 ----------
        settings.max_exam_attempts = 1
        code = None
        try:
            service.start_exam(student_id)
        except BizException as exc:
            code = exc.code
        check(code == 400, "已完成的场次达到上限后，开始考试被拒绝", f"code={code}")
        settings.max_exam_attempts = 0

        # ---------- 4. 重复提交复用首次成绩 ----------
        paper3 = service.start_exam(student_id)
        record3 = paper3["record_id"]
        first = service.submit_section(student_id, record3, 1, FakeUpload(b"pcm" * 100))
        second = service.submit_section(student_id, record3, 1, FakeUpload(b"pcm" * 100))
        check(
            second.get("cached") is True and second["score"] == first["score"],
            "同一题重复提交直接复用首次成绩，不再调一次评测",
            f"first={first['score']} second={second['score']} cached={second.get('cached')}",
        )
        rows = db.scalars(
            select(ExamSectionScore).where(
                ExamSectionScore.record_id == record3, ExamSectionScore.type == 1
            )
        ).all()
        check(len(rows) == 1, "重复提交不会写出重复的成绩行", f"rows={len(rows)}")

        # ---------- 5. 上传大小上限 ----------
        settings.max_upload_bytes = 1024
        code = None
        try:
            service.submit_section(student_id, record3, 2, FakeUpload(b"x" * 2048))
        except BizException as exc:
            code = exc.code
        check(code == 400, "超过上限的录音被拒绝", f"code={code}")
        settings.max_upload_bytes = original_max

        # ---------- 6. 录音清理 ----------
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            stamp = time.time() - 30 * 86400
            old_file = tmp_path / "rec_1_1_old.pcm"
            old_file.write_bytes(b"x" * 32)
            os.utime(old_file, (stamp, stamp))
            fresh_file = tmp_path / "rec_2_1_new.pcm"
            fresh_file.write_bytes(b"x" * 32)
            stranger = tmp_path / "notes.txt"
            stranger.write_bytes(b"x" * 32)
            os.utime(stranger, (stamp, stamp))

            result = cleanup_expired_uploads(tmp_path, retention_days=14)
            check(
                result["deleted"] == 1 and not old_file.exists() and fresh_file.exists(),
                "录音清理只删过期文件，保留期内的录音不动",
                f"deleted={result['deleted']} kept={result['kept']}",
            )
            check(stranger.exists(), "录音清理不会误删非本系统的文件")

        # ---------- 收尾 ----------
        cleanup(db)
        print("-" * 62)
        print(f"通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
        for label in FAILED:
            print(f"  失败项：{label}")
        return 1 if FAILED else 0
    finally:
        settings.max_upload_bytes = original_max
        settings.max_exam_attempts = original_attempts
        db.close()


if __name__ == "__main__":
    sys.exit(main())