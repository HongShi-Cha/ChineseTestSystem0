"""登录尝试记录表 t_login_attempt：登录失败锁定 + 登录审计（第 10 步引入）。

每次登录（无论成功失败）写一行：
  * 按 username 统计窗口内的失败次数  -> 账号锁定（防针对某个账号的撞库）
  * 按 client_ip 统计窗口内的失败次数 -> IP 锁定（防拿一堆账号轮着试）

登录成功后会把该账号的历史失败记录清掉，避免"输错几次后改对了却被锁住"。
表名用 t_ 前缀，和其余四张表保持一致；由 init_db() 的 create_all 自动建表。
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LoginAttempt(Base):
    __tablename__ = "t_login_attempt"
    __table_args__ = (
        Index("ix_login_attempt_user_time", "username", "created_at"),
        Index("ix_login_attempt_ip_time", "client_ip", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False)
    client_ip: Mapped[Optional[str]] = mapped_column(String(45))
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.now)

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<LoginAttempt {self.username}@{self.client_ip} ok={self.success}>"