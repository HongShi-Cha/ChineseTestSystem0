"""第 1 步的验证接口：确认服务起来了、数据库连上了、种子数据在不在。"""
from datetime import datetime

from fastapi import APIRouter
from sqlalchemy import func, select

from app.core.config import settings
from app.core.response import ok
from app.db.session import SessionLocal, ping
from app.models.exam_record import ExamRecord
from app.models.question import Question
from app.models.user import User

router = APIRouter(prefix="/api", tags=["health"])


def _counts() -> dict:
    """统计各表行数，顺便验证 ORM 映射是否正确。"""
    try:
        with SessionLocal() as db:
            return {
                "users": db.scalar(select(func.count()).select_from(User)) or 0,
                "questions": db.scalar(select(func.count()).select_from(Question)) or 0,
                "exam_records": db.scalar(select(func.count()).select_from(ExamRecord)) or 0,
            }
    except Exception as exc:  # noqa: BLE001 - 探活不应该把异常抛出去
        return {"error": str(exc)}


@router.get("/health")
def health() -> dict:
    return ok(
        {
            "status": "UP",
            "app": settings.app_name,
            "scoring_mode": settings.scoring_mode,
            "database": "UP" if ping() else "DOWN",
            "counts": _counts(),
            "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )


@router.get("/check")
def check() -> dict:
    """更轻量的探活接口。"""
    return ok({"status": "UP"})