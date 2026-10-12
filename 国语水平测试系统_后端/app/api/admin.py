"""管理端接口（需管理员角色，依赖注入统一把关）。"""
from typing import Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.response import ok
from app.db.session import get_db
from app.schemas.question import QuestionIn
from app.services.admin_service import AdminService
from app.services.file_cleanup import cleanup_expired_uploads

# ---------- 统计 / 学生 / 成绩 ----------
router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/stats")
def stats(user: dict = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    """控制台统计（admin/dashboard.html）。"""
    return ok(AdminService(db).stats())


@router.get("/students")
def students(
    keyword: str = "",
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """学生列表（含最近一次成绩），支持姓名/学号/班级搜索。"""
    return ok(AdminService(db).list_students(keyword))


@router.get("/students/{student_no}/records")
def student_records(
    student_no: str,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """某个学生的全部成绩（管理端弹窗）。"""
    return ok(AdminService(db).student_records(student_no))


@router.get("/exam-records")
def records(
    keyword: str = "",
    page: int = 1,
    size: int = 10,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """全部成绩记录（分页 + 搜索）。"""
    return ok(AdminService(db).list_records(keyword, page, size))


@router.get("/exam-records/{record_id}")
def record_report(
    record_id: int,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """查看任意一场考试的报告。"""
    return ok(AdminService(db).get_report(record_id))


@router.post("/uploads/cleanup")
def cleanup_uploads(user: dict = Depends(require_admin)) -> dict:
    """手动清理过期录音（保留天数见 UPLOAD_RETENTION_DAYS，0 表示永久保留）。"""
    return ok(cleanup_expired_uploads())


# ---------- 题库管理 ----------
question_router = APIRouter(prefix="/api/admin/questions", tags=["admin-questions"])


@question_router.get("")
def list_questions(
    type: Optional[int] = Query(default=None, ge=1, le=4),
    keyword: str = "",
    page: int = 1,
    size: int = 10,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """题库分页查询：?type=1&keyword=字&page=1&size=10。"""
    return ok(AdminService(db).list_questions(type, keyword, page, size))


@question_router.post("")
def create_question(
    payload: QuestionIn,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """新增题目。"""
    return ok(AdminService(db).create_question(payload))


@question_router.put("/{question_id}")
def update_question(
    question_id: int,
    payload: QuestionIn,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """编辑题目。"""
    return ok(AdminService(db).update_question(question_id, payload))


@question_router.delete("/{question_id}")
def delete_question(
    question_id: int,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """删除题目。"""
    AdminService(db).delete_question(question_id)
    return ok(message="删除成功")


@question_router.post("/upload")
def upload_questions(
    file: UploadFile = File(...),
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Excel 批量导入题库。"""
    added = AdminService(db).upload_questions(file)
    return ok({"added": added}, message=f"成功导入 {added} 条题目")