"""考试接口（需登录；考试动作仅限学生）。"""
from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import require_student
from app.core.response import ok
from app.db.session import get_db
from app.services.exam_service import ExamService

router = APIRouter(prefix="/api/exam", tags=["exam"])


@router.post("/start")
def start(user: dict = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    """开始考试（随机组卷；已有未交卷的考试则继续）。"""
    return ok(ExamService(db).start_exam(user["id"]))


@router.post("/submit")
def submit(
    record_id: int = Form(..., alias="recordId"),
    type: int = Form(...),
    file: UploadFile = File(...),
    user: dict = Depends(require_student),
    db: Session = Depends(get_db),
) -> dict:
    """提交一题：multipart 表单 file=录音、recordId=考试记录、type=题型。"""
    return ok(ExamService(db).submit_section(user["id"], record_id, type, file))


@router.post("/{record_id}/finish")
def finish(
    record_id: int, user: dict = Depends(require_student), db: Session = Depends(get_db)
) -> dict:
    """交卷：算总分、定等级。"""
    return ok(ExamService(db).finish_exam(user["id"], record_id))


@router.get("/records")
def history(user: dict = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    """历史成绩列表（history.html 表格）。"""
    return ok(ExamService(db).list_history(user["id"]))


@router.get("/chart")
def chart(user: dict = Depends(require_student), db: Session = Depends(get_db)) -> dict:
    """成绩曲线数据（history.html 的 ECharts）。"""
    return ok(ExamService(db).get_chart_data(user["id"]))


@router.get("/records/{record_id}")
def report(
    record_id: int, user: dict = Depends(require_student), db: Session = Depends(get_db)
) -> dict:
    """单次成绩报告（report.html）。"""
    return ok(ExamService(db).get_report(user["id"], record_id))