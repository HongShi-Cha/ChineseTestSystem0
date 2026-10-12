"""第 10 步安全加固的端到端验证（需要后端已在运行，连真实 MySQL）。

覆盖：
    1. 登录失败锁定：窗口内失败到阈值后，连正确密码也会被拒（返回 429）
    2. 登录成功清空失败计数：不会因为"之前输错过几次"就被锁
    3. 注册限流：同一 IP 超过 REGISTER_MAX_PER_HOUR 次后返回 429
    4. 安全响应头：nosniff / 防 iframe 嵌套 / Referrer-Policy 都在
    5. 接口文档开关：/api/docs 的可访问性与 ENABLE_DOCS 一致
    6. 真实客户端 IP：带 X-Forwarded-For 时后端能取到转发后的地址

跑完自动清理：删掉探针账号、注册的测试号，以及本次产生的登录记录。

用法：
    .venv\\Scripts\\python.exe scripts\\verify_hardening.py
"""
from __future__ import annotations

import json
import random
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import delete, select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.constants import ROLE_STUDENT  # noqa: E402
from app.core.security import hash_password, random_salt  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.login_attempt import LoginAttempt  # noqa: E402
from app.models.user import User  # noqa: E402

BASE = "http://127.0.0.1:8080"
PROBE_USER = "lock_probe"
PROBE_PASSWORD = "Probe-Pass-123"
#: 每个用例一个独立的模拟客户端 IP，互不干扰，也不污染真实 IP 的计数。
#: 第三段每次运行随机：注册限流是**进程内**计数，固定 IP 的话第二次跑就会立刻被限流。
RUN_TAG = random.randint(1, 254)
PROBE_IP_PREFIX = "10.99."
IP_A = f"{PROBE_IP_PREFIX}{RUN_TAG}.1"
IP_B = f"{PROBE_IP_PREFIX}{RUN_TAG}.2"
IP_C = f"{PROBE_IP_PREFIX}{RUN_TAG}.3"

PASSED: list[str] = []
FAILED: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    print(f"{'[PASS]' if ok else '[FAIL]'} {label}{('  -> ' + detail) if detail else ''}", flush=True)
    (PASSED if ok else FAILED).append(label)


def post(path: str, payload: dict, client_ip: str) -> dict:
    request = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8", "X-Forwarded-For": client_ip},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # pragma: no cover - 便于排错
        return {"code": exc.code, "message": str(exc), "data": None}


def login(username: str, password: str, client_ip: str) -> dict:
    return post("/api/auth/login", {"username": username, "password": password}, client_ip)


def register(username: str, client_ip: str) -> dict:
    return post(
        "/api/auth/register",
        {"name": "限流测试", "student_no": username, "class_name": "测试班", "password": "abc12345"},
        client_ip,
    )


def ensure_probe_user() -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == PROBE_USER))
        if user is None:
            salt = random_salt()
            db.add(
                User(
                    username=PROBE_USER,
                    salt=salt,
                    password=hash_password(PROBE_PASSWORD, salt),
                    name="锁定探针",
                    role=ROLE_STUDENT,
                    student_no=PROBE_USER,
                    class_name="测试班",
                )
            )
        # 清掉历史失败记录，保证每次跑都从干净状态开始
        db.execute(
            delete(LoginAttempt).where(
                LoginAttempt.username == PROBE_USER,
                LoginAttempt.success.is_(False),
            )
        )
        db.commit()


def cleanup(registered: list[str]) -> None:
    with SessionLocal() as db:
        names = [PROBE_USER, *registered]
        db.execute(delete(LoginAttempt).where(LoginAttempt.username.in_(names)))
        # 顺手清掉历史运行残留的探针 IP 记录
        db.execute(delete(LoginAttempt).where(LoginAttempt.client_ip.like(PROBE_IP_PREFIX + "%")))
        db.execute(delete(User).where(User.username.in_(names)))
        db.commit()


def main() -> int:
    print("=" * 62)
    print("第 10 步 安全加固 - 端到端验证")
    print("=" * 62)

    threshold = max(1, settings.login_max_failures)
    registered: list[str] = []
    ensure_probe_user()

    try:
        # ---------- 1. 登录成功会清空失败计数 ----------
        for _ in range(threshold - 1):
            login(PROBE_USER, "错误密码", IP_A)
        ok = login(PROBE_USER, PROBE_PASSWORD, IP_A)     # 成功 -> 历史失败清零
        again = None
        for _ in range(threshold - 1):
            again = login(PROBE_USER, "错误密码", IP_A)   # 再攒 threshold-1 次，仍不该锁
        check(
            ok.get("code") == 0 and again.get("code") == 400,
            "登录成功后失败计数被清空（前一串失败不会累积到锁定）",
            f"success={ok.get('code')} next={again.get('code')}",
        )
        login(PROBE_USER, PROBE_PASSWORD, IP_A)          # 再清一次，给下面的用例一个干净起点

        # ---------- 2. 达到阈值后锁定 ----------
        code = None
        for _ in range(threshold):
            code = login(PROBE_USER, "错误密码", IP_B).get("code")
        locked = login(PROBE_USER, PROBE_PASSWORD, IP_B)
        check(code == 400, f"连续 {threshold} 次密码错误都被正常拒绝", f"code={code}")
        check(
            locked.get("code") == 429,
            "锁定后即使密码正确也会被拒绝（业务码 429）",
            f"code={locked.get('code')} message={locked.get('message')}",
        )

        # ---------- 3. 注册限流 ----------
        limit = max(1, settings.register_max_per_hour)
        codes = []
        for _ in range(limit + 1):
            username = "9" + uuid.uuid4().hex[:9]
            result = register(username, IP_C)
            codes.append(result.get("code"))
            if result.get("code") == 0:
                registered.append(username)
        check(
            codes[:limit] == [0] * limit and codes[limit] == 429,
            f"注册接口同一 IP 超过 {limit} 次后返回 429",
            f"codes={codes}",
        )

        # ---------- 4. 安全响应头 ----------
        with urllib.request.urlopen(BASE + "/login.html", timeout=20) as response:
            headers = {k.lower(): v for k, v in response.headers.items()}
        check(
            headers.get("x-content-type-options") == "nosniff"
            and headers.get("x-frame-options") == "DENY"
            and headers.get("referrer-policy") == "same-origin",
            "静态页带上了安全响应头",
            f"nosniff={headers.get('x-content-type-options')} frame={headers.get('x-frame-options')}",
        )

        # ---------- 5. 接口文档开关 ----------
        try:
            with urllib.request.urlopen(BASE + "/api/docs", timeout=20) as response:
                docs_status = response.status
        except urllib.error.HTTPError as exc:
            docs_status = exc.code
        docs_open = docs_status == 200
        check(
            docs_open == settings.enable_docs,
            "接口文档开关与 ENABLE_DOCS 一致",
            f"ENABLE_DOCS={settings.enable_docs} /api/docs={docs_status}",
        )
        if settings.enable_docs:
            print("       提示：公网部署时请把 ENABLE_DOCS 改成 false")

        # ---------- 6. 真实客户端 IP 落到审计表 ----------
        with SessionLocal() as db:
            row = db.scalar(
                select(LoginAttempt)
                .where(LoginAttempt.username == PROBE_USER)
                .order_by(LoginAttempt.id.desc())
            )
            seen_ip = row.client_ip if row else None
        check(
            seen_ip == IP_B,
            "后端从 X-Forwarded-For 取到了真实客户端 IP（不是 nginx 自己的地址）",
            f"记录到 {seen_ip}",
        )

        print("-" * 62)
        print(f"通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
        for label in FAILED:
            print(f"  失败项：{label}")
        return 1 if FAILED else 0
    finally:
        cleanup(registered)


if __name__ == "__main__":
    sys.exit(main())