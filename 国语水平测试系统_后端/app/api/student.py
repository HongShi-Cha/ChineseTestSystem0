"""学生端接口。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_student
from app.core.response import ok
from app.db.session import get_db
from app.services.exam_service import ExamService

router = APIRouter(prefix="/api/student", tags=["student"])


@router.get("/dashboard")
def dashboard(
    user: dict = Depends(require_student), db: Session = Depends(get_db)
) -> dict:
    """学生首页数据（dashboard.html）。"""
    return ok(ExamService(db).get_dashboard(user["id"]))