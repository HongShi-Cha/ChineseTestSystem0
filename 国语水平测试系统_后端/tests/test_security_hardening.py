"""第 10 步安全加固的单元测试。

覆盖：滑动窗口限流、并发闸门、CORS 白名单、安全响应头开关、默认配置。
都不连数据库、不联网。
"""
import pytest

from app.core import limits
from app.core.config import settings
from app.core.constants import CODE_TOO_MANY_REQUESTS
from app.core.errors import BizException
from app.core.limits import ConcurrencyGate, SlidingWindowLimiter


# ============================================================
# 滑动窗口限流（注册刷号防护）
# ============================================================
def test_limiter_allows_up_to_limit_then_rejects():
    limiter = SlidingWindowLimiter(limit=3, window_seconds=60)
    assert [limiter.allow("1.2.3.4") for _ in range(4)] == [True, True, True, False]


def test_limiter_counts_each_key_separately():
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60)
    assert limiter.allow("a") is True
    assert limiter.allow("a") is False
    assert limiter.allow("b") is True     # 换个 IP 不受影响


def test_limiter_window_slides(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(limits.time, "monotonic", lambda: clock["now"])
    limiter = SlidingWindowLimiter(limit=2, window_seconds=60)

    assert limiter.allow("k") is True
    assert limiter.allow("k") is True
    assert limiter.allow("k") is False

    clock["now"] += 61                     # 窗口滑过去，计数清空
    assert limiter.allow("k") is True


def test_limiter_reset():
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60)
    assert limiter.allow("k") is True
    assert limiter.allow("k") is False
    limiter.reset("k")
    assert limiter.allow("k") is True


def test_limiter_limit_is_at_least_one():
    """配成 0 或负数时不至于把接口全锁死。"""
    assert SlidingWindowLimiter(limit=0, window_seconds=60).limit == 1


# ============================================================
# 并发闸门（讯飞评测并发保护）
# ============================================================
def test_gate_rejects_when_full():
    gate = ConcurrencyGate(limit=1, timeout_seconds=0)
    with gate.slot():
        with pytest.raises(BizException) as exc:
            with gate.slot():
                pass
    assert exc.value.code == CODE_TOO_MANY_REQUESTS


def test_gate_releases_slot_after_use():
    gate = ConcurrencyGate(limit=1, timeout_seconds=0)
    with gate.slot():
        pass
    with gate.slot():      # 前一个已经释放，这次不该报错
        pass


def test_gate_releases_slot_on_exception():
    gate = ConcurrencyGate(limit=1, timeout_seconds=0)
    with pytest.raises(ValueError):
        with gate.slot():
            raise ValueError("评测内部炸了")
    with gate.slot():      # 名额必须还回来，否则一次异常就把并发永久占掉
        pass


def test_gate_limit_is_at_least_one():
    assert ConcurrencyGate(limit=0, timeout_seconds=0).limit == 1


# ============================================================
# CORS 白名单
# ============================================================
def test_cors_default_is_localhost_only(monkeypatch):
    monkeypatch.setattr(settings, "cors_origins", "")
    origins = settings.cors_origin_list
    assert f"http://127.0.0.1:{settings.app_port}" in origins
    assert all("127.0.0.1" in o or "localhost" in o for o in origins)


def test_cors_from_env(monkeypatch):
    monkeypatch.setattr(settings, "cors_origins", "https://guoyu.example.com, https://www.example.com")
    assert settings.cors_origin_list == ["https://guoyu.example.com", "https://www.example.com"]


# ============================================================
# 安全响应头
# ============================================================
def test_security_headers_defined():
    from app.main import SECURITY_HEADERS

    assert SECURITY_HEADERS["X-Content-Type-Options"] == "nosniff"
    assert SECURITY_HEADERS["X-Frame-Options"] == "DENY"
    assert SECURITY_HEADERS["Referrer-Policy"] == "same-origin"


def test_hsts_follows_secure_cookie_flag():
    """HSTS 只在 HTTPS 部署时下发，否则本地 http 调试会被浏览器强制跳 https。"""
    from app.main import SECURITY_HEADERS

    assert ("Strict-Transport-Security" in SECURITY_HEADERS) is settings.session_cookie_secure


# ============================================================
# 默认配置的安全性
# ============================================================
def test_login_thresholds_are_sane():
    """账号级阈值要小（防撞库），IP 级阈值要大（校园网 NAT 共用一个出口）。"""
    assert 1 <= settings.login_max_failures <= 10
    assert settings.login_max_ip_failures >= 50
    assert settings.login_window_seconds >= 60


def test_upload_limits_are_sane():
    assert settings.max_upload_bytes >= 1024 * 1024
    assert settings.max_upload_mb == settings.max_upload_bytes // (1024 * 1024)


def test_scoring_concurrency_below_provider_cap():
    """讯飞官方并发约 50 路，默认配置必须留出余量。"""
    assert settings.ise_max_concurrency < 50
    assert settings.ise_max_wait_seconds >= 0