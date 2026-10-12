"""生产环境账号维护脚本（第 10 步）。

为什么需要它：演示账号（admin/admin123、2024001~2024005/123456）是随首次启动
自动写入的，公网部署前必须改密码 / 清掉演示号。系统本身没有"改密码"页面，
所以用这个脚本在服务器上改。

用法：
    # 改密码（账号必须已存在）
    .venv/bin/python scripts/set_password.py --username admin --password '新的强密码'

    # 账号不存在时顺手创建一个管理员
    .venv/bin/python scripts/set_password.py --username admin2 --password '强密码' --create-admin

    # 先看看会删掉什么（只统计，不删）
    .venv/bin/python scripts/set_password.py --drop-demo-students

    # 确认后真删：5 个演示学生 + 他们的考试记录 + 成绩明细 + 录音
    .venv/bin/python scripts/set_password.py --drop-demo-students --yes
"""
import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import delete, select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.constants import ROLE_ADMIN, ROLE_STUDENT  # noqa: E402
from app.core.security import hash_password, random_salt  # noqa: E402
from app.db.seed import DEMO_USERS  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.exam_record import ExamRecord  # noqa: E402
from app.models.exam_section_score import ExamSectionScore  # noqa: E402
from app.models.user import User  # noqa: E402

#: 一定要提醒的弱口令
WEAK_PASSWORDS = {"admin123", "123456", "password", "12345678", "88888888", "11111111"}

#: 演示学生账号（自动写入的那 5 个）
DEMO_STUDENT_NOS = [u[0] for u in DEMO_USERS if u[3] == ROLE_STUDENT]


def reset_password(username: str, password: str, create_admin: bool) -> int:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))

        if user is None:
            if not create_admin:
                print(f"[FAIL] 账号 {username} 不存在（要新建管理员请加 --create-admin）")
                return 1
            salt = random_salt()
            user = User(
                username=username,
                salt=salt,
                password=hash_password(password, salt),
                name=username,
                role=ROLE_ADMIN,
            )
            db.add(user)
            db.commit()
            print(f"[OK]   已创建管理员 {username}（id={user.id}）")
            return 0

        if len(password) < 8:
            print("[WARN] 新密码少于 8 位，公网部署很不安全")
        if password in WEAK_PASSWORDS:
            print("[WARN] 这是常见弱口令，强烈建议换一个")

        salt = random_salt()
        user.salt = salt
        user.password = hash_password(password, salt)
        db.commit()
        print(f"[OK]   已重置 {username}（角色 {user.role}）的密码")
        return 0


def drop_demo_students(confirm: bool) -> int:
    with SessionLocal() as db:
        users = list(
            db.scalars(select(User).where(User.username.in_(DEMO_STUDENT_NOS))).all()
        )
        if not users:
            print("[OK]   没有找到演示学生账号，无需清理")
            return 0

        user_ids = [u.id for u in users]
        records = list(
            db.scalars(select(ExamRecord).where(ExamRecord.student_id.in_(user_ids))).all()
        )
        record_ids = [r.id for r in records]
        scores = 0
        if record_ids:
            scores = len(
                db.scalars(
                    select(ExamSectionScore).where(
                        ExamSectionScore.record_id.in_(record_ids)
                    )
                ).all()
            )

        print(f"        待删除学生：{[u.username for u in users]}")
        print(f"        待删除考试记录：{len(record_ids)} 条，成绩明细：{scores} 条")

        if not confirm:
            print("[DRY]  这是预演，什么都没删。确认无误后加 --yes 再跑一次。")
            return 0

        if record_ids:
            db.execute(
                delete(ExamSectionScore).where(
                    ExamSectionScore.record_id.in_(record_ids)
                )
            )
            db.execute(delete(ExamRecord).where(ExamRecord.id.in_(record_ids)))
        db.execute(delete(User).where(User.id.in_(user_ids)))
        db.commit()

        # 顺手删掉这些记录的录音文件
        removed_files = 0
        upload_dir = settings.upload_path
        if upload_dir.is_dir():
            for record_id in record_ids:
                for path in upload_dir.glob(f"rec_{record_id}_*"):
                    try:
                        path.unlink()
                        removed_files += 1
                    except OSError as exc:  # noqa: BLE001
                        print(f"[WARN] 删除录音失败 {path}：{exc}")
        print(f"[OK]   已删除演示学生 {len(user_ids)} 个、记录 {len(record_ids)} 条、录音 {removed_files} 个")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="国语水平测试系统 - 账号维护")
    parser.add_argument("--username", help="要改密码的账号")
    parser.add_argument("--password", help="新密码")
    parser.add_argument("--create-admin", action="store_true", help="账号不存在时创建为管理员")
    parser.add_argument("--drop-demo-students", action="store_true", help="删除 5 个演示学生及其全部数据")
    parser.add_argument("--yes", action="store_true", help="确认执行危险操作")
    args = parser.parse_args()

    if args.drop_demo_students:
        return drop_demo_students(args.yes)
    if args.username and args.password:
        return reset_password(args.username, args.password, args.create_admin)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())