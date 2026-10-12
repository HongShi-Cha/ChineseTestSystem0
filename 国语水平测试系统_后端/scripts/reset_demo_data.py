r"""重建演示成绩数据（会先清空考试记录，请谨慎使用）。

用法：
    cd 国语水平测试系统_后端
    .venv\Scripts\python.exe scripts\reset_demo_data.py --yes

它会：
    1. 删除 t_exam_section_score / t_exam_record 的全部数据；
    2. 按 app/db/seed.py 里的 DEMO_RECORDS 重新生成演示成绩。
题库和学生账号不受影响。
"""
import sys
from pathlib import Path

# 允许直接以脚本方式运行：把后端根目录加进 sys.path
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import delete  # noqa: E402

from app.db.seed import _seed_records  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.exam_record import ExamRecord  # noqa: E402
from app.models.exam_section_score import ExamSectionScore  # noqa: E402


def main() -> int:
    if "--yes" not in sys.argv:
        print("该脚本会清空全部考试记录，确认请加 --yes 参数：")
        print("    python scripts\\reset_demo_data.py --yes")
        return 1

    with SessionLocal() as db:
        deleted_sections = db.execute(delete(ExamSectionScore)).rowcount or 0
        deleted_records = db.execute(delete(ExamRecord)).rowcount or 0
        db.commit()
        print(f"已删除：成绩明细 {deleted_sections} 条，考试记录 {deleted_records} 条")

        added = _seed_records(db)
        db.commit()
        print(f"已生成演示成绩：{added} 场")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())