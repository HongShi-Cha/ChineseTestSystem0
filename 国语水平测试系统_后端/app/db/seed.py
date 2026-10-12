"""种子 / 演示数据：首次启动时写入演示账号、示例题库与演示成绩。

规则：
  * 演示账号：按 username 逐个补齐，已存在的不动（不会覆盖你改过的密码）；
  * 示例题库：只有题库为空时才写入；
  * 演示成绩：只有 SEED_DEMO_DATA=true 且考试记录表为空时才写入。

已经导入过真实数据（比如从 Java 版 pthcs 库迁移过来）时不会重复写入。
"""
import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import (
    ROLE_ADMIN,
    ROLE_STUDENT,
    SECTION_TITLES,
    STATUS_FINISHED,
    TYPE_COUNTS_FALLBACK,
    TYPE_NAMES,
    TYPE_TOTALS,
)
from app.core.levels import level_of
from app.core.security import hash_password, random_salt
from app.models.exam_record import ExamRecord
from app.models.exam_section_score import ExamSectionScore
from app.models.question import Question
from app.models.user import User

logger = logging.getLogger(__name__)

#: 演示账号：(账号, 密码, 姓名, 角色, 学号, 班级)
DEMO_USERS = [
    ("admin", "admin123", "系统管理员", ROLE_ADMIN, "", ""),
    ("2024001", "123456", "张三", ROLE_STUDENT, "2024001", "计算机241"),
    ("2024002", "123456", "李四", ROLE_STUDENT, "2024002", "计算机241"),
    ("2024003", "123456", "王五", ROLE_STUDENT, "2024003", "计算机242"),
    ("2024004", "123456", "赵敏", ROLE_STUDENT, "2024004", "软件工程241"),
    ("2024005", "123456", "孙悦", ROLE_STUDENT, "2024005", "软件工程242"),
]

#: 示例题库：(题型, 题目, 拼音/参考答案, 难度)
DEMO_QUESTIONS = [
    (1, "爱", "ài", "简单"), (1, "白", "bái", "简单"), (1, "春", "chūn", "简单"),
    (1, "风", "fēng", "简单"), (1, "好", "hǎo", "简单"), (1, "热", "rè", "简单"),
    (1, "民", "mín", "中等"), (1, "山", "shān", "中等"), (1, "水", "shuǐ", "中等"),
    (1, "雪", "xuě", "困难"), (1, "音", "yīn", "简单"), (1, "云", "yún", "简单"),
    (2, "人民", "rén mín", "简单"), (2, "朋友", "péng you", "中等"), (2, "孩子", "hái zi", "中等"),
    (2, "花儿", "huā ér", "中等"), (2, "老师", "lǎo shī", "简单"), (2, "聪明", "cōng ming", "困难"),
    (3, "北京的秋天（短文：秋天是美丽的季节……）", "朗读提示：注意停连、语速适中、语调自然。", "中等"),
    (3, "读书的乐趣（短文：读书使人充实……）", "朗读提示：注意重音、语气连贯。", "困难"),
    (4, "我喜欢的季节", "参考提纲：季节特点、喜欢的原因、个人体验。", "中等"),
    (4, "谈谈个人修养", "参考提纲：什么是修养、身边的例子、如何提升。", "中等"),
    (4, "我尊敬的人", "参考提纲：人物介绍、印象深刻的事、对我的影响。", "困难"),
    (4, "我的家乡", "参考提纲：家乡的位置、风土人情、难忘的记忆。", "中等"),
]

#: 演示成绩：学号 -> [(距今天数, [题1分, 题2分, 题3分, 题4分]), ...]
DEMO_RECORDS = {
    "2024001": [
        (0, [8.9, 18.4, 28.0, 37.5]),
        (6, [8.4, 17.9, 27.3, 36.1]),
        (13, [8.2, 17.4, 26.8, 34.9]),
        (28, [7.8, 16.6, 25.5, 33.0]),
        (45, [8.0, 16.0, 24.6, 32.2]),
        (70, [7.2, 15.3, 23.8, 30.9]),
    ],
    "2024002": [
        (2, [8.8, 18.1, 27.5, 35.8]),
        (21, [8.1, 17.0, 26.4, 33.6]),
        (55, [7.6, 15.5, 24.2, 30.8]),
    ],
    "2024003": [
        (4, [8.6, 17.2, 26.0, 33.9]),
        (33, [7.5, 15.9, 24.8, 31.4]),
    ],
    "2024004": [
        (7, [9.1, 18.7, 28.6, 37.9]),
    ],
    "2024005": [
        (9, [8.3, 17.7, 26.9, 35.2]),
        (40, [7.9, 16.4, 25.3, 32.8]),
    ],
}


def seed_data(db: Session) -> dict:
    """首次启动补数据，返回本次写入的条数。"""
    created = {
        "users": _seed_users(db),
        "questions": _seed_questions(db),
        "records": 0,
    }
    if settings.seed_demo_data:
        created["records"] = _seed_records(db)

    if any(created.values()):
        db.commit()
        logger.info("种子/演示数据写入完成：%s", created)
    return created


# ---------------------------------------------------------------
def _seed_users(db: Session) -> int:
    """按 username 补齐演示账号。"""
    existing = {
        name for name in db.scalars(select(User.username)).all()
    }
    now = datetime.now()
    added = 0
    for username, raw_password, name, role, student_no, class_name in DEMO_USERS:
        if username in existing:
            continue
        salt = random_salt()
        db.add(
            User(
                username=username,
                salt=salt,
                password=hash_password(raw_password, salt),
                name=name,
                role=role,
                student_no=student_no,
                class_name=class_name,
                created_at=now,
            )
        )
        added += 1
    if added:
        db.flush()   # 让后面的演示成绩能查到新建的学生
    return added


def _seed_questions(db: Session) -> int:
    """题库为空时才写入示例题目。"""
    if (db.scalar(select(func.count()).select_from(Question)) or 0) > 0:
        return 0
    now = datetime.now()
    for type_no, content, answer, difficulty in DEMO_QUESTIONS:
        db.add(
            Question(
                type=type_no,
                content=content,
                answer=answer,
                difficulty=difficulty,
                updated_at=now,
            )
        )
    return len(DEMO_QUESTIONS)


def _seed_records(db: Session) -> int:
    """给"还没有任何成绩"的演示学生补一批演示成绩，让统计图表有内容可看。

    按学生逐个判断：已经有成绩的学生一律不动，
    避免把你自己考出来的真实成绩和演示数据混在一起。
    """
    papers = _fallback_paper()
    added = 0
    for student_no, rows in DEMO_RECORDS.items():
        student = db.scalar(select(User).where(User.student_no == student_no))
        if student is None:
            continue
        has_records = db.scalar(
            select(func.count())
            .select_from(ExamRecord)
            .where(
                ExamRecord.student_id == student.id,
                ExamRecord.status == STATUS_FINISHED,
            )
        ) or 0
        if has_records:
            continue
        for days_ago, section_scores in rows:
            finished = datetime.now() - timedelta(days=days_ago, minutes=8 + days_ago)
            started = finished - timedelta(minutes=13)
            total = round(sum(section_scores), 1)

            record = ExamRecord(
                student_id=student.id,
                status=STATUS_FINISHED,
                started_at=started,
                finished_at=finished,
                total_score=total,
                level=level_of(total),
            )
            record.paper = papers
            db.add(record)
            db.flush()   # 拿到 record.id

            for type_no, score in zip((1, 2, 3, 4), section_scores):
                row = ExamSectionScore(
                    record_id=record.id,
                    type=type_no,
                    score=score,
                    total=TYPE_TOTALS[type_no],
                )
                row.detail = _detail_for(type_no, score, days_ago)
                db.add(row)
            added += 1
    return added


def _fallback_paper() -> dict:
    """演示成绩用的试卷结构（题目内容取兜底题库，保证报告页有内容）。"""
    sections = []
    for type_no in (1, 2, 3, 4):
        sections.append(
            {
                "type": type_no,
                "title": SECTION_TITLES[type_no],
                "name": TYPE_NAMES[type_no],
                "items": list(TYPE_COUNTS_FALLBACK.get(type_no, [])),
            }
        )
    return {"sections": sections}


def _detail_for(type_no: int, score: float, seed: int) -> dict:
    """按得分率生成稳定的声韵调百分比。"""
    total = TYPE_TOTALS[type_no]
    pct = score / total * 100 if total else 0
    offset = (seed + type_no * 3) % 5
    return {
        "shengmu": int(round(min(99, pct + 2 + offset * 0.4))),
        "yunmu": int(round(min(99, pct - 1 + offset * 0.6))),
        "shengdiao": int(round(min(99, pct - 2 + offset * 0.5))),
    }


def seed_if_empty(db: Session) -> dict:
    """兼容旧调用名。"""
    return seed_data(db)