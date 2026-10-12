"""考试核心业务：随机组卷 / 提交评分 / 交卷 / 成绩报告 / 历史曲线 / 学生首页。

Mock data added, backend calls removed for Python demo.

第 9 步考试闭环加固：服务端权威超时自动交卷、同一题重复提交只评分一次、
重考次数上限、录音上传大小限制。
"""
import logging
import random
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import (
    CODE_EXAM_EXPIRED,
    SECTION_TITLES,
    STATUS_FINISHED,
    STATUS_IN_PROGRESS,
    TYPE_COUNTS_FALLBACK,
    TYPE_PICK_COUNTS,
    TYPE_DURATIONS,
    TYPE_LIMIT_TEXTS,
    TYPE_COUNT_TEXTS,
    TYPE_NAMES,
    TYPE_TIPS,
    TYPE_TOTALS,
)
from app.core.errors import BizException
from app.core.levels import level_of
from app.models.exam_record import ExamRecord
from app.models.exam_section_score import ExamSectionScore
from app.models.question import Question
from app.models.user import User
from app.services.scoring import ScoreRequest, get_scoring_service

logger = logging.getLogger(__name__)

ALL_TYPES = (1, 2, 3, 4)

#: 交给讯飞评测时需要用空格分隔的题型（单字 / 词语）
SPACED_TYPES = (1, 2)

#: 读取上传录音时的分块大小（字节）
UPLOAD_CHUNK_SIZE = 1024 * 1024


class ExamService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ============================================================
    # 组卷
    # ============================================================
    def start_exam(self, student_id: int) -> dict:
        """开始考试：已有未交卷且未超时的考试就接着考，否则重新随机组卷。

        第 9 步加固：上一次考试若已超过"时长 + 宽限"，服务端先按超时自动交卷，再开新的
        一场。否则学生只要关掉浏览器，那场考试就永远挂在 IN_PROGRESS，重新进入等于无限加时。
        """
        record = self.db.scalar(
            select(ExamRecord)
            .where(ExamRecord.student_id == student_id, ExamRecord.status == STATUS_IN_PROGRESS)
            .order_by(ExamRecord.id.desc())
        )
        if record is not None:
            if self._is_expired(record):
                self._auto_finish(record, "学生重新进入考试页")
                record = None
            elif self._paper_is_usable(record):
                return self._paper_payload(record)

        # 重考次数上限（MAX_EXAM_ATTEMPTS=0 表示不限次数）
        self._ensure_attempt_allowed(student_id)

        if record is None:
            record = ExamRecord(
                student_id=student_id,
                status=STATUS_IN_PROGRESS,
                started_at=datetime.now(),
            )
            self.db.add(record)

        # 走到这里说明：没有未交卷的考试，或旧试卷已不可用（例如从 Java 版迁移过来的
        # 驼峰字段试卷）——两种情况都重新组一份卷写回同一条记录，避免脏数据卡住考试。
        self.db.flush()          # 先拿到自增 id，再写 paper_json
        record.paper = {"sections": self._build_sections()}
        # 重新组卷等于开新的一场：开始时间必须重置，否则新卷一出场就已经过期
        record.started_at = datetime.now()
        record.finished_at = None
        self.db.commit()
        self.db.refresh(record)
        logger.info("学生 %s 开始考试，记录号 %s", student_id, record.id)
        return self._paper_payload(record)

    def _build_sections(self) -> list[dict]:
        """随机组卷：每个题型随机抽题，题量不足时用内置默认题兜底。"""
        sections: list[dict] = []
        for type_no in ALL_TYPES:
            rows = list(
                self.db.scalars(select(Question).where(Question.type == type_no))
            )
            random.shuffle(rows)
            need = TYPE_PICK_COUNTS.get(type_no, 1)
            picked = [row.content for row in rows[:need]]
            # 题库为空（或不够）时用兜底题目补齐，保证考试能正常进行
            if len(picked) < need:
                fallback = TYPE_COUNTS_FALLBACK.get(type_no, [])
                picked.extend(fallback[: need - len(picked)])

            sections.append(
                {
                    "type": type_no,
                    "title": SECTION_TITLES[type_no],
                    "name": TYPE_NAMES[type_no],
                    "limit_text": TYPE_LIMIT_TEXTS[type_no],
                    "count_text": TYPE_COUNT_TEXTS[type_no],
                    "duration": TYPE_DURATIONS[type_no],
                    "tip": TYPE_TIPS[type_no],
                    "items": picked,
                }
            )
        return sections

    @staticmethod
    def _paper_payload(record: ExamRecord) -> dict:
        paper = record.paper or {}
        return {
            "record_id": record.id,
            "duration_seconds": settings.exam_duration_seconds,
            "status": record.status,
            "sections": [ExamService._normalize_section(s) for s in paper.get("sections", [])],
        }

    @classmethod
    def _paper_is_usable(cls, record: ExamRecord) -> bool:
        """旧试卷是否还能用：必须四个题型齐全且每题都有内容。

        从 Java 版迁移过来的记录字段是驼峰命名、结构也可能不同，
        这里直接判定为不可用，让 start_exam 重新组卷。
        """
        sections = (record.paper or {}).get("sections") or []
        if len(sections) != len(ALL_TYPES):
            return False
        types = {s.get("type") for s in sections}
        if types != set(ALL_TYPES):
            return False
        return all(s.get("items") for s in sections)

    @staticmethod
    def _normalize_section(section: dict) -> dict:
        """把板块结构补齐成前端需要的下划线字段，并兼容旧的驼峰字段。"""
        type_no = int(section.get("type") or 0)
        return {
            "type": type_no,
            "title": section.get("title") or SECTION_TITLES.get(type_no, ""),
            "name": section.get("name") or TYPE_NAMES.get(type_no, ""),
            "limit_text": section.get("limit_text")
            or section.get("limitText")
            or TYPE_LIMIT_TEXTS.get(type_no, ""),
            "count_text": section.get("count_text")
            or section.get("countText")
            or TYPE_COUNT_TEXTS.get(type_no, ""),
            "duration": section.get("duration") or TYPE_DURATIONS.get(type_no, 0),
            "tip": section.get("tip") or TYPE_TIPS.get(type_no, ""),
            "items": list(section.get("items") or []),
        }

    # ============================================================
    # 提交单题（录音上传 + 评分）
    # ============================================================
    def submit_section(self, student_id: int, record_id: int, type_no: int, upload) -> dict:
        # 先锁住考试记录行：同一场考试的重复提交（网络重试 / 多标签页 / 时间到与手动提交
        # 撞在一起）会在这里排好队，第二个人看到已有成绩就直接返回，不会再多调一次讯飞。
        record = self._own_record(student_id, record_id, lock=True)
        if record.status != STATUS_IN_PROGRESS:
            raise BizException("本场考试已交卷，不能再提交")

        if type_no not in ALL_TYPES:
            raise BizException("题型不正确")

        # 服务端权威超时：前端倒计时可以改系统时间绕过，这里才是最终裁判
        if self._is_expired(record):
            self._auto_finish(record, "提交时已超过考试截止时间")
            raise BizException("考试时间已到，系统已自动交卷，本题不再计分", CODE_EXAM_EXPIRED)

        row = self.db.scalar(
            select(ExamSectionScore).where(
                ExamSectionScore.record_id == record_id,
                ExamSectionScore.type == type_no,
            )
        )
        if row is not None and row.score is not None:
            logger.info("考试记录 %s 第 %s 题重复提交，直接返回已有成绩", record_id, type_no)
            return self._cached_payload(row, record_id)

        section = self._section_of(record, type_no)
        text = self._reference_text(section)

        audio_path, audio_name = self._save_audio(record_id, type_no, upload)
        result = get_scoring_service().score(
            ScoreRequest(
                record_id=record_id,
                type=type_no,
                text=text,
                audio_path=audio_path,
                audio_name=audio_name,
            )
        )

        if row is None:
            row = ExamSectionScore(record_id=record_id, type=type_no)
            self.db.add(row)
        row.score = result.score
        row.total = result.total
        row.detail = result.detail
        self.db.commit()

        payload = result.to_dict()
        payload["record_id"] = record_id
        payload["title"] = SECTION_TITLES[type_no]
        return payload

    @staticmethod
    def _reference_text(section: dict) -> str:
        """把题目内容拼成评测参考文本。

        单字 / 词语题用空格分隔：实测把 50 个词（101 个字）连成一串交给讯飞会被判
        48195「试题格式错误」，用空格分开就正常；单字题加空格同样能正常评测。
        短文题保持原文（标点照旧），命题说话传话题本身（实际由本地流利度评分处理）。
        """
        items = section.get("items") or []
        type_no = int(section.get("type") or 0)
        if type_no in SPACED_TYPES:
            return " ".join(str(x).strip() for x in items if str(x).strip())
        return "".join(str(x) for x in items)

    def _save_audio(self, record_id: int, type_no: int, upload) -> tuple[str, str]:
        """把上传的录音落盘，返回 (绝对路径, 原始文件名)。"""
        filename = getattr(upload, "filename", "") or f"rec_{record_id}_{type_no}.wav"
        if not getattr(upload, "filename", None):
            return "", filename

        upload_dir: Path = settings.upload_path
        upload_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d%H%M%S")
        suffix = Path(filename).suffix or ".wav"
        target = upload_dir / f"rec_{record_id}_{type_no}_{stamp}{suffix}"

        content = self._read_upload(upload)
        try:
            target.write_bytes(content)
        except Exception as exc:  # noqa: BLE001 - 落盘失败不应中断评分
            logger.warning("录音保存失败：%s", exc)
            return "", filename
        return str(target), filename

    @staticmethod
    def _read_upload(upload) -> bytes:
        """分块读取上传内容，超过 MAX_UPLOAD_BYTES 直接拒绝。

        公网部署必须设上限：否则任何人 POST 一个超大文件就能把内存和磁盘打满。
        分块读是为了不让超大请求一次性进内存。
        """
        limit = settings.max_upload_bytes
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = upload.file.read(UPLOAD_CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                logger.warning("录音超过上传上限（%s 字节），已拒绝", limit)
                raise BizException(
                    f"录音文件超过 {settings.max_upload_mb}MB 上限，请缩短录音后重试"
                )
            chunks.append(chunk)
        return b"".join(chunks)

    @staticmethod
    def _cached_payload(row: ExamSectionScore, record_id: int) -> dict:
        """重复提交时返回首次评分结果（结构同 ScoreResult.to_dict，多一个 cached 标记）。"""
        return {
            "type": row.type,
            "score": row.score,
            "total": row.total,
            "detail": row.detail,
            "record_id": record_id,
            "title": SECTION_TITLES.get(row.type, ""),
            "cached": True,
        }

    # ============================================================
    # 考试闭环保护：超时自动交卷 / 重考次数 / 上传上限
    # ============================================================
    @staticmethod
    def _deadline_of(record: ExamRecord) -> datetime | None:
        """本场考试的硬截止时间 = 开始时间 + 时长 + 宽限；没有开始时间就不判超时。"""
        if record.started_at is None:
            return None
        return record.started_at + timedelta(seconds=settings.exam_deadline_seconds)

    @classmethod
    def _is_expired(cls, record: ExamRecord) -> bool:
        deadline = cls._deadline_of(record)
        return deadline is not None and datetime.now() > deadline

    def _auto_finish(self, record: ExamRecord, reason: str) -> None:
        """服务端超时兜底：按已有得分结算交卷，避免考试永远挂在 IN_PROGRESS。"""
        # 结束时间记成"真正到点的那一刻"，而不是发现超时的时刻，成绩单上的用时才准确
        ended_at = (
            record.started_at + timedelta(seconds=max(0, settings.exam_duration_seconds))
            if record.started_at
            else datetime.now()
        )
        payload = self._settle(record, finished_at=ended_at)
        logger.warning(
            "考试记录 %s 超时自动交卷（%s）：总分 %s（%s）",
            record.id,
            reason,
            payload["total_score"],
            payload["level"],
        )

    def _ensure_attempt_allowed(self, student_id: int) -> None:
        """重考次数限制：已完成场次达到 MAX_EXAM_ATTEMPTS 就不再放行（0 = 不限）。"""
        limit = settings.max_exam_attempts
        if limit <= 0:
            return
        used = self.db.scalar(
            select(func.count())
            .select_from(ExamRecord)
            .where(ExamRecord.student_id == student_id, ExamRecord.status == STATUS_FINISHED)
        ) or 0
        if used >= limit:
            raise BizException(f"重考次数已用完（上限 {limit} 次），如需补考请联系管理员")

    # ============================================================
    # 交卷
    # ============================================================
    def finish_exam(self, student_id: int, record_id: int) -> dict:
        record = self._own_record(student_id, record_id)
        if record.status == STATUS_FINISHED:
            return self._finish_payload(record)

        payload = self._settle(record)
        logger.info(
            "学生 %s 交卷，记录 %s 总分 %s（%s）",
            student_id,
            record_id,
            payload["total_score"],
            payload["level"],
        )
        return payload

    def _settle(self, record: ExamRecord, finished_at: datetime | None = None) -> dict:
        """结算：未作答的题按 0 分计，算总分、定等级、置为已交卷。"""
        scores = self._scores_map(record.id)
        total = round(sum(scores.get(t, 0.0) for t in ALL_TYPES), 1)
        record.total_score = total
        record.level = level_of(total)
        record.status = STATUS_FINISHED
        record.finished_at = finished_at or datetime.now()
        self.db.commit()
        return self._finish_payload(record)

    @staticmethod
    def _finish_payload(record: ExamRecord) -> dict:
        return {
            "record_id": record.id,
            "total_score": record.total_score,
            "level": record.level,
            "status": record.status,
        }

    # ============================================================
    # 查询：报告 / 历史 / 曲线 / 首页
    # ============================================================
    def get_report(self, student_id: int, record_id: int) -> dict:
        record = self._own_record(student_id, record_id)
        return self.report_payload(record)

    def report_payload(self, record: ExamRecord) -> dict:
        """成绩报告：四道大题 + 声韵调详情（未提交的题 score 为 None）。"""
        student = self.db.get(User, record.student_id)
        scores = self._scores_map(record.id)
        rows = self.db.scalars(
            select(ExamSectionScore).where(ExamSectionScore.record_id == record.id)
        ).all()
        details = {row.type: row.detail for row in rows}

        sections = []
        for section in record.paper.get("sections", []):
            type_no = section["type"]
            sections.append(
                {
                    "type": type_no,
                    "title": section.get("title") or SECTION_TITLES.get(type_no, ""),
                    "score": scores.get(type_no),
                    "total": TYPE_TOTALS.get(type_no, 100.0),
                    "detail": details.get(type_no, {}),
                }
            )

        return {
            "record_id": record.id,
            "student_no": student.student_no if student else None,
            "student_name": student.name if student else None,
            "class_name": student.class_name if student else None,
            "total_score": record.total_score,
            "level": record.level,
            "status": record.status,
            "started_at": _fmt(record.started_at),
            "finished_at": _fmt(record.finished_at),
            "sections": sections,
        }

    def list_history(self, student_id: int) -> list[dict]:
        records = self.db.scalars(
            select(ExamRecord)
            .where(ExamRecord.student_id == student_id, ExamRecord.status == STATUS_FINISHED)
            .order_by(ExamRecord.finished_at.desc(), ExamRecord.id.desc())
        ).all()
        return [self.report_payload(record) for record in records]

    def get_chart_data(self, student_id: int) -> dict:
        """历史成绩曲线：按时间正序的日期 + 总分。"""
        history = self.list_history(student_id)
        ordered = list(reversed(history))
        return {
            "dates": [item["finished_at"] or "" for item in ordered],
            "scores": [item["total_score"] for item in ordered],
            "levels": [item["level"] for item in ordered],
        }

    def get_dashboard(self, student_id: int) -> dict:
        """学生首页：考试次数 / 平均分 / 最高分 / 当前等级 / 最近 5 次成绩。"""
        history = self.list_history(student_id)
        scores = [item["total_score"] or 0.0 for item in history]

        recent = [
            {
                "record_id": item["record_id"],
                "date": item["finished_at"],
                "score": item["total_score"],
                "level": item["level"],
            }
            for item in history[:5]
        ]

        return {
            "exam_count": len(history),
            "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
            "max_score": max(scores) if scores else None,
            "current_level": history[0]["level"] if history else "",
            "recent_exams": recent,
        }

    # ============================================================
    # 内部工具
    # ============================================================
    def _own_record(self, student_id: int, record_id: int, lock: bool = False) -> ExamRecord:
        """取自己的考试记录；lock=True 时加行锁（FOR UPDATE），串行化同一场考试的提交。"""
        if lock:
            record = self.db.scalar(
                select(ExamRecord).where(ExamRecord.id == record_id).with_for_update()
            )
        else:
            record = self.db.get(ExamRecord, record_id)
        if record is None or record.student_id != student_id:
            raise BizException("考试记录不存在", 404)
        return record

    def _scores_map(self, record_id: int) -> dict[int, float]:
        rows = self.db.scalars(
            select(ExamSectionScore).where(ExamSectionScore.record_id == record_id)
        ).all()
        return {row.type: row.score for row in rows if row.score is not None}

    @staticmethod
    def _section_of(record: ExamRecord, type_no: int) -> dict:
        for section in record.paper.get("sections", []):
            if section.get("type") == type_no:
                return section
        section = {"type": type_no, "items": []}
        return ExamService._normalize_section(section)


def _fmt(value: datetime | None) -> str | None:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else None


def today_str() -> str:
    return date.today().strftime("%Y-%m-%d")