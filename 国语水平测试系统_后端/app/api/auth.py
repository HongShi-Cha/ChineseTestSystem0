"""认证接口：登录 / 注册 / 退出 / 当前用户。

第 10 步加固：登录失败锁定（见 AuthService/LoginGuard）、注册按 IP 限流、
会话 Cookie 支持 Secure 开关（配合 nginx + HTTPS 使用）。
"""
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import client_ip, require_login
from app.core.config import settings
from app.core.constants import CODE_TOO_MANY_REQUESTS
from app.core.errors import BizException
from app.core.limits import register_limiter
from app.core.response import ok
from app.core.security import SESSION_COOKIE_NAME, dump_session
from app.db.session import get_db
from app.schemas.auth import LoginIn, RegisterIn
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _cookie_options() -> dict:
    """会话 Cookie 的公共属性。

    SESSION_COOKIE_SECURE=true 时只允许 HTTPS 回传 Cookie —— 公网部署必须打开，
    否则在公共 WiFi 下会话可能被直接劫持。
    """
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": settings.session_cookie_secure,
        "path": "/",
    }


def _write_session(response: Response, login_user: dict) -> None:
    """把登录用户写进签名 Cookie（HttpOnly，防脚本读取）。"""
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=dump_session(login_user),
        max_age=settings.session_max_age,
        **_cookie_options(),
    )


@router.post("/login")
def login(
    payload: LoginIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    login_user = AuthService(db).login(payload.username, payload.password, client_ip(request))
    _write_session(response, login_user)
    return ok(login_user)


@router.post("/register")
def register(payload: RegisterIn, request: Request, db: Session = Depends(get_db)) -> dict:
    """学生注册：按 IP 限流，防止有人批量刷号。"""
    if not register_limiter.allow(client_ip(request) or "unknown"):
        raise BizException("注册过于频繁，请稍后再试", CODE_TOO_MANY_REQUESTS)

    user_id = AuthService(db).register(payload)
    return ok({"user_id": user_id}, message="注册成功，请登录")


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(SESSION_COOKIE_NAME, **_cookie_options())
    return ok(message="已退出登录")


@router.get("/me")
def me(user: dict = Depends(require_login), db: Session = Depends(get_db)) -> dict:
    """当前登录用户（附带完整档案）。"""
    profile = AuthService(db).get_profile(user.get("username", ""))
    if profile is None:
        raise BizException("未登录", 401)
    return ok(profile)