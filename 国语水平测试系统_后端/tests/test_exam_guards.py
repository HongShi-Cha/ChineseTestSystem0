"""第 9 步考试闭环加固的单元测试。

覆盖：服务端权威超时判定、重考次数上限、重复提交复用首次成绩、
录音上传大小限制、参考文本拼装。用例都不连数据库，直接就能跑。
"""
import io
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.core.config import settings
from app.core.constants import STATUS_IN_PROGRESS
from app.core.errors import BizException
from app.models.exam_record import ExamRecord
from app.models.exam_section_score import ExamSectionScore
from app.services.exam_service import ExamService


class FakeUpload:
    """模拟 FastAPI 的 UploadFile：只要 filename 和 file.read() 就够用。"""

    def __init__(self, content: bytes = b"", filename: str = "rec_1.pcm") -> None:
        self.file = io.BytesIO(content)
        self.filename = filename


class FakeDb:
    """只实现被调用到的 scalar()，用来替掉数据库会话。"""

    def __init__(self, finished_count: int = 0) -> None:
        self.finished_count = finished_count

    def scalar(self, *args, **kwargs) -> int:
        return self.finished_count


def make_record(seconds_ago: int) -> ExamRecord:
    return ExamRecord(
        student_id=1,
        status=STATUS_IN_PROGRESS,
        started_at=datetime.now() - timedelta(seconds=seconds_ago),
    )


# ============================================================
# 服务端权威超时
# ============================================================
def test_not_expired_within_exam_duration():
    assert ExamService._is_expired(make_record(settings.exam_duration_seconds - 60)) is False


def test_grace_period_still_allows_submit():
    """倒计时刚走完、但还在宽限期内：不算超时，在途的提交必须能落地。"""
    seconds_ago = settings.exam_duration_seconds + settings.exam_deadline_grace_seconds - 5
    assert ExamService._is_expired(make_record(seconds_ago)) is False


def test_expired_after_duration_plus_grace():
    seconds_ago = settings.exam_duration_seconds + settings.exam_deadline_grace_seconds + 5
    assert ExamService._is_expired(make_record(seconds_ago)) is True


def test_record_without_start_time_is_never_expired():
    """没有开始时间的脏数据不该被判超时，否则会被误交卷。"""
    record = ExamRecord(student_id=1, status=STATUS_IN_PROGRESS)
    assert ExamService._is_expired(record) is False
    assert ExamService._deadline_of(record) is None


def test_deadline_is_duration_plus_grace():
    record = make_record(0)
    deadline = ExamService._deadline_of(record)
    assert (deadline - record.started_at).total_seconds() == settings.exam_deadline_seconds


# ============================================================
# 重考次数上限
# ============================================================
def test_attempt_limit_blocks_when_used_up(monkeypatch):
    monkeypatch.setattr(settings, "max_exam_attempts", 2)
    service = ExamService(db=FakeDb(finished_count=2))
    with pytest.raises(BizException) as exc:
        service._ensure_attempt_allowed(1)
    assert "重考次数" in exc.value.message


def test_attempt_limit_allows_below_limit(monkeypatch):
    monkeypatch.setattr(settings, "max_exam_attempts", 3)
    ExamService(db=FakeDb(finished_count=2))._ensure_attempt_allowed(1)   # 不应抛异常


def test_attempt_limit_disabled_by_default(monkeypatch):
    """默认 0 = 不限次数：哪怕已经考了 99 场也照样放行。"""
    monkeypatch.setattr(settings, "max_exam_attempts", 0)
    ExamService(db=FakeDb(finished_count=99))._ensure_attempt_allowed(1)


# ============================================================
# 重复提交：直接复用首次成绩，不再多调一次评测
# ============================================================
def test_cached_payload_reuses_first_score():
    row = ExamSectionScore(record_id=5, type=3, score=26.5, total=30.0)
    row.detail = {"shengmu": 90}

    payload = ExamService._cached_payload(row, 5)

    assert payload["score"] == 26.5
    assert payload["total"] == 30.0
    assert payload["detail"] == {"shengmu": 90}
    assert payload["record_id"] == 5
    assert payload["title"]
    assert payload["cached"] is True


# ============================================================
# 录音上传大小限制
# ============================================================
def test_read_upload_accepts_content_within_limit(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_bytes", 1024)
    assert ExamService._read_upload(FakeUpload(b"x" * 1024)) == b"x" * 1024


def test_read_upload_rejects_oversize(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_bytes", 1024)
    with pytest.raises(BizException) as exc:
        ExamService._read_upload(FakeUpload(b"x" * 1025))
    assert "上限" in exc.value.message


def test_read_upload_handles_empty_file(monkeypatch):
    """浏览器不支持录音时会传空文件，这里要能正常读出空内容而不是报错。"""
    monkeypatch.setattr(settings, "max_upload_bytes", 1024)
    assert ExamService._read_upload(FakeUpload(b"")) == b""


def test_save_audio_writes_file_to_upload_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    service = ExamService(db=None)

    path, name = service._save_audio(7, 2, FakeUpload(b"pcm-data", "rec_2.pcm"))

    assert name == "rec_2.pcm"
    assert Path(path).name.startswith("rec_7_2_")
    assert Path(path).read_bytes() == b"pcm-data"


def test_save_audio_skips_when_filename_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    service = ExamService(db=None)

    assert service._save_audio(7, 2, FakeUpload(b"pcm", filename="")) == ("", "rec_7_2.wav")
    assert list(tmp_path.iterdir()) == []


# ============================================================
# 参考文本拼装（讯飞评测的前置条件）
# ============================================================
def test_reference_text_spaces_out_word_items():
    """词语题必须用空格分隔，否则讯飞回 48195「试题格式错误」。"""
    section = {"type": 2, "items": ["人民", "朋友", "孩子"]}
    assert ExamService._reference_text(section) == "人民 朋友 孩子"


def test_reference_text_spaces_out_single_char_items():
    section = {"type": 1, "items": ["爱", "白", "春"]}
    assert ExamService._reference_text(section) == "爱 白 春"


def test_reference_text_keeps_short_article_intact():
    """短文题要保留原文标点，不能被拆开。"""
    section = {"type": 3, "items": ["北京的秋天是美丽而宁静的。"]}
    assert ExamService._reference_text(section) == "北京的秋天是美丽而宁静的。"


# ============================================================
# 试卷可用性（决定是接着考还是重新组卷）
# ============================================================
def test_paper_is_usable_requires_all_four_types():
    record = ExamRecord(student_id=1, status=STATUS_IN_PROGRESS)

    record.paper = {"sections": [{"type": t, "items": ["x"]} for t in (1, 2, 3, 4)]}
    assert ExamService._paper_is_usable(record) is True

    record.paper = {"sections": [{"type": t, "items": ["x"]} for t in (1, 2, 3)]}
    assert ExamService._paper_is_usable(record) is False


def test_paper_is_usable_rejects_section_without_items():
    record = ExamRecord(student_id=1, status=STATUS_IN_PROGRESS)
    record.paper = {
        "sections": [{"type": t, "items": [] if t == 3 else ["x"]} for t in (1, 2, 3, 4)]
    }
    assert ExamService._paper_is_usable(record) is False


def test_paper_is_usable_rejects_empty_paper():
    record = ExamRecord(student_id=1, status=STATUS_IN_PROGRESS)
    assert ExamService._paper_is_usable(record) is False