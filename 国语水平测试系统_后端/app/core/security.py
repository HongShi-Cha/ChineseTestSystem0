"""密码加盐 SHA-256 + 签名会话 Cookie。

密码算法与 Java 版 PasswordUtil 完全一致：
    hash = hex( SHA256( salt + 明文密码 ) )
这样原来 Java 版数据库里的账号可以直接登录，不用重置密码。
"""
import hashlib
import hmac
import secrets
from typing import Any, Optional

from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.core.config import settings

#: 会话 Cookie 名
SESSION_COOKIE_NAME = "guoyu_session"
#: 会话里存放登录用户的键（与 Java 版 AuthController.SESSION_KEY 对齐）
SESSION_KEY = "loginUser"


def random_salt(length: int = 8) -> str:
    """生成随机盐（默认 8 位）。"""
    return secrets.token_hex(16)[:length]


def hash_password(raw_password: str, salt: str) -> str:
    """hex(SHA256(salt + raw_password))。"""
    digest = hashlib.sha256((salt + raw_password).encode("utf-8")).digest()
    return digest.hex()


def verify_password(raw_password: str, salt: str, expected: str) -> bool:
    """用同样方式算一次，跟库存密文做恒定时间比较。"""
    return hmac.compare_digest(hash_password(raw_password, salt), expected or "")


_serializer = URLSafeTimedSerializer(settings.session_secret_key, salt="guoyu-session")


def dump_session(login_user: dict) -> str:
    """把登录用户序列化成签名串，存进 Cookie。"""
    return _serializer.dumps(login_user)


def load_session(token: Optional[str]) -> Optional[dict]:
    """校验并还原登录用户；过期或签名不对都返回 None。"""
    if not token:
        return None
    try:
        data: Any = _serializer.loads(token, max_age=settings.session_max_age)
    except BadSignature:
        return None
    except Exception:  # noqa: BLE001 - 会话损坏一律当作未登录
        return None
    return data if isinstance(data, dict) else None