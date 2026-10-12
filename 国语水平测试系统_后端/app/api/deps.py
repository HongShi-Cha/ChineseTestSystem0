"""公共依赖：读取会话、角色拦截（相当于 Java 版的 SessionUtil + 拦截器）。"""
from typing import Optional

from fastapi import Cookie, Depends, Request

from app.core.constants import ROLE_ADMIN, ROLE_STUDENT
from app.core.errors import BizException
from app.core.security import SESSION_COOKIE_NAME, load_session


def current_user(
    guoyu_session: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME)
) -> Optional[dict]:
    """从签名 Cookie 还原登录用户，未登录返回 None。"""
    return load_session(guoyu_session)


def client_ip(request: Request) -> str:
    """取客户端 IP，供限流与登录锁定使用。

    公网部署时后端跑在 nginx 后面，必须用
        uvicorn --proxy-headers --forwarded-allow-ips=127.0.0.1
    启动，uvicorn 才会把 request.client 换成 X-Forwarded-For 里的真实 IP；
    否则这里拿到的是 nginx 自己的地址，所有用户会被算成同一个来源。
    """
    return (request.client.host if request.client else "") or ""


def require_login(user: Optional[dict] = Depends(current_user)) -> dict:
    if not user:
        raise BizException("未登录", 401)
    return user


def require_student(user: dict = Depends(require_login)) -> dict:
    if user.get("role") != ROLE_STUDENT:
        raise BizException("仅学生可访问", 403)
    return user


def require_admin(user: dict = Depends(require_login)) -> dict:
    if user.get("role") != ROLE_ADMIN:
        raise BizException("仅管理员可访问", 403)
    return user