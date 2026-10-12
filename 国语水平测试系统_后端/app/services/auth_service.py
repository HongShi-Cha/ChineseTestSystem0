"""登录 / 注册业务逻辑。

Controller 只负责接请求、回结果，真正的判断都在这里。
"""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import ROLE_STUDENT
from app.core.errors import BizException
from app.core.security import hash_password, random_salt, verify_password
from app.models.user import User
from app.schemas.auth import RegisterIn
from app.services.login_guard import LoginGuard

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def login(self, username: str, password: str, client_ip: str | None = None) -> dict:
        """校验账号密码，返回可存入会话的精简用户信息。

        第 10 步加固：先过登录失败锁定（同一账号 / 同一 IP 在窗口内失败太多次就拒绝），
        再看密码；失败记一笔，成功则清空该账号的历史失败，避免改对密码还被锁着。
        """
        guard = LoginGuard(self.db)
        guard.ensure_allowed(username, client_ip)

        # 用同样的方式（盐 + 明文）重新算一次，跟库里的密文比较
        user = self.db.scalar(select(User).where(User.username == username))
        # 账号不存在与密码错误返回同一句话：不给撞库的人"这个账号存在"的线索
        if user is None or not verify_password(password, user.salt or "", user.password):
            guard.record_failure(username, client_ip)
            raise BizException("账号或密码错误")

        guard.record_success(username, client_ip)
        return user.to_login_user()

    def register(self, data: RegisterIn) -> int:
        """注册（只开放给学生）。"""
        exists = self.db.scalar(select(User).where(User.username == data.username))
        if exists is not None:
            raise BizException("该学号已被注册，请直接登录")

        salt = random_salt()
        user = User(
            username=data.username,
            salt=salt,
            password=hash_password(data.password, salt),
            name=data.name,
            student_no=data.student_no,
            class_name=data.class_name,
            role=ROLE_STUDENT,   # 注册入口只给学生，管理员账号由管理端创建
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        logger.info("新学生注册：%s（%s）", user.name, user.username)
        return user.id

    def get_profile(self, username: str) -> dict | None:
        user = self.db.scalar(select(User).where(User.username == username))
        return user.to_dict() if user else None