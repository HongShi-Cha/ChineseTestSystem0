"""考试记录表 t_exam_record：一场考试一行。

paper_json 存这份试卷的完整内容（组卷后即定死，防止中途变题）。
"""
import json
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import STATUS_IN_PROGRESS
from app.db.base import Base


class ExamRecord(Base):
    __tablename__ = "t_exam_record"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    paper_json: Mapped[Optional[str]] = mapped_column(Text)
    total_score: Mapped[Optional[float]] = mapped_column(Float)
    level: Mapped[Optional[str]] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=STATUS_IN_PROGRESS)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.now)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # ---------- paper_json 读写 ----------
    @property
    def paper(self) -> dict:
        if not self.paper_json:
            return {}
        try:
            return json.loads(self.paper_json)
        except (ValueError, TypeError):
            return {}

    @paper.setter
    def paper(self, value: dict) -> None:
        self.paper_json = json.dumps(value, ensure_ascii=False)

    def stamp(self, fmt: str = "%Y-%m-%d %H:%M:%S") -> Optional[str]:
        return self.finished_at.strftime(fmt) if self.finished_at else None

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<ExamRecord {self.id} student={self.student_id} {self.status}>"