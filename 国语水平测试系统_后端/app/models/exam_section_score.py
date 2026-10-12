"""考试各题得分表 t_exam_section_score：一场考试 4 行（题型 1-4）。"""
import json
from typing import Optional

from sqlalchemy import BigInteger, Float, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ExamSectionScore(Base):
    __tablename__ = "t_exam_section_score"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    record_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    type: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[Optional[float]] = mapped_column(Float)
    total: Mapped[Optional[float]] = mapped_column(Float)
    detail_json: Mapped[Optional[str]] = mapped_column(Text)

    @property
    def detail(self) -> dict:
        if not self.detail_json:
            return {}
        try:
            return json.loads(self.detail_json)
        except (ValueError, TypeError):
            return {}

    @detail.setter
    def detail(self, value: dict) -> None:
        self.detail_json = json.dumps(value, ensure_ascii=False)

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<ExamSectionScore record={self.record_id} type={self.type} score={self.score}>"