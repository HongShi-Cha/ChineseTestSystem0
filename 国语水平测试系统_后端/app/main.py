"""FastAPI 应用入口：注册路由、托管前端静态页、启动时建表 + 补种子数据。

启动方式：
    python run.py                 # 开发（热重载）
    uvicorn app.main:app --port 8080
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app.api import admin, auth, exam, health as health_api, student
from app.core.config import BACKEND_DIR, settings
from app.core.constants import ROLE_STUDENT
from app.core.errors import register_exception_handlers
from app.core.security import verify_password
from app.db.seed import seed_if_empty
from app.db.session import SessionLocal, init_db, ping
from app.models.user import User
from app.services.file_cleanup import cleanup_expired_uploads

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def warn_weak_passwords() -> None:
    """启动时检查默认弱密码（第 10 步）。

    默认口令在演示时很方便，公网部署时就是最大的漏洞。这里只告警不拦截，
    避免把本地演示也堵死；`.env` 里关掉 SEED_DEMO_DATA 并改掉密码即可。
    """
    try:
        with SessionLocal() as db:
            weak: list[str] = []
            admin = db.scalar(select(User).where(User.username == "admin"))
            if admin is not None and verify_password("admin123", admin.salt or "", admin.password):
                weak.append("管理员账号 admin 仍是默认密码 admin123")

            students = db.scalars(select(User).where(User.role == ROLE_STUDENT)).all()
            weak_students = sum(
                1 for u in students if verify_password("123456", u.salt or "", u.password)
            )
            if weak_students:
                weak.append(f"{weak_students} 个学生账号仍是默认密码 123456")

            for item in weak:
                logger.warning("⚠️ 安全检查：%s —— 公网部署前请务必修改", item)
    except Exception as exc:  # noqa: BLE001 - 告警失败不该影响启动
        logger.debug("弱密码检查跳过：%s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时：建表 + 补种子数据 + 准备上传目录。"""
    logger.info("正在启动 %s ...", settings.app_name)
    try:
        init_db()
        with SessionLocal() as db:
            seed_if_empty(db)
        settings.upload_path.mkdir(parents=True, exist_ok=True)
        logger.info("数据库连接：%s", "正常" if ping() else "异常")
        # 第 9 步：顺手清掉超过保留期的录音（UPLOAD_RETENTION_DAYS=0 表示永久保留，跳过）
        cleanup = cleanup_expired_uploads()
        if cleanup["deleted"]:
            logger.info("已清理过期录音 %s 个", cleanup["deleted"])
        # 第 10 步：默认弱密码告警，公网部署最容易出事的地方
        warn_weak_passwords()
    except Exception as exc:  # noqa: BLE001 - 启动期报错只提示，不阻止服务拉起
        logger.error("初始化失败（请检查 MySQL 是否启动、.env 配置是否正确）：%s", exc)
        logger.error("连接串：%s", settings.database_url.replace(settings.db_password, "****"))

    logger.info(
        "服务地址：http://127.0.0.1:%s/  接口文档：%s",
        settings.app_port,
        "/api/docs" if settings.enable_docs else "已关闭（ENABLE_DOCS=false）",
    )
    yield
    logger.info("%s 已停止", settings.app_name)


app = FastAPI(
    title=f"{settings.app_name} - 后端接口",
    description="Python(FastAPI) + MySQL 实现，对接前端静态页面",
    version="1.0.0",
    lifespan=lifespan,
    # 第 10 步：接口文档开关。公网部署时把 ENABLE_DOCS 改成 false，
    # 否则任何人都能拿到完整的接口结构（含参数与响应示例），等于给攻击者送地图。
    docs_url="/api/docs" if settings.enable_docs else None,
    redoc_url="/api/redoc" if settings.enable_docs else None,
    openapi_url="/api/openapi.json" if settings.enable_docs else None,
)

# 前后端同源部署时用不到 CORS；这里保留，方便单独用 5500 端口预览前端。
# 白名单来自 CORS_ORIGINS（逗号分隔），留空则只放行本机调试地址。
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

# ---------- 接口路由 ----------
app.include_router(health_api.router)
app.include_router(auth.router)
app.include_router(student.router)
app.include_router(exam.router)
app.include_router(admin.router)
app.include_router(admin.question_router)

# ---------- 静态资源保护 ----------
# 前端目录与后端目录是父子关系，必须挡住后端源码/配置/上传文件，避免被直接下载
BLOCKED_PREFIXES = (
    "/" + BACKEND_DIR.name,   # 后端目录
    "/.git",
    "/.env",
    "/data",
)


#: 这些后缀的静态资源每次都要回源校验（避免改了前端学生还在跑旧脚本）
NO_CACHE_SUFFIXES = (".js", ".css", ".html")

#: 安全响应头（第 10 步）：nosniff 防 MIME 嗅探、X-Frame-Options 防 iframe 嵌套挂马、
#: Referrer-Policy 防止把完整 URL 带到外部站点
SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "X-Permitted-Cross-Domain-Policies": "none",
}

#: HSTS 只在 HTTPS 部署（SESSION_COOKIE_SECURE=true）时才加，
#: 否则本地 http 调试会被浏览器强制跳 https。
if settings.session_cookie_secure:
    SECURITY_HEADERS["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"


@app.middleware("http")
async def guard_static_files(request, call_next):
    path = request.url.path
    if path.startswith(BLOCKED_PREFIXES) or ".." in path:
        return JSONResponse(
            status_code=404,
            content={"code": 404, "message": "资源不存在", "data": None},
        )
    response = await call_next(request)
    if settings.security_headers:
        for key, value in SECURITY_HEADERS.items():
            response.headers[key] = value
    # StaticFiles 只带 ETag / Last-Modified，浏览器会"启发式缓存"，
    # 前端改了但页面还在跑旧脚本就是这么来的；这里强制每次校验。
    if path == "/" or request.url.path.endswith(NO_CACHE_SUFFIXES):
        response.headers["Cache-Control"] = "no-cache"
    return response


# ---------- 前端静态页 ----------
frontend_dir = settings.frontend_path
if frontend_dir.is_dir() and (frontend_dir / "index.html").exists():
    # 挂载在最后：/api/** 已先注册，剩下的路径才交给静态文件
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
    logger.info("前端静态目录：%s", frontend_dir)
else:
    logger.warning("未找到前端目录（%s），仅提供 /api 接口", frontend_dir)