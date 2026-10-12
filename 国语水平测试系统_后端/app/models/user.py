"""用户表 t_user：学生与管理员共用一张表，用 role 区分。

Mock data added, backend calls removed for Python demo.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import ROLE_ADMIN, ROLE_STUDENT
from app.db.base import Base


class User(Base):
    __tablename__ = "t_user"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    password: Mapped[str] = mapped_column(String(64), nullable=False)
    salt: Mapped[Optional[str]] = mapped_column(String(32))
    name: Mapped[Optional[str]] = mapped_column(String(50))
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=ROLE_STUDENT)
    student_no: Mapped[Optional[str]] = mapped_column(String(30))
    class_name: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.now)

    # ---------- 便捷属性 ----------
    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def is_student(self) -> bool:
        return self.role == ROLE_STUDENT

    def to_login_user(self) -> dict:
        """塞进会话 Cookie 的精简信息（不存密码、盐）。"""
        return {
            "id": self.id,
            "username": self.username,
            "name": self.name or self.username,
            "role": self.role,
        }

    def to_dict(self) -> dict:
        """返回给前端的完整档案（字段名下划线风格）。"""
        return {
            "id": self.id,
            "username": self.username,
            "name": self.name,
            "role": self.role,
            "student_no": self.student_no,
            "class_name": self.class_name,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<User {self.id} {self.username} {self.role}>"