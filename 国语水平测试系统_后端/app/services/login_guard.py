"""登录失败锁定（第 10 步引入）。

规则（都在 .env 里可调）：

* 同一个账号在 ``LOGIN_WINDOW_SECONDS`` 内失败 ``LOGIN_MAX_FAILURES`` 次 -> 锁；
* 同一个 IP 在同一个窗口内失败 ``LOGIN_MAX_IP_FAILURES`` 次 -> 锁；
* 锁定时间就是窗口本身：窗口内不再接受该账号/IP 的登录尝试。

为什么用数据库而不是内存计数：多 worker 部署时内存计数是各算各的，
账号锁定必须全局生效，否则多开几个 worker 就等于把阈值放宽了几倍。
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import CODE_TOO_MANY_REQUESTS
from app.core.errors import BizException
from app.models.login_attempt import LoginAttempt

logger = logging.getLogger(__name__)

#: 登录审计记录保留天数（超过就删，表不会无限增长）
AUDIT_RETENTION_DAYS = 7


class LoginGuard:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ---------- 对外接口 ----------
    def ensure_allowed(self, username: str, client_ip: str | None) -> None:
        """在真正校验密码之前调用：已经被锁定就直接拒绝。"""
        limit = settings.login_max_failures
        if limit > 0 and self._fail_count(LoginAttempt.username, username) >= limit:
            logger.warning("账号 %s 登录失败次数达到上限，已锁定", username)
            raise BizException(self._locked_message(), CODE_TOO_MANY_REQUESTS)

        ip_limit = settings.login_max_ip_failures
        if client_ip and ip_limit > 0 and self._fail_count(LoginAttempt.client_ip, client_ip) >= ip_limit:
            logger.warning("IP %s 登录失败次数达到上限，已锁定", client_ip)
            raise BizException(self._locked_message(), CODE_TOO_MANY_REQUESTS)

    def record_failure(self, username: str, client_ip: str | None) -> None:
        self._add(username, client_ip, success=False)
        self.db.commit()

    def record_success(self, username: str, client_ip: str | None) -> None:
        self._add(username, client_ip, success=True)
        # 登录成功就把该账号的历史失败记录清掉：输错几次之后改对了不该还被锁着
        self.db.execute(
            delete(LoginAttempt).where(
                LoginAttempt.username == username, LoginAttempt.success.is_(False)
            )
        )
        self.db.commit()

    # ---------- 内部工具 ----------
    @property
    def window_start(self) -> datetime:
        return datetime.now() - timedelta(seconds=max(1, settings.login_window_seconds))

    def _fail_count(self, column, value: str) -> int:
        return self.db.scalar(
            select(func.count())
            .select_from(LoginAttempt)
            .where(
                column == value,
                LoginAttempt.success.is_(False),
                LoginAttempt.created_at >= self.window_start,
            )
        ) or 0

    def _add(self, username: str, client_ip: str | None, success: bool) -> None:
        self.db.add(
            LoginAttempt(
                username=(username or "")[:50],
                client_ip=(client_ip or "")[:45] or None,
                success=success,
                created_at=datetime.now(),
            )
        )
        # 顺手清掉过期审计记录，保持表体积可控
        self.db.execute(
            delete(LoginAttempt).where(
                LoginAttempt.created_at
                < datetime.now() - timedelta(days=AUDIT_RETENTION_DAYS)
            )
        )

    @staticmethod
    def _locked_message() -> str:
        minutes = max(1, settings.login_window_seconds // 60)
        return f"登录失败次数过多，请 {minutes} 分钟后再试，或联系管理员重置密码"