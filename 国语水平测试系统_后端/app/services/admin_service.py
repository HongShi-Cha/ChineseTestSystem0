"""管理端业务：控制台统计 / 学生列表 / 全部成绩 / 题库增删改查 / Excel 导入。

Mock data added, backend calls removed for Python demo.
"""
import logging
import math
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.constants import (
    ROLE_STUDENT,
    SECTION_TITLES,
    STATUS_FINISHED,
    TYPE_NAMES,
    TYPE_TOTALS,
)
from app.core.errors import BizException
from app.core.levels import level_of
from app.models.exam_record import ExamRecord
from app.models.exam_section_score import ExamSectionScore
from app.models.question import Question
from app.models.user import User
from app.schemas.question import QuestionIn

logger = logging.getLogger(__name__)

ALL_TYPES = (1, 2, 3, 4)


class AdminService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ============================================================
    # 控制台
    # ============================================================
    def stats(self) -> dict:
        student_count = self.db.scalar(
            select(func.count()).select_from(User).where(User.role == ROLE_STUDENT)
        ) or 0
        question_count = self.db.scalar(select(func.count()).select_from(Question)) or 0

        finished = self.db.scalars(
            select(ExamRecord)
            .where(ExamRecord.status == STATUS_FINISHED)
            .order_by(ExamRecord.finished_at.desc(), ExamRecord.id.desc())
        ).all()

        today = date.today().strftime("%Y-%m-%d")
        today_count = sum(
            1 for r in finished if r.finished_at and r.finished_at.strftime("%Y-%m-%d") == today
        )
        scores = [r.total_score for r in finished if r.total_score is not None]

        return {
            "student_count": student_count,
            "question_count": question_count,
            "today_exam_count": today_count,
            "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
            "type_averages": self._type_averages(finished),
            "recent_exams": [self._recent_item(r) for r in finished[:6]],
        }

    def _type_averages(self, records: list[ExamRecord]) -> list[dict]:
        """各题型平均分（管理端柱状图）。"""
        if not records:
            return []
        record_ids = [r.id for r in records]
        rows = self.db.scalars(
            select(ExamSectionScore).where(ExamSectionScore.record_id.in_(record_ids))
        ).all()

        buckets: dict[int, list[float]] = {t: [] for t in ALL_TYPES}
        for row in rows:
            if row.score is not None and row.type in buckets:
                buckets[row.type].append(row.score)

        return [
            {
                "type": type_no,
                "name": TYPE_NAMES[type_no],
                "avg": round(sum(values) / len(values), 1) if values else 0.0,
                "total": TYPE_TOTALS[type_no],
            }
            for type_no, values in buckets.items()
        ]

    def _recent_item(self, record: ExamRecord) -> dict:
        student = self.db.get(User, record.student_id)
        return {
            "record_id": record.id,
            "student_name": student.name if student else "-",
            "student_no": student.student_no if student else None,
            "class_name": student.class_name if student else "",
            "total_score": record.total_score,
            "level": record.level,
            "finished_at": _fmt(record.finished_at),
        }

    # ============================================================
    # 学生列表（含最近一次成绩）
    # ============================================================
    def list_students(self, keyword: str = "") -> list[dict]:
        stmt = select(User).where(User.role == ROLE_STUDENT)
        keyword = (keyword or "").strip()
        if keyword:
            like = f"%{keyword}%"
            stmt = stmt.where(
                or_(
                    User.name.like(like),
                    User.student_no.like(like),
                    User.class_name.like(like),
                    User.username.like(like),
                )
            )
        students = self.db.scalars(stmt.order_by(User.student_no)).all()

        result = []
        for student in students:
            records = self.db.scalars(
                select(ExamRecord)
                .where(
                    ExamRecord.student_id == student.id,
                    ExamRecord.status == STATUS_FINISHED,
                )
                .order_by(ExamRecord.finished_at.desc(), ExamRecord.id.desc())
            ).all()
            scores = [r.total_score for r in records if r.total_score is not None]
            latest = records[0] if records else None

            result.append(
                {
                    "id": student.id,
                    "student_no": student.student_no or student.username,
                    "name": student.name,
                    "class_name": student.class_name or "",
                    "exam_count": len(records),
                    "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
                    "last_score": latest.total_score if latest else None,
                    "last_level": latest.level if latest else "",
                    "last_finished_at": _fmt(latest.finished_at) if latest else None,
                }
            )
        return result

    def student_records(self, student_no: str) -> list[dict]:
        """某个学生的全部已完成成绩（管理端弹窗用）。"""
        student = self.db.scalar(select(User).where(User.student_no == student_no))
        if student is None:
            student = self.db.scalar(select(User).where(User.username == student_no))
        if student is None:
            raise BizException("学生不存在", 404)

        records = self.db.scalars(
            select(ExamRecord)
            .where(ExamRecord.student_id == student.id, ExamRecord.status == STATUS_FINISHED)
            .order_by(ExamRecord.finished_at.desc(), ExamRecord.id.desc())
        ).all()
        return [
            {
                "record_id": r.id,
                "total_score": r.total_score,
                "level": r.level,
                "finished_at": _fmt(r.finished_at),
            }
            for r in records
        ]

    # ============================================================
    # 全部成绩记录（分页 + 搜索）
    # ============================================================
    def list_records(self, keyword: str = "", page: int = 1, size: int = 10) -> dict:
        keyword = (keyword or "").strip()
        stmt = select(ExamRecord).where(ExamRecord.status == STATUS_FINISHED)

        if keyword:
            like = f"%{keyword}%"
            matched_ids = select(User.id).where(
                or_(User.name.like(like), User.student_no.like(like), User.class_name.like(like))
            )
            stmt = stmt.where(ExamRecord.student_id.in_(matched_ids))

        total = self.db.scalar(
            select(func.count()).select_from(stmt.subquery())
        ) or 0

        page = max(1, page)
        size = max(1, min(size, 100))
        total_pages = max(1, math.ceil(total / size))
        page = min(page, total_pages)

        rows = self.db.scalars(
            stmt.order_by(ExamRecord.finished_at.desc(), ExamRecord.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        ).all()

        return {
            "list": [self._recent_item(r) for r in rows],
            "total": total,
            "page": page,
            "size": size,
            "total_pages": total_pages,
        }

    def get_report(self, record_id: int) -> dict:
        from app.services.exam_service import ExamService

        record = self.db.get(ExamRecord, record_id)
        if record is None:
            raise BizException("考试记录不存在", 404)
        return ExamService(self.db).report_payload(record)

    # ============================================================
    # 题库管理
    # ============================================================
    def list_questions(
        self, type_no: int | None = None, keyword: str = "", page: int = 1, size: int = 10
    ) -> dict:
        stmt = select(Question)
        if type_no:
            stmt = stmt.where(Question.type == type_no)
        keyword = (keyword or "").strip()
        if keyword:
            like = f"%{keyword}%"
            stmt = stmt.where(or_(Question.content.like(like), Question.answer.like(like)))

        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        page = max(1, page)
        size = max(1, min(size, 100))
        total_pages = max(1, math.ceil(total / size))
        page = min(page, total_pages)

        rows = self.db.scalars(
            stmt.order_by(Question.id).offset((page - 1) * size).limit(size)
        ).all()

        return {
            "list": [row.to_dict() for row in rows],
            "total": total,
            "page": page,
            "size": size,
            "total_pages": total_pages,
        }

    def create_question(self, data: QuestionIn) -> dict:
        payload = data.normalized()
        if not payload["content"]:
            raise BizException("题目内容不能为空")
        question = Question(**payload, updated_at=datetime.now())
        self.db.add(question)
        self.db.commit()
        self.db.refresh(question)
        return question.to_dict()

    def update_question(self, question_id: int, data: QuestionIn) -> dict:
        question = self.db.get(Question, question_id)
        if question is None:
            raise BizException("题目不存在", 404)
        payload = data.normalized()
        if not payload["content"]:
            raise BizException("题目内容不能为空")
        for key, value in payload.items():
            setattr(question, key, value)
        question.updated_at = datetime.now()
        self.db.commit()
        self.db.refresh(question)
        return question.to_dict()

    def delete_question(self, question_id: int) -> None:
        question = self.db.get(Question, question_id)
        if question is None:
            raise BizException("题目不存在", 404)
        self.db.delete(question)
        self.db.commit()

    def upload_questions(self, upload) -> int:
        """Excel 批量导入题库（表头：题型, 题目, 答案/拼音, 难度）。"""
        filename = getattr(upload, "filename", "") or ""
        if not filename:
            raise BizException("请选择要上传的 Excel 文件")

        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise BizException("缺少依赖 openpyxl，请执行 pip install openpyxl", 500) from exc

        suffix = Path(filename).suffix.lower()
        if suffix not in (".xlsx", ".xlsm"):
            raise BizException("只支持 .xlsx 格式的题库文件")

        try:
            workbook = load_workbook(upload.file, read_only=True, data_only=True)
        except Exception as exc:  # noqa: BLE001 - 解析失败统一提示
            logger.warning("题库 Excel 解析失败：%s", exc)
            raise BizException("Excel 解析失败，请检查文件格式") from exc

        sheet = workbook.active
        added = 0
        now = datetime.now()
        for index, row in enumerate(sheet.iter_rows(values_only=True)):
            if index == 0:
                continue   # 跳过表头
            if not row or all(cell is None for cell in row):
                continue
            type_no = _to_int(row[0] if len(row) > 0 else None)
            content = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
            answer = str(row[2]).strip() if len(row) > 2 and row[2] is not None else ""
            difficulty = str(row[3]).strip() if len(row) > 3 and row[3] is not None else "简单"
            if type_no not in ALL_TYPES or not content:
                continue
            self.db.add(
                Question(
                    type=type_no,
                    content=content,
                    answer=answer,
                    difficulty=difficulty or "简单",
                    updated_at=now,
                )
            )
            added += 1

        self.db.commit()
        logger.info("题库 Excel 导入完成，新增 %s 条", added)
        return added


def _to_int(value) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return 0


def _fmt(value: datetime | None) -> str | None:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else None