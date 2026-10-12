"""ORM 模型集合（导入即注册到 Base.metadata）。"""
from app.models.exam_record import ExamRecord
from app.models.exam_section_score import ExamSectionScore
from app.models.login_attempt import LoginAttempt
from app.models.question import Question
from app.models.user import User

__all__ = ["User", "Question", "ExamRecord", "ExamSectionScore", "LoginAttempt"]